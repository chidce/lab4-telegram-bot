import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import hashlib

TOKEN = "ВАШ_ТОКЕН_БОТА"
bot = telebot.TeleBot(TOKEN)

# --- База данных ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    password_hash TEXT,
    is_logged_in INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    predictions_count INTEGER DEFAULT 0
)
""")
conn.commit()

# --- Хеширование пароля ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- Клавиатуры ---
def main_keyboard(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/register"), KeyboardButton("/login"))
    markup.add(KeyboardButton("/predict"), KeyboardButton("/logout"))
    if is_admin:
        markup.add(KeyboardButton("/admin_help"))
    return markup

# --- Состояния ---
user_register_state = {}
user_login_state = {}
admin_action_state = {}

# --- /start ---
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM users")
    first_user = cursor.fetchone()[0] == 0

    if first_user:
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, is_admin) VALUES (?, ?)", (chat_id, 1))
        conn.commit()
        bot.send_message(chat_id, "Привет! Ты первый пользователь, назначен администратором.",
                         reply_markup=main_keyboard(True))
    else:
        bot.send_message(chat_id, "Привет! Используй /help для списка команд.",
                         reply_markup=main_keyboard(user and user[0] == 1 if user else False))

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
    password_hash = hash_password(message.text)
    cursor.execute("INSERT INTO users (chat_id, password_hash) VALUES (?, ?)", (chat_id, password_hash))
    conn.commit()
    bot.send_message(chat_id, "Регистрация успешна!", reply_markup=main_keyboard())
    user_register_state.pop(chat_id)

# --- Логин ---
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
    password_hash = hash_password(message.text)
    cursor.execute("SELECT * FROM users WHERE chat_id=? AND password_hash=?", (chat_id, password_hash))
    if cursor.fetchone():
        cursor.execute("UPDATE users SET is_logged_in=1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Успешный вход!", reply_markup=main_keyboard())
    else:
        bot.send_message(chat_id, "Неверный пароль.")
    user_login_state.pop(chat_id)

# --- Logout ---
@bot.message_handler(commands=['logout'])
def logout_handler(message):
    chat_id = message.chat.id
    cursor.execute("UPDATE users SET is_logged_in=0 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "Вы вышли из системы.", reply_markup=main_keyboard())

# --- Predict заглушка ---
@bot.message_handler(commands=['predict'])
def predict_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_logged_in FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone() or cursor.fetchone()[0] != 1:
        bot.send_message(chat_id, "Сначала войдите через /login.")
        return
    cursor.execute("UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "Все работает! (заглушка)")

# --- Админ команды ---
@bot.message_handler(commands=['admin_help'])
def admin_help_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user or user[0] != 1:
        bot.send_message(chat_id, "Нет доступа.")
        return
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/view_users"))
    markup.add(KeyboardButton("/delete_user"), KeyboardButton("/add_admin"))
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# --- Просмотр пользователей ---
@bot.message_handler(commands=['view_users'])
def view_users_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone()[0]:
        bot.send_message(chat_id, "Нет доступа.")
        return
    cursor.execute("SELECT chat_id, predictions_count, is_admin FROM users")
    users = cursor.fetchall()
    text = "\n".join([f"{uid} – {'Админ' if is_admin else 'Пользователь'} – Предсказаний: {cnt}" 
                      for uid, cnt, is_admin in users])
    bot.send_message(chat_id, text)

# --- Выбор пользователя для удаления ---
@bot.message_handler(commands=['delete_user'])
def delete_user_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone()[0]:
        bot.send_message(chat_id, "Нет доступа.")
        return
    cursor.execute("SELECT chat_id FROM users WHERE chat_id != ?", (chat_id,))
    users = cursor.fetchall()
    if not users:
        bot.send_message(chat_id, "Нет других пользователей.")
        return
    markup = InlineKeyboardMarkup()
    for uid in users:
        markup.add(InlineKeyboardButton(f"{uid[0]}", callback_data=f"delete_{uid[0]}"))
    bot.send_message(chat_id, "Выберите пользователя для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def callback_delete_user(call):
    chat_id = call.from_user.id
    target_id = int(call.data.split("_")[1])
    cursor.execute("DELETE FROM users WHERE chat_id=?", (target_id,))
    conn.commit()
    bot.answer_callback_query(call.id, f"Пользователь {target_id} удалён.")

# --- Выбор пользователя для добавления админа ---
@bot.message_handler(commands=['add_admin'])
def add_admin_handler(message):
    chat_id = message.chat.id
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone()[0]:
        bot.send_message(chat_id, "Нет доступа.")
        return
    cursor.execute("SELECT chat_id FROM users WHERE is_admin=0")
    users = cursor.fetchall()
    if not users:
        bot.send_message(chat_id, "Нет пользователей для назначения администратором.")
        return
    markup = InlineKeyboardMarkup()
    for uid in users:
        markup.add(InlineKeyboardButton(f"{uid[0]}", callback_data=f"addadmin_{uid[0]}"))
    bot.send_message(chat_id, "Выберите пользователя для назначения админом:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addadmin_"))
def callback_add_admin(call):
    chat_id = call.from_user.id
    target_id = int(call.data.split("_")[1])
    cursor.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (target_id,))
    conn.commit()
    bot.answer_callback_query(call.id, f"Пользователь {target_id} теперь администратор.")

# --- Запуск ---
bot.infinity_polling()
