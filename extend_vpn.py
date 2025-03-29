import os
import psycopg2
from datetime import datetime, timedelta, timezone
from db import get_db_connection


def process_extend_username(message, bot):
    """Продлевает подписку пользователя на 30 дней от текущей даты окончания"""
    username = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем наличие пользователя и получаем текущую дату окончания
        cursor.execute("SELECT expiration_date FROM vpn_users WHERE username = %s", (username,))
        user_data = cursor.fetchone()

        if not user_data:
            bot.send_message(message.chat.id, f"❌ Пользователь {username} не найден.")
            return

        current_expiration = user_data[0]

        # Если даты нет (NULL), устанавливаем от текущей даты +30 дней
        if current_expiration is None:
            new_expiration_date = datetime.now(timezone.utc) + timedelta(days=30)
        else:
            # Добавляем 30 дней к текущей дате окончания
            new_expiration_date = current_expiration + timedelta(days=30)

        # Обновляем срок действия в БД
        cursor.execute(
            "UPDATE vpn_users SET expiration_date = %s, status = 'active' WHERE username = %s",
            (new_expiration_date, username)
        )
        conn.commit()

        bot.send_message(
            message.chat.id,
            f"✅ Подписка для {username} продлена до {new_expiration_date.strftime('%Y-%m-%d')}"
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при продлении подписки: {str(e)}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()