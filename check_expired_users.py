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


def revoke_certificate(username):
    """Отзывает сертификат пользователя и обновляет CRL."""
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
