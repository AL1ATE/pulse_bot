import os
import shutil
import subprocess
import psycopg2
from datetime import datetime, timezone
from db import get_db_connection

EASYRSA_PATH = "/root/openvpn-ca"
ISSUED_CERTS_PATH = "/root/openvpn-ca/pki/issued"
PRIVATE_KEYS_PATH = "/root/openvpn-ca/pki/private"
REVOKED_CERTS_PATH = "/root/openvpn-ca/pki/revoked_issued"
REVOKED_KEYS_PATH = "/root/openvpn-ca/pki/revoked_private"
CRL_PATH = "/root/openvpn-ca/pki/crl.pem"
OPENVPN_CRL_DEST = "/etc/openvpn/crl.pem"

def revoke_certificate(username):
    """Отзывает сертификат пользователя, обновляет CRL и статус в БД, если он еще не отозван."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM vpn_users WHERE username = %s", (username,))
    user_status = cursor.fetchone()

    if user_status and user_status[0] == 'inactive':
        print(f"⚠️ Сертификат {username} уже отозван (статус: inactive). Пропускаем.")
        cursor.close()
        conn.close()
        return

    cert_path = os.path.join(ISSUED_CERTS_PATH, f"{username}.crt")
    key_path = os.path.join(PRIVATE_KEYS_PATH, f"{username}.key")
    revoked_cert_path = os.path.join(REVOKED_CERTS_PATH, f"{username}.crt")
    revoked_key_path = os.path.join(REVOKED_KEYS_PATH, f"{username}.key")

    try:
        # Копируем сертификаты в папку отозванных ДО отзыва
        if os.path.exists(cert_path):
            shutil.copy(cert_path, revoked_cert_path)
        if os.path.exists(key_path):
            shutil.copy(key_path, revoked_key_path)

        print(f"⛔ Отзываем сертификат {username}...")
        process = subprocess.Popen(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "revoke", username],
            cwd=EASYRSA_PATH,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        process.communicate(input=b"yes\n")

        print("🔄 Обновляем CRL...")
        subprocess.run(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "gen-crl"],
            cwd=EASYRSA_PATH,
            check=True
        )

        print(f"📂 Копируем новый CRL в {OPENVPN_CRL_DEST}...")
        subprocess.run(["cp", CRL_PATH, OPENVPN_CRL_DEST], check=True)

        print(f"✅ Сертификат {username} отозван и сохранён в {REVOKED_CERTS_PATH}")

        print("🔄 Перезапускаем OpenVPN...")
        subprocess.run(["systemctl", "restart", "openvpn"], check=True)
        print("✅ OpenVPN перезапущен")

        cursor.execute("UPDATE vpn_users SET status = %s WHERE username = %s", ("inactive", username))
        conn.commit()
        print(f"✅ Статус пользователя {username} обновлён на inactive")

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при отзыве сертификата {username}: {e}")
    finally:
        cursor.close()
        conn.close()

def check_expired_users():
    """Проверяет срок действия пользователей и отзывает просроченные сертификаты."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT username, expiration_date FROM vpn_users WHERE expiration_date IS NOT NULL")
    users = cursor.fetchall()

    for username, expiration_date in users:
        if expiration_date and expiration_date < datetime.now(timezone.utc):
            print(f"⛔ Подписка {username} истекла. Блокируем доступ...")
            revoke_certificate(username)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_expired_users()
