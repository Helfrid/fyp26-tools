"""Tests for the Jev client: budget enforcement, caching, retries, parsing.

Every test runs against an httpx MockTransport, so the suite never touches the
network and never spends anything.
"""

from __future__ import annotations

import json

import httpx
import pytest

from jev_client import (
    Answer,
    Budget,
    BudgetExceeded,
    JevClient,
    JevError,
    choice,
    estimate_corpus_cost,
    noul,
    score,
)

ABSTRACT = "A PROTAC recruiting CRBN degrades PPP1CC with a DC50 of 12 nM."
QUESTIONS = {"on_target": noul("The abstract reports degradation of PPP1CC")}


def _response(noul_value: float = 0.97, input_tokens: int = 400) -> dict:
    return {
        "model": "jev-1.14.0",
        "answers": {"on_target": {"type": "noul", "noul": noul_value}},
        "usage": {"input_tokens": input_tokens, "output_tokens": 0},
    }


def _client(handler, **kwargs) -> JevClient:
    return JevClient(
        budget=kwargs.pop("budget", Budget(max_usd=1.0)),
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


# ---- question builders ----


def test_choice_requires_two_options():
    with pytest.raises(ValueError):
        choice("pick one", ["only"])


def test_score_requires_a_range():
    with pytest.raises(ValueError):
        score("rate it", minimum=5, maximum=5)


# ---- answers ----


def test_answer_normalises_each_type():
    a = Answer.from_payload({"type": "noul", "noul": 0.4})
    assert a.value == 0.4 and a.confidence is None

    b = Answer.from_payload(
        {
            "type": "choice",
            "choice": "protac",
            "confidence": 0.8,
            "probabilities": {"protac": 0.8, "none": 0.2},
        }
    )
    assert b.value == "protac"
    assert b.probabilities is not None and b.probabilities["protac"] == 0.8


def test_answer_rejects_unknown_type():
    with pytest.raises(JevError):
        Answer.from_payload({"type": "vibes", "vibes": 1})


def test_answer_rejects_missing_value():
    with pytest.raises(JevError):
        Answer.from_payload({"type": "noul", "confidence": 0.5})


# ---- budget ----


def test_budget_prices_from_reported_usage():
    budget = Budget(max_usd=1.0)
    budget.record(1_000_000)
    assert budget.spent_usd == pytest.approx(0.042)
    assert budget.requests == 1


def test_budget_blocks_before_the_call_is_made():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_response())

    # A ceiling far below the cost of even one request.
    with (
        _client(handler, budget=Budget(max_usd=1e-9)) as jev,
        pytest.raises(BudgetExceeded),
    ):
        jev.ask(ABSTRACT, QUESTIONS)
    assert calls == [], "budget must block before anything is sent"


def test_budget_stops_a_runaway_loop():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response(input_tokens=500_000))

    budget = Budget(max_usd=0.05)
    with _client(handler, budget=budget) as jev, pytest.raises(BudgetExceeded):
        for _ in range(100):
            jev.ask(ABSTRACT, QUESTIONS, use_cache=False)
    assert budget.spent_usd <= budget.max_usd
    assert budget.requests < 100


def test_estimate_is_pessimistic_against_real_usage():
    """The pre-flight estimate must never undercount, or the guard leaks."""
    text = "word " * 500
    assert Budget.estimate_tokens(text) >= len(text.split())


# ---- requests ----


def test_ask_sends_the_documented_shape():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["_auth"] = request.headers["authorization"]
        seen["_path"] = request.url.path
        return httpx.Response(200, json=_response())

    with _client(handler) as jev:
        answers = jev.ask(ABSTRACT, QUESTIONS)

    assert seen["_path"] == "/v1/systemone"
    assert seen["_auth"] == "Bearer test-key"
    assert seen["state"] == ABSTRACT
    assert seen["questions"] == QUESTIONS
    assert answers["on_target"].value == 0.97


def test_empty_question_set_is_rejected():
    with (
        _client(lambda r: httpx.Response(200, json=_response())) as jev,
        pytest.raises(ValueError),
    ):
        jev.ask(ABSTRACT, {})


def test_http_error_surfaces_as_jev_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad question type")

    with _client(handler) as jev, pytest.raises(JevError, match="400"):
        jev.ask(ABSTRACT, QUESTIONS)


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("jev_client.client.time.sleep", lambda _: None)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json=_response())

    with _client(handler) as jev:
        assert jev.ask(ABSTRACT, QUESTIONS)["on_target"].value == 0.97
    assert attempts["n"] == 2


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("jev_client.client.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with (
        _client(handler, max_retries=2) as jev,
        pytest.raises(JevError, match="giving up"),
    ):
        jev.ask(ABSTRACT, QUESTIONS)


def test_malformed_response_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "jev-1.14.0"})

    with _client(handler) as jev, pytest.raises(JevError, match="answers"):
        jev.ask(ABSTRACT, QUESTIONS)


# ---- caching ----


def test_cache_hit_costs_nothing(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_response())

    budget = Budget(max_usd=1.0)
    with _client(handler, budget=budget, cache_dir=tmp_path) as jev:
        jev.ask(ABSTRACT, QUESTIONS)
        spent_after_first = budget.spent_usd
        jev.ask(ABSTRACT, QUESTIONS)

    assert calls["n"] == 1, "second identical ask must not hit the network"
    assert budget.spent_usd == spent_after_first


def test_cache_misses_when_the_question_changes(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_response())

    with _client(handler, cache_dir=tmp_path) as jev:
        jev.ask(ABSTRACT, QUESTIONS)
        jev.ask(ABSTRACT, {"on_target": noul("A different question entirely")})

    assert calls["n"] == 2


def test_corrupt_cache_entry_is_ignored(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response())

    with _client(handler, cache_dir=tmp_path) as jev:
        jev.ask(ABSTRACT, QUESTIONS)
        for path in tmp_path.glob("*.json"):
            path.write_text("{not json")
        assert jev.ask(ABSTRACT, QUESTIONS)["on_target"].value == 0.97


# ---- estimation ----


def test_estimate_corpus_cost_scales_with_corpus():
    one = estimate_corpus_cost([ABSTRACT], QUESTIONS)
    ten = estimate_corpus_cost([ABSTRACT] * 10, QUESTIONS)
    assert ten["n_requests"] == 10
    assert ten["estimated_usd"] == pytest.approx(float(one["estimated_usd"]) * 10)


def test_a_thousand_abstracts_is_pennies():
    """Guards the claim the cost plan rests on."""
    cost = estimate_corpus_cost([ABSTRACT * 4] * 1000, QUESTIONS)
    assert float(cost["estimated_usd"]) < 0.10


def test_missing_api_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(JevError, match="TYPESAFE_API_KEY"):
        JevClient(budget=Budget(max_usd=1.0))
