from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "hr_agent.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resume_excerpt TEXT NOT NULL,
            vacancy_description TEXT NOT NULL,
            result_json TEXT NOT NULL,
            sources_json TEXT,
            created_at TEXT NOT NULL,
            engine TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def with_connection(func: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        conn = get_connection()
        try:
            result = func(conn, *args, **kwargs)
        finally:
            conn.close()
        return result

    return wrapper
