"""Unit + integration tests. Run: pytest -q"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("STORE_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient

from app.entities import entity_signal, resolve
from app.main import app
from app.scoring import novelty_signal, priority_of, recency_signal, score
from app.store import canonicalise, hamming, jaccard, simhash, tokenise

client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}


# --------------------------- entity resolution ---------------------------- #

def test_alias_forms_collapse_to_one_symbol():
    for text in ("The Federal Reserve held rates", "FOMC minutes released",
                 "Powell signals patience on rates"):
        assert [e["symbol"] for e in resolve(text)] == ["FED"], text


def test_generic_word_needs_financial_context():
    assert resolve("Apple harvest season begins") == []
    assert [e["symbol"] for e in resolve("Apple shares fall on weak guidance")] == ["AAPL"]


def test_fed_up_is_not_the_fed():
    assert resolve("I am fed up with the weather") == []


def test_unverified_llm_hint_is_discounted():
    verified = resolve("Nvidia earnings beat", [])
    hinted = resolve("Chipmaker beats expectations", ["NVDA"])
    assert hinted[0]["matched"] == ["llm_hint"]
    assert hinted[0]["weight"] < verified[0]["weight"]


def test_entity_signal_saturates_not_averages():
    one_strong = entity_signal(resolve("Nvidia earnings beat"))
    plus_weak = entity_signal(resolve("Nvidia earnings beat; gold price steady"))
    assert plus_weak >= one_strong


# ------------------------------- clustering ------------------------------- #

def test_canonicalise_strips_tracking_params():
    assert canonicalise("https://www.reuters.com/a/b/?utm_source=x&id=7") == \
        "https://reuters.com/a/b?id=7"


def test_tokenise_drops_stopwords():
    assert "the" not in tokenise("The Fed and the market")


def test_simhash_distance_tracks_similarity():
    a = simhash("Fed holds interest rates steady as inflation cools")
    b = simhash("Federal Reserve holds interest rates steady as inflation cools")
    c = simhash("Nvidia beats earnings on data centre demand")
    assert hamming(a, b) < hamming(a, c)


def test_jaccard_bounds():
    assert jaccard(set(), {"a"}) == 0.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


# -------------------------------- scoring --------------------------------- #

def test_recency_halves_at_half_life():
    now = datetime.now(timezone.utc)
    assert recency_signal(now - timedelta(hours=8), now) == pytest.approx(0.5, abs=0.01)
    assert recency_signal(None) == 0.5


def test_novelty_penalises_repeats_with_a_floor():
    assert novelty_signal(False, 1) == 1.0
    assert novelty_signal(True, 2) > novelty_signal(True, 5) >= 0.35


def test_repeat_story_scores_lower_than_the_original():
    now = datetime.now(timezone.utc)
    common = dict(impact_score=9, entity_signal_value=0.95,
                  published_at=now - timedelta(hours=1), source="reuters", now=now)
    first, _, _ = score(is_followup=False, cluster_size=1, **common)
    repeat, _, _ = score(is_followup=True, cluster_size=5, **common)
    assert first > repeat
    assert priority_of(first) == "high"


def test_score_is_deterministic():
    now = datetime.now(timezone.utc)
    args = dict(impact_score=7, entity_signal_value=0.8, published_at=now,
                source="cnbc", is_followup=False, cluster_size=1, now=now)
    assert score(**args)[0] == score(**args)[0]


def test_breakdown_weights_sum_to_one():
    from app.scoring import WEIGHTS
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


# ------------------------------ API surface ------------------------------- #

PAYLOAD = {
    "title": "Fed holds interest rates steady as inflation cools",
    "summary": "The Federal Reserve kept its benchmark rate unchanged.",
    "url": "https://www.reuters.com/markets/fed-holds/?utm_source=twitter",
    "source": "Reuters",
    "published_at": datetime.now(timezone.utc).isoformat(),
    "category": "monetary_policy",
    "impact_score": 8.5,
    "sentiment": "neutral",
    "tickers": ["SPX"],
}


def test_health_is_open():
    assert client.get("/health").json()["status"] == "ok"


def test_enrich_requires_api_key():
    assert client.post("/v1/enrich", json=PAYLOAD).status_code == 401


def test_enrich_returns_a_full_scored_payload():
    r = client.post("/v1/enrich", json=PAYLOAD, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["canonical_url"] == "https://reuters.com/markets/fed-holds"
    assert "FED" in [e["symbol"] for e in body["entities"]]
    assert 0 <= body["relevance_score"] <= 100
    assert body["priority"] in {"high", "medium", "low"}
    assert set(body["score_breakdown"]) == {
        "impact", "entity", "recency", "source", "novelty"}
    assert "X-Request-ID" in r.headers


def test_same_story_from_another_outlet_is_flagged_as_followup():
    client.post("/v1/enrich", json={**PAYLOAD,
                "url": "https://reuters.com/unique-1"}, headers=HEADERS)
    second = client.post("/v1/enrich", json={
        **PAYLOAD,
        "url": "https://cnbc.com/unique-2",
        "title": "Federal Reserve holds interest rates steady as inflation cools further",
        "source": "CNBC",
    }, headers=HEADERS).json()
    assert second["is_followup"] is True
    assert second["cluster_size"] >= 2


def test_invalid_payload_is_rejected_with_422():
    assert client.post("/v1/enrich", json={"title": "x"}, headers=HEADERS).status_code == 422


def test_stats_endpoint():
    body = client.get("/v1/stats", headers=HEADERS).json()
    assert body["articles_total"] >= 1
    assert isinstance(body["top_entities"], list)
