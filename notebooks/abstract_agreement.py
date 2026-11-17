import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    # Part 6 — How well did the classifier agree with you?

    You classified 50 abstracts by hand. The classifier answered the same four
    questions about the same abstracts. This notebook measures the agreement and
    produces your first result figure.

    **Work through it with the agent, but make sure you can explain every step.**
    You will have to describe this analysis in your report, and "the agent wrote
    it" is not a description. After each section, ask yourself: *could I explain
    this to someone who has not seen the code?*

    Fill in the cells marked **TODO**. The scaffolding is given; the analysis is
    yours.

    /// admonition | This is a marimo notebook, not Jupyter.
    Cells are connected by the variables they define and use. Change a cell and
    everything downstream re-runs on its own — there is no stale state and no
    "restart and run all". The consequence: **a variable may only be defined in
    one cell.** If you want to try a second version of something, give it a new
    name.
    ///
    """
    )
    return


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl

    return Path, json, mo, pl, plt


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 1. Load the two sets of answers

    `results/jev_tagging_v3.jsonl` — one JSON object per abstract, from Part 5.
    `abstracts_annotated/` — the hand classifications, one file per student.
    """
    )
    return


@app.cell
def _(Path):
    # This notebook lives in notebooks/, so the repository root is one level up.
    ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()

    MY_STUDENT_ID = "S1"  # TODO: change to your own
    RESULTS = ROOT / "results" / "jev_tagging_v3.jsonl"
    ANNOTATIONS = ROOT / "abstracts_annotated"

    FIELDS = ["is_tagging_paper", "tag_type", "locus_strategy", "terminus"]
    return ANNOTATIONS, FIELDS, MY_STUDENT_ID, RESULTS, ROOT


@app.cell
def _(Path, RESULTS, json, pl):
    def load_model_answers(path: Path) -> pl.DataFrame:
        """One row per abstract, one column per field, plus the confidences."""
        rows = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            row = {"pmid": record["id"]}
            for field, answer in record["answers"].items():
                row[field] = answer["value"]
                row[f"{field}_confidence"] = answer["confidence"]
            rows.append(row)
        return pl.DataFrame(rows)

    model = load_model_answers(RESULTS)
    print(model.shape)
    model.head()
    return (model,)


@app.cell
def _(ANNOTATIONS, MY_STUDENT_ID, Path, pl):
    # TODO: write the matching loader for your own annotations.
    #
    # Each file in abstracts_annotated/ is a JSON list of records with keys:
    #   item_id, annotator, annotator_role, stage, schema_version, annotated_at,
    #   is_tagging_paper, and -- only when is_tagging_paper is not "no" --
    #   tag_type, locus_strategy, terminus
    #
    # Two things to decide, and to justify in your report:
    #   1. Your file has item_id (e.g. "s1_003"), the model output has pmid.
    #      How will you join them? (input_data/phase1_tagging_abstracts.json
    #      carries both.)
    #   2. Records where is_tagging_paper == "no" have no other fields at all.
    #      What should those become in a table -- null, or something else?

    def load_my_annotations(directory: Path, student: str) -> pl.DataFrame: ...

    mine = load_my_annotations(ANNOTATIONS, MY_STUDENT_ID)
    return (mine,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 2. Join them

    You can only compare abstracts that appear in both sets. Join on the identifier
    you chose above.

    **Check the row count after joining.** If it is not 50, find out why before
    going further — a silent loss of rows is the most common way an analysis like
    this goes wrong.
    """
    )
    return


@app.cell
def _(mine, model):
    # TODO: join `mine` and `model` into one table, one row per abstract,
    # with a column pair per field (yours and the model's).
    #
    # Then assert the row count is what you expect:
    #   assert paired.height == 50, f"expected 50 rows, got {paired.height}"

    paired = ...
    return (paired,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 3. Apply the skip rule

    When you answered `no` to `is_tagging_paper`, you were told to leave the other
    three fields blank — the schema does not even allow them.

    The classifier does not work that way: it answers all four questions
    independently, every time, so it has produced a `tag_type` even for papers it
    called `no`.

    **If you compare those fields anyway, you will mark the model wrong on fields
    you yourself left blank, and the agreement will look worse than it is.**

    Decide what to do about this, apply it, and record the decision — it is a real
    methodological choice and belongs in your report.
    """
    )
    return


@app.cell
def _(paired):
    # TODO: handle the skip rule before comparing the three dependent fields.
    scored = paired
    return (scored,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 4. Agreement on `is_tagging_paper`

    Start with the screening decision, which every abstract has.

    Begin with the simplest number: in what fraction of abstracts did you and the
    classifier give the same answer?
    """
    )
    return


@app.cell
def _(scored):
    # TODO: overall agreement on is_tagging_paper.
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    /// warning | Why that number on its own is not enough
    Your 50 abstracts were drawn deliberately: roughly 8 tagging papers, 2
    ambiguous, and 40 negatives. A classifier that answered `no` to everything
    would score about 80% — while being useless.

    So a single accuracy figure cannot tell you whether the classifier works.
    You need to know **which** answers it got right and **what kind** of
    mistakes it made. That is what the next section is for.
    ///
    """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 5. Where does it disagree?

    Build a confusion matrix: your answer against the model's, counting every
    combination. The diagonal is agreement; everything off it is a disagreement
    with a specific shape.

    Then look at the two kinds of error separately:

    - papers you called `yes` that it called `no` — **missed tagging papers**
    - papers you called `no` that it called `yes` — **false alarms**

    For a screening tool that feeds into full-text reading, these costs are not
    equal. Which matters more here, and why?
    """
    )
    return


@app.cell
def _(scored):
    # TODO: confusion matrix for is_tagging_paper.
    return


@app.cell
def _(scored):
    # TODO: pull out the disagreements and READ THE ABSTRACTS.
    #
    # This is the most valuable half-hour in this notebook. For each disagreement:
    # were you right, was the model right, or was the abstract genuinely ambiguous?
    # Note the pmid and a one-line reason. Several of these will go in your report.
    #
    # Tip: `mo.ui.table(...)` renders a DataFrame you can sort and page through,
    # which beats squinting at a print-out of 50 rows.
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 6. The other three fields

    `tag_type`, `locus_strategy` and `terminus` are only meaningful on the subset
    where tagging was actually found. Report the subset size alongside the
    agreement — an agreement figure computed on six abstracts means something very
    different from one computed on forty, and a reader cannot tell them apart
    unless you say so.
    """
    )
    return


@app.cell
def _(FIELDS, scored):
    # TODO: agreement for each of the three dependent fields, with n.
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 7. Does confidence predict correctness?

    The classifier returns a confidence for every answer. A useful classifier is
    not just accurate — it is **right when it is confident and uncertain when it
    is wrong**, so you know which answers to trust.

    Compare the confidence on the answers it got right with the confidence on the
    ones it got wrong. Is there a separation? Is there a threshold above which it
    is reliable enough to trust without checking?
    """
    )
    return


@app.cell
def _(scored):
    # TODO: confidence on agreements vs disagreements.
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 8. Your first result figure

    One figure that answers: **how well did the classifier reproduce my
    classifications?**

    Make it stand alone — a reader should understand it without the notebook.
    That means axis labels with units or counts, the n stated, and a caption that
    says what was compared and on how many abstracts.

    Save it to `figures/` as both PNG and PDF (PDF is vector, so it stays sharp in
    your report).
    """
    )
    return


@app.cell
def _(ROOT, plt, scored):
    # TODO: your figure.
    #
    # figures = ROOT / "figures"
    # figures.mkdir(exist_ok=True)
    # fig.savefig(figures / "abstract_agreement.png", dpi=300, bbox_inches="tight")
    # fig.savefig(figures / "abstract_agreement.pdf", bbox_inches="tight")
    #
    # In marimo, end the cell with the figure object itself (not plt.show()) and
    # it renders as the cell output.
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 9. Write down what you found

    Before you close this notebook, answer these in a few sentences each. They are
    the backbone of the results section of your report.

    1. How often did the classifier agree with you on `is_tagging_paper`?
    2. What kind of mistake did it make more often — missed tagging papers, or
       false alarms?
    3. On the disagreements you read: how many were the model's error, how many
       were yours, and how many were genuinely ambiguous abstracts?
    4. Did confidence tell you anything useful about which answers to trust?
    5. Would you use this classifier to screen the literature for your own gene?
       Under what conditions — and what would you still check by hand?

    Question 3 is the one that matters most. A disagreement where you were wrong
    is not a failure of the experiment; it is the experiment working.
    """
    )
    return


if __name__ == "__main__":
    app.run()
