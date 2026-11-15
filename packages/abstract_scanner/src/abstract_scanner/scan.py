"""Running a scan: incremental output, resumable, and always manifested.

Two properties matter more than speed here.

*Partial work survives.* Results are appended to JSONL as they arrive, so a
budget stop, a network failure or a Ctrl-C leaves everything scanned so far on
disk. The run can then be resumed and only the missing ids are sent.

*Every run is self-describing.* The manifest records the question-set
fingerprint, the model id, the token count and the actual spend. Comparing a
scan against ground truth without knowing exactly what was asked is not an
evaluation, and a month later nobody remembers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from abstract_scanner.corpus import Record
from abstract_scanner.questions import QuestionSet
from jev_client import Budget, BudgetExceeded, JevClient, JevError


@dataclass
class RunManifest:
    """Everything needed to say what a results file actually is."""

    question_set: str
    question_set_version: str
    question_fingerprint: str
    model: str
    n_records: int = 0
    n_scanned: int = 0
    n_skipped_existing: int = 0
    n_failed: int = 0
    input_tokens: int = 0
    spent_usd: float = 0.0
    stopped_early: bool = False
    stop_reason: str | None = None
    started: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    finished: str | None = None

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))


def completed_ids(path: Path) -> set[str]:
    """Ids already present in a results file, for resuming a stopped run."""
    if not path.is_file():
        return set()
    done: set[str] = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            done.add(str(json.loads(line)["id"]))
        except (json.JSONDecodeError, KeyError):
            logger.warning("ignoring unreadable line in {}", path.name)
    return done


def scan(
    records: list[Record],
    question_set: QuestionSet,
    client: JevClient,
    out_path: Path,
    *,
    resume: bool = True,
) -> RunManifest:
    """Scan every record, appending one JSON object per line to ``out_path``.

    Returns the manifest. The caller is responsible for writing it, so a
    stopped run still reports what it managed to do.
    """
    budget: Budget = client.budget
    manifest = RunManifest(
        question_set=question_set.name,
        question_set_version=question_set.version,
        question_fingerprint=question_set.fingerprint,
        model=client.model,
        n_records=len(records),
    )

    done = completed_ids(out_path) if resume else set()
    if done:
        logger.info("resuming: {} records already scanned", len(done))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("a") as handle:
        for record in records:
            if record.id in done:
                manifest.n_skipped_existing += 1
                continue
            try:
                answers = client.ask(record.state, question_set.questions)
            except BudgetExceeded as exc:
                manifest.stopped_early = True
                manifest.stop_reason = str(exc)
                logger.warning("stopping: {}", exc)
                break
            except JevError as exc:
                manifest.n_failed += 1
                logger.error("{}: {}", record.id, exc)
                continue

            handle.write(
                json.dumps(
                    {
                        "id": record.id,
                        "question_fingerprint": question_set.fingerprint,
                        "answers": {
                            qid: {
                                "type": a.type,
                                "value": a.value,
                                "confidence": a.confidence,
                                "probabilities": a.probabilities,
                            }
                            for qid, a in answers.items()
                        },
                    }
                )
                + "\n"
            )
            handle.flush()
            manifest.n_scanned += 1

    manifest.input_tokens = budget.input_tokens
    manifest.spent_usd = round(budget.spent_usd, 6)
    manifest.finished = datetime.now(UTC).isoformat(timespec="seconds")
    return manifest
