from flask import Flask, request
import telebot
import db

TOKEN = "8359451352:AAG-z6lpvX0QP18weJfBS5T7twBcS7qMoEw"  # вставь сюда свой токен
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

db.init_db()

@bot.message_handler(commands=['register'])
def register(message):
    chat_id = message.chat.id
    if db.is_logged_in(chat_id) or db.check_password(chat_id, ""):
        bot.send_message(chat_id, "Вы уже зарегистрированы.")
        return
    bot.send_message(chat_id, "Введите пароль для регистрации:")
    bot.register_next_step_handler(message, process_registration)

def process_registration(message):
    chat_id = message.chat.id
    password = message.text.strip()
    is_admin = 0
    if len(db.get_users()) == 0:
        is_admin = 1
    if db.register_user(chat_id, password, is_admin):
        bot.send_message(chat_id, "Регистрация успешна!")
    else:
        bot.send_message(chat_id, "Вы уже зарегистрированы.")

@bot.message_handler(commands=['login'])
def login(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Введите пароль для входа:")
    bot.register_next_step_handler(message, process_login)

def process_login(message):
    chat_id = message.chat.id
    password = message.text.strip()
    if db.check_password(chat_id, password):
        db.set_logged_in(chat_id, 1)
        bot.send_message(chat_id, "Вход выполнен.")
    else:
        bot.send_message(chat_id, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout(message):
    chat_id = message.chat.id
    db.set_logged_in(chat_id, 0)
    bot.send_message(chat_id, "Вы вышли из системы.")

@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    if not db.is_logged_in(chat_id):
        bot.send_message(chat_id, "Вы должны войти с помощью /login.")
        return
    db.add_prediction(chat_id)
    bot.send_message(chat_id, "Здесь было бы ваше предсказание 📷")

@bot.message_handler(commands=['admin_panel'])
def admin_panel(message):
    chat_id = message.chat.id
    if not db.is_admin(chat_id):
        bot.send_message(chat_id, "Нет доступа.")
        return
    users = db.get_users()
    text = "Пользователи:\n"
    for uid, preds, adm in users:
        text += f"ID: {uid}, Предсказаний: {preds}, Админ: {adm}\n"
    bot.send_message(chat_id, text)
    bot.send_message(chat_id, "Команды:\n/del_user ID\n/add_admin ID")

@bot.message_handler(commands=['del_user'])
def del_user_cmd(message):
    chat_id = message.chat.id
    if not db.is_admin(chat_id):
        return
    try:
        uid = int(message.text.split()[1])
        db.delete_user(uid)
        bot.send_message(chat_id, f"Пользователь {uid} удалён.")
    except:
        bot.send_message(chat_id, "Формат: /del_user ID")

@bot.message_handler(commands=['add_admin'])
def add_admin_cmd(message):
    chat_id = message.chat.id
    if not db.is_admin(chat_id):
        return
    try:
        uid = int(message.text.split()[1])
        db.make_admin(uid)
        bot.send_message(chat_id, f"Пользователь {uid} теперь админ.")
    except:
        bot.send_message(chat_id, "Формат: /add_admin ID")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200
