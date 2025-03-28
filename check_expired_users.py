import os
import subprocess
import psycopg2
from datetime import datetime, timezone
from db import get_db_connection  # Убедись, что у тебя есть этот импорт

EASYRSA_PATH = "/root/openvpn-ca"
ISSUED_CERTS_PATH = "/root/openvpn-ca/pki/issued"
PRIVATE_KEYS_PATH = "/root/openvpn-ca/pki/private"
REVOKED_CERTS_PATH = "/root/openvpn-ca/pki/revoked_issued"
REVOKED_KEYS_PATH = "/root/openvpn-ca/pki/revoked_private"
CRL_PATH = "/root/openvpn-ca/pki/crl.pem"
OPENVPN_CRL_DEST = "/etc/openvpn/crl.pem"


def revoke_certificate(username):
    """Отзывает сертификат пользователя, обновляет CRL и статус в БД."""
    try:
        print(f"⛔ Отзываем сертификат {username}...")
        subprocess.run(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "revoke", username],
            cwd=EASYRSA_PATH,
            check=True
        )

        # Обновляем список отозванных сертификатов (CRL)
        print("🔄 Обновляем CRL...")
        subprocess.run(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "gen-crl"],
            cwd=EASYRSA_PATH,
            check=True
        )

        # Копируем новый CRL в директорию OpenVPN
        print(f"📂 Копируем новый CRL в {OPENVPN_CRL_DEST}...")
        subprocess.run(
            ["cp", CRL_PATH, OPENVPN_CRL_DEST],
            check=True
        )

        # Перемещаем файлы в папку revoked
        cert_path = os.path.join(ISSUED_CERTS_PATH, f"{username}.crt")
        key_path = os.path.join(PRIVATE_KEYS_PATH, f"{username}.key")
        revoked_cert_path = os.path.join(REVOKED_CERTS_PATH, f"{username}.crt")
        revoked_key_path = os.path.join(REVOKED_KEYS_PATH, f"{username}.key")

        if os.path.exists(cert_path):
            os.rename(cert_path, revoked_cert_path)
        if os.path.exists(key_path):
            os.rename(key_path, revoked_key_path)

        print(f"✅ Сертификат {username} отозван и перемещён в {REVOKED_CERTS_PATH}")

        # Перезапускаем OpenVPN, чтобы применить обновление CRL
        print("🔄 Перезапускаем OpenVPN...")
        subprocess.run(["systemctl", "restart", "openvpn"], check=True)

        print("✅ OpenVPN перезапущен")

        # Обновляем статус пользователя в базе данных
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE vpn_users SET status = %s WHERE username = %s",
            ("inactive", username)
        )
        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Статус пользователя {username} обновлён на inactive")

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при отзыве сертификата {username}: {e}")


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
