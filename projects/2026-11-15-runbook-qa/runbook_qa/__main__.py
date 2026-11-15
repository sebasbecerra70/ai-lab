"""CLI: python -m runbook_qa ["question"]"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, RunbookQA, load_runbooks

DATA = Path(__file__).resolve().parent.parent / "data" / "runbooks"
QUESTIONS = [
    "A PDU breaker tripped in row C, what do I do?",
    "UPS is on battery and the generator hasn't started",
    "The breaker keeps tripping, can I reset it again?",
    "How do I remove another tech's lock so I can finish the job?",
    "How do I renew the SSL certificate on the customer portal?",
]


def main() -> None:
    live = bool(os.environ.get("ANTHROPIC_API_KEY"))
    qa = RunbookQA(load_runbooks(DATA), AnthropicLLM() if live else MockLLM())
    questions = sys.argv[1:] or QUESTIONS
    for q in questions:
        a = qa.ask(q)
        print(f"Q: {q}\n-> {a.status} ({a.source})")
        for line in a.text.splitlines():
            print(f"   {line}")
        print()
    if not sys.argv[1:] and not live:
        bad = RunbookQA(load_runbooks(DATA), MockLLM(hallucinate=True)).ask(QUESTIONS[0])
        print(f"Validator check with a hallucinating model: {bad.problems} -> served {bad.source} answer")


if __name__ == "__main__":
    main()
