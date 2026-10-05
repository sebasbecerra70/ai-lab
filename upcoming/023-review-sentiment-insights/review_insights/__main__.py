"""CLI: python -m review_insights"""
import os
from pathlib import Path

from . import AnthropicLLM, MockLLM, analyze, load_reviews, ranked_pains, rating_agreement, summarize, uncovered_terms, unverified_quotes

DATA = Path(__file__).resolve().parent.parent / "data" / "reviews.csv"


def main() -> None:
    reviews = load_reviews(DATA)
    r, acc = rating_agreement(reviews)
    avg = sum(x.rating for x in reviews) / len(reviews)
    print(f"{len(reviews)} reviews, average {avg:.2f} stars; lexicon score vs stars: r={r:.2f}, polarity accuracy {acc:.0%}\n")

    stats = analyze(reviews)
    print(f"{'aspect':<10}{'mentions':>9}{'negative':>10}{'avg score':>11}{'pain':>7}{'also named':>12}")
    for s in sorted(stats.values(), key=lambda s: -s.pain):
        print(f"{s.aspect:<10}{s.mentions:>9}{s.negative_share:>10.0%}{s.avg:>+11.2f}{s.pain:>7.1f}{s.secondary:>12}")
    print("\nfrequent words in negative sentences not covered by any aspect: "
          + ", ".join(f"{w} ({n})" for w, n in uncovered_terms(reviews)))

    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    brief = summarize(llm, ranked_pains(stats))
    print(f"\n----- brief ({type(llm).__name__}) -----\n{brief}\n-----")
    bad = unverified_quotes(brief, reviews)
    print(f"quote check: {'all quotes verbatim' if not bad else f'NOT FOUND in reviews: {bad}'}")


if __name__ == "__main__":
    main()
