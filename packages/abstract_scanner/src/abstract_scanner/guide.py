"""The procedure an agent follows when a student asks for a literature scan.

This text ships *with the package* rather than living in a CLAUDE.md, because
the student's agent runs in their own workspace and never sees this repo. The
agent reads it by running ``abstract-scanner guide``, so the instructions can
never drift from the version of the tool actually installed.
"""

from __future__ import annotations

QUESTION_SET_SCHEMA = """\
A question set is a JSON object with three keys:

  name       short slug, e.g. "ppp1cc-screen"
  version    string, bump it whenever you change a question
  questions  object mapping question id -> question

Each question is one of three types.

  {"type": "noul", "instructions": "<a statement that is true or false
                                     of the abstract>"}
      Returns a probability from 0 to 1. Use this for most things. Phrase
      the instructions as a STATEMENT, not a question: "The abstract
      reports experimental work on PPP1CC", not "Does it study PPP1CC?".

  {"type": "choice", "instructions": "<what is being chosen>",
   "options": ["a", "b", "none"]}
      Returns one option plus per-option probabilities. The options must
      be mutually exclusive, and one of them MUST be an escape:
      none / not_stated / unclear / insufficient_evidence / manual_review.
      Without an escape the model is forced to pick, and a forced pick is
      a wrong answer.

  {"type": "score", "instructions": "<what is being rated, and what the
                                      ends of the scale mean>",
   "min": 1, "max": 5}
      Returns an ordinal rating.

Rules that matter:
  - One question, one judgment. Never bundle two ideas into one question.
  - Prefer several independent nouls over one multi-label choice: nouls are
    scored independently, so adding a label later does not disturb the rest.
  - Ask only about what is in the title and abstract. The model sees nothing
    else -- no full text, no journal, no author, no year.
  - Question ids become column names in the results. Keep them short and
    snake_case.
"""

PROCEDURE = """\
HOW TO RUN A SCAN FOR A STUDENT

Stage 1 -- understand what they want to find
  Ask the student, in plain language, what makes a paper relevant to them.
  Do not write any JSON yet. Get them to say it as sentences: "I want
  papers where someone actually measured what happens when PPP1CC is
  degraded." Push back if it is vague -- "interesting papers" is not a
  screening criterion.

Stage 2 -- draft the question set
  Turn their description into a JSON question set (run
  `abstract-scanner guide --schema` for the exact shape). Keep it small:
  three to six questions. More questions make the results harder to
  interpret, not better.

Stage 3 -- CHECK BACK WITH THE STUDENT. Do not skip this.
  Show them the questions in plain English, one line each, and ask:
    - Is this what you meant?
    - Would YOU be able to answer each of these from an abstract alone?
      If you could not, neither can the model.
    - What should happen to a paper that is borderline?
  Change what they ask you to change. This is their experimental design,
  not yours.

Stage 4 -- validate, free
  `abstract-scanner validate -q questions.json`
  Fix any errors. Take the warnings seriously, especially a choice with no
  escape option.

Stage 5 -- price it, free
  `abstract-scanner estimate -a abstracts.json -q questions.json`
  Tell the student the number before anything is spent.

Stage 6 -- trial run on a few records
  `abstract-scanner scan -a abstracts.json -q questions.json \\
       -o trial.jsonl --budget 0.05 --limit 20 --cache .cache`
  Read the output WITH the student. Do the answers look sane on papers
  they know? If not, go back to stage 2 -- that is normal, and cheap.

Stage 7 -- the full scan
  Same command without --limit, with a budget a little above the estimate.
  If it stops at the ceiling it exits with code 2 and leaves partial
  results; raise the budget and re-run the identical command to resume.

Stage 8 -- hand back
  The results are `<out>.jsonl`, one JSON object per abstract. The run is
  described by `<out>.manifest.json` -- keep both together. Offer the
  student a line for ai-use-log.md.

NEVER:
  - run a scan without showing the student the questions first;
  - run a scan without --budget;
  - change a question set after a scan and reuse the old results --
    the fingerprint will not match, and the two cannot be pooled;
  - touch anything in references/.
"""


def guide_text(schema_only: bool = False) -> str:
    if schema_only:
        return QUESTION_SET_SCHEMA
    return f"{PROCEDURE}\n\n{'-' * 70}\n\n{QUESTION_SET_SCHEMA}"
