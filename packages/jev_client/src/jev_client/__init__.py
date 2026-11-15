"""Budget-guarded access to Jev, TypeSafe's typed-question model.

Jev answers bounded, typed questions about a piece of state rather than
generating prose, which is the right shape for screening literature: many
independent judgments per paper and no free text to parse.

Everything here is deliberately vendor-neutral at the transport level -- see
:mod:`jev_client.client` for why.
"""

from jev_client.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PRICE_PER_MTOK_USD,
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

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_PRICE_PER_MTOK_USD",
    "Answer",
    "Budget",
    "BudgetExceeded",
    "JevClient",
    "JevError",
    "__version__",
    "choice",
    "estimate_corpus_cost",
    "noul",
    "score",
]
