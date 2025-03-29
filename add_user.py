import os
from datetime import datetime, timedelta
import subprocess
from telebot import types
from db import get_db_connection
from config import *


def generate_certificates(username, ca_password):
    """Генерирует сертификаты для пользователя"""
    try:
        # Генерация запроса на сертификат
        gen_req = subprocess.Popen(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "gen-req", username, "nopass"],
            cwd=EASYRSA_PATH,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        gen_req.communicate(input='\n' * 10)

        # Подпись сертификата
        sign_req = subprocess.Popen(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "sign-req", "client", username],
            cwd=EASYRSA_PATH,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        sign_req.communicate(input=f'yes\n{ca_password}\n\n')

        return sign_req.returncode == 0
    except Exception as e:
        print(f"Ошибка генерации сертификатов: {e}")
        return False


def extract_cert_content(cert_path):
    """Извлекает только часть сертификата без метаданных"""
    with open(cert_path, "r") as f:
        cert_data = f.read()

    # Извлекаем только часть сертификата, начиная с BEGIN CERTIFICATE и заканчивая END CERTIFICATE
    cert_start = cert_data.find("-----BEGIN CERTIFICATE-----")
    cert_end = cert_data.find("-----END CERTIFICATE-----") + len("-----END CERTIFICATE-----")

    if cert_start != -1 and cert_end != -1:
        return cert_data[cert_start:cert_end]

    return None


def create_ovpn_config(username):
    """Создает конфигурационный файл .ovpn"""
    try:
        with open(os.path.join(CA_PATH, "ca.crt"), "r") as f:
            ca_cert = f.read()

        # Извлекаем только нужную часть сертификата
        user_cert = extract_cert_content(os.path.join(ISSUED_CERTS_PATH, f"{username}.crt"))

        with open(os.path.join(PRIVATE_KEYS_PATH, f"{username}.key"), "r") as f:
            user_key = f.read()

        if not user_cert:
            raise Exception("Не удалось извлечь сертификат пользователя.")

        config_content = f"""client
dev tun
proto udp
remote {SERVER_IP} {SERVER_PORT}
resolv-retry infinite
nobind
persist-key
persist-tun
comp-lzo
verb 3

<ca>
{ca_cert}
</ca>
<cert>
{user_cert}
</cert>
<key>
{user_key}
</key>
"""
        config_path = os.path.join(CONFIGS_DIR, f"{username}.ovpn")
        with open(config_path, "w") as f:
            f.write(config_content)

        return config_path
    except Exception as e:
        print(f"Ошибка создания конфига: {e}")
        return None


def add_user_start(bot, message):
    """Начало процесса добавления пользователя"""
    msg = bot.send_message(message.chat.id, "Введите имя пользователя для VPN:")
    bot.register_next_step_handler(msg, lambda m: add_user_expiration(bot, m))


def add_user_expiration(bot, message):
    """Обработка имени пользователя и запрос срока действия"""
    username = message.text.strip()
    if not username:
        bot.send_message(message.chat.id, "❌ Имя пользователя не может быть пустым!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vpn_users WHERE username = %s", (username,))
    if cursor.fetchone():
        bot.send_message(message.chat.id, "❌ Пользователь с таким именем уже существует!")
        cursor.close()
        conn.close()
        return
    cursor.close()
    conn.close()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("30 дней"), types.KeyboardButton("Навсегда"))
    bot.send_message(message.chat.id, "Выберите срок действия:", reply_markup=markup)
    bot.register_next_step_handler(message, lambda m: add_user_final(bot, m, username))


def add_user_final(bot, message, username):
    """Финальное добавление пользователя в систему"""
    if message.text not in ["30 дней", "Навсегда"]:
        bot.send_message(message.chat.id, "❌ Неверный выбор срока!")
        return

    bot.send_message(message.chat.id, "⏳ Генерирую сертификаты...")
    if not generate_certificates(username, os.getenv("CA_PASSWORD")):
        bot.send_message(message.chat.id, "❌ Ошибка при генерации сертификатов!")
        return

    bot.send_message(message.chat.id, "⏳ Создаю конфигурационный файл...")
    config_path = create_ovpn_config(username)
    if not config_path:
        bot.send_message(message.chat.id, "❌ Ошибка при создании конфига!")
        return

    expiration_date = datetime.now() + timedelta(days=30) if message.text == "30 дней" else None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO vpn_users (username, vpn_config, expiration_date) VALUES (%s, %s, %s)",
            (username, f"{username}.ovpn", expiration_date)
        )
        conn.commit()
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка базы данных: {e}")
        return
    finally:
        cursor.close()
        conn.close()

    with open(config_path, "rb") as f:
        bot.send_document(
            message.chat.id,
            f,
            caption=f"✅ Пользователь {username} успешно создан!\nСрок действия: {message.text}"
        )

    os.remove(config_path)

    # Отправить сообщение с кнопками "Добавить пользователя" и "Список пользователей" после создания пользователя
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Добавить пользователя"),
               types.KeyboardButton("Список пользователей"),
               types.KeyboardButton("Продлить VPN"))
    bot.send_message(message.chat.id, "👋 Добро пожаловать в админ-панель VPN!", reply_markup=markup)

