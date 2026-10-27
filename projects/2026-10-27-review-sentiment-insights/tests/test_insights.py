from pathlib import Path

import pytest

from review_insights import (MockLLM, Review, analyze, aspects_in, build_facts, load_reviews, ranked_pains, rating_agreement,
                             score_text, sentences, summarize, uncovered_terms, unverified_quotes)

DATA = Path(__file__).resolve().parent.parent / "data" / "reviews.csv"


@pytest.fixture(scope="module")
def reviews():
    return load_reviews(DATA)


def test_basic_polarity():
    assert score_text("Love it, excellent value.") > 0.5
    assert score_text("Useless and rude support.") < -0.5
    assert score_text("The box is blue.") == 0


def test_negation_flips_and_intensifiers_amplify():
    assert score_text("Scheduling is not intuitive.") < 0
    assert score_text("It stays connected without problems.") > 0
    assert score_text("very slow") < score_text("slow") < 0


def test_but_clause_carries_the_verdict():
    assert score_text("Setup was easy but the app crashes.") < 0


def test_sentence_split_and_aspect_order():
    assert sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert aspects_in("The app is slow and crashes when I open the schedule.") == ["app", "schedule"]
    assert aspects_in("Nice box.") == []


def test_only_primary_aspect_gets_the_sentiment():
    stats = analyze([Review("x", 1, "The app crashes when I open the schedule.")])
    assert (stats["app"].negative, stats["schedule"].negative, stats["schedule"].secondary) == (1, 0, 1)


def test_lexicon_tracks_star_ratings(reviews):
    r, acc = rating_agreement(reviews)
    assert r > 0.7 and acc > 0.85


def test_analysis_recovers_the_known_worst_aspects(reviews):
    stats = analyze(reviews)
    worst_share = max(stats.values(), key=lambda s: s.negative_share).aspect
    assert worst_share == "wifi"  # generated with the highest complaint rate
    assert [p.aspect for p in ranked_pains(stats, 2)] == ["app", "wifi"]  # volume x intensity


def test_uncovered_terms_skip_sentiment_words(reviews):
    words = [w for w, _ in uncovered_terms(reviews)]
    assert "disappointed" not in words and "very" not in words
    assert words  # still surfaces topic words for the analyst


def test_facts_quote_most_negative_unique_sentences(reviews):
    facts = build_facts(ranked_pains(analyze(reviews), 1), quotes_per=3)[0]
    texts = [q["text"] for q in facts["quotes"]]
    assert len(set(texts)) == len(texts) == 3
    assert facts["negative"] <= facts["mentions"]


def test_brief_quotes_are_verbatim_and_fabrications_are_caught(reviews):
    brief = summarize(MockLLM(), ranked_pains(analyze(reviews)))
    assert unverified_quotes(brief, reviews) == []
    assert unverified_quotes('Users say "the thermostat caught fire twice"', reviews) == ["the thermostat caught fire twice"]
