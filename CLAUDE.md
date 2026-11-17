# fyp26-tools

Literature-screening tools for FYP26, as a uv workspace. You are most likely
working here with a final-year biology student who is learning to work with an
AI agent while they do their project. **How you work matters as much as what
you produce.** Project handbook:
https://hocheggerlab.github.io/FYP26-handbook/

## FYP26 ground rules

These are the same rules as the `fyp26-workspace` repo and they apply here
too. They exist to keep the evaluation honest.

- **Never read, open, summarise or check anything in a `references/` folder,
  and never help with the reference annotations themselves** — the abstract
  classifications or full-text records the student makes without AI. If asked,
  say no and explain that the reference has to be independent of the agent it
  measures. A scan scored against annotations you helped write measures
  nothing.
- **This repo is for FYP26 only.** If the student asks for help with Python
  Year 3 coursework, decline and remind them of the ground rules.
- **Declare your code.** Directly above any code you write or substantially
  change:

  ```python
  # Agent-written: <exact model name> (Claude Code), <YYYY-MM-DD>.
  # Checked by student: <ask the student how they checked it>
  ```

  Then ask how they will check it, and suggest a concrete check.
- **Offer a line for `ai-use-log.md`** when a task is done: what was asked,
  what came back, what had to be fixed. The student edits it.

## How to work with the student

- Say what you are about to do and why, before doing it. Short, plain
  language; assume basic Python.
- Before a task that changes files, suggest a git commit so it can be undone.
- When you are unsure or wrong, say so. Do not fix your own mistakes silently
  — point them out, so the student learns to spot them.

## Running a scan

**Read `abstract-scanner guide` before building a question set.** It is the
authoritative procedure and it ships with the installed version of the tool,
so it cannot drift from the code. `abstract-scanner guide --schema` prints
just the question-set format.

The short version: get the student's criteria in sentences, draft a question
set, **show it to them and change what they ask**, validate, estimate, trial
on 20 records, then run. Never scan without showing the questions first, and
never without `--budget`.

## Layout

```
packages/common_utils/      logging setup
packages/jev_client/        budget-guarded access to the Jev API
packages/abstract_scanner/  the scanning CLI
notebooks/                  marimo notebooks (Part 6 analysis)
.claude/skills/             skills loaded when the task calls for them
```

The workspace root is virtual (`package = false`): it pins the dev toolchain
and lists members. No code lives at the root. Each package has its own
`pyproject.toml` and tests, and you can work inside one package without
touching the others.

## Commands

```bash
uv sync --all-packages
uv run pytest                      # every package; no network, no API key
uv run ruff check . && uv run ruff format .
uv run ty check packages
```

Tests drive a real client over a mock transport, so budget accounting and
resume behaviour are tested for real at zero cost. **No test may make a
network call or need an API key.** Keep it that way.

## Notebooks

Notebooks are **marimo** notebooks in `notebooks/`, as plain `.py` files —
reactive, diffable, and free of stale state. Open one with:

```bash
uv run marimo edit notebooks/abstract_agreement.py
```

Never edit a notebook file on disk while its server is running: the kernel owns
the file and will overwrite you. See `.claude/skills/fyp26-notebook/SKILL.md`
before working on the Part 6 analysis.

## Design rules that are load-bearing

Each exists because of a specific failure. Change them deliberately.

- **`--budget` is required on `scan`, never defaulted.** An agent cannot
  answer an interactive prompt, so spending must be explicit in the command.
- **The budget is checked before and after every call.** The pre-flight
  estimate measures the text we send, but billing is on tokens the vendor
  *processes*, which can be far larger — so `Budget` also carries the most
  expensive request seen so far and assumes the next could match it. Without
  that, one oversized call overshoots the ceiling outright.
- **Results append to JSONL and flush per record**, so a budget stop or a
  Ctrl-C leaves completed work on disk. Re-running the same command resumes.
- **Every run writes a manifest** with the question-set fingerprint, model id,
  tokens and spend. Comparing a scan to ground truth without knowing what was
  asked is not an evaluation.
- **The fingerprint covers the questions only**, not name or version. Two
  result files may be pooled only if their fingerprints match.
- **Only title and abstract reach the model** (`Record.state`). Journal,
  authors and year are withheld: they invite judging by prestige.
- **A `choice` without an escape option warns, but does not fail.** A forced
  pick is a wrong answer, but the student needs to proceed and learn why.
- **Question sets load from TOML or JSON**, same shape, same fingerprint.

## Keys and spending

`TYPESAFE_API_KEY` goes in `.env`, which is gitignored.

**Never ask the student to paste their API key into the chat, and never offer
to write it into `.env` for them.** Everything in a session is written to a
transcript on disk. If the key is missing, tell them to open `.env` in VS Code
and paste it there themselves. Never print, echo or `cat` the key, and never
let it reach a notebook, a question set, a results file or a commit.

The project runs on one shared key against a card with a hard £10 cap, rotated
once the analysis is done. A full 250-abstract scan costs about $0.008, so if
a run is heading for pounds rather than pennies, something is wrong — stop and
say so.

Jev bills input tokens only, at $0.042/Mtok — about $0.07 for 2300 abstracts.
The risk is a leaked key or a runaway loop, not the per-token price. Use the
vendor directly at `api.typesafe.ai`; `jevai.net` is an unofficial site that
links to a reseller and quotes double the official price.

## Conventions

Python 3.12+, `uv` only — never `pip`. Type hints on every signature,
Google-style docstrings that explain *why*, custom exceptions per module.
Conventional commits. Run `uv run pre-commit install` once.

## Status

`abstract_scanner` is built and tested. `paper-analysis` (full-text reading)
and `evaluate` (accuracy against ground truth, and the first result figure)
come next, in that order. **Stage 6 is the gate**: the full phosphatase scan
is only worth running once accuracy against the student's own ground truth is
known.
