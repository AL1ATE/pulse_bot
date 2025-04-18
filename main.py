import os
import telebot
from telebot import types
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
import subprocess

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))

# Конфигурационные пути
EASYRSA_PATH = "/root/openvpn-ca/"
CA_PATH = os.path.join(EASYRSA_PATH, "pki")
ISSUED_CERTS_PATH = os.path.join(CA_PATH, "issued")
PRIVATE_KEYS_PATH = os.path.join(CA_PATH, "private")
CONFIGS_DIR = "configs"
SERVER_IP = "176.124.208.223"

# Создаем директорию для конфигов, если ее нет
os.makedirs(CONFIGS_DIR, exist_ok=True)


def get_db_connection():
    """Устанавливает соединение с PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admins WHERE telegram_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None


def generate_certificates(username, ca_password):
    """Генерирует сертификаты с автоматическим вводом пароля CA"""
    try:
        # 1. Генерация запроса на сертификат
        gen_req = subprocess.Popen(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "gen-req", username, "nopass"],
            cwd=EASYRSA_PATH,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Автоматический ввод пустых значений для всех полей
        output, error = gen_req.communicate(input='\n' * 10)

        if gen_req.returncode != 0:
            print(f"Ошибка gen-req: {error}")
            return False

        # 2. Подпись сертификата
        sign_req = subprocess.Popen(
            [os.path.join(EASYRSA_PATH, "easyrsa"), "sign-req", "client", username],
            cwd=EASYRSA_PATH,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Последовательность ввода:
        # 1. Подтверждение 'yes'
        # 2. Пароль CA
        inputs = [
            'yes\n',  # Подтверждение подписи
            f"{ca_password}\n",  # Пароль CA key
            '\n'  # Дополнительный перевод строки на всякий случай
        ]
        output, error = sign_req.communicate(input=''.join(inputs))

        if sign_req.returncode != 0:
            print(f"Ошибка sign-req: {error}")
            return False

        return True

    except Exception as e:
        print(f"Ошибка генерации сертификатов: {str(e)}")
        return False


def create_ovpn_config(username):
    """Создает .ovpn файл с правильным форматированием"""
    try:
        # Чтение CA сертификата
        with open(os.path.join(CA_PATH, "ca.crt"), "r") as f:
            ca_content = f.read()
            ca_cert = extract_pem_content(ca_content, "CERTIFICATE")

        # Чтение пользовательского сертификата
        with open(os.path.join(ISSUED_CERTS_PATH, f"{username}.crt"), "r") as f:
            user_cert_content = f.read()
            user_cert = extract_pem_content(user_cert_content, "CERTIFICATE")

        # Чтение приватного ключа
        with open(os.path.join(PRIVATE_KEYS_PATH, f"{username}.key"), "r") as f:
            user_key = f.read().strip()

        # Формирование конфига
        config_content = f"""client
dev tun
proto udp
remote 176.124.208.223 1194
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
        # Сохранение файла
        config_path = os.path.join(CONFIGS_DIR, f"{username}.ovpn")
        with open(config_path, "w") as f:
            f.write(config_content)

        return config_path
    except Exception as e:
        print(f"Ошибка создания конфига: {str(e)}")
        return None


def extract_pem_content(content, pem_type):
    """Извлекает только PEM-блоки из содержимого файла"""
    start_marker = f"-----BEGIN {pem_type}-----"
    end_marker = f"-----END {pem_type}-----"

    start = content.find(start_marker)
    end = content.find(end_marker)

    if start == -1 or end == -1:
        raise ValueError(f"Не найден PEM-блок для {pem_type}")

    # Включаем маркеры в результат
    return content[start:end + len(end_marker)]


@bot.message_handler(commands=['start'])
def start(message):
    """Обработчик команды /start"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 У вас нет доступа к этому боту!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_add = types.KeyboardButton("Добавить пользователя")
    markup.add(btn_add)
    bot.send_message(message.chat.id, "👋 Добро пожаловать в админ-панель VPN!", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Добавить пользователя")
def add_user_start(message):
    """Начало процесса добавления пользователя"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 У вас нет доступа!")
        return

    msg = bot.send_message(message.chat.id, "Введите имя пользователя для VPN:")
    bot.register_next_step_handler(msg, add_user_expiration)


def add_user_expiration(message):
    """Обработка имени пользователя и запрос срока действия"""
    username = message.text.strip()
    if not username:
        bot.send_message(message.chat.id, "❌ Имя пользователя не может быть пустым!")
        return

    # Проверяем, существует ли уже пользователь
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
    btn_30 = types.KeyboardButton("30 дней")
    btn_forever = types.KeyboardButton("Навсегда")
    markup.add(btn_30, btn_forever)

    bot.send_message(message.chat.id, "Выберите срок действия:", reply_markup=markup)
    bot.register_next_step_handler(message, lambda m: add_user_final(m, username))


def add_user_final(message, username):
    """Финальное добавление пользователя"""
    if message.text not in ["30 дней", "Навсегда"]:
        bot.send_message(message.chat.id, "❌ Неверный выбор срока!")
        return

    # Генерация сертификатов
    bot.send_message(message.chat.id, "⏳ Генерирую сертификаты...")
    if not generate_certificates(username, os.getenv("CA_PASSWORD")):
        bot.send_message(message.chat.id, "❌ Ошибка при генерации сертификатов!")
        return

    # Создание конфига
    bot.send_message(message.chat.id, "⏳ Создаю конфигурационный файл...")
    config_path = create_ovpn_config(username)
    if not config_path:
        bot.send_message(message.chat.id, "❌ Ошибка при создании конфига!")
        return

    # Установка срока действия
    expiration_date = None
    if message.text == "30 дней":
        expiration_date = datetime.now() + timedelta(days=30)

    # Сохранение в БД
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO vpn_users (username, vpn_config, expiration_date) VALUES (%s, %s, %s)",
            (username, f"{username}.ovpn", expiration_date)
        )
        conn.commit()
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка базы данных: {str(e)}")
        return
    finally:
        cursor.close()
        conn.close()

    # Отправка файла пользователю
    with open(config_path, "rb") as f:
        bot.send_document(
            message.chat.id,
            f,
            caption=f"✅ Пользователь {username} успешно создан!\nСрок действия: {message.text}"
        )

    # Удаление временного файла
    os.remove(config_path)

    # Возврат на старт
    start(message)


if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling()
