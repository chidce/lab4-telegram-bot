import telebot
from telebot import types
import tensorflow as tf
import numpy as np
import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from tensorflow.keras.preprocessing import image

# Bot configuration
TOKEN = '7593523748:AAGtmDsBVFQ1fVN2X_yKHtJphDPHJRafefY'
bot = telebot.TeleBot(TOKEN)

# SQLite database setup
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

# Create users table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                 (chat_id INTEGER PRIMARY KEY,
                  password TEXT,
                  logged_in BOOLEAN,
                  predictions_count INTEGER DEFAULT 0)''')

# Create admins table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS admins
                 (chat_id INTEGER PRIMARY KEY,
                  username TEXT)''')
conn.commit()

# Ensure predictions_count column exists in users table
cursor.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cursor.fetchall()]
if "predictions_count" not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN predictions_count INTEGER DEFAULT 0")
    conn.commit()

# State management
user_states = {}
login_attempts = {}

# TensorFlow model setup (retained for potential future use)
model = tf.keras.models.Sequential([
    tf.keras.layers.Conv2D(32, (3, 3), activation='relu', input_shape=(200, 200, 3)),
    tf.keras.layers.MaxPooling2D(2, 2),
    tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),
    tf.keras.layers.MaxPooling2D(2, 2),
    tf.keras.layers.Flatten(),
    tf.keras.layers.Dense(128, activation='relu'),
    tf.keras.layers.Dense(1, activation='sigmoid')
])
model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
model.load_weights('best_weights.h5')

# Password handling
def hash_password(password):
    salt = secrets.token_hex(8)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{hashed}"

def check_password(hashed_password, user_password):
    salt, hashed = hashed_password.split(':')
    return hashed == hashlib.sha256((user_password + salt).encode()).hexdigest()

# Admin check
def is_admin(chat_id):
    cursor.execute("SELECT * FROM admins WHERE chat_id=?", (chat_id,))
    return cursor.fetchone() is not None

# Keyboards
def create_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('/register'), types.KeyboardButton('/login'))
    markup.row(types.KeyboardButton('/predict'), types.KeyboardButton('/logout'))
    markup.row(types.KeyboardButton('/user_info'))
    return markup

def create_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('/list_users'), types.KeyboardButton('/delete_user'))
    markup.row(types.KeyboardButton('/add_admin'), types.KeyboardButton('/admin_exit'))
    return markup

# Command handlers
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    # Auto-assign first user as admin if no admins exist
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO admins VALUES (?, ?)", 
                      (chat_id, message.from_user.username or str(chat_id)))
        conn.commit()
        bot.send_message(chat_id, "👑 Вы стали первым администратором!")
    
    welcome_message = (
        "Привет! Я бот для распознавания панд и людей 🐼👤.\n"
        "Команды:\n"
        "/register — регистрация\n"
        "/login — вход\n"
        "/predict — вывод приветствия\n"
        "/user_info — информация о пользователе\n"
        "/logout — выход\n"
        "Админы могут использовать /admin_help для дополнительных команд."
    )
    bot.send_message(chat_id, welcome_message, reply_markup=create_main_keyboard())

@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "🚫 Доступ запрещён. Эта команда только для администраторов.")
        return

    admin_commands = """
🛠 <b>Команды администратора:</b>

/admin_help — список команд
/list_users — список пользователей
/add_admin <code>chat_id</code> — назначить админа
/remove_admin <code>chat_id</code> — снять админа
/list_admins — список админов
/delete_user <code>chat_id</code> — удалить пользователя
/send_all <code>текст</code> — рассылка всем пользователям
"""
    bot.send_message(chat_id, admin_commands, parse_mode="HTML", reply_markup=create_admin_keyboard())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    bot.send_message(chat_id, "Панель администратора:", reply_markup=create_admin_keyboard())

@bot.message_handler(commands=['admin_exit'])
def admin_exit(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    bot.send_message(chat_id, "Выход из панели администратора.", reply_markup=create_main_keyboard())

@bot.message_handler(commands=['list_users'])
def list_users(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    cursor.execute('''SELECT u.chat_id, u.logged_in, u.predictions_count, 
                      a.chat_id IS NOT NULL as is_admin 
                      FROM users u LEFT JOIN admins a ON u.chat_id = a.chat_id''')
    users = cursor.fetchall()
    if not users:
        bot.send_message(chat_id, "Нет зарегистрированных пользователей.")
        return
    
    response = "📊 Список пользователей:\n\n"
    for user in users:
        status = "✅ В сети" if user[1] else "❌ Не в сети"
        role = "👑 Админ" if user[3] else "👤 Пользователь"
        response += f"ID: {user[0]}\n{status} | {role}\nПредсказаний: {user[2]}\n\n"
    bot.send_message(chat_id, response)

@bot.message_handler(commands=['delete_user'])
def delete_user(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    user_states[chat_id] = 'awaiting_user_id_for_deletion'
    bot.send_message(chat_id, "Введите ID пользователя для удаления:")

@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    user_states[chat_id] = 'awaiting_admin_id'
    bot.send_message(chat_id, "Введите ID пользователя для назначения администратором:")

@bot.message_handler(commands=['remove_admin'])
def remove_admin(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    user_states[chat_id] = 'awaiting_admin_id_for_removal'
    bot.send_message(chat_id, "Введите ID администратора для снятия прав:")

@bot.message_handler(commands=['list_admins'])
def list_admins(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    cursor.execute("SELECT chat_id, username FROM admins")
    admins = cursor.fetchall()
    if not admins:
        bot.send_message(chat_id, "Нет администраторов.")
        return
    response = "👑 Список администраторов:\n\n"
    for admin in admins:
        response += f"ID: {admin[0]} | Имя: {admin[1] or 'Не указано'}\n"
    bot.send_message(chat_id, response)

@bot.message_handler(commands=['send_all'])
def send_all(message):
    chat_id = message.chat.id
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ У вас нет прав администратора!")
        return
    user_states[chat_id] = 'awaiting_broadcast_message'
    bot.send_message(chat_id, "Введите сообщение для рассылки всем пользователям:")

@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if cursor.fetchone():
        bot.send_message(chat_id, "Вы уже зарегистрированы! Используйте /login.")
        return
    user_states[chat_id] = 'registering'
    bot.send_message(chat_id, "Введите пароль для регистрации:")

@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone():
        bot.send_message(chat_id, "Сначала зарегистрируйтесь через /register!")
        return
    if chat_id in login_attempts and login_attempts[chat_id]['attempts'] >= 3:
        if datetime.now() < login_attempts[chat_id]['block_time']:
            remaining = (login_attempts[chat_id]['block_time'] - datetime.now()).seconds // 60
            bot.send_message(chat_id, f"🔒 Слишком много попыток. Подождите {remaining} минут.")
            return
    user_states[chat_id] = 'logging_in'
    bot.send_message(chat_id, "Введите пароль для входа:")

@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    cursor.execute("UPDATE users SET logged_in=0 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "Вы вышли из системы.", reply_markup=create_main_keyboard())

@bot.message_handler(commands=['predict'])
def predict_command(message):
    chat_id = message.chat.id
    cursor.execute("SELECT logged_in FROM users WHERE chat_id=?", (chat_id,))
    result = cursor.fetchone()
    if not result:
        bot.send_message(chat_id, "Сначала зарегистрируйтесь через /register!")
        return
    if not result[0]:
        bot.send_message(chat_id, "Сначала выполните /login!")
        return
    # Increment predictions_count
    cursor.execute("UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    bot.send_message(chat_id, "привет")

@bot.message_handler(commands=['user_info'])
def user_info(message):
    chat_id = message.chat.id
    cursor.execute("SELECT logged_in, predictions_count FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        bot.send_message(chat_id, "Сначала зарегистрируйтесь через /register!")
        return
    status = "✅ В сети" if user[0] else "❌ Не в сети"
    is_admin_status = "👑 Админ" if is_admin(chat_id) else "👤 Пользователь"
    response = (
        f"📋 Информация о пользователе:\n\n"
        f"ID: {chat_id}\n"
        f"Статус: {status}\n"
        f"Роль: {is_admin_status}\n"
        f"Предсказаний: {user[1]}"
    )
    bot.send_message(chat_id, response, reply_markup=create_main_keyboard())

# Text handler
@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(chat_id)

    if state == 'registering':
        hashed_password = hash_password(text)
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?)", 
                       (chat_id, hashed_password, False, 0))
        conn.commit()
        user_states.pop(chat_id, None)
        bot.send_message(chat_id, "✅ Регистрация успешна! Используйте /login.")

    elif state == 'logging_in':
        cursor.execute("SELECT password FROM users WHERE chat_id=?", (chat_id,))
        result = cursor.fetchone()
        if result and check_password(result[0], text):
            cursor.execute("UPDATE users SET logged_in=1 WHERE chat_id=?", (chat_id,))
            conn.commit()
            login_attempts.pop(chat_id, None)
            bot.send_message(chat_id, "🔓 Вход выполнен успешно! Используйте /predict.")
        else:
            login_attempts.setdefault(chat_id, {'attempts': 0, 'block_time': datetime.now()})
            login_attempts[chat_id]['attempts'] += 1
            if login_tasks[chat_id]['attempts'] >= 3:
                login_attempts[chat_id]['block_time'] = datetime.now() + timedelta(minutes=5)
            remaining_attempts = 3 - login_attempts[chat_id]['attempts']
            bot.send_message(chat_id, f"❌ Неверный пароль. Осталось попыток: {remaining_attempts}")
        user_states.pop(chat_id, None)

    elif state == 'awaiting_user_id_for_deletion':
        if not is_admin(chat_id):
            bot.send_message(chat_id, "❌ У вас нет прав администратора!")
            user_states.pop(chat_id, None)
            return
        try:
            user_id = int(text)
            if user_id == chat_id:
                bot.send_message(chat_id, "❌ Нельзя удалить самого себя!")
            else:
                cursor.execute("DELETE FROM users WHERE chat_id=?", (user_id,))
                cursor.execute("DELETE FROM admins WHERE chat_id=?", (user_id,))
                conn.commit()
                bot.send_message(chat_id, f"✅ Пользователь {user_id} удалён.")
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат ID. Введите число.")
        finally:
            user_states.pop(chat_id, None)

    elif state == 'awaiting_admin_id':
        if not is_admin(chat_id):
            bot.send_message(chat_id, "❌ У вас нет прав администратора!")
            user_states.pop(chat_id, None)
            return
        try:
            new_admin_id = int(text)
            cursor.execute("SELECT * FROM users WHERE chat_id=?", (new_admin_id,))
            if not cursor.fetchone():
                bot.send_message(chat_id, "❌ Пользователь не найден. Он должен зарегистрироваться.")
            else:
                cursor.execute("INSERT OR IGNORE INTO admins VALUES (?, ?)", 
                               (new_admin_id, f"admin_{new_admin_id}"))
                conn.commit()
                bot.send_message(chat_id, f"✅ Пользователь {new_admin_id} теперь администратор.")
                bot.send_message(new_admin_id, "👑 Вас назначили администратором!")
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат ID. Введите число.")
        finally:
            user_states.pop(chat_id, None)

    elif state == 'awaiting_admin_id_for_removal':
        if not is_admin(chat_id):
            bot.send_message(chat_id, "❌ У вас нет прав администратора!")
            user_states.pop(chat_id, None)
            return
        try:
            admin_id = int(text)
            if admin_id == chat_id:
                bot.send_message(chat_id, "❌ Нельзя снять права с самого себя!")
            else:
                cursor.execute("DELETE FROM admins WHERE chat_id=?", (admin_id,))
                conn.commit()
                bot.send_message(chat_id, f"✅ Пользователь {admin_id} больше не администратор.")
                bot.send_message(admin_id, "❌ Ваши права администратора были сняты.")
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат ID. Введите число.")
        finally:
            user_states.pop(chat_id, None)

    elif state == 'awaiting_broadcast_message':
        if not is_admin(chat_id):
            bot.send_message(chat_id, "❌ У вас нет прав администратора!")
            user_states.pop(chat_id, None)
            return
        cursor.execute("SELECT chat_id FROM users")
        users = cursor.fetchall()
        for user in users:
            try:
                bot.send_message(user[0], f"📢 Сообщение от админа: {text}")
            except:
                continue
        bot.send_message(chat_id, "✅ Сообщение отправлено всем пользователям.")
        user_states.pop(chat_id, None)

# Photo handler (retained for potential future use)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    cursor.execute("SELECT logged_in FROM users WHERE chat_id=?", (chat_id,))
    result = cursor.fetchone()
    if not result or not result[0]:
        bot.send_message(chat_id, "Сначала выполните вход через /login.")
        return

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    img_path = f"temp_{chat_id}.jpg"
    with open(img_path, 'wb') as f:
        f.write(downloaded_file)

    try:
        prediction, confidence = predict_image(img_path)
        cursor.execute("UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, f"🔍 На изображении: {prediction} (вероятность: {confidence:.2f}%)")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка при распознавании: {str(e)}")
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)

# Prediction function (retained for potential future use)
def predict_image(img_path):
    img = image.load_img(img_path, target_size=(200, 200))
    x = image.img_to_array(img)
    x = np.expand_dims(x, axis=0) / 255.0
    prediction = model.predict(x)
    return ("панда 🐼", (1 - prediction[0][0]) * 100) if prediction[0] < 0.5 else ("человек 👤", prediction[0][0] * 100)

# Start bot
bot.polling(none_stop=True)