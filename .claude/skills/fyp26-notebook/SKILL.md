---
name: fyp26-notebook
description: >-
  Run and pair on the Part 6 agreement notebook (notebooks/abstract_agreement.py,
  a marimo notebook) — start the server, fill in the TODO cells, and keep the
  student able to explain every step. Use when the student is working on the
  abstract-agreement analysis or asks to open the notebook.
---

# The Part 6 agreement notebook

`notebooks/abstract_agreement.py` is a **marimo** notebook: a plain Python file,
not JSON. It diffs properly in git, and the student can read it in any editor.

## Starting it

```bash
uv run marimo edit notebooks/abstract_agreement.py --no-token
```

That opens a browser tab. The notebook stays running; the student edits cells
there, not in the file on disk.

`--no-token` is required for pairing: without it the session does not register
and `marimo pair notebook list` returns nothing. The server listens on
localhost only.

**The browser tab is the session.** A running server with no tab open cannot be
paired with. If the student starts Claude Code first and asks for help with the
notebook, the first thing to check is whether the notebook is actually open.

To check something without opening a browser:

```bash
uv run marimo export md notebooks/abstract_agreement.py   # parses and prints it
```

## What marimo changes

- **Reactive.** Changing a cell re-runs everything that depends on it. There is
  no "restart and run all", and no stale state.
- **A variable may only be defined in one cell.** A second definition is an
  error, not a silent overwrite. For a second version of something, use a new
  name.
- **Cells are functions.** A cell takes the variables it uses as arguments and
  returns the ones it defines. The file shows this explicitly — that is what
  makes the dependency graph real rather than a convention.
- **No `plt.show()`.** End the cell with the figure object and it renders.
- `mo.ui.table(df)` gives a sortable, paged table — much better than printing
  50 rows when reading the disagreements.

## Working with the student

The notebook is a scaffold with TODO cells. The analysis is theirs.

**Do:**
- Ask what they think the cell should do before writing it.
- Explain the two methodological decisions when they reach them (the join key
  in section 1, and the skip rule in section 3) — these go in their report and
  they must be able to defend them.
- After writing a cell, ask them to say back what it does. If they cannot, the
  cell is not finished regardless of whether it runs.
- Point out when a number looks suspicious (a join that loses rows, an
  agreement figure computed on four abstracts).

**Do not:**
- Fill in all the TODOs at once and hand back a finished notebook. They have to
  describe this analysis in a report, and "the agent wrote it" is not a
  description.
- Edit `notebooks/abstract_agreement.py` on disk while the notebook is running —
  the kernel owns the file and will overwrite you.
- Change anything in `question_sets/` or re-run the scan to make the numbers
  look better.
- Open, read or summarise anything in a `references/` folder.

## Declaring agent-written code

Any cell written with the agent's help gets a comment naming the model and the
date, and a line in `ai-use-log.md`. This is a course requirement, not a
formality.

## If a live marimo session is open

Use the **`marimo-pair`** skill in this repo. It drives the running kernel
directly through `marimo pair`: it can run code in the same session the student
is looking at, read cell errors, and commit cell changes. Prefer it over
touching the file whenever a session is live.
