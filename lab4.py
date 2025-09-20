import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
import sqlite3

API_TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"
WEBHOOK_URL = "https://lab4-telegram-bot.onrender.com"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- База данных ---
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    password TEXT,
    logged_in INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    predictions_count INTEGER DEFAULT 0
)
""")
conn.commit()

# --- Вспомогательные функции ---
def get_user(chat_id):
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    return cursor.fetchone()

def is_logged_in(chat_id):
    user = get_user(chat_id)
    return user[2] == 1 if user else False

def is_admin(chat_id):
    user = get_user(chat_id)
    return user[3] == 1 if user else False

# --- Регистрация и логин ---
@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    if get_user(chat_id):
        bot.reply_to(message, "Вы уже зарегистрированы! Используйте /login.")
        return
    msg = bot.send_message(chat_id, "Введите пароль для регистрации:")
    bot.register_next_step_handler(msg, process_registration)

def process_registration(message):
    chat_id = message.chat.id
    password = message.text.strip()
    is_first = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    is_admin_flag = 1 if is_first else 0
    cursor.execute("INSERT INTO users(chat_id,password,is_admin) VALUES(?,?,?)",
                   (chat_id, password, is_admin_flag))
    conn.commit()
    bot.reply_to(message, f"Вы зарегистрированы! {'Вы стали администратором.' if is_admin_flag else ''}")

@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    if not user:
        bot.reply_to(message, "Вы не зарегистрированы! Используйте /register.")
        return
    msg = bot.send_message(chat_id, "Введите пароль для входа:")
    bot.register_next_step_handler(msg, process_login)

def process_login(message):
    chat_id = message.chat.id
    password = message.text.strip()
    user = get_user(chat_id)
    if user[1] == password:
        cursor.execute("UPDATE users SET logged_in=1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.reply_to(message, "Вы вошли в систему!")
    else:
        bot.reply_to(message, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    if not is_logged_in(chat_id):
        bot.reply_to(message, "Вы не вошли в систему.")
        return
    cursor.execute("UPDATE users SET logged_in=0 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.reply_to(message, "Вы вышли из системы.")

# --- Заглушка для /predict ---
@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    if not is_logged_in(chat_id):
        bot.reply_to(message, "Сначала войдите в систему с помощью /login.")
        return
    cursor.execute("UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.reply_to(message, "Все работает!")

# --- Панель администратора с кнопками ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.reply_to(message, "Только администратор может использовать панель.")
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Показать пользователей", callback_data="show_users"))
    markup.add(InlineKeyboardButton("Добавить админа", callback_data="add_admin"))
    markup.add(InlineKeyboardButton("Удалить пользователя", callback_data="delete_user"))
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    if call.data == "show_users":
        users = cursor.execute("SELECT chat_id, predictions_count, is_admin FROM users").fetchall()
        reply = "\n".join([f"ID: {u[0]}, predictions: {u[1]}, admin: {bool(u[2])}" for u in users])
        bot.send_message(chat_id, reply or "Нет пользователей.")
    elif call.data == "add_admin":
        msg = bot.send_message(chat_id, "Введите chat_id нового администратора:")
        bot.register_next_step_handler(msg, process_add_admin)
    elif call.data == "delete_user":
        msg = bot.send_message(chat_id, "Введите chat_id пользователя для удаления:")
        bot.register_next_step_handler(msg, process_delete_user)

def process_add_admin(message):
    try:
        new_admin_id = int(message.text.strip())
        cursor.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (new_admin_id,))
        conn.commit()
        bot.reply_to(message, f"{new_admin_id} теперь администратор!")
    except:
        bot.reply_to(message, "Ошибка: введён некорректный chat_id.")

def process_delete_user(message):
    try:
        user_id = int(message.text.strip())
        cursor.execute("DELETE FROM users WHERE chat_id=?", (user_id,))
        conn.commit()
        bot.reply_to(message, f"Пользователь {user_id} удалён.")
    except:
        bot.reply_to(message, "Ошибка: введён некорректный chat_id.")

# --- Flask сервер для webhook ---
@app.route("/", methods=["GET"])
def index():
    return "<h1>Bot is running</h1><p>Check console logs for incoming messages</p>"

@app.route("/", methods=["POST"])
def webhook():
    json_data = request.get_json()
    print("Incoming update:", json_data)
    bot.process_new_updates([telebot.types.Update.de_json(json_data)])
    return "OK", 200

# --- Установка webhook ---
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
