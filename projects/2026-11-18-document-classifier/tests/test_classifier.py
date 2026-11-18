import math
from pathlib import Path

import pytest

from doc_classifier import NaiveBayes, cross_validate, evaluate, featurize, load_jsonl, needs_review, words
from doc_classifier.docgen import generate

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def train():
    return load_jsonl(DATA / "train.jsonl")


@pytest.fixture(scope="module")
def model(train):
    return NaiveBayes().fit([d["text"] for d in train], [d["label"] for d in train])


def test_numbers_are_normalized_but_kept_as_layout_signal():
    assert words("Gross weight 8,379 kg") == ["gross", "weight", "0", "kg"]
    assert words("42x32x24 cm") == ["0", "cm"]


def test_char_ngrams_survive_ocr_typos():
    clean, noisy = featurize("components", char_n=4), featurize("componennts", char_n=4)
    shared = {k for k in clean if k.startswith("#")} & {k for k in noisy if k.startswith("#")}
    assert len(shared) >= 5
    assert "components" not in noisy  # the word feature itself is lost


def test_toy_naive_bayes_matches_hand_computation():
    nb = NaiveBayes(alpha=1.0, char_n=0).fit(["duty entry", "cartons kg"], ["CUS", "PL"])
    ll = nb.log_likelihoods("duty")
    v = len(nb.vocab)  # duty, entry, duty_entry, cartons, kg, cartons_kg
    assert v == 6
    assert ll["CUS"] == pytest.approx(math.log(0.5) + math.log((1 + 1) / (3 + v)))
    assert ll["PL"] == pytest.approx(math.log(0.5) + math.log((0 + 1) / (3 + v)))
    assert nb.predict("duty").label == "CUS"


def test_unseen_words_carry_no_evidence(model):
    a = model.log_likelihoods("customs duty entry")
    b = model.log_likelihoods("customs duty entry zzqx plumbus")
    assert a == b


def test_posteriors_sum_to_one_and_temperature_softens(model, train):
    text = train[0]["text"]
    hot, cool = model.predict(text), NaiveBayes(temperature=200).fit([d["text"] for d in train], [d["label"] for d in train]).predict(text)
    assert sum(hot.scores.values()) == pytest.approx(1.0)
    assert cool.label == hot.label and cool.confidence < hot.confidence


@pytest.mark.parametrize("text,label", [
    ("Shipper: X\nConsignee: Y\nPort of discharge: Hamburg\nShipped on board in apparent good order", "bill_of_lading"),
    ("Description Qty Unit price Amount\nTotal amount due USD 4,200.00\nBank SWIFT CITIUS33", "commercial_invoice"),
    ("Carton Pcs/ctn Cartons N.W. kg G.W. kg\nTotal cartons: 40\nTotal volume 12.5 CBM", "packing_list"),
    ("Entry number 123-4567890-1\nHTS number duty rate\nMerchandise processing fee USD 30", "customs_declaration"),
])
def test_classifies_handwritten_examples(model, text, label):
    assert model.predict(text).label == label


def test_held_out_noisy_test_accuracy(model):
    r = evaluate(model, load_jsonl(DATA / "test.jsonl"))
    assert r.accuracy >= 0.95
    assert min(r.recall.values()) >= 0.9


def test_cross_validation_is_stable(train):
    scores = cross_validate(train, k=5)
    assert len(scores) == 5 and min(scores) >= 0.9


def test_short_fragments_go_to_review_even_when_confident(model):
    pred = model.predict("stainless cookware\nceramic mugs\nGross weight 8379 kg")
    assert pred.confidence > 0.9 and pred.evidence < 8
    assert needs_review(pred, threshold=0.9, min_evidence=8)


def test_generator_is_reproducible():
    assert generate(2, seed=5) == generate(2, seed=5)
    assert {d["label"] for d in generate(1, seed=5)} == {"bill_of_lading", "commercial_invoice", "packing_list", "customs_declaration"}
