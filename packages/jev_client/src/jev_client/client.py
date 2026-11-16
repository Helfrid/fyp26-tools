"""Jev (TypeSafe System One) client for typed abstract classification.

Jev answers *bounded, typed questions* about a piece of state rather than
generating prose. One request carries many questions; each is evaluated in
parallel and in isolation against the same state, and each returns a typed
answer with a probability or confidence. That is the right shape for abstract
screening: dozens of independent judgments per paper, no free text to parse.

Deliberately built on ``httpx`` rather than the vendor SDK, for three reasons:

* ``base_url`` stays configurable, so a reseller endpoint or a recorded-replay
  stub can be swapped in without touching call sites;
* every response passes through :class:`Budget`, so a runaway loop stops at a
  spend ceiling instead of at the credit-card statement;
* responses are cached on disk by content hash, so re-running a scan over an
  unchanged corpus costs nothing.

Usage::

    budget = Budget(max_usd=1.00)
    with JevClient(budget=budget) as jev:
        answers = jev.ask(abstract_text, {
            "on_target": noul("The abstract reports degradation of PPP1CC"),
            "modality": choice("Degrader modality used",
                               ["protac", "molecular_glue", "other", "none"]),
        })
    print(answers["on_target"].value, budget.spent_usd)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from loguru import logger

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.14.0"
ENDPOINT = "/v1/systemone"

# Official list price, 2026-11: $42 per Btok input, output free. A reseller
# charges differently, so this is a parameter rather than a constant in the
# pricing maths -- see Budget(price_per_mtok=...).
DEFAULT_PRICE_PER_MTOK_USD = 0.042

QuestionType = Literal["noul", "choice", "score", "box"]


class JevError(RuntimeError):
    """A Jev request failed, or returned something we cannot interpret."""


class BudgetExceeded(JevError):
    """The configured spend ceiling would be crossed by this request."""


# ---- question builders ------------------------------------------------------
#
# Thin dict builders rather than classes: the wire format is already a plain
# mapping, and keeping it that way makes a question set trivially serialisable
# into a run manifest alongside the results.


def noul(
    instructions: str,
    criteria: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """An independent 0-1 judgment ("how true is this of the state?").

    Prefer several Nouls over one multi-label Choice: they are scored
    independently, so adding a label later does not shift the others.
    ``criteria`` optionally describes what ``true`` and ``false`` mean.
    """
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria:
        unknown = set(criteria) - {"true", "false"}
        if unknown:
            raise ValueError(
                f"noul criteria keys must be 'true'/'false', got {sorted(unknown)}"
            )
        question["criteria"] = criteria
    return question


def choice(
    instructions: str,
    criteria: dict[str, str | None] | list[str],
) -> dict[str, Any]:
    """A single pick from a closed set of named options.

    The API takes ``criteria`` as an object mapping each option name to a
    description, where the description may be ``None`` when the name speaks
    for itself. A plain list of names is accepted here and expanded to that
    form, because most question sets do not need per-option prose.

    Always include an explicit escape option (``"none"``, ``"unsure"``,
    ``"unclear"``, ``"not_stated"`` or ``"manual_review"``) so the model is
    never forced into a wrong bucket.
    """
    if isinstance(criteria, list):
        criteria = {name: None for name in criteria}
    if not 1 <= len(criteria) <= 255:
        raise ValueError(f"choice needs 1-255 options, got {len(criteria)}")
    if len(criteria) < 2:
        raise ValueError("a choice needs at least two options to be meaningful")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, criteria: list[str]) -> dict[str, Any]:
    """An ordinal rating over named levels, lowest first.

    ``criteria`` is an ordered list of level descriptions; position sets the
    score, **starting at 0**. So three levels score 0, 1, 2 — not 1-5. The
    returned score may be fractional, since it is the expectation over the
    probability distribution rather than the top pick.
    """
    if not 1 <= len(criteria) <= 10:
        raise ValueError(f"score needs 1-10 levels, got {len(criteria)}")
    if len(criteria) < 2:
        raise ValueError("a score needs at least two levels to be meaningful")
    return {"type": "score", "instructions": instructions, "criteria": criteria}


@dataclass(frozen=True)
class Answer:
    """One typed answer, normalised across question types.

    ``value`` is the answer proper (a float for noul/score, a string for
    choice); ``confidence`` is the model's own confidence where it reports one
    (choice, score, box) and ``None`` for noul, which *is* a probability.
    ``legend`` maps a score's integer levels back to their descriptions.
    ``raw`` keeps the untouched payload so nothing is lost by normalising.
    """

    type: QuestionType
    value: Any
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    legend: dict[str, str] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Answer:
        kind = payload.get("type")
        if kind not in ("noul", "choice", "score", "box"):
            raise JevError(f"unknown answer type: {kind!r}")
        value = payload.get(kind)
        if value is None:
            raise JevError(f"answer of type {kind!r} carries no {kind!r} field")
        return cls(
            type=kind,
            value=value,
            confidence=payload.get("confidence"),
            probabilities=payload.get("probabilities"),
            legend=payload.get("legend"),
            raw=payload,
        )


# ---- budget -----------------------------------------------------------------


@dataclass
class Budget:
    """A hard spend ceiling enforced locally, before and after every call.

    The vendor meters input tokens and bills only those. We cannot know the
    exact count before sending, so the pre-flight check uses a conservative
    character-based estimate and the post-flight accounting uses the exact
    ``usage.input_tokens`` the response reports. The estimate only ever
    *blocks* a call; it never under-reports actual spend.

    This exists because the realistic failure mode is not an expensive corpus
    -- 1000 abstracts costs a few cents -- but a loop that retries forever.
    """

    max_usd: float
    price_per_mtok: float = DEFAULT_PRICE_PER_MTOK_USD
    spent_usd: float = 0.0
    input_tokens: int = 0
    requests: int = 0
    peak_request_usd: float = 0.0

    def price(self, tokens: int) -> float:
        """Cost in USD of ``tokens`` input tokens."""
        return tokens * self.price_per_mtok / 1_000_000

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative token estimate: ~3 characters per token.

        Deliberately pessimistic (real English is closer to 4) so the guard
        trips early rather than late.
        """
        return max(1, len(text) // 3)

    def check(self, estimated_tokens: int) -> None:
        """Raise :class:`BudgetExceeded` if this call would cross the ceiling.

        The character estimate only covers the text *we* send. The vendor bills
        the tokens it actually processes, which can be substantially more, so
        the guard also carries forward the most expensive request seen so far
        and assumes this one could cost the same. Without that, a single
        unexpectedly large call can overshoot the ceiling outright; with it,
        the overshoot is bounded and the guard tightens as it learns.
        """
        projected = self.spent_usd + max(
            self.price(estimated_tokens), self.peak_request_usd
        )
        if projected > self.max_usd:
            raise BudgetExceeded(
                f"request would take spend to ${projected:.4f}, over the "
                f"${self.max_usd:.2f} ceiling "
                f"(already spent ${self.spent_usd:.4f} over {self.requests} requests)"
            )

    def record(self, input_tokens: int) -> None:
        """Account for a completed call using the reported token usage."""
        cost = self.price(input_tokens)
        self.input_tokens += input_tokens
        self.spent_usd += cost
        self.peak_request_usd = max(self.peak_request_usd, cost)
        self.requests += 1


# ---- client -----------------------------------------------------------------


def _cache_key(model: str, state: str, questions: dict[str, Any]) -> str:
    """Stable hash of everything that determines an answer."""
    blob = json.dumps(
        {"model": model, "state": state, "questions": questions},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class JevClient:
    """Synchronous Jev client with budget enforcement and on-disk caching."""

    def __init__(
        self,
        *,
        budget: Budget,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        cache_dir: Path | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = api_key or os.getenv("TYPESAFE_API_KEY")
        if not key:
            raise JevError(
                "no API key: set TYPESAFE_API_KEY (in .env) or pass api_key="
            )
        self.budget = budget
        self.model = model
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            base_url=base_url or os.getenv("TYPESAFE_BASE_URL", DEFAULT_BASE_URL),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> JevClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- cache --

    def _cached(self, key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("discarding corrupt cache entry {}", path)
            return None

    def _store(self, key: str, payload: dict[str, Any]) -> None:
        if self.cache_dir is not None:
            (self.cache_dir / f"{key}.json").write_text(json.dumps(payload))

    # -- request --

    def ask(
        self,
        state: str,
        questions: dict[str, dict[str, Any]],
        *,
        use_cache: bool = True,
    ) -> dict[str, Answer]:
        """Ask every question in ``questions`` about ``state``.

        Returns answers keyed by the same question ids. A cache hit costs
        nothing and is not charged against the budget.
        """
        if not questions:
            raise ValueError("no questions to ask")

        key = _cache_key(self.model, state, questions)
        if use_cache:
            hit = self._cached(key)
            if hit is not None:
                logger.debug("jev cache hit {}", key[:12])
                return self._parse(hit)

        body = {"state": state, "model": self.model, "questions": questions}
        estimated = self.budget.estimate_tokens(json.dumps(body, ensure_ascii=False))
        self.budget.check(estimated)

        payload = self._post(body)
        usage = payload.get("usage") or {}
        self.budget.record(int(usage.get("input_tokens", estimated)))
        if use_cache:
            self._store(key, payload)
        return self._parse(payload)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST with 429/5xx retry, honouring ``retry-after`` when present."""
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.post(ENDPOINT, json=body)
            except httpx.HTTPError as exc:  # network-level
                last = exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                wait = float(response.headers.get("retry-after") or 2**attempt)
                logger.warning(
                    "jev {} -- retrying in {}s ({}/{})",
                    response.status_code,
                    wait,
                    attempt + 1,
                    self.max_retries,
                )
                last = JevError(f"HTTP {response.status_code}")
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                raise JevError(f"HTTP {response.status_code}: {response.text[:300]}")
            try:
                return dict(response.json())
            except json.JSONDecodeError as exc:
                raise JevError("response was not JSON") from exc
        raise JevError(f"giving up after {self.max_retries} attempts: {last}")

    @staticmethod
    def _parse(payload: dict[str, Any]) -> dict[str, Answer]:
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise JevError("response carries no 'answers' object")
        return {qid: Answer.from_payload(a) for qid, a in answers.items()}


def estimate_corpus_cost(
    states: list[str],
    questions: dict[str, dict[str, Any]],
    *,
    price_per_mtok: float = DEFAULT_PRICE_PER_MTOK_USD,
    model: str = DEFAULT_MODEL,
) -> dict[str, float | int]:
    """Price a whole scan before spending anything.

    Run this first, every time. It is the cheapest possible sanity check that
    a question set and a corpus are the size you think they are.
    """
    overhead = json.dumps({"model": model, "questions": questions})
    total = sum(
        Budget.estimate_tokens(state) + Budget.estimate_tokens(overhead)
        for state in states
    )
    return {
        "n_requests": len(states),
        "estimated_input_tokens": total,
        "estimated_usd": total * price_per_mtok / 1_000_000,
    }
