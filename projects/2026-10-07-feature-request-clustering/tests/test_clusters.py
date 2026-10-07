from pathlib import Path

import pytest

from request_clusters import (MockLLM, Request, TfidfVectorizer, cluster_requests, kmeans, load_requests,
                              silhouette, stem, tokenize)

DATA = Path(__file__).resolve().parent.parent / "data" / "requests.csv"


@pytest.fixture(scope="module")
def requests():
    return load_requests(DATA)


def test_tokenize_stems_and_drops_stopwords():
    assert tokenize("Please add email notifications for exporting") == ["add", "email", "notification", "export"]
    assert stem("sso") == "sso" and stem("status") == "status"


def test_synonyms_merge_vocabulary():
    assert tokenize("Single sign-on with SAML") == tokenize("SSO with SAML")
    assert "msteam" in tokenize("Notify our Teams channel") and "team" in tokenize("our IT team")


def test_tfidf_vectors_are_unit_length_and_drop_rare_terms():
    vecs = TfidfVectorizer(min_df=2).fit_transform(["slack alert", "slack digest", "okta"])
    assert sum(v * v for v in vecs[0].values()) == pytest.approx(1.0)
    assert vecs[2] == {}  # 'okta' appears once and is filtered


def test_kmeans_separates_obvious_groups():
    texts = ["sso saml okta", "saml sso login", "okta sso", "csv export excel", "export csv", "excel export"]
    vecs = TfidfVectorizer(min_df=1).fit_transform(texts)
    labels = kmeans(vecs, 2).labels
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]
    assert silhouette(vecs, labels) > 0.5


def test_kmeans_is_deterministic_for_a_seed(requests):
    vecs = TfidfVectorizer().fit_transform([r.text for r in requests])
    assert kmeans(vecs, 5, seed=3).labels == kmeans(vecs, 5, seed=3).labels


def test_kmeans_rejects_bad_k():
    with pytest.raises(ValueError):
        kmeans([{"a": 1.0}], 2)


def test_sample_data_recovers_the_sso_theme(requests):
    themes, _ = cluster_requests(requests, MockLLM(), k=6)
    sso = next(t for t in themes if "sso" in t.top_terms)
    ids = {r.id for r in sso.requests}
    assert {1, 2, 3, 5, 6} <= ids


def test_silhouette_picks_a_reasonable_k(requests):
    themes, scores = cluster_requests(requests, MockLLM(), k_range=range(3, 9))
    assert 5 <= len(themes) <= 8
    assert set(scores) == set(range(3, 9))


def test_arr_counts_each_account_once():
    from request_clusters import Theme
    t = Theme("x", [Request(1, "A", 100, "a"), Request(2, "A", 100, "b"), Request(3, "B", 50, "c")], [])
    assert t.arr_at_stake == 150 and t.accounts == {"A", "B"}


def test_themes_ranked_by_arr_and_llm_sees_terms_and_examples(requests):
    class Spy(MockLLM):
        prompts = []

        def complete(self, system, prompt):
            self.prompts.append(prompt)
            return super().complete(system, prompt)

    spy = Spy()
    themes, _ = cluster_requests(requests, spy, k=6)
    arr = [t.arr_at_stake for t in themes]
    assert arr == sorted(arr, reverse=True)
    assert len(spy.prompts) == len(themes)
    assert all(p.startswith("Top terms:") and "- " in p for p in spy.prompts)
