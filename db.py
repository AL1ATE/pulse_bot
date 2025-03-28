import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

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