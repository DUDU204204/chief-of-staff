"""SQLite helpers for the Chief of Staff registry."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "registry.db"
SCHEMA_PATH = ROOT / "schema.sql"


def init_schema() -> None:
    """Create the DB and apply schema.sql if the DB doesn't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        if SCHEMA_PATH.exists():
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
    finally:
        conn.close()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn.cursor(), conn
        conn.commit()
    finally:
        conn.close()


def upsert(table: str, key_field: str, row: dict) -> None:
    """Insert or update a row keyed by `key_field`."""
    cols = list(row.keys())
    placeholders = ",".join(["?"] * len(cols))
    col_names = ",".join(cols)
    updates = ",".join([f"{c}=excluded.{c}" for c in cols if c != key_field])
    sql = (
        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT({key_field}) DO UPDATE SET {updates}, updated_at=datetime('now')"
    )
    with cursor() as (cur, _conn):
        cur.execute(sql, [row[c] for c in cols])


def log_observation(
    *,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    subject_kind: str | None = None,
    subject_slug: str | None = None,
    recommended_action: str | None = None,
    auto_fixable: bool = False,
    fix_command: str | None = None,
) -> int:
    with cursor() as (cur, _conn):
        cur.execute(
            """
            INSERT INTO observations
              (kind, severity, subject_kind, subject_slug, title, body,
               recommended_action, auto_fixable, fix_command)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (kind, severity, subject_kind, subject_slug, title, body,
             recommended_action, 1 if auto_fixable else 0, fix_command),
        )
        return cur.lastrowid


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with cursor() as (cur, _conn):
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def log_agent_message(
    *,
    from_agent: str,
    kind: str = "handoff",
    to_agent: str | None = None,
    title: str | None = None,
    body: str | None = None,
    subject_kind: str | None = None,
    subject_slug: str | None = None,
    correlation_id: str | None = None,
) -> int:
    """Record an agent-to-agent message. Used by automations + scanners to
    make collaboration visible in the office UI and in the briefing.

    `kind`: 'handoff' | 'ask' | 'escalate' | 'report' | 'standup' | 'system'
    `to_agent=None` means a broadcast/standup.
    `correlation_id` threads a handoff with its later report — pass the same
    value through both rows.
    """
    with cursor() as (cur, _conn):
        cur.execute(
            """
            INSERT INTO agent_messages
              (from_agent, to_agent, kind, title, body, subject_kind,
               subject_slug, correlation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (from_agent, to_agent, kind, title, body, subject_kind,
             subject_slug, correlation_id),
        )
        return cur.lastrowid


def recent_agent_messages(limit: int = 30) -> list[dict]:
    return query_all(
        "SELECT * FROM agent_messages ORDER BY ts DESC LIMIT ?", (limit,)
    )
