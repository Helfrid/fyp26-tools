# fyp26-tools

Literature-screening tools for **FYP26**. A uv workspace: each stage of the
project is its own package, so a student can be given one tool at a time and
a stage that is still being written cannot break the stage before it.

```
packages/
  common_utils/       loguru + dotenv logging setup (from uv-start)
  jev_client/         budget-guarded access to the Jev typed-question API
  abstract_scanner/   CLI: screen abstracts against a frozen question set
```

## The student workflow

Each stage hands the next one a **file**, never a live object. A student who
gets stuck on stage 2 can still start stage 3 from the supplied results file,
and an agent driving the CLI can be re-run at any point without redoing the
earlier work.

| Stage | Tool | Produces |
|---|---|---|
| 1. Build a corpus | existing PubMed search | `pool.json` |
| 2. Write the questions | `abstract-scanner validate` | a frozen `.toml` question set |
| 3. Price it | `abstract-scanner estimate` | a cost, before any spend |
| 4. Scan abstracts | `abstract-scanner scan` | `results.jsonl` + `.manifest.json` |
| 5. Read full papers | `paper-analysis` *(next)* | deeper structured records |
| 6. Score against ground truth | `evaluate` *(planned)* | metrics + the first result figure |
| 7. Scan the phosphatase literature | stages 2–4, at scale | the actual dataset |

Stage 6 is the gate: the phosphatase scan in stage 7 is only worth running
once accuracy against hand-labelled ground truth is known.

## Data in this repository

| Path | What |
|---|---|
| `input_data/` | The 250 abstracts assigned to students S1-S5 in phase 1 |
| `abstracts_annotated/` | The students' own classifications — the reference the model is scored against |

Abstract text and bibliographic metadata are facts about the literature, not
protected expression, and are redistributed here so the evaluation is
reproducible. Model output is **not** committed: regenerate it with
`abstract-scanner scan`.

## Setup

```bash
uv sync --all-packages
cp .env.example .env     # then paste the key into .env
```

`TYPESAFE_API_KEY` belongs in `.env`, which is gitignored.

**Paste the key into `.env` in your editor, not through the agent.** Anything
typed into a Claude Code session — including a `!` shell command — is written
to the session transcript on disk. Opening the file and pasting keeps the key
out of every transcript.

The project runs on one shared key against a card with a hard £10 cap. The key
is rotated once the analysis is finished.

## Spending

Jev bills input tokens only, at $0.042/Mtok, so a thousand abstracts costs a
few pence. The risk is not the per-token price but a leaked key or a runaway
loop, so:

- `--budget` is a required argument on `scan`; there is no default;
- the ceiling is enforced locally, before and after every call, and the run
  stops itself rather than crossing it;
- `--cache` makes re-runs free while a question set is being tuned;
- `estimate` prices a whole scan without sending anything.

Use the vendor directly at [typesafe.ai](https://docs.typesafe.ai) — not a
reseller.

## Development

```bash
uv run pytest          # 45 tests, none touch the network
uv run ruff check .
uv run ty check packages
```
