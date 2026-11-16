"""Question sets: authored as TOML, hashed, and frozen before a run.

A question set is the experiment. If it changes mid-way the results are no
longer comparable, so every set carries a name and version, and every run
records a fingerprint over the questions themselves. Comparing a scan against
ground truth is only meaningful once that fingerprint is fixed.

Two formats, same shape. **TOML** when a person writes it, because it takes
comments. **JSON** when an agent generates it from a student's description,
because that is what models emit reliably and what the student can then read
back and check. The loader dispatches on the file suffix; everything
downstream is identical, including the fingerprint::

    name = "phosphatase-screen"
    version = "1"

    [questions.on_target]
    type = "noul"
    instructions = "The abstract reports experimental work on PPP1CC"

    [questions.evidence]
    type = "choice"
    instructions = "Strongest evidence for a direct role"
    options = ["direct", "indirect", "none", "manual_review"]

A ``choice`` may instead give a description per option, which is the API's own
form and usually worth it when the names alone are ambiguous::

    [questions.evidence.criteria]
    direct = "The authors measured it themselves"
    none = "The abstract does not say"

A ``score`` takes ``levels``, an ordered list lowest first. **Position sets
the score, starting at 0** — three levels score 0, 1, 2, not 1 to 3::

    [questions.relevance]
    type = "score"
    instructions = "How relevant is this paper?"
    levels = ["Irrelevant", "Tangential", "Directly on topic"]
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jev_client import choice, noul, score

# Options that let the model decline rather than be forced into a wrong bucket.
ESCAPE_OPTIONS = frozenset(
    {
        "none",
        "not_stated",
        "unclear",
        "unsure",
        "insufficient_evidence",
        "manual_review",
    }
)

BUILDERS = {"noul": noul, "choice": choice, "score": score}


class QuestionSetError(RuntimeError):
    """The question set file is missing, malformed, or internally invalid."""


@dataclass(frozen=True)
class QuestionSet:
    """A named, versioned set of typed questions plus its fingerprint."""

    name: str
    version: str
    questions: dict[str, dict]
    warnings: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        """Hash of the questions, independent of name and version.

        Two runs with the same fingerprint asked exactly the same thing, so
        their outputs can be pooled; two runs with different fingerprints
        cannot, however similar the prose looks.
        """
        blob = json.dumps(self.questions, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    @property
    def label(self) -> str:
        return f"{self.name} v{self.version} ({self.fingerprint})"


def _criteria_from(spec: dict, qid: str) -> dict[str, str | None] | list[str]:
    """Accept either ``options = [...]`` or a ``criteria`` table/array.

    ``options`` is the short form for when the option names speak for
    themselves; ``criteria`` is the API's own form and allows a description
    per option. Both end up as the same wire payload.
    """
    if "criteria" in spec:
        criteria = spec["criteria"]
        if isinstance(criteria, dict):
            return {
                str(k): (None if v is None else str(v)) for k, v in criteria.items()
            }
        if isinstance(criteria, list):
            return [str(v) for v in criteria]
        raise QuestionSetError(f"question {qid!r}: criteria must be a table or list")
    options = spec.get("options")
    if isinstance(options, list):
        return [str(o) for o in options]
    raise QuestionSetError(
        f"question {qid!r}: needs options = [...] or a criteria table"
    )


def _build(qid: str, spec: dict) -> tuple[dict, list[str]]:
    """Turn one authored question into a wire dict, collecting design warnings."""
    kind = spec.get("type")
    if kind not in BUILDERS:
        raise QuestionSetError(
            f"question {qid!r}: type must be one of {sorted(BUILDERS)}, got {kind!r}"
        )
    instructions = spec.get("instructions")
    if not instructions or not str(instructions).strip():
        raise QuestionSetError(f"question {qid!r}: instructions must not be empty")

    warnings: list[str] = []
    try:
        if kind == "noul":
            built = noul(str(instructions), spec.get("criteria"))
        elif kind == "choice":
            criteria = _criteria_from(spec, qid)
            built = choice(str(instructions), criteria)
            names = {str(n).lower() for n in criteria}
            if not ESCAPE_OPTIONS & names:
                warnings.append(
                    f"{qid}: no escape option — the model is forced to pick one "
                    f"of {sorted(names)}. Add one of {sorted(ESCAPE_OPTIONS)}."
                )
        else:
            levels = spec.get("levels") or spec.get("criteria")
            if not isinstance(levels, list):
                raise QuestionSetError(
                    f"question {qid!r}: score needs levels = [...], an ordered "
                    f"list of level descriptions (lowest first)"
                )
            built = score(str(instructions), [str(level) for level in levels])
    except ValueError as exc:
        raise QuestionSetError(f"question {qid!r}: {exc}") from exc
    return built, warnings


def _parse(path: Path) -> dict:
    """Parse a question set file as TOML or JSON, by suffix."""
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise QuestionSetError(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise QuestionSetError(f"{path.name} must be a JSON object")
        return payload
    if suffix in (".toml", ""):
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise QuestionSetError(f"{path.name} is not valid TOML: {exc}") from exc
    raise QuestionSetError(f"question sets must be .toml or .json, got {path.suffix!r}")


def load_question_set(path: Path) -> QuestionSet:
    """Read, validate and fingerprint a question set (TOML or JSON)."""
    if not path.is_file():
        raise QuestionSetError(f"no such question set: {path}")
    payload = _parse(path)

    raw = payload.get("questions")
    if not isinstance(raw, dict) or not raw:
        raise QuestionSetError(f"{path.name} defines no [questions.*] tables")

    questions: dict[str, dict] = {}
    warnings: list[str] = []
    for qid, spec in raw.items():
        if not isinstance(spec, dict):
            raise QuestionSetError(f"question {qid!r} is not a table")
        built, warns = _build(qid, spec)
        questions[qid] = built
        warnings.extend(warns)

    return QuestionSet(
        name=str(payload.get("name") or path.stem),
        version=str(payload.get("version") or "0"),
        questions=questions,
        warnings=tuple(warnings),
    )
