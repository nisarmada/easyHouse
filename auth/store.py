from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


def init_accounts(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id              TEXT PRIMARY KEY,
            email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash   TEXT NOT NULL,
            verified_at     TEXT,
            alerts_enabled  INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS verification_tokens (
            token       TEXT PRIMARY KEY,
            account_id  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            account_id  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _expires_iso_minutes(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def get_account_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM accounts WHERE email = ? COLLATE NOCASE",
        (email.strip(),),
    ).fetchone()


def get_account_by_id(conn: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()


def create_account(conn: sqlite3.Connection, *, email: str, password_hash: str) -> sqlite3.Row:
    account_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO accounts (id, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (account_id, email.strip().lower(), password_hash),
    )
    conn.commit()
    row = get_account_by_id(conn, account_id)
    assert row is not None
    return row


def create_verification_code(conn: sqlite3.Connection, account_id: str, code: str) -> None:
    conn.execute("DELETE FROM verification_tokens WHERE account_id = ?", (account_id,))
    conn.execute(
        """
        INSERT INTO verification_tokens (token, account_id, expires_at)
        VALUES (?, ?, ?)
        """,
        (code, account_id, _expires_iso_minutes(15)),
    )
    conn.commit()


def consume_verification_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT vt.token, vt.account_id, vt.expires_at, a.email, a.verified_at
        FROM verification_tokens vt
        JOIN accounts a ON a.id = vt.account_id
        WHERE vt.token = ?
        """,
        (code,),
    ).fetchone()
    if row is None:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        conn.execute("DELETE FROM verification_tokens WHERE token = ?", (code,))
        conn.commit()
        return None

    conn.execute(
        "UPDATE accounts SET verified_at = ? WHERE id = ?",
        (_now_iso(), row["account_id"]),
    )
    conn.execute("DELETE FROM verification_tokens WHERE account_id = ?", (row["account_id"],))
    conn.commit()
    return get_account_by_id(conn, row["account_id"])


def create_session(conn: sqlite3.Connection, account_id: str, token: str) -> None:
    conn.execute(
        """
        INSERT INTO sessions (token, account_id, expires_at)
        VALUES (?, ?, ?)
        """,
        (token, account_id, _expires_iso(30)),
    )
    conn.commit()


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def get_session_account(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT s.token, s.expires_at, a.*
        FROM sessions s
        JOIN accounts a ON a.id = s.account_id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        delete_session(conn, token)
        return None
    return row


def set_alerts_enabled(conn: sqlite3.Connection, account_id: str, enabled: bool) -> None:
    conn.execute(
        "UPDATE accounts SET alerts_enabled = ? WHERE id = ?",
        (1 if enabled else 0, account_id),
    )
    conn.commit()


def account_to_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "email": row["email"],
        "verified": row["verified_at"] is not None,
        "alerts_enabled": bool(row["alerts_enabled"]),
    }
