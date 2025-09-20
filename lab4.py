import sqlite3
import telebot
from flask import Flask, request

# ======= Настройки =======
API_TOKEN = "ТВОЙ_ТОКЕН_БОТА"  # Вставь свой токен
WEBHOOK_URL = "https://твое-имя-проекта.up.railway.app"  # Публичный URL проекта Railway/Render
DB_NAME = "users.db"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ===== Инициализация базы данных =====
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        password TEXT,
                        is_logged_in INTEGER DEFAULT 0,
                        is_admin INTEGER DEFAULT 0
                    )''')
    conn.commit()
    conn.close()

init_db()

# ===== Функции для работы с БД =====
def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, password, is_admin=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (id, password, is_logged_in, is_admin) VALUES (?, ?, 0, ?)",
                   (user_id, password, is_admin))
    conn.commit()
    conn.close()

def set_login(user_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_logged_in=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()

def set_admin(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def del_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def list_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_logged_in, is_admin FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

# ===== Команды бота =====
@bot.message_handler(commands=['start'])
def start(message):
    user = get_user(message.chat.id)
    if not user:
        add_user(message.chat.id, "admin", is_admin=1)
        bot.send_message(message.chat.id, "Привет! Ты первый пользователь, назначен администратором.")
    else:
        bot.send_message(message.chat.id, "Привет! Используй /help для списка команд.")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id,
                     "/register – регистрация\n"
                     "/login – вход\n"
                     "/predict – тест классификатора (заглушка)\n"
                     "/logout – выход\n"
                     "/admin_help – команды администратора")

@bot.message_handler(commands=['register'])
def register(message):
    msg = bot.send_message(message.chat.id, "Введите пароль для регистрации:")
    bot.register_next_step_handler(msg, process_register)

def process_register(message):
    if get_user(message.chat.id):
        bot.send_message(message.chat.id, "Ты уже зарегистрирован.")
    else:
        add_user(message.chat.id, message.text)
        bot.send_message(message.chat.id, "Регистрация успешна!")

@bot.message_handler(commands=['login'])
def login(message):
    msg = bot.send_message(message.chat.id, "Введите пароль для входа:")
    bot.register_next_step_handler(msg, process_login)

def process_login(message):
    user = get_user(message.chat.id)
    if not user:
        bot.send_message(message.chat.id, "Ты не зарегистрирован.")
        return
    if user[1] == message.text:
        set_login(message.chat.id, 1)
        bot.send_message(message.chat.id, "Успешный вход!")
    else:
        bot.send_message(message.chat.id, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout(message):
    user = get_user(message.chat.id)
    if user and user[2] == 1:
        set_login(message.chat.id, 0)
        bot.send_message(message.chat.id, "Вы вышли из системы.")
    else:
        bot.send_message(message.chat.id, "Ты не авторизован.")

@bot.message_handler(commands=['predict'])
def predict(message):
    user = get_user(message.chat.id)
    if user and user[2] == 1:
        bot.send_message(message.chat.id, "Все работает! (заглушка)")
    else:
        bot.send_message(message.chat.id, "Сначала войдите через /login.")

# ===== Админ команды =====
@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    user = get_user(message.chat.id)
    if user and user[3] == 1:
        bot.send_message(message.chat.id,
                         "/list_users – список пользователей\n"
                         "/del_user <id> – удалить пользователя\n"
                         "/add_admin <id> – добавить администратора")
    else:
        bot.send_message(message.chat.id, "Нет доступа.")

@bot.message_handler(commands=['list_users'])
def list_users_cmd(message):
    user = get_user(message.chat.id)
    if user and user[3] == 1:
        users = list_users()
        text = "\n".join([f"ID: {u[0]}, logged_in={u[1]}, admin={u[2]}" for u in users])
        bot.send_message(message.chat.id, text if text else "Нет пользователей.")
    else:
        bot.send_message(message.chat.id, "Нет доступа.")

@bot.message_handler(commands=['del_user'])
def del_user_cmd(message):
    user = get_user(message.chat.id)
    if user and user[3] == 1:
        try:
            user_id = int(message.text.split()[1])
            del_user(user_id)
            bot.send_message(message.chat.id, f"Пользователь {user_id} удален.")
        except:
            bot.send_message(message.chat.id, "Используй: /del_user <id>")
    else:
        bot.send_message(message.chat.id, "Нет доступа.")

@bot.message_handler(commands=['add_admin'])
def add_admin_cmd(message):
    user = get_user(message.chat.id)
    if user and user[3] == 1:
        try:
            user_id = int(message.text.split()[1])
            set_admin(user_id)
            bot.send_message(message.chat.id, f"Пользователь {user_id} назначен администратором.")
        except:
            bot.send_message(message.chat.id, "Используй: /add_admin <id>")
    else:
        bot.send_message(message.chat.id, "Нет доступа.")

# ===== Flask webhook =====
@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def index():
    return "Бот работает!", 200

# ===== Запуск =====
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + "/" + API_TOKEN)
    app.run(host="0.0.0.0", port=5000)
