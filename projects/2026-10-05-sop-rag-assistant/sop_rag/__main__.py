"""CLI: python -m sop_rag "How do I handle a damaged inbound pallet?" """
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, SOPAssistant, TfidfRetriever


def main() -> None:
    question = " ".join(sys.argv[1:]) or "What temperature must frozen loads be received at?"
    docs = Path(__file__).resolve().parent.parent / "docs"
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    answer = SOPAssistant(TfidfRetriever.from_directory(docs), llm).ask(question)
    print(answer.text)
    for i, src in enumerate(answer.sources, 1):
        print(f"  [{i}] {src.source}: {src.text.splitlines()[0]}")


if __name__ == "__main__":
    main()
