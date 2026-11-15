# Exercise: what should an agent be told?

*A short exercise before you start scanning. It takes about an hour and it
will make everything after it go faster.*

A `CLAUDE.md` is the file an AI agent reads automatically when it starts work
in a folder. Everything in it is in the agent's head before you type anything;
everything not in it, the agent has to guess.

The skill you are practising is deciding **what is worth saying**. A bad
CLAUDE.md describes the code — which the agent can already read. A good one
records what the agent *cannot* work out from the code: why a decision was
made, what broke last time, what must never happen.

---

## Part A — audit the one we wrote

Open `CLAUDE.md` in the repository root. Pick **three** claims and check each
against the actual code. Suggested ones:

1. *"`--budget` is required on `scan`, never defaulted."*
   Find where that is enforced. What exactly happens if you leave it out, and
   what if you pass `0`?

2. *"Only title and abstract reach the model."*
   Find the code that builds what gets sent. Is it true? Could a journal name
   reach the model by some other route?

3. *"Results append to JSONL and flush per record."*
   Find the write. Why `flush()` on every record rather than at the end —
   what would go wrong without it?

For each: write one sentence saying whether the claim holds, and name the file
and line where you checked. **If you find something the file gets wrong, say
so — that is the most valuable outcome of this exercise, not a failure of it.**

Do this yourself, without the agent. You are checking the instructions the
agent is given; asking it to mark its own brief defeats the point.

---

## Part B — write one yourself

Write `packages/jev_client/CLAUDE.md`, for the package that talks to the Jev
API. Read the code first — it is one module, `client.py`, about 350 lines.

A useful file here would cover:

- **What this package is for**, in two sentences.
- **What it deliberately does not do.** There is at least one obvious thing it
  refuses to do; find it and say why.
- **The one rule about money.** Someone editing this package could remove a
  safeguard without noticing. Which one, and what would happen?
- **How to test it.** What is unusual about the test setup, and what rule must
  anyone adding a test follow?
- **Anything that would surprise a newcomer.** There is a non-obvious piece of
  arithmetic in `Budget`. Explain it in your own words.

Aim for under a page. Shorter and sharper beats longer.

### How to check it

Ask the agent to do a small task in that package — add a question-type helper,
say — *in a fresh session*, and watch what it does. Does it follow your file?
Did it need to ask something your file should have told it? Add that, and try
again.

Then compare with `docs/reference/jev_client-CLAUDE.md`. It is one reasonable
answer, not the only one. Where yours says something ours does not, work out
which of you is right — sometimes it will be you.

---

## What to hand in

Your `packages/jev_client/CLAUDE.md`, your three audit sentences, and a short
paragraph: what did you put in that the agent could not have guessed, and what
did you leave out because it could?
