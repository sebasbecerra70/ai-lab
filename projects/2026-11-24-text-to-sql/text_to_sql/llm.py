"""LLM client interface: a scripted mock for tests, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


REVENUE = "SUM(oi.qty * oi.unit_price)"
SQL_SCRIPT = [
    # (question pattern, first attempt, attempt after an error)
    (r"top \d+ customers by revenue",
     f"SELECT c.name, ROUND({REVENUE}, 0) AS revenue FROM customers c JOIN orders o ON o.customer_id = c.id "
     f"JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'shipped' GROUP BY c.name ORDER BY revenue DESC LIMIT 5", None),
    (r"revenue by region",
     # first draft assumes orders has a region column: a classic schema hallucination
     f"SELECT o.region, ROUND({REVENUE}, 0) AS revenue FROM orders o JOIN order_items oi ON oi.order_id = o.id "
     f"WHERE o.status = 'shipped' GROUP BY o.region ORDER BY revenue DESC",
     f"SELECT c.region, ROUND({REVENUE}, 0) AS revenue FROM customers c JOIN orders o ON o.customer_id = c.id "
     f"JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'shipped' GROUP BY c.region ORDER BY revenue DESC"),
    (r"category .*units|units .*category",
     "SELECT p.category, SUM(oi.qty) AS units FROM products p JOIN order_items oi ON oi.product_id = p.id "
     "JOIN orders o ON o.id = oi.order_id WHERE o.quarter = 'Q4' AND o.status != 'cancelled' "
     "GROUP BY p.category ORDER BY units DESC", None),
    (r"discount",
     "SELECT c.segment, ROUND(100 * (1 - SUM(oi.qty * oi.unit_price) / SUM(oi.qty * p.list_price)), 1) AS discount_pct "
     "FROM customers c JOIN orders o ON o.customer_id = c.id JOIN order_items oi ON oi.order_id = o.id "
     "JOIN products p ON p.id = oi.product_id GROUP BY c.segment ORDER BY discount_pct DESC", None),
    (r"cancel(l)?ed orders.*(delete|remove)|(delete|remove).*cancel", "DELETE FROM orders WHERE status = 'cancelled'", None),
    (r"ignore (all )?previous", "SELECT 1; DROP TABLE orders", None),
]


class MockLLM:
    """Plays both roles: writes SQL from a script keyed on the question, and explains result tables."""

    def complete(self, system: str, prompt: str) -> str:
        if "RESULT:" in prompt:
            return self._explain(prompt)
        q = re.search(r"^QUESTION: (.+)$", prompt, re.M).group(1).lower()
        retry = "ERROR:" in prompt
        for pattern, first, fixed in SQL_SCRIPT:
            if re.search(pattern, q):
                return f"```sql\n{fixed if retry and fixed else first}\n```"
        return "SELECT 'I could not map that question to the schema' AS note"

    def _explain(self, prompt: str) -> str:
        cols = re.search(r"^COLUMNS: (.+)$", prompt, re.M).group(1).split(" | ")
        rows = re.findall(r"^ROW: (.+)$", prompt, re.M)
        if not rows:
            return "The query returned no rows."
        top = rows[0].split(" | ")
        lead = f"{top[0]} leads with {cols[1]} of {top[1]}" if len(top) > 1 else f"The answer is {top[0]}"
        tail = ""
        if len(rows) > 1:
            last = rows[-1].split(" | ")
            tail = f"; {last[0]} is lowest at {last[1]}" if len(last) > 1 else ""
        return f"{lead}{tail} ({len(rows)} rows)."


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 800,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
