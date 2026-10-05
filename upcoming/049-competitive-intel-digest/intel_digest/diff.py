"""Turn two snapshots of a competitor (pricing JSON + page text) into a list of typed, ranked changes."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

NOISE = [re.compile(p, re.I) for p in (r"updated \d+ \w+ ago", r"cookie", r"^©", r"all rights reserved")]
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Change:
    competitor: str
    kind: str        # price_increase | price_decrease | plan_added | plan_removed | feature_added | feature_removed
                     # | limit_change | positioning | claim_change | copy_added | copy_removed | copy_changed
    detail: str
    severity: str = "low"
    id: str = ""


def _pct(a: float, b: float) -> float:
    return (b - a) / a * 100 if a else float("inf")


def pricing_diff(name: str, prev: dict, curr: dict, watch: set[str] = frozenset()) -> list[Change]:
    out: list[Change] = []
    p, c = {pl["name"]: pl for pl in prev["plans"]}, {pl["name"]: pl for pl in curr["plans"]}
    for plan in c.keys() - p.keys():
        out.append(Change(name, "plan_added", f"new {plan} plan at {_price(c[plan])}", "high"))
    for plan in p.keys() - c.keys():
        out.append(Change(name, "plan_removed", f"{plan} plan removed (was {_price(p[plan])})", "high"))
    for plan in p.keys() & c.keys():
        a, b = p[plan], c[plan]
        if a["price"] != b["price"] and a["price"] is not None and b["price"] is not None:
            pct = _pct(a["price"], b["price"])
            kind = "price_increase" if pct > 0 else "price_decrease"
            sev = "high" if abs(pct) >= 5 else "medium"
            out.append(Change(name, kind, f"{plan}: {_price(a)} -> {_price(b)} ({pct:+.0f}%)", sev))
        for f in [f for f in b["features"] if f not in a["features"]]:
            sev = "high" if f in watch else ("medium" if a["price"] != 0 else "low")
            out.append(Change(name, "feature_added", f"{plan} gains {f}", sev))
        for f in [f for f in a["features"] if f not in b["features"]]:
            out.append(Change(name, "feature_removed", f"{plan} loses {f}", "medium"))
        for k in sorted(set(a["limits"]) | set(b["limits"])):
            va, vb = a["limits"].get(k), b["limits"].get(k)
            if va != vb:
                more = vb is None or (va is not None and vb > va)
                sev = "medium" if a["price"] == 0 or (va and vb and abs(_pct(va, vb)) >= 50) else "low"
                out.append(Change(name, "limit_change", f"{plan} {k}: {_lim(va)} -> {_lim(vb)} ({'more' if more else 'less'} generous)", sev))
    return out


def _price(plan: dict) -> str:
    return "contact sales" if plan["price"] is None else f"${plan['price']:,}/{plan['unit'].split('/')[-1]}"


def _lim(v) -> str:
    return "unlimited" if v is None else str(v)


def clean_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln and not any(n.search(ln) for n in NOISE)]


def _numbers(s: str) -> list[str]:
    return re.findall(r"\d[\d,]*\+?", s)


def page_diff(name: str, page: str, prev: str, curr: str) -> list[Change]:
    a, b = clean_lines(prev), clean_lines(curr)
    out: list[Change] = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        old, new = a[i1:i2], b[j1:j2]
        # pair up replaced lines; leftovers are pure adds/removes
        for k in range(max(len(old), len(new))):
            o = old[k] if k < len(old) else None
            n = new[k] if k < len(new) else None
            if o and n:
                out.append(_classify_edit(name, page, o, n, is_tagline=(i1 + k) <= 1))
            elif n:
                out.append(Change(name, "copy_added", f"{page}: + \"{n}\"", "medium"))
            elif o:
                out.append(Change(name, "copy_removed", f"{page}: - \"{o}\"", "low"))
    return out


def _classify_edit(name: str, page: str, old: str, new: str, is_tagline: bool) -> Change:
    if is_tagline:
        return Change(name, "positioning", f"{page} tagline: \"{old}\" -> \"{new}\"", "high")
    if _numbers(old) and re.sub(r"\d[\d,]*\+?", "#", old).split()[:2] == re.sub(r"\d[\d,]*\+?", "#", new).split()[:2]:
        sev = "low" if "hiring" in old.lower() else "medium"
        return Change(name, "claim_change", f"{page}: \"{old}\" -> \"{new}\"", sev)
    return Change(name, "copy_changed", f"{page}: \"{old}\" -> \"{new}\"", "low")


def diff_competitor(prev_dir: Path, curr_dir: Path, watch: set[str] = frozenset()) -> list[Change]:
    name = curr_dir.name
    changes: list[Change] = []
    if (prev_dir / "pricing.json").exists() and (curr_dir / "pricing.json").exists():
        changes += pricing_diff(name, json.loads((prev_dir / "pricing.json").read_text()),
                                json.loads((curr_dir / "pricing.json").read_text()), watch)
    for page in sorted(curr_dir.glob("*.md")):
        before = prev_dir / page.name
        changes += page_diff(name, page.stem, before.read_text() if before.exists() else "", page.read_text())
    return changes


def diff_all(prev_root: Path, curr_root: Path, watch: set[str] = frozenset()) -> list[Change]:
    changes: list[Change] = []
    for comp in sorted(p for p in curr_root.iterdir() if p.is_dir()):
        changes += diff_competitor(prev_root / comp.name, comp, watch)
    changes.sort(key=lambda c: (SEVERITY_RANK[c.severity], c.competitor))
    for i, c in enumerate(changes, 1):
        c.id = f"C{i}"
    return changes
