import os
import shutil
from datetime import datetime
from db import get_db_connection

# Пути к директориям
CERTS_DIR = "/etc/openvpn/easy-rsa/pki/issued/"
KEYS_DIR = "/etc/openvpn/easy-rsa/pki/private/"
REVOKED_DIR = "/etc/openvpn/revoked/"

# Убедимся, что папка для заблокированных сертификатов существует
os.makedirs(REVOKED_DIR, exist_ok=True)


def check_and_revoke_users():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Выбираем пользователей с истекшей подпиской
    cursor.execute("SELECT username FROM vpn_users WHERE expiration_date IS NOT NULL AND expiration_date < NOW()")
    expired_users = cursor.fetchall()

    for (username,) in expired_users:
        cert_path = os.path.join(CERTS_DIR, f"{username}.crt")
        key_path = os.path.join(KEYS_DIR, f"{username}.key")
        revoked_cert_path = os.path.join(REVOKED_DIR, f"{username}.crt")
        revoked_key_path = os.path.join(REVOKED_DIR, f"{username}.key")

        # Перемещаем файлы, если они существуют
        if os.path.exists(cert_path) and os.path.exists(key_path):
            shutil.move(cert_path, revoked_cert_path)
            shutil.move(key_path, revoked_key_path)
            print(f"Доступ для {username} заблокирован")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    check_and_revoke_users()
