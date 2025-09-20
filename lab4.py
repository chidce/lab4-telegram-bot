import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request
import sqlite3

TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"
WEBHOOK_URL = "https://lab4-telegram-bot.onrender.com"  # твой URL на Render

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --------------------- База данных ---------------------
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users(
    chat_id INTEGER PRIMARY KEY,
    password TEXT,
    is_logged INTEGER,
    is_admin INTEGER,
    predictions_count INTEGER DEFAULT 0
)
''')
conn.commit()

# --------------------- Функции ---------------------
def is_registered(chat_id):
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    return cursor.fetchone() is not None

def is_logged_in(chat_id):
    cursor.execute("SELECT is_logged FROM users WHERE chat_id=?", (chat_id,))
    res = cursor.fetchone()
    return res and res[0] == 1

def is_admin(chat_id):
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    res = cursor.fetchone()
    return res and res[0] == 1

def first_user_is_admin(chat_id):
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute("INSERT INTO users(chat_id, password, is_logged, is_admin) VALUES (?,?,?,?)",
                       (chat_id, "", 0, 1))
        conn.commit()
        return True
    return False

# --------------------- Команды ---------------------
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    if not is_registered(chat_id):
        if first_user_is_admin(chat_id):
            bot.send_message(chat_id, "Ты первый пользователь, назначен администратором.")
        else:
            bot.send_message(chat_id, "Ты не зарегистрирован.")
    else:
        bot.send_message(chat_id, "Привет! Используй /help для списка команд.")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    help_text = ("/register – регистрация\n"
                 "/login – вход\n"
                 "/predict – тест классификатора (заглушка)\n"
                 "/logout – выход\n"
                 "/admin_help – команды администратора")
    bot.send_message(chat_id, help_text)

@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    if is_registered(chat_id):
        bot.send_message(chat_id, "Ты уже зарегистрирован.")
        return
    msg = bot.send_message(chat_id, "Введите пароль для регистрации:")
    bot.register_next_step_handler(msg, finish_register)

def finish_register(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("INSERT INTO users(chat_id, password, is_logged, is_admin) VALUES (?,?,?,?)",
                   (chat_id, password, 1, 0))
    conn.commit()
    bot.send_message(chat_id, "Регистрация успешна! Теперь ты вошёл в систему.")

@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    if not is_registered(chat_id):
        bot.send_message(chat_id, "Ты не зарегистрирован.")
        return
    msg = bot.send_message(chat_id, "Введите пароль для входа:")
    bot.register_next_step_handler(msg, finish_login)

def finish_login(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("SELECT password FROM users WHERE chat_id=?", (chat_id,))
    real_password = cursor.fetchone()[0]
    if password == real_password:
        cursor.execute("UPDATE users SET is_logged=1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Успешный вход!")
    else:
        bot.send_message(chat_id, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    if is_logged_in(chat_id):
        cursor.execute("UPDATE users SET is_logged=0 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Вы вышли из системы.")
    else:
        bot.send_message(chat_id, "Ты не авторизован.")

@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    if is_logged_in(chat_id):
        cursor.execute("UPDATE users SET predictions_count=predictions_count+1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Все работает! (заглушка)")
    else:
        bot.send_message(chat_id, "Сначала войдите через /login.")

@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/view_users"))
    markup.add(KeyboardButton("/delete_user"))
    markup.add(KeyboardButton("/add_admin"))
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(commands=['view_users'])
def view_users(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    cursor.execute("SELECT chat_id, predictions_count FROM users")
    users = cursor.fetchall()
    text = "Пользователи:\n"
    for u in users:
        text += f"ID: {u[0]}, предсказаний: {u[1]}\n"
    bot.send_message(chat_id, text)

@bot.message_handler(commands=['delete_user'])
def delete_user(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    msg = bot.send_message(chat_id, "Введите chat_id пользователя для удаления:")
    bot.register_next_step_handler(msg, finish_delete_user)

def finish_delete_user(message):
    chat_id = message.chat.id
    target_id = int(message.text)
    cursor.execute("DELETE FROM users WHERE chat_id=?", (target_id,))
    conn.commit()
    bot.send_message(chat_id, f"Пользователь {target_id} удалён.")

@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    msg = bot.send_message(chat_id, "Введите chat_id нового администратора:")
    bot.register_next_step_handler(msg, finish_add_admin)

def finish_add_admin(message):
    chat_id = message.chat.id
    target_id = int(message.text)
    cursor.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (target_id,))
    conn.commit()
    bot.send_message(chat_id, f"Пользователь {target_id} теперь администратор.")

# --------------------- Webhook ---------------------
@app.route('/', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

@app.route('/')
def index():
    return "Бот работает", 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=5000)
