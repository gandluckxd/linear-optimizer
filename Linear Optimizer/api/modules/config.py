"""
Конфигурация для Linear Optimizer API
"""

import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки подключения к базе данных Altawin
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '10.8.0.3'),
    'port': int(os.getenv('DB_PORT', '3050')),
    'database': os.getenv('DB_NAME', 'D:/altAwinDB/ppk.gdb'),
    'user': os.getenv('DB_USER', 'sysdba'),
    'password': os.getenv('DB_PASSWORD', 'masterkey'),
    'charset': 'WIN1251'
}

# Настройки API
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '300'))  # 5 минут
MAX_POOL_SIZE = int(os.getenv('MAX_POOL_SIZE', '5'))

# Настройки логирования
ENABLE_LOGGING = os.getenv('ENABLE_LOGGING', 'true').lower() == 'true'

# Настройки оптимизации
DEFAULT_SAW_WIDTH = float(os.getenv('DEFAULT_SAW_WIDTH', '3.0'))  # Ширина пропила в мм
MIN_REMAINDER_LENGTH = float(os.getenv('MIN_REMAINDER_LENGTH', '100.0'))  # Минимальная длина остатка в мм 