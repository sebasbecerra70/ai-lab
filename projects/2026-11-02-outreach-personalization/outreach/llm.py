"""LLM boundary: a deterministic mock for tests/offline runs and a stdlib-only Anthropic Messages API client."""
from __future__ import annotations

import json
import os
import urllib.request
import zlib
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class AnthropicClient:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-5-5", max_tokens: int = 700):
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.model, self.max_tokens = model, max_tokens

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")


def facts_from(prompt: str) -> dict:
    return json.loads(prompt[prompt.index("FACTS:") + 6:prompt.index("END FACTS")])


class MockLLM:
    """Writes a plausible email from the facts in the prompt.

    First drafts deliberately reproduce failure modes seen in real LLM sales copy (a hype guarantee, an
    invented statistic, a rambling second ask) for some prospects, chosen by a stable hash of the name, so
    the eval suite and the revise loop have something real to catch. A prompt carrying reviewer feedback
    gets a clean rewrite.
    """

    def complete(self, system: str, prompt: str) -> str:
        f = facts_from(prompt)
        p, prod = f["prospect"], f["product"]
        proof = pick_proof(p["industry"], prod["proof_points"])
        value = prod["value_props"][2 if "pain" in p and "response" in p["pain"] else 0]
        body = (f"Hi {p['first_name']},\n\n"
                f"I saw that {p['company']} {p['trigger']}. Teams in {p['industry']} often tell us the hard part "
                f"after a move like that is {p['pain']}.\n\n"
                f"We work with {proof['customer']} that {proof['result']}, using {value}.\n\n"
                f"Would {prod['cta']} be useful to see whether the same approach fits {p['company']}?\n\n"
                f"{prod['sender']['name']}\n{prod['sender']['title']}, {prod['company']}\n{prod['footer']}")
        if "REVIEWER FEEDBACK" not in prompt:
            flaw = zlib.crc32(p["first_name"].encode()) % 5  # 0-2: a flaw, 3-4: clean
            if flaw == 0:
                body = body.replace("We work with", "We guarantee results. We work with")
            elif flaw == 1:
                body = body.replace(f"is {p['pain']}.", f"is {p['pain']}; most teams lose 12% of inventory "
                                    "to temperature excursions.")
            elif flaw == 2:
                body = body.replace(f"{prod['sender']['name']}\n", "Also, do you have time for a quick demo "
                                    "this Friday? Or could you point me to the right person on your team?\n\n"
                                    f"{prod['sender']['name']}\n")
        return json.dumps({"subject": f"Cold chain at {p['company']}", "body": body})


def pick_proof(industry: str, proofs: list[dict]) -> dict:
    """Closest proof point by industry: a pharma prospect hears the pharma story."""
    for key, word in (("pharma", "pharma"), ("seafood", "seafood")):
        if key in industry:
            return next(pp for pp in proofs if word in pp["customer"])
    return proofs[0]
