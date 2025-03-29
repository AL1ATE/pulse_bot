import os
import psycopg2
import subprocess
from datetime import datetime, timedelta, timezone
from db import get_db_connection

EASYRSA_PATH = "/root/openvpn-ca"
REVOKED_CERTS_PATH = "/root/openvpn-ca/pki/revoked_issued"
REVOKED_KEYS_PATH = "/root/openvpn-ca/pki/revoked_private"
ISSUED_CERTS_PATH = "/root/openvpn-ca/pki/issued"
PRIVATE_KEYS_PATH = "/root/openvpn-ca/pki/private"
CRL_PATH = "/root/openvpn-ca/pki/crl.pem"
OPENVPN_CRL_DEST = "/etc/openvpn/crl.pem"


def fix_index_txt():
    """Проверяет и корректирует файл index.txt, чтобы исправить статус сертификатов с неверной датой отзыва."""
    index_txt_path = os.path.join(EASYRSA_PATH, "pki", "index.txt")

    with open(index_txt_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    for line in lines:
        # Проверяем, есть ли дата отзыва, но статус не изменён на R
        if "/CN=" in line and "R" not in line:
            # Прописываем новый статус если нужно
            if "not revoked yet, but has a revocation date" in line:
                line = line.replace("not revoked yet, but has a revocation date", "R")
        fixed_lines.append(line)

    with open(index_txt_path, "w") as f:
        f.writelines(fixed_lines)


def process_extend_username(message, bot):
    """Проверяем, существует ли пользователь и продлеваем подписку"""
    username = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Проверяем наличие пользователя
    cursor.execute("SELECT expiration_date, status FROM vpn_users WHERE username = %s", (username,))
    user_data = cursor.fetchone()

    if not user_data:
        bot.send_message(message.chat.id, f"❌ Пользователь {username} не найден.")
        return

    bot.send_message(message.chat.id, "Продлеваем подписку на 30 дней...")

    new_expiration_date = datetime.now(timezone.utc) + timedelta(days=30)

    # Обновляем срок действия в БД
    cursor.execute("UPDATE vpn_users SET expiration_date = %s, status = 'active' WHERE username = %s",
                   (new_expiration_date, username))
    conn.commit()

    # Перемещаем файлы сертификатов обратно в активные
    revoked_cert_path = os.path.join(REVOKED_CERTS_PATH, f"{username}.crt")
    revoked_key_path = os.path.join(REVOKED_KEYS_PATH, f"{username}.key")
    active_cert_path = os.path.join(ISSUED_CERTS_PATH, f"{username}.crt")
    active_key_path = os.path.join(PRIVATE_KEYS_PATH, f"{username}.key")

    if os.path.exists(revoked_cert_path):
        os.rename(revoked_cert_path, active_cert_path)

    if os.path.exists(revoked_key_path):
        os.rename(revoked_key_path, active_key_path)

    # Обновляем статус в index.txt (удаляем отметку об отзыве)
    index_path = os.path.join(EASYRSA_PATH, "pki", "index.txt")
    with open(index_path, "r") as f:
        lines = f.readlines()

    with open(index_path, "w") as f:
        for line in lines:
            if username in line and line.startswith("R"):
                # Меняем статус с R (revoked) на V (valid)
                new_line = "V" + line[1:]
                f.write(new_line)
            else:
                f.write(line)

    bot.send_message(message.chat.id, "🔄 Обновляем CRL и перезапускаем OpenVPN...")

    # Пересоздаём CRL и перезапускаем OpenVPN
    subprocess.run([os.path.join(EASYRSA_PATH, "easyrsa"), "gen-crl"], cwd=EASYRSA_PATH, check=True)
    subprocess.run(["cp", CRL_PATH, OPENVPN_CRL_DEST], check=True)
    subprocess.run(["systemctl", "restart", "openvpn"], check=True)

    bot.send_message(message.chat.id,
                     f"✅ Подписка для {username} продлена до {new_expiration_date.strftime('%Y-%m-%d')}")

    cursor.close()
    conn.close()
