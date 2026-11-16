"""Pre-commit guard: refuse to commit anything that looks like an API key.

`.env` is gitignored, which covers the expected path. This covers the
*unexpected* one: a key pasted into a notebook cell, a question set, a results
file or a README while debugging. That mistake is invisible until the fork is
public, and by then the key is already out.

Fails closed and names the file and line, without ever printing the secret.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# An assignment with something substantial after it -- an empty placeholder in
# .env.example must stay committable.
ASSIGNMENT = re.compile(
    r"""(TYPESAFE_API_KEY|API_KEY|SECRET|TOKEN)\s*[=:]\s*['"]?([^\s'"#]{16,})""",
    re.IGNORECASE,
)
# Bearer headers pasted from curl examples.
BEARER = re.compile(r"Authorization\s*:\s*Bearer\s+\S{16,}", re.IGNORECASE)

PLACEHOLDERS = {
    "test-key",
    "your-key-here",
    "changeme",
    "xxx",
    "<api_key>",
    "<your_key>",
}

# Values that announce themselves as fixtures. Prefix matching rather than an
# exact list, so a new test fixture does not need this file edited -- a
# too-strict guard is one people stop running.
PLACEHOLDER_PREFIXES = (
    "fake-",
    "dummy-",
    "example-",
    "test-",
    "placeholder",
    "sk-test",
)


def offending_lines(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = ASSIGNMENT.search(line)
        value = match.group(2).lower() if match else ""
        if match and not (
            value in PLACEHOLDERS or value.startswith(PLACEHOLDER_PREFIXES)
        ):
            hits.append((number, match.group(1)))
        elif BEARER.search(line):
            hits.append((number, "Authorization: Bearer"))
    return hits


def main(argv: list[str]) -> int:
    failures = 0
    for name in argv:
        path = Path(name)
        if not path.is_file():
            continue
        for number, what in offending_lines(path):
            print(f"{path}:{number}: looks like a secret ({what})")
            failures += 1
    if failures:
        print(
            "\nRefusing to commit. If this is a real key:\n"
            "  1. remove it from the file and put it in .env instead;\n"
            "  2. if it was ever pushed, rotate it at console.typesafe.ai.\n"
            "If it is a placeholder, add it to PLACEHOLDERS in "
            "scripts/check_no_secrets.py."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
