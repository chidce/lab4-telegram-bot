import sqlite3
import hashlib

DB_NAME = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        password_hash TEXT NOT NULL,
        logged_in INTEGER DEFAULT 0,
        predictions INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(chat_id: int, password: str, is_admin: int = 0) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (chat_id, password_hash, is_admin) VALUES (?, ?, ?)",
            (chat_id, hash_password(password), is_admin)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def check_password(chat_id: int, password: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password_hash FROM users WHERE chat_id = ?",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row and row[0] == hash_password(password)

def set_logged_in(chat_id: int, value: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET logged_in = ? WHERE chat_id = ?",
        (value, chat_id)
    )
    conn.commit()
    conn.close()

def is_logged_in(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT logged_in FROM users WHERE chat_id = ?",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])

def add_prediction(chat_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET predictions = predictions + 1 WHERE chat_id = ?",
        (chat_id,)
    )
    conn.commit()
    conn.close()

def is_admin(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_admin FROM users WHERE chat_id = ?",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])

def get_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, predictions, is_admin FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_user(chat_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def make_admin(chat_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin = 1 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
