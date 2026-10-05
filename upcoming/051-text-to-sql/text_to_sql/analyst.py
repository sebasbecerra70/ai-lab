"""Question -> grounded prompt -> SQL -> guard -> execute (retry once on DB error) -> plain-English explanation."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .guard import GuardError, ReadOnlyDB
from .llm import LLMClient
from .schema import link, render

SQL_SYSTEM = (
    "You translate business questions into a single SQLite SELECT statement. Use only the tables and columns in "
    "the schema. Revenue = SUM(qty * unit_price) over shipped orders unless the question says otherwise. "
    "Return only the SQL in a ```sql block. Never modify data."
)
EXPLAIN_SYSTEM = (
    "Explain the query result to a business user in one or two sentences. Use only numbers that appear in "
    "the result. Do not speculate about causes."
)


@dataclass
class Answer:
    question: str
    status: str                       # ok | blocked | error
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    explanation: str = ""
    tables: list[str] = field(default_factory=list)
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


class Analyst:
    def __init__(self, db: ReadOnlyDB, llm: LLMClient, max_attempts: int = 2):
        self.db, self.llm, self.max_attempts = db, llm, max_attempts
        self.tables = db.tables

    def ask(self, question: str) -> Answer:
        names = link(question, self.tables)
        ans = Answer(question, "error", tables=names)
        prompt = f"SCHEMA:\n{render(self.tables, names)}\n\nQUESTION: {question}"
        for attempt in range(1, self.max_attempts + 1):
            ans.attempts = attempt
            ans.sql = extract_sql(self.llm.complete(SQL_SYSTEM, prompt))
            try:
                ans.columns, ans.rows = self.db.query(ans.sql)
            except GuardError as e:
                # never retry a blocked statement: a model that tried to write once gets no second chance
                ans.status, ans.errors = "blocked", ans.errors + [str(e)]
                return ans
            except sqlite3.Error as e:
                ans.errors.append(str(e))
                prompt += f"\n\nPREVIOUS SQL:\n{ans.sql}\nERROR: {e}\nFix the query."
                continue
            ans.status = "ok"
            ans.explanation = self.explain(ans)
            return ans
        return ans

    def explain(self, ans: Answer) -> str:
        body = [f"QUESTION: {ans.question}", "RESULT:", "COLUMNS: " + " | ".join(ans.columns)]
        body += ["ROW: " + " | ".join(_fmt(v) for v in r) for r in ans.rows[:20]]
        return self.llm.complete(EXPLAIN_SYSTEM, "\n".join(body))


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)
