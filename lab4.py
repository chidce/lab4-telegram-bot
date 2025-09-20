import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request
import sqlite3
import hashlib
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен указан напрямую
TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"
WEBHOOK_URL = "https://lab4-telegram-bot.onrender.com"

# Проверка токена
if not TOKEN or len(TOKEN.strip()) == 0:
    raise ValueError("Ошибка: Токен бота не указан или пустой.")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --------------------- База данных ---------------------
try:
    # Для persistent disk на Render
    db_dir = '/opt/render/project/src/data'
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(db_dir, 'bot.db'), check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
        chat_id INTEGER PRIMARY KEY,
        password_hash TEXT,
        is_logged INTEGER,
        is_admin INTEGER,
        predictions_count INTEGER DEFAULT 0
    )
    ''')
    conn.commit()
    logger.info("База данных инициализирована успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации базы данных: {e}")
    raise

# --------------------- Функции ---------------------
def is_registered(chat_id):
    try:
        cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки регистрации для chat_id {chat_id}: {e}")
        return False

def is_logged_in(chat_id):
    try:
        cursor.execute("SELECT is_logged FROM users WHERE chat_id=?", (chat_id,))
        res = cursor.fetchone()
        return res and res[0] == 1
    except Exception as e:
        logger.error(f"Ошибка проверки логина для chat_id {chat_id}: {e}")
        return False

def is_admin(chat_id):
    try:
        cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
        res = cursor.fetchone()
        return res and res[0] == 1
    except Exception as e:
        logger.error(f"Ошибка проверки админа для chat_id {chat_id}: {e}")
        return False

def get_user_count():
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Ошибка подсчёта пользователей: {e}")
        return 0

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --------------------- Команды ---------------------
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    logger.info(f"Команда /start от chat_id {chat_id}")
    
    # Создаём клавиатуру
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Добавляем все возможные команды
    markup.add(KeyboardButton("/register"))
    markup.add(KeyboardButton("/login"))
    markup.add(KeyboardButton("/predict"))
    markup.add(KeyboardButton("/logout"))
    markup.add(KeyboardButton("/help"))
    if is_admin(chat_id):
        markup.add(KeyboardButton("/admin_help"))

    if not is_registered(chat_id):
        user_count = get_user_count()
        if user_count == 0:
            bot.send_message(chat_id, "Ты первый пользователь. Зарегистрируйся, и ты станешь администратором.", reply_markup=markup)
        else:
            bot.send_message(chat_id, "Ты не зарегистрирован. Используй /register.", reply_markup=markup)
    else:
        bot.send_message(chat_id, "Привет! Выбери команду:", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    logger.info(f"Команда /help от chat_id {chat_id}")
    help_text = ("/register – регистрация\n"
                 "/login – вход\n"
                 "/predict – тест классификатора (заглушка)\n"
                 "/logout – выход\n"
                 "/admin_help – команды администратора")
    bot.send_message(chat_id, help_text)

@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    logger.info(f"Команда /register от chat_id {chat_id}")
    if is_registered(chat_id):
        bot.send_message(chat_id, "Ты уже зарегистрирован.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите пароль для регистрации (минимум 6 символов):")
    bot.register_next_step_handler(msg, finish_register)

def finish_register(message):
    chat_id = message.chat.id
    try:
        if not message.text:
            bot.send_message(chat_id, "Пароль не введён. Попробуй снова /register.")
            logger.warning(f"Пустой пароль от chat_id {chat_id}")
            return
        password = message.text.strip()
        logger.info(f"Получен пароль для регистрации от chat_id {chat_id}")
        if len(password) < 6:
            bot.send_message(chat_id, "Пароль слишком короткий. Попробуй снова /register.")
            return
        password_hash = hash_password(password)
        is_admin_val = 1 if get_user_count() == 0 else 0
        cursor.execute("INSERT INTO users(chat_id, password_hash, is_logged, is_admin) VALUES (?,?,?,?)",
                       (chat_id, password_hash, 1, is_admin_val))
        conn.commit()
        logger.info(f"Пользователь chat_id {chat_id} зарегистрирован, is_admin={is_admin_val}")
        if is_admin_val:
            bot.send_message(chat_id, "Регистрация успешна! Ты первый пользователь и назначен администратором. Теперь ты вошёл в систему.")
        else:
            bot.send_message(chat_id, "Регистрация успешна! Теперь ты вошёл в систему.")
    except Exception as e:
        logger.error(f"Ошибка при регистрации chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при регистрации. Попробуй снова /register.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    logger.info(f"Команда /login от chat_id {chat_id}")
    if not is_registered(chat_id):
        bot.send_message(chat_id, "Ты не зарегистрирован.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите пароль для входа:")
    bot.register_next_step_handler(msg, finish_login)

def finish_login(message):
    chat_id = message.chat.id
    try:
        if not message.text:
            bot.send_message(chat_id, "Пароль не введён. Попробуй снова /login.")
            logger.warning(f"Пустой пароль для входа от chat_id {chat_id}")
            return
        password = message.text
        logger.info(f"Получен пароль для входа от chat_id {chat_id}")
        password_hash = hash_password(password)
        cursor.execute("SELECT password_hash FROM users WHERE chat_id=?", (chat_id,))
        real_hash = cursor.fetchone()[0]
        if password_hash == real_hash:
            cursor.execute("UPDATE users SET is_logged=1 WHERE chat_id=?", (chat_id,))
            conn.commit()
            bot.send_message(chat_id, "Успешный вход!")
            logger.info(f"Успешный вход для chat_id {chat_id}")
        else:
            bot.send_message(chat_id, "Неверный пароль.")
            logger.info(f"Неверный пароль для chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при входе chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при входе. Попробуй снова /login.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    logger.info(f"Команда /logout от chat_id {chat_id}")
    if is_logged_in(chat_id):
        cursor.execute("UPDATE users SET is_logged=0 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Вы вышли из системы.")
        logger.info(f"Выход из системы для chat_id {chat_id}")
    else:
        bot.send_message(chat_id, "Ты не авторизован.")

@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    logger.info(f"Команда /predict от chat_id {chat_id}")
    if is_logged_in(chat_id):
        cursor.execute("UPDATE users SET predictions_count=predictions_count+1 WHERE chat_id=?", (chat_id,))
        conn.commit()
        bot.send_message(chat_id, "Все работает! (заглушка)")
        logger.info(f"Предсказание выполнено для chat_id {chat_id}")
    else:
        bot.send_message(chat_id, "Сначала войдите через /login.")

@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    chat_id = message.chat.id
    logger.info(f"Команда /admin_help от chat_id {chat_id}")
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
    logger.info(f"Команда /view_users от chat_id {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    try:
        cursor.execute("SELECT chat_id, predictions_count FROM users")
        users = cursor.fetchall()
        text = "Пользователи:\n"
        for u in users:
            text += f"ID: {u[0]}, предсказаний: {u[1]}\n"
        bot.send_message(chat_id, text)
        logger.info(f"Список пользователей отправлен для chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при просмотре пользователей для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при просмотре пользователей.")

@bot.message_handler(commands=['delete_user'])
def delete_user(message):
    chat_id = message.chat.id
    logger.info(f"Команда /delete_user от chat_id {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите chat_id пользователя для удаления:")
    bot.register_next_step_handler(msg, finish_delete_user)

def finish_delete_user(message):
    chat_id = message.chat.id
    try:
        target_id = int(message.text)
        logger.info(f"Попытка удаления пользователя {target_id} от chat_id {chat_id}")
        if target_id == chat_id:
            bot.send_message(chat_id, "Нельзя удалить самого себя.")
            return
        cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (target_id,))
        user = cursor.fetchone()
        if user and user[0] == 1:
            bot.send_message(chat_id, "Нельзя удалить другого администратора.")
            return
        cursor.execute("DELETE FROM users WHERE chat_id=?", (target_id,))
        if cursor.rowcount == 0:
            bot.send_message(chat_id, f"Пользователь {target_id} не найден.")
            return
        conn.commit()
        bot.send_message(chat_id, f"Пользователь {target_id} удалён.")
        logger.info(f"Пользователь {target_id} удалён chat_id {chat_id}")
    except ValueError:
        bot.send_message(chat_id, "Неверный chat_id. Должен быть числом.")
        logger.error(f"Неверный chat_id для удаления от {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при удалении пользователя.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    chat_id = message.chat.id
    logger.info(f"Команда /add_admin от chat_id {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите chat_id нового администратора:")
    bot.register_next_step_handler(msg, finish_add_admin)

def finish_add_admin(message):
    chat_id = message.chat.id
    try:
        target_id = int(message.text)
        logger.info(f"Попытка назначения админа {target_id} от chat_id {chat_id}")
        if not is_registered(target_id):
            bot.send_message(chat_id, "Пользователь не зарегистрирован.")
            return
        cursor.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (target_id,))
        conn.commit()
        bot.send_message(chat_id, f"Пользователь {target_id} теперь администратор.")
        logger.info(f"Пользователь {target_id} назначен админом chat_id {chat_id}")
    except ValueError:
        bot.send_message(chat_id, "Неверный chat_id. Должен быть числом.")
        logger.error(f"Неверный chat_id для назначения админа от {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при назначении админа для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при назначении администратора.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

# --------------------- Webhook ---------------------
@app.route('/', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        logger.info("Webhook обработан успешно")
        return '', 200
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return '', 500

@app.route('/')
def index():
    return "Бот работает", 200

if __name__ == '__main__':
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook установлен на {WEBHOOK_URL}")
        port = int(os.environ.get('PORT', 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise