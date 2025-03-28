import os
import shutil
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Пути к папкам
ISSUED_CERTS_PATH = "/root/openvpn-ca/pki/issued"
PRIVATE_KEYS_PATH = "/root/openvpn-ca/pki/private"
REVOKED_ISSUED_PATH = "/root/openvpn-ca/pki/revoked_issued"
REVOKED_PRIVATE_PATH = "/root/openvpn-ca/pki/revoked_private"

# Подключение к базе данных
DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

def move_file(src, dst):
    """Перемещает файл, если он существует"""
    if os.path.exists(src):
        shutil.move(src, dst)

def check_expired_users():
    """Проверяет подписки и блокирует/разблокирует доступ"""
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    # Получаем список пользователей с истекшим сроком
    cursor.execute("SELECT username, expiration_date FROM vpn_users")
    users = cursor.fetchall()

    for username, expiration_date in users:
        cert_file = f"{username}.crt"
        key_file = f"{username}.key"

        cert_path = os.path.join(ISSUED_CERTS_PATH, cert_file)
        key_path = os.path.join(PRIVATE_KEYS_PATH, key_file)

        revoked_cert_path = os.path.join(REVOKED_ISSUED_PATH, cert_file)
        revoked_key_path = os.path.join(REVOKED_PRIVATE_PATH, key_file)

        # Проверяем, истек ли срок
        if expiration_date and expiration_date < datetime.now():
            print(f"⛔ Блокируем {username} (подписка истекла)")
            move_file(cert_path, revoked_cert_path)
            move_file(key_path, revoked_key_path)
        else:
            # Если срок не истек и файлы находятся в `revoked`, возвращаем их
            if os.path.exists(revoked_cert_path) and os.path.exists(revoked_key_path):
                print(f"✅ Разблокируем {username} (подписка продлена)")
                move_file(revoked_cert_path, cert_path)
                move_file(revoked_key_path, key_path)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_expired_users()
