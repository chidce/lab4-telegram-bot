import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request
import sqlite3

TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"
bot = telebot.TeleBot(TOKEN)

# --- База данных ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    password TEXT,
    is_admin INTEGER DEFAULT 0
)
""")
conn.commit()

# --- Клавиатура ---
def main_keyboard(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/register"), KeyboardButton("/login"))
    markup.add(KeyboardButton("/predict"), KeyboardButton("/logout"))
    if is_admin:
        markup.add(KeyboardButton("/admin_help"))
    return markup

# --- /start ---
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()

    if user_count == 0:
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, is_admin) VALUES (?, ?)", (chat_id, 1))
        conn.commit()
        bot.send_message(chat_id, "Привет! Ты первый пользователь, назначен администратором.",
                         reply_markup=main_keyboard(True))
    else:
        bot.send_message(chat_id, "Привет! Используй /help для списка команд.",
                         reply_markup=main_keyboard(user and user[0] == 1))

# --- /help ---
@bot.message_handler(commands=['help'])
def help_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    is_admin = cursor.fetchone() and cursor.fetchone()[0] == 1
    bot.send_message(chat_id,
                     "/register – регистрация\n/login – вход\n/predict – тест классификатора\n/logout – выход\n/admin_help – команды администратора",
                     reply_markup=main_keyboard(is_admin))

# --- Регистрация ---
user_register_state = {}
@bot.message_handler(commands=['register'])
def register_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if cursor.fetchone():
        bot.send_message(chat_id, "Вы уже зарегистрированы.")
        return
    bot.send_message(chat_id, "Введите пароль для регистрации:")
    user_register_state[chat_id] = True

@bot.message_handler(func=lambda m: user_register_state.get(m.chat.id))
def register_password_handler(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("SELECT COUNT(*) FROM users")
    first_user = cursor.fetchone()[0] == 0
    is_admin = 1 if first_user else 0
    cursor.execute("INSERT INTO users (chat_id, password, is_admin) VALUES (?, ?, ?)",
                   (chat_id, password, is_admin))
    conn.commit()
    bot.send_message(chat_id, "Регистрация успешна!" + (" Вы администратор." if is_admin else ""))
    user_register_state.pop(chat_id)

# --- Логин ---
user_login_state = {}
@bot.message_handler(commands=['login'])
def login_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone():
        bot.send_message(chat_id, "Вы не зарегистрированы. Используйте /register")
        return
    bot.send_message(chat_id, "Введите пароль для входа:")
    user_login_state[chat_id] = True

@bot.message_handler(func=lambda m: user_login_state.get(m.chat.id))
def login_password_handler(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("SELECT * FROM users WHERE chat_id=? AND password=?", (chat_id, password))
    if cursor.fetchone():
        bot.send_message(chat_id, "Успешный вход!", reply_markup=main_keyboard())
    else:
        bot.send_message(chat_id, "Неверный пароль.")
    user_login_state.pop(chat_id)

# --- Logout ---
@bot.message_handler(commands=['logout'])
def logout_handler(message):
    bot.send_message(message.chat.id, "Вы вышли из системы.", reply_markup=main_keyboard())

# --- Predict заглушка ---
@bot.message_handler(commands=['predict'])
def predict_handler(message):
    bot.send_message(message.chat.id, "Все работает! (заглушка)")

# --- Admin ---
@bot.message_handler(commands=['admin_help'])
def admin_help_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user or user[0] != 1:
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.send_message(chat_id, "Команды администратора:\n/view_users\n/delete_user\n/add_admin")

# --- Просмотр пользователей ---
@bot.message_handler(commands=['view_users'])
def view_users_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone()[0]:
        bot.send_message(chat_id, "Нет доступа.")
        return
    cursor.execute("SELECT chat_id, is_admin FROM users")
    users = cursor.fetchall()
    text = "\n".join([f"{uid} – {'Админ' if is_admin else 'Пользователь'}" for uid, is_admin in users])
    bot.send_message(chat_id, text)

# --- Flask приложение для webhook ---
WEBHOOK_URL = "https://lab4-telegram-bot.onrender.com"
WEBHOOK_PATH = "/webhook/" + TOKEN
WEBHOOK_FULL_URL = WEBHOOK_URL + WEBHOOK_PATH

app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_FULL_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
