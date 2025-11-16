from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Optional

from app.database.connection import get_connection


PASSWORD_SALT = "hr-agent-salt"


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{PASSWORD_SALT}:{password}".encode("utf-8")).hexdigest()


def create_user(name: str, email: str, password: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ?", (normalized_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Пользователь уже зарегистрирован.")
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (name.strip(), normalized_email, hash_password(password), datetime.utcnow().isoformat()),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return int(user_id)


def get_user_by_email(email: str) -> Optional[Dict[str, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def update_user_profile(user_id: int, *, name: str, email: str, new_password: Optional[str]) -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ? AND id <> ?", (normalized_email, user_id))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Эта почта уже используется.")
    fields = ["name = ?", "email = ?"]
    params = [name.strip(), normalized_email]
    if new_password:
        fields.append("password_hash = ?")
        params.append(hash_password(new_password))
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated
