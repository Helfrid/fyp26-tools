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
    {"none", "not_stated", "unclear", "insufficient_evidence", "manual_review"}
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


def _build(qid: str, spec: dict) -> tuple[dict, list[str]]:
    """Turn one TOML question into a wire dict, collecting design warnings."""
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
            built = noul(str(instructions))
        elif kind == "choice":
            options = spec.get("options")
            if not isinstance(options, list):
                raise QuestionSetError(f"question {qid!r}: choice needs options")
            built = choice(str(instructions), [str(o) for o in options])
            if not ESCAPE_OPTIONS & {str(o).lower() for o in options}:
                warnings.append(
                    f"{qid}: no escape option — the model is forced to pick one "
                    f"of {options}. Add one of {sorted(ESCAPE_OPTIONS)}."
                )
        else:
            built = score(
                str(instructions),
                minimum=int(spec.get("min", 1)),
                maximum=int(spec.get("max", 5)),
            )
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
