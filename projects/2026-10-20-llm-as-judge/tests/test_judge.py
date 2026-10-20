import json
from pathlib import Path

import pytest

from llm_judge import (JudgeOutputError, MockJudge, PairVerdict, cohens_kappa, heuristic_quality, judge_pair, judge_rubric,
                       pairwise_report, parse_json, spearman)

DATA = Path(__file__).resolve().parent.parent / "data"


class Scripted:
    """Returns canned outputs in order and records prompts."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def complete(self, system, prompt):
        self.prompts.append(prompt)
        return self.outputs.pop(0)


def load(name):
    return [json.loads(x) for x in (DATA / name).read_text().splitlines() if x.strip()]


def test_parse_json_accepts_fenced_output_and_rejects_prose():
    assert parse_json('```json\n{"winner": "1"}\n```') == {"winner": "1"}
    with pytest.raises(JudgeOutputError):
        parse_json("Response 1 is better.")


def test_judge_pair_swaps_the_order_of_answers():
    llm = Scripted('{"winner": "1"}', '{"winner": "2"}')
    v = judge_pair(llm, "q", "ANSWER_A", "ANSWER_B")
    assert llm.prompts[0].index("ANSWER_A") < llm.prompts[0].index("ANSWER_B")
    assert llm.prompts[1].index("ANSWER_B") < llm.prompts[1].index("ANSWER_A")
    assert v == PairVerdict("A", "A", "A", True)


def test_position_biased_judge_is_downgraded_to_tie():
    # Judge always picks whatever it saw first: forward says A, backward says B.
    v = judge_pair(Scripted('{"winner": "1"}', '{"winner": "1"}'), "q", "a", "b")
    assert (v.forward, v.backward, v.winner, v.consistent) == ("A", "B", "tie", False)


def test_invalid_winner_label_is_an_error():
    with pytest.raises(JudgeOutputError):
        judge_pair(Scripted('{"winner": "A"}'), "q", "a", "b")


def test_rubric_retries_once_on_malformed_scores():
    good = json.dumps({"scores": {"correctness": 4, "completeness": 4, "concision": 5, "tone": 5}})
    llm = Scripted('{"scores": {"correctness": 9}}', good)
    assert judge_rubric(llm, "q", "a").overall == 4.5
    with pytest.raises(JudgeOutputError, match="after 2 attempts"):
        judge_rubric(Scripted("nope", "still nope"), "q", "a")


def test_heuristic_quality_rewards_grounded_answers_and_penalises_hedging():
    q, ref = "How long do payouts take?", "Payouts reach US banks in 2 business days."
    good = heuristic_quality(q, "Payouts reach US banks in 2 business days.", ref)
    hedged = heuristic_quality(q, "I think payouts maybe take 2 business days.", ref)
    assert good > hedged


def test_cohens_kappa_known_values():
    assert cohens_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]) == 1.0
    # 50% observed agreement with 50% expected by chance -> 0
    assert cohens_kappa(["A", "A", "B", "B"], ["A", "B", "A", "B"]) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cohens_kappa([], [])


def test_spearman_handles_ties_and_direction():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2, 2], [1, 1, 2, 2]) == pytest.approx(1.0)


def test_report_measures_flip_rate_and_first_position_bias():
    verdicts = [PairVerdict("A", "A", "A", True), PairVerdict("tie", "A", "B", False)]
    r = pairwise_report(verdicts, ["A", "tie"])
    assert r.flip_rate == 0.5
    assert r.first_position_win_rate == pytest.approx(3 / 4)
    assert r.single_pass_agreement == 0.5 and r.swapped_agreement == 1.0


def test_swap_improves_agreement_on_the_sample_set():
    pairs = load("pairs.jsonl")
    verdicts = [judge_pair(MockJudge(), p["question"], p["a"], p["b"], p["reference"]) for p in pairs]
    r = pairwise_report(verdicts, [p["human"] for p in pairs])
    assert r.flip_rate > 0
    assert r.first_position_win_rate > 0.5
    assert r.swapped_agreement > r.single_pass_agreement


def test_rubric_scores_track_human_ratings():
    items = load("rubric_set.jsonl")
    overall = [judge_rubric(MockJudge(), i["question"], i["answer"], i["reference"]).overall for i in items]
    assert spearman(overall, [i["human"] for i in items]) > 0.7
