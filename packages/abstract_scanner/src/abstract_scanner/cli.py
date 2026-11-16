"""Command-line interface — the surface an agent drives on a student's behalf.

Three commands, in the order they should be run::

    abstract-scanner validate  --questions my_set.toml
    abstract-scanner estimate  --abstracts pool.json --questions my_set.toml
    abstract-scanner scan      --abstracts pool.json --questions my_set.toml \
                               --out results.jsonl --budget 0.50

``--budget`` is required rather than defaulted: spending money should be an
explicit act, and there is no interactive prompt to lean on when an agent is
running the command. Everything prints a short human-readable summary and
exits non-zero on failure, so the agent can tell what happened without
parsing prose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from abstract_scanner.corpus import CorpusError, load_records
from abstract_scanner.guide import guide_text
from abstract_scanner.questions import QuestionSetError, load_question_set
from abstract_scanner.scan import scan as run_scan
from common_utils.logging_setup import setup_logging
from jev_client import (
    DEFAULT_MODEL,
    Budget,
    JevClient,
    JevError,
    estimate_corpus_cost,
)

app = typer.Typer(
    add_completion=False,
    help="Screen abstracts with typed Jev questions, within a spend ceiling.",
)

AbstractsOption = Annotated[
    Path, typer.Option("--abstracts", "-a", help="Corpus .json, .jsonl or .csv.")
]
QuestionsOption = Annotated[
    Path, typer.Option("--questions", "-q", help="Question set .toml.")
]


def _load_questions(path: Path):
    try:
        question_set = load_question_set(path)
    except QuestionSetError as exc:
        typer.secho(f"✗ {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    for warning in question_set.warnings:
        typer.secho(f"⚠ {warning}", fg=typer.colors.YELLOW, err=True)
    return question_set


def _load_corpus(path: Path):
    try:
        return load_records(path)
    except CorpusError as exc:
        typer.secho(f"✗ {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc


@app.command()
def guide(
    schema: Annotated[
        bool,
        typer.Option("--schema", help="Print only the question-set format."),
    ] = False,
) -> None:
    """Print the procedure for running a scan on a student's behalf.

    Read this before building a question set. It ships with the installed
    version of the tool, so it cannot drift from the code.
    """
    typer.echo(guide_text(schema_only=schema))


@app.command()
def validate(questions: QuestionsOption) -> None:
    """Check a question set without sending anything or spending anything."""
    question_set = _load_questions(questions)
    typer.echo(f"{question_set.label}")
    for qid, spec in question_set.questions.items():
        typer.echo(f"  {qid:<24} {spec['type']}")
    if question_set.warnings:
        typer.secho(
            f"{len(question_set.warnings)} design warning(s) — see above.",
            fg=typer.colors.YELLOW,
        )
    typer.secho("✓ question set is valid", fg=typer.colors.GREEN)


@app.command()
def estimate(abstracts: AbstractsOption, questions: QuestionsOption) -> None:
    """Price a scan before running it. Costs nothing, sends nothing."""
    question_set = _load_questions(questions)
    records = _load_corpus(abstracts)
    cost = estimate_corpus_cost([r.state for r in records], question_set.questions)
    typer.echo(f"question set : {question_set.label}")
    typer.echo(f"records      : {cost['n_requests']}")
    typer.echo(f"input tokens : ~{cost['estimated_input_tokens']:,}")
    typer.secho(
        f"estimated    : ${float(cost['estimated_usd']):.4f}",
        fg=typer.colors.GREEN,
        bold=True,
    )
    typer.echo(
        "\nThe estimate is deliberately pessimistic. Set --budget a little "
        "above it;\nthe scan stops itself rather than crossing the ceiling."
    )


@app.command()
def scan(
    abstracts: AbstractsOption,
    questions: QuestionsOption,
    out: Annotated[Path, typer.Option("--out", "-o", help="Results .jsonl.")],
    budget: Annotated[
        float, typer.Option("--budget", "-b", help="Hard spend ceiling in USD.")
    ],
    cache: Annotated[
        Path | None,
        typer.Option("--cache", help="Cache directory; re-runs are then free."),
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Scan only the first N records.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="Pin a Jev model id.")
    ] = None,
    no_resume: Annotated[
        bool, typer.Option("--no-resume", help="Re-scan ids already in --out.")
    ] = False,
) -> None:
    """Scan abstracts and append typed answers to a JSONL results file."""
    if budget <= 0:
        typer.secho("✗ --budget must be positive", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    question_set = _load_questions(questions)
    records = _load_corpus(abstracts)
    if limit is not None:
        records = records[:limit]

    try:
        client = JevClient(
            budget=Budget(max_usd=budget),
            cache_dir=cache,
            model=model or DEFAULT_MODEL,
        )
    except JevError as exc:
        typer.secho(f"✗ {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    manifest_path = out.with_suffix(".manifest.json")
    with client:
        manifest = run_scan(records, question_set, client, out, resume=not no_resume)
    manifest.write(manifest_path)

    typer.echo(f"scanned  : {manifest.n_scanned}")
    if manifest.n_skipped_existing:
        typer.echo(f"skipped  : {manifest.n_skipped_existing} (already done)")
    if manifest.n_failed:
        typer.secho(f"failed   : {manifest.n_failed}", fg=typer.colors.YELLOW)
        for failure in manifest.failures:
            typer.secho(f"  {failure[:160]}", fg=typer.colors.YELLOW, err=True)
    typer.echo(f"tokens   : {manifest.input_tokens:,}")
    typer.echo(f"spent    : ${manifest.spent_usd:.4f} of ${budget:.2f}")
    typer.echo(f"results  : {out}")
    typer.echo(f"manifest : {manifest_path}")

    if manifest.n_scanned == 0 and manifest.n_failed:
        typer.secho(
            "\n✗ every record failed — nothing was scanned.\n"
            f"  First error: {manifest.failures[0]}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if manifest.stopped_early:
        typer.secho(
            "\n⚠ stopped at the budget ceiling — results are partial.\n"
            "  Raise --budget and re-run the same command to resume.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(2)
    typer.secho("✓ scan complete", fg=typer.colors.GREEN)


# Agent-written: Claude Opus 5.5 (Claude Code), 2026-11-15.
# Checked by student: <how did you check it?>
def main() -> None:
    """Entry point for the ``abstract-scanner`` command.

    Loads ``.env`` (so ``TYPESAFE_API_KEY`` is found without exporting it in
    the shell) and configures logging, then hands over to Typer. This must be
    the console-script target rather than ``app`` itself: pointing the script
    at ``app`` skips this function, and with it the ``.env`` loading.
    ``.env`` is resolved from the current directory, so run from the repo root.
    """
    setup_logging()
    app()


if __name__ == "__main__":
    main()
