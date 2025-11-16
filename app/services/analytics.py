from __future__ import annotations

from app.database.connection import get_connection


def increment_counter(key: str, amount: int = 1) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO analytics (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = value + ?
        """,
        (key, amount, amount),
    )
    conn.commit()
    conn.close()


def get_counter(key: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM analytics WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 0
