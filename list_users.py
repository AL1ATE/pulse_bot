# list_users.py
import os
from datetime import datetime
import openpyxl
from openpyxl.styles import Font
from telebot import types
from db import get_db_connection


def create_users_excel(users):
    """Создает Excel файл со списком пользователей"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VPN Users"

    # Заголовки
    headers = ["ID", "Username", "Expiration Date", "Status"]
    ws.append(headers)

    # Стиль для заголовков
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Данные пользователей
    for user in users:
        user_id, username, exp_date = user
        # Приводим даты к одному типу для сравнения
        today = datetime.now().date()
        if isinstance(exp_date, datetime):
            exp_date = exp_date.date()

        status = "Active" if not exp_date or exp_date >= today else "Expired"
        exp_str = exp_date.strftime('%Y-%m-%d') if exp_date else "Lifetime"
        ws.append([user_id, username, exp_str, status])

    # Автоматическая ширина столбцов
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        ws.column_dimensions[column_letter].width = adjusted_width

    filename = f"vpn_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(filename)
    return filename


def list_users(bot, message):
    """Выводит список пользователей в Excel файле"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, expiration_date FROM vpn_users ORDER BY id")
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        if not users:
            bot.send_message(message.chat.id, "❌ В базе нет пользователей.")
            return

        # Создаем Excel файл
        filename = create_users_excel(users)

        # Отправляем файл пользователю
        with open(filename, 'rb') as file:
            bot.send_document(
                chat_id=message.chat.id,
                document=file,
                caption="📊 Полный список пользователей VPN",
                parse_mode="HTML"
            )

        # Удаляем временный файл
        os.remove(filename)

    except Exception as e:
        print(f"Ошибка при экспорте пользователей: {e}")
        bot.send_message(message.chat.id, f"⚠ Произошла ошибка при создании отчета: {str(e)}")