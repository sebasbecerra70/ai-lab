"""CLI: python -m rfp_rag [questions.txt]"""
import os
import sys
from pathlib import Path

from . import BM25, AnthropicLLM, ExtractiveLLM, RFPDrafter, load_passages


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    qfile = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data" / "rfp_questions.txt"
    questions = [q.strip() for q in qfile.read_text().splitlines() if q.strip()]
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else ExtractiveLLM()
    drafter = RFPDrafter(BM25(load_passages(root / "docs" / "proposals")), llm)
    drafts = [drafter.draft(q) for q in questions]
    for i, d in enumerate(drafts, 1):
        print(f"{i}. {d.question}\n   [{d.status}, confidence {d.confidence:.2f}]")
        if d.status == "drafted":
            print(f"   {d.answer}")
            for n, p in enumerate(d.sources, 1):
                print(f"     [{n}] {p.source}: {p.question}")
            for issue in d.citation_issues:
                print(f"   ! {issue}")
        else:
            print("   -> route to a subject-matter expert; closest past answer: "
                  + (d.sources[0].question if d.sources else "none"))
    drafted = sum(d.status == "drafted" for d in drafts)
    print(f"\n{drafted}/{len(drafts)} drafted from past proposals, {len(drafts) - drafted} routed to SMEs")


if __name__ == "__main__":
    main()
