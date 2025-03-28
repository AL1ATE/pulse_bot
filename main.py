import os
import telebot
from telebot import types
from db import is_admin
from add_user import add_user_start
from list_users import list_users

# Инициализация бота
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))


@bot.message_handler(commands=['start'])
def start(message):
    """Обработка команды /start"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 У вас нет доступа к этому боту!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Добавить пользователя"),
               types.KeyboardButton("Список пользователей"))
    bot.send_message(message.chat.id, "👋 Добро пожаловать в админ-панель VPN!", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "Список пользователей")
def handle_list_users(message):
    """Обработка кнопки списка пользователей"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 У вас нет доступа!")
        return
    list_users(bot, message)


@bot.message_handler(func=lambda m: m.text == "Добавить пользователя")
def handle_add_user(message):
    """Обработка кнопки добавления пользователя"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 У вас нет доступа!")
        return
    add_user_start(bot, message)


if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling()