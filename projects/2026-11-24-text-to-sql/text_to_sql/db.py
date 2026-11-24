"""Build the sample database: load the seed script into memory, then hand out a read-only wrapper."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .guard import ReadOnlyDB

DATA = Path(__file__).resolve().parent.parent / "data"


def connect(seed: Path = DATA / "sales.sql") -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(seed.read_text())
    return conn


def read_only(seed: Path = DATA / "sales.sql") -> ReadOnlyDB:
    return ReadOnlyDB(connect(seed))
