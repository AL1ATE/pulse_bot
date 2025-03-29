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
        shutil.copy(revoked_cert_path, active_cert_path)
    if os.path.exists(revoked_key_path):
        shutil.copy(revoked_key_path, active_key_path)

    # Обновляем статус сертификата в базе EasyRSA
    try:
        # Используем update-db для изменения статуса с R (отозван) на V (валидный)
        subprocess.run(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "update-db"],
            cwd=EASYRSA_PATH,
            check=True
        )

        # Генерируем новый CRL
        bot.send_message(message.chat.id, "🔄 Обновляем CRL и перезапускаем OpenVPN...")
        subprocess.run([os.path.join(EASYRSA_PATH, "easyrsa"), "gen-crl"],
                       cwd=EASYRSA_PATH, check=True)
        subprocess.run(["cp", CRL_PATH, OPENVPN_CRL_DEST], check=True)
        subprocess.run(["systemctl", "restart", "openvpn"], check=True)

        bot.send_message(message.chat.id,
                         f"✅ Подписка для {username} продлена до {new_expiration_date.strftime('%Y-%m-%d')}")
    except subprocess.CalledProcessError as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при обновлении статуса сертификата: {e}")
    finally:
        cursor.close()
        conn.close()
