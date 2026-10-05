"""Tool allow-list with per-argument validation and approval rules, plus the output guard."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

from .pii import redact

Validator = Callable[[object, dict], Optional[str]]  # (value, session) -> error or None


def pattern(rx: str) -> Validator:
    c = re.compile(rx)
    return lambda v, s: None if isinstance(v, str) and c.fullmatch(v) else f"must match {rx}"


def own_email(v: object, session: dict) -> str | None:
    return None if v == session.get("customer_email") else "may only email the authenticated customer"


def own_order(v: object, session: dict) -> str | None:
    return None if v in session.get("order_ids", []) else "order does not belong to this customer"


def amount(max_value: float) -> Validator:
    return lambda v, s: None if isinstance(v, (int, float)) and 0 < v <= max_value else f"must be a number in (0, {max_value}]"


@dataclass(frozen=True)
class ToolRule:
    args: dict[str, list[Validator]]
    needs_approval: Callable[[dict], bool] = lambda a: False


TOOLS: dict[str, ToolRule] = {
    "lookup_order": ToolRule({"order_id": [pattern(r"ORD-\d{6}"), own_order]}),
    "send_email": ToolRule({"to": [own_email], "body": [lambda v, s: None if isinstance(v, str) and len(v) < 2000 else "body too long"]}),
    "issue_refund": ToolRule({"order_id": [pattern(r"ORD-\d{6}"), own_order], "amount": [amount(500)]},
                             needs_approval=lambda a: a.get("amount", 0) > 100),
}


@dataclass(frozen=True)
class ToolDecision:
    tool: str
    verdict: str  # execute | needs_approval | deny
    reason: str


def check_tool_call(name: str, args: dict, session: dict) -> ToolDecision:
    rule = TOOLS.get(name)
    if rule is None:
        return ToolDecision(name, "deny", "tool not on the allow-list")
    if set(args) != set(rule.args):
        return ToolDecision(name, "deny", f"expected args {sorted(rule.args)}, got {sorted(args)}")
    for arg, validators in rule.args.items():
        for v in validators:
            err = v(args[arg], session)
            if err:
                return ToolDecision(name, "deny", f"{arg}: {err}")
    if rule.needs_approval(args):
        return ToolDecision(name, "needs_approval", "over the auto-approve limit; queued for a human")
    return ToolDecision(name, "execute", "ok")


URL = re.compile(r"https?://[^\s)\]]+")
MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


@dataclass(frozen=True)
class OutputResult:
    text: str
    issues: tuple[str, ...]
    blocked: bool


def guard_output(text: str, system_prompt: str, canary: str, allowed_domains: set[str]) -> OutputResult:
    issues = []
    if canary in text or _overlap(text, system_prompt) >= 0.5:
        return OutputResult("Sorry, I can't share that.", ("system_prompt_leak",), True)
    for img in MD_IMAGE.findall(text):
        # Markdown images are fetched automatically by the client: a classic zero-click exfiltration channel.
        text = text.replace(img, "")
        issues.append("markdown_image_removed")
    for url in URL.findall(text):
        host = urlparse(url).hostname or ""
        if not any(host == d or host.endswith("." + d) for d in allowed_domains):
            text = text.replace(url, "[link removed]")
            issues.append(f"url_removed:{host}")
    text, _, found = redact(text)
    issues += [f"pii_redacted:{k}" for k in found]
    return OutputResult(text, tuple(issues), False)


def _overlap(text: str, reference: str, n: int = 6) -> float:
    """Share of the reference's word 6-grams that appear verbatim in the text."""
    ref = reference.lower().split()
    grams = {tuple(ref[i:i + n]) for i in range(len(ref) - n + 1)}
    if not grams:
        return 0.0
    words = text.lower().split()
    seen = {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}
    return len(grams & seen) / len(grams)
