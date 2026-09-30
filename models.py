import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "data/users.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            expires_at TEXT,
            email_confirmed INTEGER DEFAULT 0,
            confirm_token TEXT,
            reset_token TEXT,
            reset_expires TEXT,
            is_admin INTEGER DEFAULT 1
        )
        """
    )
    # purchases table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            stripe_session_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@crystalsports.local"
DEFAULT_FREE_USERNAME = "freeuser"
DEFAULT_FREE_EMAIL = "freeuser@crystalsports.local"
DEFAULT_ADMIN_PASSWORD = "Admin123!"
DEFAULT_FREE_PASSWORD = "Free123!"


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            expires_at TEXT,
            email_confirmed INTEGER DEFAULT 0,
            confirm_token TEXT,
            reset_token TEXT,
            reset_expires TEXT,
            is_admin INTEGER DEFAULT 0
        )
        """
    )
    # purchases table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            stripe_session_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    _ensure_default_users()


def _ensure_default_users() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        admin_pw_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        free_pw_hash = generate_password_hash(DEFAULT_FREE_PASSWORD)
        admin_expires = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO users (username, email, password_hash, plan, expires_at, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
            (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL, admin_pw_hash, "vip", admin_expires, 1),
        )
        cur.execute(
            "INSERT INTO users (username, email, password_hash, plan, expires_at, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
            (DEFAULT_FREE_USERNAME, DEFAULT_FREE_EMAIL, free_pw_hash, "free", None, 0),
        )
        conn.commit()
    conn.close()


def create_user(username: str, email: str, password: str, plan: str = "free", days: int = 30, is_admin: bool = False) -> Dict[str, Any]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    effective_password = password or (DEFAULT_ADMIN_PASSWORD if is_admin else DEFAULT_FREE_PASSWORD)
    pw_hash = generate_password_hash(effective_password)
    expires = None
    if plan != "free":
        expires = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    is_admin_flag = 1 if is_admin else 0
    cur.execute(
        "INSERT INTO users (username, email, password_hash, plan, expires_at, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
        (username, email, pw_hash, plan, expires, is_admin_flag),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "username": username, "email": email, "plan": plan, "expires_at": expires, "is_admin": bool(is_admin_flag)}


def create_purchase(user_id: int, plan: str, amount: int, currency: str = 'usd', stripe_session_id: str | None = None) -> Dict[str, Any]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO purchases (user_id, plan, amount, currency, stripe_session_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, plan, amount, currency, stripe_session_id, created_at),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return {"id": pid, "user_id": user_id, "plan": plan, "amount": amount, "currency": currency, "stripe_session_id": stripe_session_id, "created_at": created_at}


def get_purchases_for_user(user_id: int) -> list:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_confirm_token(user_id: int, token: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET confirm_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    conn.close()


def confirm_email_by_token(token: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE confirm_token = ?", (token,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cur.execute("UPDATE users SET email_confirmed = 1, confirm_token = NULL WHERE id = ?", (row['id'],))
    conn.commit()
    conn.close()
    return dict(row)


def set_reset_token(user_id: int, token: str, expires_minutes: int = 60) -> None:
    expires = (datetime.utcnow() + timedelta(minutes=expires_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?", (token, expires, user_id))
    conn.commit()
    conn.close()


def verify_reset_token(token: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE reset_token = ?", (token,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    if row['reset_expires'] and datetime.strptime(row['reset_expires'], "%Y-%m-%d %H:%M:%S") < datetime.utcnow():
        conn.close()
        return None
    conn.close()
    return dict(row)


def reset_password(token: str, new_password: str) -> bool:
    user = verify_reset_token(token)
    if not user:
        return False
    pw_hash = generate_password_hash(new_password)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?", (pw_hash, user['id']))
    conn.commit()
    conn.close()
    return True


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def verify_user(identifier: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(identifier) if "@" in identifier else get_user_by_username(identifier)
    if not user:
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def update_subscription(user_id: int, plan: str, days: int = 30) -> None:
    conn = get_conn()
    cur = conn.cursor()
    expires = None
    if plan != "free":
        expires = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE users SET plan = ?, expires_at = ? WHERE id = ?", (plan, expires, user_id))
    conn.commit()
    conn.close()
