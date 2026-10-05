# Review Sentiment Insights

Turns a pile of app-store reviews into a ranked list of product pain points. A lexicon sentiment scorer handles negation and "but" clauses, keyword aspect extraction attributes each sentence to what it's about, and a pain index combines volume with intensity. An LLM then writes the brief for the product team, and every quote in it is checked against the source reviews.

```text
$ python -m review_insights
180 reviews, average 3.08 stars; lexicon score vs stars: r=0.83, polarity accuracy 93%

aspect     mentions  negative  avg score   pain  also named
app              65       49%      -0.08   28.7           0
wifi             55       80%      -0.42   26.0           0
install          51       43%      -0.09   13.7           0
support          38       53%      -0.06   11.3           0
price            26       46%      +0.01    7.9           0
battery          23       43%      -0.07    7.4           0
accuracy         32       28%      +0.02    3.1           0
schedule         34       26%      +0.27    2.6          31

frequent words in negative sentences not covered by any aspect: days (18), stops (18), working (18), weekly (15), twice (14)

----- brief (MockLLM) -----
Top customer pain points:
1. app: 32 of 65 mentions are negative (49%). "The app is slow and crashes when I open the schedule." (R002)
2. wifi: 44 of 55 mentions are negative (80%). "Constant wifi disconnects, I have to reboot it weekly." (R006)
3. install: 22 of 51 mentions are negative (43%). "Installation was a nightmare, the wiring diagram did not match my system." (R014)
Next steps: investigate app first; then wifi; then install.
-----
quote check: all quotes verbatim
```

## Why it matters
A 3.1-star average tells a PM that something is wrong, not what. Reading 180 reviews by hand takes about two hours and produces a gut feeling. This produces a ranked list with counts in under a second. The ranking has a business meaning: **wifi** has the worst complaint rate (80% of mentions negative), but **app** generates the most total pain because more people talk about it. That's the "fix the thing most customers hit" versus "fix the thing that hurts most" trade-off, and it's now visible in two columns.

The "also named" column shows why attribution matters. "Schedule" appears in 31 sentences that are actually about something else ("the app crashes when I open the schedule", "drops off wifi and the schedule stops working"). Naive keyword counting would have put scheduling in the top three and sent a team to fix the wrong feature.

## Architecture
```
data/reviews.csv (id, stars, text)
        │ sentences()
        ▼
score_text(): lexicon weights · negation flips the next 3 words (×0.8) · intensifiers (very, constant ×1.3–1.8)
              · words after "but" count double · normalized to [-1, 1]
        ▼
aspects_in(): keyword sets per aspect, ordered by first mention → primary aspect gets the sentiment,
              the others get "also named"
        ▼
AspectStats: mentions · negative share · avg score · pain = Σ |negative scores|   ──► ranked_pains()
uncovered_terms(): frequent non-sentiment words in negative sentences → candidate new aspects
rating_agreement(): Pearson r vs stars, polarity accuracy (sanity check on the lexicon)
        ▼
summarize(): facts JSON (counts + most negative unique quotes) → LLMClient → brief
unverified_quotes(): every "quoted" span must exist verbatim in a review
```
- **Why a lexicon, not an LLM, for scoring:** it's deterministic, free, fast enough for millions of reviews, and auditable word by word. Its agreement with star ratings (r = 0.83) is measured on every run, so drift shows up. The LLM is used where it's strongest: writing a readable brief from verified numbers.
- **Primary-aspect attribution** is a small heuristic with a big effect (see "schedule" above). A dependency parser would do better, but this needs no model and is easy to explain.
- **Pain = volume × intensity.** Negative share alone ranks rare-but-angry topics first. Mentions alone ranks popular topics first. Summing negative magnitude balances the two.
- **Quote verification.** LLMs "tidy up" quotes. A PM who pastes a fabricated customer quote into a roadmap deck loses credibility, so any quote not found verbatim is flagged.
- **Trade-off:** the lexicon and aspect keywords are tuned to this product domain. A new product needs a new keyword list. `uncovered_terms()` is there to show where the list is missing something.

## Run
```bash
python -m pytest -q                              # 10 tests
python -m review_insights                        # mock brief
ANTHROPIC_API_KEY=... python -m review_insights  # Claude writes the brief; the quote check still runs
python -m review_insights.synth                  # regenerate the synthetic reviews
```

## Next steps
- Trend pain by app version or month to catch regressions right after a release.
- Let an LLM propose new aspect keyword sets from `uncovered_terms()`, with a human approving them.
- Join with support tickets and churn to weight pain by revenue at risk.
- Compare against a small supervised classifier on a few hundred labelled sentences.
