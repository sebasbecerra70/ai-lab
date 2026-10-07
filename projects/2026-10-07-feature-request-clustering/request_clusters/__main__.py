"""CLI: python -m request_clusters [k]   (omit k to pick it by silhouette)"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, cluster_requests, load_requests, render


def main() -> None:
    requests = load_requests(Path(__file__).resolve().parent.parent / "data" / "requests.csv")
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    k = int(sys.argv[1]) if len(sys.argv) > 1 else None
    themes, scores = cluster_requests(requests, llm, k=k)
    print(f"{len(requests)} feature requests -> {len(themes)} themes, ranked by ARR at stake")
    print(render(themes, scores))


if __name__ == "__main__":
    main()
