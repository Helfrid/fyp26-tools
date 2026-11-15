"""Loading abstracts from whatever the upstream step happened to write.

Students arrive with a PubMed export, a pool JSON from a corpus build, or a
spreadsheet a supervisor sent them. Rather than force one format, this reads
the three shapes that actually turn up and normalises them to
:class:`Record`.

Records without an abstract are dropped rather than sent: an empty state
costs money and returns confident nonsense.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

ID_FIELDS = ("id", "pmid", "PMID", "pmcid", "doi")
TITLE_FIELDS = ("title", "Title", "ti")
ABSTRACT_FIELDS = ("abstract", "Abstract", "ab")


class CorpusError(RuntimeError):
    """The corpus file could not be read, or carried no usable records."""


@dataclass(frozen=True)
class Record:
    """One paper, reduced to what the classifier is allowed to see."""

    id: str
    title: str
    abstract: str

    @property
    def state(self) -> str:
        """The text sent to the model: title and abstract, nothing else.

        Deliberately excludes journal, authors and year. Those invite the
        model to judge by prestige rather than content, and they are exactly
        the fields a reviewer would object to.
        """
        return f"{self.title}\n\n{self.abstract}".strip()


def _first(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = row.get(field)
        if value:
            return str(value).strip()
    return ""


def _rows(path: Path) -> list[dict]:
    """Rows from .jsonl, .json (list or {"articles": [...]}) or .csv."""
    if not path.is_file():
        raise CorpusError(f"no such corpus file: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            return [
                json.loads(line)
                for line in path.read_text().splitlines()
                if line.strip()
            ]
        if suffix == ".json":
            payload = json.loads(path.read_text())
            if isinstance(payload, dict):
                for key in ("articles", "records", "items"):
                    if isinstance(payload.get(key), list):
                        return payload[key]
                raise CorpusError(
                    f"{path.name} is an object with no 'articles' list in it"
                )
            if isinstance(payload, list):
                return payload
            raise CorpusError(f"{path.name} is neither a list nor an object")
        if suffix == ".csv":
            with path.open(newline="") as handle:
                return list(csv.DictReader(handle))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path.name} is not valid JSON: {exc}") from exc
    raise CorpusError(f"unsupported corpus format: {path.suffix!r}")


def load_records(path: Path) -> list[Record]:
    """Read a corpus file and return the records that can actually be scanned."""
    rows = _rows(path)
    records: list[Record] = []
    no_abstract = 0
    no_id = 0
    for index, row in enumerate(rows):
        abstract = _first(row, ABSTRACT_FIELDS)
        if not abstract:
            no_abstract += 1
            continue
        identifier = _first(row, ID_FIELDS)
        if not identifier:
            no_id += 1
            identifier = f"row-{index}"
        records.append(
            Record(
                id=identifier,
                title=_first(row, TITLE_FIELDS),
                abstract=abstract,
            )
        )
    if no_abstract:
        logger.warning(
            "skipped {} of {} records with no abstract", no_abstract, len(rows)
        )
    if no_id:
        logger.warning("{} records had no id; using row numbers", no_id)
    if not records:
        raise CorpusError(f"{path.name} yielded no records with an abstract")

    duplicates = len(records) - len({r.id for r in records})
    if duplicates:
        logger.warning("{} duplicate ids in the corpus", duplicates)
    logger.info("loaded {} records from {}", len(records), path.name)
    return records
