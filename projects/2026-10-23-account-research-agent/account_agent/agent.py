"""The agent loop: the LLM picks one tool per step from the history; the loop runs it and records the observation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .llm import LLMClient
from .tools import DocStore, extract_signals, score_fit

SYSTEM = """You are a business development researcher preparing an account brief for a sales call.
Work step by step. Each turn, reply with ONE JSON object and nothing else:
  {"thought": "<short>", "tool": "<name>", "args": {...}}   to call a tool, or
  {"final": "<markdown brief>"}                              when done.
Tools:
  list_companies()                     -> [{doc, name}]
  read_section(doc, section)           -> {ref, text}
  search(query, doc?)                  -> [{ref, score, snippet}]
  extract_signals(doc)                 -> [{signal, value, ref}]
  score_fit(doc)                       -> {score, max, reasons[{criterion, met, evidence, ref}]}
Our product is in doc "our_product" (sections: Offering, Capabilities, Ideal customer).
The brief must have sections: Snapshot, Fit, Why now, Pains and plays, Who to talk to, Suggested opener.
Every bullet must end with a citation like [doc#Section] for a section you actually read or that a tool returned.
Never state a number or name that is not in an observation."""


@dataclass
class Step:
    tool: str
    args: dict
    observation: object


@dataclass
class Result:
    brief: str
    steps: list[Step] = field(default_factory=list)
    seen_refs: set[str] = field(default_factory=set)
    stopped: str = "final"  # or "max_steps"


class AgentError(RuntimeError):
    pass


class ResearchAgent:
    def __init__(self, llm: LLMClient, store: DocStore, max_steps: int = 12):
        self.llm = llm
        self.store = store
        self.max_steps = max_steps
        self.tools: dict[str, Callable[..., object]] = {
            "list_companies": self._list_companies,
            "read_section": self._read_section,
            "search": self._search,
            "extract_signals": lambda doc: extract_signals(self.store, doc),
            "score_fit": lambda doc: score_fit(self.store, doc),
        }

    def _list_companies(self) -> list[dict]:
        return [{"doc": d, "name": t} for d, t in sorted(self.store.titles.items()) if d != "our_product"]

    def _read_section(self, doc: str, section: str) -> dict:
        s = self.store.get(doc, section)
        return {"ref": s.ref, "text": s.text}

    def _search(self, query: str, doc: str | None = None) -> list[dict]:
        return [{"ref": s.ref, "score": score, "snippet": s.text[:400]} for s, score in self.store.search(query, doc)]

    def run(self, account: str) -> Result:
        result = Result(brief="")
        for _ in range(self.max_steps):
            history = [{"tool": s.tool, "args": s.args, "observation": s.observation} for s in result.steps]
            prompt = f"TARGET:\n{account}\nHISTORY:\n{json.dumps(history)}\n"
            action = self._parse(self.llm.complete(SYSTEM, prompt))
            if "final" in action:
                result.brief = action["final"]
                return result
            tool, args = action.get("tool"), action.get("args", {})
            try:
                if tool not in self.tools:
                    raise KeyError(f"unknown tool '{tool}'")
                obs = self.tools[tool](**args)
            except (KeyError, TypeError) as e:
                # Errors go back to the model as observations so it can recover (e.g. pick a real section).
                obs = {"error": e.args[0] if isinstance(e, KeyError) else str(e)}
            result.steps.append(Step(tool, args, obs))
            result.seen_refs |= set(re.findall(r"'ref': '([^']+)'", repr(obs)))
        result.stopped = "max_steps"
        result.brief = "Research incomplete: step budget exhausted."
        return result

    @staticmethod
    def _parse(text: str) -> dict:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise AgentError(f"model did not return JSON: {text[:120]!r}")
        return json.loads(m.group(0))


def check_citations(brief: str, seen_refs: set[str]) -> dict:
    """Grounding check: cited refs must have been observed, and bullets must carry a citation."""
    cited = set(re.findall(r"\[([\w]+#[^\]]+)\]", brief))
    bullets = [ln for ln in brief.splitlines() if ln.startswith("- ")]
    return {
        "cited": len(cited),
        "unseen": sorted(cited - seen_refs),
        # "(no evidence)" admits a gap rather than claiming a fact, so it needs no source.
        "uncited_bullets": [b for b in bullets if not re.search(r"\[[\w]+#[^\]]+\]", b) and "(no evidence)" not in b],
    }
