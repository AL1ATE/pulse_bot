import os

# Настройки OpenVPN
EASYRSA_PATH = "/root/openvpn-ca/"
CA_PATH = os.path.join(EASYRSA_PATH, "pki")
ISSUED_CERTS_PATH = os.path.join(CA_PATH, "issued")
PRIVATE_KEYS_PATH = os.path.join(CA_PATH, "private")
CONFIGS_DIR = "configs"
SERVER_IP = "176.124.208.223"
SERVER_PORT = "1194"

# Настройки бота
PAGE_SIZE = 10  # Количество пользователей на странице

# Создаем директорию для конфигов
os.makedirs(CONFIGS_DIR, exist_ok=True)