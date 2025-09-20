import sqlite3
from telebot import TeleBot, types

# -------------------- НАСТРОЙКИ --------------------
TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"
WEBHOOK_URL = "https://lab4-telegram-bot.onrender.com"  # URL вашего Render-проекта

bot = TeleBot(TOKEN)

# -------------------- БАЗА ДАННЫХ --------------------
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    password TEXT,
    is_logged_in INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    predict_count INTEGER DEFAULT 0
)
""")
conn.commit()

# -------------------- СОСТОЯНИЯ --------------------
user_register_state = {}
user_login_state = {}

# -------------------- КЛАВИАТУРЫ --------------------
def main_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("/register"), types.KeyboardButton("/login"))
    markup.row(types.KeyboardButton("/predict"), types.KeyboardButton("/logout"))
    if is_admin:
        markup.row(types.KeyboardButton("/admin_help"))
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Просмотр пользователей", callback_data="view_users"))
    markup.add(types.InlineKeyboardButton("Удалить пользователя", callback_data="delete_user"))
    markup.add(types.InlineKeyboardButton("Добавить администратора", callback_data="add_admin"))
    return markup

# -------------------- ОБРАБОТЧИКИ --------------------
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        is_admin = 1 if total == 0 else 0  # Первый пользователь — админ
        cursor.execute("INSERT INTO users (chat_id, is_admin) VALUES (?, ?)", (chat_id, is_admin))
        conn.commit()
        if is_admin:
            bot.send_message(chat_id, "Привет! Ты первый пользователь, назначен администратором.",
                             reply_markup=main_keyboard(True))
        else:
            bot.send_message(chat_id, "Привет! Ты не зарегистрирован.", reply_markup=main_keyboard())
    else:
        is_admin = user[3]  # is_admin
        bot.send_message(chat_id, "Привет! Используй /help для списка команд.",
                         reply_markup=main_keyboard(is_admin))

@bot.message_handler(commands=['help'])
def help_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    is_admin = user[0] if user else 0
    text = "/register – регистрация\n/login – вход\n/predict – тест классификатора (заглушка)\n/logout – выход"
    if is_admin:
        text += "\n/admin_help – команды администратора"
    bot.send_message(chat_id, text, reply_markup=main_keyboard(is_admin))

# -------------------- РЕГИСТРАЦИЯ --------------------
@bot.message_handler(commands=['register'])
def register_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if cursor.fetchone():
        bot.send_message(chat_id, "Ты уже зарегистрирован.")
        return
    bot.send_message(chat_id, "Введите пароль для регистрации:")
    user_register_state[chat_id] = True

@bot.message_handler(func=lambda m: m.chat.id in user_register_state)
def register_password(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("UPDATE users SET password=? WHERE chat_id=?", (password, chat_id))
    conn.commit()
    user_register_state.pop(chat_id)
    bot.send_message(chat_id, "Регистрация успешна!")

# -------------------- ВХОД --------------------
@bot.message_handler(commands=['login'])
def login_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone():
        bot.send_message(chat_id, "Ты не зарегистрирован.")
        return
    bot.send_message(chat_id, "Введите пароль для входа:")
    user_login_state[chat_id] = True

@bot.message_handler(func=lambda m: m.chat.id in user_login_state)
def login_password(message):
    chat_id = message.chat.id
    password = message.text
    cursor.execute("SELECT password FROM users WHERE chat_id=?", (chat_id,))
    real_password = cursor.fetchone()[0]
    if password == real_password:
        cursor.execute("UPDATE users SET is_logged_in=1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Успешный вход!", reply_markup=main_keyboard(True))
    else:
        bot.send_message(chat_id, "Неверный пароль.")
    user_login_state.pop(chat_id)

# -------------------- ВЫХОД --------------------
@bot.message_handler(commands=['logout'])
def logout_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_logged_in FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user or user[0] == 0:
        bot.send_message(chat_id, "Ты не авторизован.")
        return
    cursor.execute("UPDATE users SET is_logged_in=0 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "Вы вышли из системы.")

# -------------------- ЗАГЛУШКА PREDICT --------------------
@bot.message_handler(commands=['predict'])
def predict_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_logged_in FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user or user[0] != 1:
        bot.send_message(chat_id, "Сначала войдите через /login.")
        return
    cursor.execute("UPDATE users SET predict_count = predict_count + 1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "Все работает! (заглушка)")

# -------------------- АДМИН --------------------
@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user or user[0] != 1:
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.send_message(chat_id, "Выберите действие:", reply_markup=admin_keyboard())

# -------------------- CALLBACK АДМИНА --------------------
@bot.callback_query_handler(func=lambda call: True)
def admin_actions(call):
    chat_id = call.message.chat.id
    if call.data == "view_users":
        cursor.execute("SELECT chat_id, predict_count FROM users")
        users = cursor.fetchall()
        text = "\n".join([f"{u[0]} – предсказаний: {u[1]}" for u in users])
        bot.send_message(chat_id, text)
    elif call.data == "delete_user":
        bot.send_message(chat_id, "Эта функция ещё не реализована (можно добавить через инлайн-кнопки)")
    elif call.data == "add_admin":
        bot.send_message(chat_id, "Эта функция ещё не реализована (можно добавить через инлайн-кнопки)")

# -------------------- ЗАПУСК БОТА --------------------
bot.infinity_polling()
