"""Eval suite for outbound emails. Every check is deterministic so the same draft always gets the same verdict."""
from __future__ import annotations

import re
from dataclasses import dataclass

WORD = re.compile(r"[A-Za-z0-9'%-]+")
NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
PLACEHOLDER = re.compile(r"\{\{|\}\}|\[(?:first ?name|company|name|title)\]|<[A-Z_]{3,}>", re.I)
STOP = {"the", "and", "for", "with", "into", "from", "that", "this", "their", "about", "after", "before", "posted",
        "opened", "announced", "reported"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def words(text: str) -> list[str]:
    return WORD.findall(text)


def body_without_signature(body: str, product: dict) -> str:
    return body.split(f"\n{product['sender']['name']}\n")[0]


def personalization_tokens(prospect: dict) -> dict[str, list[str]]:
    """What a reader would recognise as 'written for me': their name, their company, and the event we cite."""
    trigger = [w for w in re.findall(r"[a-z]+", prospect["trigger"].lower()) if len(w) > 4 and w not in STOP]
    return {"first name": [prospect["first_name"]], "company": [prospect["company"]], "trigger": trigger}


def run_checks(email: dict, prospect: dict, product: dict, min_words: int = 60, max_words: int = 140) -> list[Check]:
    subject, body = email.get("subject", ""), email.get("body", "")
    main = body_without_signature(body, product)
    n_words = len(words(main))
    checks = [
        Check("subject", 0 < len(subject) <= 60 and "!" not in subject
              and not any(w.isupper() and len(w) > 3 for w in subject.split()), f"{len(subject)} chars"),
        Check("length", min_words <= n_words <= max_words, f"{n_words} words (target {min_words}-{max_words})"),
    ]
    missing = [k for k, toks in personalization_tokens(prospect).items()
               if not any(t.lower() in body.lower() for t in toks)]
    checks.append(Check("personalized", not missing, "missing " + ", ".join(missing) if missing else "name, company, trigger"))
    ph = PLACEHOLDER.findall(subject + body)
    checks.append(Check("no placeholders", not ph, ", ".join(ph)))
    lower = (subject + " " + body).lower()
    banned = [b for b in product["banned_claims"] if re.search(rf"(?<!\w){re.escape(b.lower())}(?!\w)", lower)]
    checks.append(Check("no banned claims", not banned, ", ".join(banned)))
    allowed = " ".join([str(product), str(prospect)])
    invented = [n for n in NUMBER.findall(main) if n not in allowed]
    checks.append(Check("numbers grounded", not invented, "unsupported: " + ", ".join(invented) if invented else ""))
    asks = main.count("?")
    checks.append(Check("one call to action", asks == 1, f"{asks} questions"))
    checks.append(Check("opt-out line", product["footer"] in body))
    sentences = [s for s in re.split(r"[.!?]+\s", main) if words(s)]
    avg = n_words / max(1, len(sentences))
    checks.append(Check("readable", avg <= 24, f"{avg:.1f} words/sentence (max 24)"))
    return checks


def failures(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.passed]
