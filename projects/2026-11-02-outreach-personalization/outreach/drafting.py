"""Draft -> evaluate -> revise loop. The eval suite, not the model, decides when an email is ready to send."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .evals import Check, failures, run_checks
from .llm import LLMClient

SYSTEM = (
    "You write short, specific B2B cold emails. Use only the facts provided: never invent statistics, customers "
    "or claims. Mention the prospect's first name, company and the trigger event. 60-140 words before the "
    "signature, one question as the call to action, end with the signature and the footer exactly as given. "
    "Avoid hype words such as guarantee, #1, risk-free. Reply with JSON only: {\"subject\": ..., \"body\": ...}."
)


@dataclass
class Draft:
    prospect: dict
    email: dict
    attempts: list[list[Check]] = field(default_factory=list)  # eval results per attempt

    @property
    def passed(self) -> bool:
        return not failures(self.attempts[-1])

    @property
    def first_pass(self) -> bool:
        return not failures(self.attempts[0])


def build_prompt(prospect: dict, product: dict, feedback: list[Check] | None = None, previous: dict | None = None) -> str:
    facts = json.dumps({"prospect": prospect, "product": product}, indent=1)
    prompt = f"Write a first-touch email.\nFACTS:{facts}END FACTS\n"
    if feedback:
        issues = "\n".join(f"- {c.name}: {c.detail}" for c in feedback)
        prompt += (f"\nREVIEWER FEEDBACK on your previous draft (fix every item, change nothing else):\n{issues}\n"
                   f"Previous draft:\n{json.dumps(previous)}\n")
    return prompt


def parse_email(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outermost object."""
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {"subject": "", "body": text.strip()}


def draft_email(llm: LLMClient, prospect: dict, product: dict, max_revisions: int = 2) -> Draft:
    email = parse_email(llm.complete(SYSTEM, build_prompt(prospect, product)))
    d = Draft(prospect, email, [run_checks(email, prospect, product)])
    while failures(d.attempts[-1]) and len(d.attempts) <= max_revisions:
        prompt = build_prompt(prospect, product, failures(d.attempts[-1]), d.email)
        d.email = parse_email(llm.complete(SYSTEM, prompt))
        d.attempts.append(run_checks(d.email, prospect, product))
    return d
