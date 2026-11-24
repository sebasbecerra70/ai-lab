"""Read-only guard, three layers deep: static SQL checks, PRAGMA query_only, and a SQLite authorizer."""
from __future__ import annotations

import re
import sqlite3

from .schema import describe

FORBIDDEN = {"insert", "update", "delete", "drop", "alter", "create", "replace", "attach", "detach", "pragma",
             "vacuum", "reindex", "trigger", "upsert", "grant", "truncate"}
# SQLITE_RECURSIVE (33) lets recursive CTEs run; older Pythons don't export the constant.
ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
ROW_LIMIT = 200


class GuardError(Exception):
    pass


def _strip_literals_and_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str) -> str:
    """Return a safe, single SELECT with a row limit, or raise GuardError explaining why not."""
    sql = sql.strip().rstrip(";").strip()
    bare = _strip_literals_and_comments(sql).lower()
    if not bare.strip():
        raise GuardError("empty query")
    if ";" in bare:
        raise GuardError("multiple statements are not allowed")
    first = bare.split()[0]
    if first not in ("select", "with"):
        raise GuardError(f"only SELECT queries are allowed, got {first.upper()}")
    bad = sorted(FORBIDDEN & set(re.findall(r"[a-z_]+", bare)))
    if bad:
        raise GuardError(f"forbidden keyword(s): {', '.join(b.upper() for b in bad)}")
    if not re.search(r"\blimit\s+\d+\s*$", bare):
        sql = f"{sql}\nLIMIT {ROW_LIMIT}"
    return sql


def _authorizer(action, arg1, arg2, db, trigger):
    return sqlite3.SQLITE_OK if action in ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


class ReadOnlyDB:
    """Wraps a connection so it refuses writes whatever SQL reaches it, and aborts runaway queries."""

    def __init__(self, conn: sqlite3.Connection, max_steps: int = 2_000_000):
        self.conn, self.max_steps, self._steps = conn, max_steps, 0
        self.tables = describe(conn)  # introspection uses PRAGMA, so it happens before the lock
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_authorizer)
        conn.set_progress_handler(self._tick, 1000)

    def _tick(self) -> int:
        self._steps += 1000
        return 1 if self._steps > self.max_steps else 0  # non-zero aborts the statement

    def query(self, sql: str) -> tuple[list[str], list[tuple]]:
        self._steps = 0
        cur = self.conn.execute(check_sql(sql))
        return [d[0] for d in cur.description], cur.fetchall()
