import os
import sqlite3
import hashlib
import logging
import threading
import datetime
import io
import csv

from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# --------------------- Настройка логирования ---------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------- Конфигурация ---------------------
TOKEN = os.environ.get('8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw')
WEBHOOK_URL = os.environ.get('https://lab4-telegram-bot.onrender.com')  # укажи в env

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения.")

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL не указан. Убедитесь, что установите вебхук вручную или задайте WEBHOOK_URL.")

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# --------------------- База данных ---------------------
db_dir = os.environ.get('BOT_DB_DIR', '/opt/render/project/src/data')
os.makedirs(db_dir, exist_ok=True)
DB_PATH = os.path.join(db_dir, 'bot.db')

# Для многопоточности: один connection с check_same_thread=False + lock
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
db_lock = threading.Lock()

def init_db():
    with db_lock:
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS users(
            chat_id INTEGER PRIMARY KEY,
            password_hash TEXT,
            salt TEXT,
            iterations INTEGER,
            is_logged INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            predictions_count INTEGER DEFAULT 0,
            created_at TEXT,
            last_login TEXT
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS admin_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            timestamp TEXT
        )
        ''')
        conn.commit()
        logger.info("DB initialized at %s", DB_PATH)

init_db()

# --------------------- Безопасное хеширование пароля ---------------------
def _gen_salt(nbytes=16):
    return os.urandom(nbytes)

def hash_password_pbkdf2(password: str, salt: bytes = None, iterations: int = 200_000):
    if salt is None:
        salt = _gen_salt()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return dk.hex(), salt.hex(), iterations

def verify_password_pbkdf2(password: str, stored_hash_hex: str, salt_hex: str, iterations: int):
    if salt_hex and iterations:
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return dk.hex() == stored_hash_hex
    # fallback: legacy sha256 without salt
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash_hex

# --------------------- Вспомогательные функции работы с БД ---------------------
def get_user_row(chat_id):
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
        return cur.fetchone()

def is_registered(chat_id):
    return get_user_row(chat_id) is not None

def is_logged_in(chat_id):
    row = get_user_row(chat_id)
    return bool(row and row['is_logged'] == 1)

def is_admin(chat_id):
    row = get_user_row(chat_id)
    return bool(row and row['is_admin'] == 1)

def get_user_count():
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        return cur.fetchone()['cnt']

def count_admins():
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users WHERE is_admin=1")
        return cur.fetchone()['cnt']

def log_admin_action(admin_id, action, target_id=None):
    ts = datetime.datetime.utcnow().isoformat()
    with db_lock:
        cur = conn.cursor()
        cur.execute("INSERT INTO admin_actions(admin_id, action, target_id, timestamp) VALUES (?,?,?,?)",
                    (admin_id, action, target_id, ts))
        conn.commit()

# --------------------- Команды ---------------------
def build_main_markup(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("/register"))
    markup.add(KeyboardButton("/login"))
    markup.add(KeyboardButton("/predict"))
    markup.add(KeyboardButton("/logout"))
    markup.add(KeyboardButton("/help"))
    if is_admin(chat_id):
        markup.add(KeyboardButton("/admin_help"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    logger.info(f"/start from {chat_id}")
    markup = build_main_markup(chat_id)
    if not is_registered(chat_id):
        user_count = get_user_count()
        if user_count == 0:
            bot.send_message(chat_id, "Ты первый пользователь. Зарегистрируйся — станешь администратором.", reply_markup=markup)
        else:
            bot.send_message(chat_id, "Ты не зарегистрирован. Используй /register.", reply_markup=markup)
    else:
        bot.send_message(chat_id, "Привет! Выбери команду:", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    help_text = (
        "/register — регистрация\n"
        "/login — вход\n"
        "/predict — тест классификатора (заглушка)\n"
        "/logout — выход\n"
        "/admin_help — команды администратора (только для админов)\n"
    )
    bot.send_message(chat_id, help_text)

# ---------- Регистрация ----------
@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    logger.info(f"/register from {chat_id}")
    if is_registered(chat_id):
        bot.send_message(chat_id, "Ты уже зарегистрирован.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите пароль для регистрации (минимум 8 символов):")
    bot.register_next_step_handler(msg, finish_register)

def finish_register(message):
    chat_id = message.chat.id
    try:
        if not message.text:
            bot.send_message(chat_id, "Пароль не введён. Попробуй снова /register.")
            return
        password = message.text.strip()
        if len(password) < 8:
            bot.send_message(chat_id, "Пароль слишком короткий (минимум 8 символов). Попробуй снова /register.")
            return
        # безопасное хеширование
        pwd_hash, salt_hex, iters = hash_password_pbkdf2(password)
        created_at = datetime.datetime.utcnow().isoformat()
        is_admin_val = 1 if get_user_count() == 0 else 0
        with db_lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users(chat_id, password_hash, salt, iterations, is_logged, is_admin, created_at, last_login) VALUES (?,?,?,?,?,?,?,?)",
                (chat_id, pwd_hash, salt_hex, iters, 1, is_admin_val, created_at, created_at)
            )
            conn.commit()
        logger.info(f"User {chat_id} registered; admin={is_admin_val}")
        if is_admin_val:
            bot.send_message(chat_id, "Регистрация успешна! Ты первый пользователь и назначен администратором. Ты автоматически вошёл.")
            log_admin_action(chat_id, "auto_assign_first_admin", chat_id)
        else:
            bot.send_message(chat_id, "Регистрация успешна! Теперь ты вошёл в систему.")
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "Пользователь уже существует.")
        logger.warning(f"IntegrityError при регистрации {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка регистрации {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при регистрации. Попробуй позже.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

# ---------- Вход ----------
@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    logger.info(f"/login from {chat_id}")
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
            return
        password = message.text
        with db_lock:
            cur = conn.cursor()
            cur.execute("SELECT password_hash, salt, iterations FROM users WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "Пользователь не найден.")
            return
        stored_hash = row['password_hash']
        salt = row['salt']
        iterations = row['iterations'] if row['iterations'] else None
        if verify_password_pbkdf2(password, stored_hash, salt, iterations):
            with db_lock:
                cur = conn.cursor()
                cur.execute("UPDATE users SET is_logged=1, last_login=? WHERE chat_id=?", (datetime.datetime.utcnow().isoformat(), chat_id))
                conn.commit()
            bot.send_message(chat_id, "Успешный вход!")
            logger.info(f"User {chat_id} logged in")
        else:
            bot.send_message(chat_id, "Неверный пароль.")
            logger.info(f"Failed login for {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при входе {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при входе. Попробуй позже.")
    finally:
        bot.clear_step_handler_by_chat_id(chat_id)

# ---------- Выход ----------
@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    logger.info(f"/logout from {chat_id}")
    if is_logged_in(chat_id):
        with db_lock:
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_logged=0 WHERE chat_id=?", (chat_id,))
            conn.commit()
        bot.send_message(chat_id, "Вы вышли из системы.")
    else:
        bot.send_message(chat_id, "Ты не авторизован.")

# ---------- Predict ----------
@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    logger.info(f"/predict from {chat_id}")
    if is_logged_in(chat_id):
        with db_lock:
            cur = conn.cursor()
            cur.execute("UPDATE users SET predictions_count=predictions_count+1 WHERE chat_id=?", (chat_id,))
            conn.commit()
        bot.send_message(chat_id, "Все работает!")
    else:
        bot.send_message(chat_id, "Сначала войдите через /login.")

# --------------------- Админские команды ---------------------
@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    chat_id = message.chat.id
    logger.info(f"/admin_help from {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/view_users"))
    markup.add(KeyboardButton("/export_users"))
    markup.add(KeyboardButton("/delete_user"))
    markup.add(KeyboardButton("/add_admin"))
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(commands=['view_users'])
def view_users(message):
    chat_id = message.chat.id
    logger.info(f"/view_users from {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    try:
        with db_lock:
            cur = conn.cursor()
            cur.execute("SELECT chat_id, is_admin, predictions_count, created_at, last_login FROM users")
            users = cur.fetchall()
        if not users:
            bot.send_message(chat_id, "Пользователей нет.")
            return
        lines = ["Пользователи:"]
        for u in users:
            lines.append(f"ID: {u['chat_id']}, admin: {u['is_admin']}, preds: {u['predictions_count']}, created: {u['created_at']}, last_login: {u['last_login']}")
        bot.send_message(chat_id, "\n".join(lines))
    except Exception as e:
        logger.error(f"Ошибка view_users by {chat_id}: {e}")
        bot.send_message(chat_id, "Произошла ошибка при просмотре пользователей.")

@bot.message_handler(commands=['export_users'])
def export_users(message):
    chat_id = message.chat.id
    logger.info(f"/export_users from {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    try:
        with db_lock:
            cur = conn.cursor()
            cur.execute("SELECT chat_id, is_admin, predictions_count, created_at, last_login FROM users")
            users = cur.fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["chat_id", "is_admin", "predictions_count", "created_at", "last_login"])
        for u in users:
            writer.writerow([u['chat_id'], u['is_admin'], u['predictions_count'], u['created_at'], u['last_login']])
        output.seek(0)
        bio = io.BytesIO(output.read().encode('utf-8'))
        bio.name = 'users_export.csv'
        bot.send_document(chat_id, bio)
        logger.info(f"Users exported by admin {chat_id}")
    except Exception as e:
        logger.error(f"Error exporting users by {chat_id}: {e}")
        bot.send_message(chat_id, "Ошибка при экспорте пользователей.")

# ---------- Удаление пользователя: двухшаговое подтверждение ----------
_pending_delete = {}  # admin_chat_id -> target_id (temp store for confirmation)

@bot.message_handler(commands=['delete_user'])
def delete_user(message):
    chat_id = message.chat.id
    logger.info(f"/delete_user from {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите chat_id пользователя для удаления:")
    bot.register_next_step_handler(msg, finish_delete_user_step1)

def finish_delete_user_step1(message):
    admin_id = message.chat.id
    try:
        text = message.text.strip()
        target_id = int(text)
        if target_id == admin_id:
            bot.send_message(admin_id, "Нельзя удалить самого себя.")
            return
        row = get_user_row(target_id)
        if not row:
            bot.send_message(admin_id, f"Пользователь {target_id} не найден.")
            return
        if row['is_admin'] == 1:
            bot.send_message(admin_id, "Нельзя удалить другого администратора.")
            return
        # ask for confirmation
        _pending_delete[admin_id] = target_id
        msg = bot.send_message(admin_id, f"Подтвердите удаление пользователя {target_id}. Введите 'YES' для подтверждения или 'NO' для отмены:")
        bot.register_next_step_handler(msg, finish_delete_user_step2)
    except ValueError:
        bot.send_message(admin_id, "Неверный chat_id. Должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка delete_user step1 by {admin_id}: {e}")
        bot.send_message(admin_id, "Произошла ошибка. Попробуй снова.")
    finally:
        pass

def finish_delete_user_step2(message):
    admin_id = message.chat.id
    try:
        ans = message.text.strip().upper()
        target_id = _pending_delete.pop(admin_id, None)
        if target_id is None:
            bot.send_message(admin_id, "Нет ожидаемой операции удаления.")
            return
        if ans == 'YES':
            with db_lock:
                cur = conn.cursor()
                cur.execute("DELETE FROM users WHERE chat_id=?", (target_id,))
                deleted = cur.rowcount
                conn.commit()
            if deleted:
                bot.send_message(admin_id, f"Пользователь {target_id} удалён.")
                log_admin_action(admin_id, "delete_user", target_id)
                logger.info(f"Admin {admin_id} deleted user {target_id}")
            else:
                bot.send_message(admin_id, f"Пользователь {target_id} не найден или уже удалён.")
        else:
            bot.send_message(admin_id, "Удаление отменено.")
    except Exception as e:
        logger.error(f"Ошибка delete_user step2 by {admin_id}: {e}")
        bot.send_message(admin_id, "Произошла ошибка при удалении.")
    finally:
        bot.clear_step_handler_by_chat_id(admin_id)

# ---------- Назначение администратора ----------
@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    chat_id = message.chat.id
    logger.info(f"/add_admin from {chat_id}")
    if not is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    bot.clear_step_handler_by_chat_id(chat_id)
    msg = bot.send_message(chat_id, "Введите chat_id пользователя, которого нужно сделать администратором:")
    bot.register_next_step_handler(msg, finish_add_admin)

def finish_add_admin(message):
    admin_id = message.chat.id
    try:
        target_id = int(message.text.strip())
        if not is_registered(target_id):
            bot.send_message(admin_id, "Пользователь не зарегистрирован.")
            return
        with db_lock:
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (target_id,))
            conn.commit()
        bot.send_message(admin_id, f"Пользователь {target_id} теперь администратор.")
        log_admin_action(admin_id, "add_admin", target_id)
        logger.info(f"Admin {admin_id} promoted {target_id}")
    except ValueError:
        bot.send_message(admin_id, "Неверный chat_id. Должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка add_admin by {admin_id}: {e}")
        bot.send_message(admin_id, "Произошла ошибка при назначении администратора.")
    finally:
        bot.clear_step_handler_by_chat_id(admin_id)

# --------------------- Webhook ---------------------
@app.route('/', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return '', 500

@app.route('/', methods=['GET'])
def index():
    return "Бот работает (webhook)", 200

# --------------------- Запуск ---------------------
if __name__ == '__main__':
    try:
        bot.remove_webhook()
        if WEBHOOK_URL:
            bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook установлен на {WEBHOOK_URL}")
        else:
            logger.warning("WEBHOOK_URL не указан — webhook не установлен автоматически.")
        port = int(os.environ.get('PORT', 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
