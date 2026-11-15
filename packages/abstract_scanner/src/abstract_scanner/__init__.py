"""Screen PubMed abstracts with typed Jev questions.

The pipeline is three files deep on purpose: :mod:`abstract_scanner.corpus`
normalises whatever the upstream step wrote, :mod:`abstract_scanner.questions`
freezes what is being asked, and :mod:`abstract_scanner.scan` runs it with a
spend ceiling and a manifest. The CLI in :mod:`abstract_scanner.cli` is the
surface a student's agent drives.
"""

from abstract_scanner.corpus import CorpusError, Record, load_records
from abstract_scanner.questions import (
    QuestionSet,
    QuestionSetError,
    load_question_set,
)
from abstract_scanner.scan import RunManifest, scan

__version__ = "0.1.0"

__all__ = [
    "CorpusError",
    "QuestionSet",
    "QuestionSetError",
    "Record",
    "RunManifest",
    "__version__",
    "load_question_set",
    "load_records",
    "scan",
]
