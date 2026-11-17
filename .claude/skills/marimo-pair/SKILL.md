---
name: marimo-pair
description: >-
  Pair on a live marimo notebook — run code in the same kernel the student is
  looking at, read cell state and errors, and commit durable cell changes
  through marimo's code mode. Use when a marimo notebook is open and the
  student wants the agent to work in it with them, rather than editing the
  .py file.
---

# Pairing on a live marimo notebook

A marimo notebook that is open in the browser has a **running kernel**. That
kernel, not the `.py` file, is the source of truth: it holds the variables, the
cell outputs, and the dataflow graph. The file is what the kernel writes out.

So while a notebook is open:

> **Do not edit the `.py` file.** `Edit` and `Write` will not reach the running
> kernel, the student will not see the change, and the kernel will overwrite
> your edit the next time it saves. Reading the file is fine.

Everything below goes through `marimo pair`, which is part of marimo itself.

## 1. Find the notebook

```bash
uv run marimo pair notebook list
```

This prints JSON with a `url` and a `session_id` for every **open** notebook.
You need both for every later command.

A session exists only while the notebook is open in a browser tab. A running
server with no tab open reports `"notebooks": []`, even if you pass its `--url`
directly — the server is not the session, the tab is.

If it reports no sessions, ask the student to open the notebook. It is theirs,
so let them start it:

```bash
uv run marimo edit notebooks/abstract_agreement.py --no-token
```

`--no-token` is not optional here: without it the session does not register
and `notebook list` will not find it, however long you wait. The server is
localhost-only, so this is safe on a personal laptop.

If several sessions are listed, **ask which one** rather than guessing. And if
a command later reports an unknown session, the notebook was closed or
restarted — re-run `notebook list` and take the new `session_id`. Do not switch
sessions to work around a connection error.

## 2. Run code in the kernel

```bash
uv run marimo pair execute --url <URL> --session <SESSION> -c "print(paired.height)"
```

This runs in marimo's **scratchpad**: a temporary namespace holding a shallow
copy of the kernel's globals. That means:

- You can read any notebook variable by name — `model`, `paired`, `scored`.
- Anything you assign at the top level is **discarded** when the call ends.
- Mutating a notebook object in place *does* persist, because the name still
  points at the same live object. Be careful with this; it is easy to change
  the student's data without meaning to.

Use the scratchpad freely for looking: inspect a DataFrame, check a dtype, test
a join before committing it, read an error. For anything that should survive,
go to code mode.

## 3. Commit a change

```bash
uv run marimo pair execute --url <URL> --session <SESSION> --code-file - <<'PY'
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    cid = ctx.create_cell("confusion = paired.pivot(...)")
    ctx.run_cell(cid)
PY
```

The API:

| Call | Does |
|---|---|
| `ctx.cells` | every cell, each with `.id`, `.code`, `.status`, `.errors`, `.console_outputs` |
| `ctx.create_cell(code)` | adds a cell, returns its id — **does not run it** |
| `ctx.edit_cell(cid, code)` | replaces a cell's whole body |
| `ctx.run_cell(cid)` | runs it, and marimo re-runs whatever depends on it |
| `ctx.delete_cell(cid)` | removes the cell *and the variables it defined* |
| `ctx.packages.add("polars>=2")` | installs on exit — not `uv add` |

Rules that bite:

- Use `async with`. Do not `await` the `ctx` methods — they queue work that is
  applied when the block exits cleanly. If the block raises, the whole queue is
  thrown away.
- `create_cell` and `edit_cell` change structure only. Nothing runs until you
  call `run_cell`.
- **Read a cell before replacing it.** The student may have typed in it since
  you last looked. `edit_cell` takes the full new body, not a patch.
- Submit cell *contents*, not the `@app.cell` wrapper you see in the file.
- `create_cell` defaults to `hide_code=True`, which collapses the editor. For a
  student notebook pass `hide_code=False` — they need to see the code.
- If an empty cell is already there, edit it rather than adding another.
- **Ask before `delete_cell`.** It destroys the variables that cell owned, and
  everything downstream of them breaks.

`marimo._code_mode` is private and unstable (hence the underscore). It is for
driving a kernel from the scratchpad only. Never put `import marimo._code_mode`
into a notebook cell or into package code.

## 4. The graph contract

marimo keeps the notebook a directed acyclic graph, so a submitted cell must
not:

- define a public name that another cell already defines,
- form a dependency cycle,
- use `import *`.

Break one and marimo rejects the structural change and hands back a validation
error. The fix for a duplicate name is to edit the owning cell or choose a new
name — never to smuggle the value in under a private alias just to get past the
check.

Names with a leading underscore stay private to their cell and do not enter the
graph. Use them for intermediates; use public names for things later cells
genuinely need.

## 5. Working with an FYP26 student

This matters more here than the API does.

- **The notebook is theirs.** They have to describe this analysis in a report
  and defend it in a viva. A cell you wrote that they cannot explain is worse
  than no cell at all.
- Ask what they think a cell should do before you write it. When they are
  stuck, offer the shape of the answer rather than the answer.
- After committing a cell, ask them to read it back to you.
- Do not fill in the TODOs in a burst because it is faster. See
  `.claude/skills/fyp26-notebook/SKILL.md` for what each section is for.
- Any cell written with your help carries a comment naming the model and the
  date, plus a line in `ai-use-log.md`. Course requirement.
- Never open, read or summarise anything in a `references/` folder.
- Never change a question set or re-run a scan to improve the agreement number.

## Checking your work

After `run_cell`, look at what actually happened rather than assuming:

```bash
uv run marimo pair execute --url <URL> --session <SESSION> --code-file - <<'PY'
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    cell = ctx.cells["<CELL_ID>"]
    print(cell.status, cell.errors, [o.data for o in cell.console_outputs])
PY
```

If a `cm` call fails in a way you do not recognise, ask the kernel what it has:

```bash
uv run marimo pair execute --url <URL> --session <SESSION> -c 'import marimo._code_mode as cm; help(cm)'
```

marimo also ships its own guidance: `uv run marimo pair docs`.
