"""Schema grounding: introspect SQLite, pick the tables a question needs, render a compact prompt."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field


@dataclass
class Table:
    name: str
    columns: list[tuple[str, str]]
    fks: list[tuple[str, str, str]] = field(default_factory=list)   # (column, ref_table, ref_column)
    samples: dict[str, list[str]] = field(default_factory=dict)     # low-cardinality text values
    rows: int = 0

    def render(self) -> str:
        cols = ", ".join(f"{c} {t}" for c, t in self.columns)
        lines = [f"TABLE {self.name} ({cols})  -- {self.rows} rows"]
        lines += [f"  {c} -> {t}.{rc}" for c, t, rc in self.fks]
        lines += [f"  {c} values: {', '.join(v)}" for c, v in self.samples.items()]
        return "\n".join(lines)


def describe(conn: sqlite3.Connection, max_distinct: int = 6) -> dict[str, Table]:
    tables = {}
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for name in names:
        cols = [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({name})")]
        fks = [(r[3], r[2], r[4]) for r in conn.execute(f"PRAGMA foreign_key_list({name})")]
        t = Table(name, cols, fks, rows=conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        for c, typ in cols:
            if typ.upper() == "TEXT":
                vals = [r[0] for r in conn.execute(f"SELECT DISTINCT {c} FROM {name} LIMIT {max_distinct + 1}")]
                if len(vals) <= max_distinct:  # enums like region/status; names would only leak data and tokens
                    t.samples[c] = sorted(vals)
        tables[name] = t
    return tables


def _words(text: str) -> set[str]:
    ws = set(re.findall(r"[a-z0-9]+", text.lower()))
    return ws | {w[:-1] for w in ws if w.endswith("s")}


# business vocabulary -> column names, so "revenue" finds order_items without the word appearing in the schema
SYNONYMS = {"revenue": {"unit_price", "qty"}, "sales": {"unit_price", "qty"}, "units": {"qty"}, "sold": {"qty"},
            "spend": {"unit_price"}, "discount": {"list_price", "unit_price"}, "client": {"customers"}}


def link(question: str, tables: dict[str, Table]) -> list[str]:
    """Pick tables whose name, columns or enum values the question mentions, then add whatever tables sit
    on the FK path between them so the model can actually write the joins."""
    q = _words(question)
    for w in list(q):
        q |= SYNONYMS.get(w, set())
    hits = set()
    for t in tables.values():
        values = " ".join(v for vals in t.samples.values() for v in vals)
        vocab = _words(t.name) | {c for c, _ in t.columns} | _words(values)
        if q & vocab:
            hits.add(t.name)
    if not hits:
        return sorted(tables)
    graph: dict[str, set[str]] = {n: set() for n in tables}
    for t in tables.values():
        for _, ref, _ in t.fks:
            graph[t.name].add(ref)
            graph[ref].add(t.name)
    picked = set(hits)
    anchor = sorted(hits)[0]
    for target in sorted(hits):
        picked |= set(_path(graph, anchor, target))
    return sorted(picked)


def _path(graph: dict[str, set[str]], start: str, goal: str) -> list[str]:
    """Shortest FK path (BFS) between two tables."""
    prev: dict[str, str | None] = {start: None}
    frontier = [start]
    while frontier:
        nxt = []
        for node in frontier:
            for nb in sorted(graph[node]):
                if nb not in prev:
                    prev[nb] = node
                    nxt.append(nb)
        frontier = nxt
    if goal not in prev:
        return []
    path, node = [], goal
    while node is not None:
        path.append(node)
        node = prev[node]
    return path


def render(tables: dict[str, Table], names: list[str]) -> str:
    return "\n".join(tables[n].render() for n in names)
