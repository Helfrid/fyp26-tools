"""Tests for corpus loading, question sets, the scan loop and the CLI.

Nothing here touches the network: the scan tests drive a real JevClient over
an httpx MockTransport, so budget accounting and resume behaviour are
exercised for real while costing nothing.
"""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from abstract_scanner.cli import app
from abstract_scanner.corpus import CorpusError, Record, load_records
from abstract_scanner.questions import QuestionSetError, load_question_set
from abstract_scanner.scan import completed_ids, scan
from jev_client import Budget, JevClient

runner = CliRunner()

ROWS = [
    {"pmid": "1", "title": "PPP1CC in mitosis", "abstract": "We show that..."},
    {"pmid": "2", "title": "Unrelated", "abstract": "Something else entirely."},
]

QUESTION_TOML = """
name = "test-set"
version = "3"

[questions.on_target]
type = "noul"
instructions = "The abstract concerns PPP1CC"
"""


@pytest.fixture
def questions(tmp_path):
    path = tmp_path / "set.toml"
    path.write_text(QUESTION_TOML)
    return load_question_set(path)


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"articles": ROWS}))
    return path


def _client(budget: Budget | None = None, handler=None) -> JevClient:
    def default(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {"on_target": {"type": "noul", "noul": 0.8}},
                "usage": {"input_tokens": 300},
            },
        )

    return JevClient(
        budget=budget or Budget(max_usd=1.0),
        api_key="test-key",
        transport=httpx.MockTransport(handler or default),
    )


# ---- corpus ----


def test_loads_json_object_with_articles(corpus):
    records = load_records(corpus)
    assert [r.id for r in records] == ["1", "2"]


def test_loads_jsonl_and_csv(tmp_path):
    jsonl = tmp_path / "c.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in ROWS))
    assert len(load_records(jsonl)) == 2

    csv_path = tmp_path / "c.csv"
    csv_path.write_text("pmid,title,abstract\n9,A title,An abstract\n")
    assert load_records(csv_path)[0].id == "9"


def test_records_without_an_abstract_are_dropped(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps([*ROWS, {"pmid": "3", "title": "No abstract"}]))
    assert len(load_records(path)) == 2


def test_corpus_with_no_usable_records_is_an_error(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps([{"pmid": "3", "title": "No abstract"}]))
    with pytest.raises(CorpusError, match="no records"):
        load_records(path)


def test_unsupported_format_is_rejected(tmp_path):
    path = tmp_path / "c.xlsx"
    path.write_text("nope")
    with pytest.raises(CorpusError, match="unsupported"):
        load_records(path)


def test_state_excludes_everything_but_title_and_abstract():
    state = Record(id="1", title="T", abstract="A").state
    assert state == "T\n\nA"


# ---- question sets ----


def test_fingerprint_ignores_name_and_version(tmp_path):
    a = tmp_path / "a.toml"
    a.write_text(QUESTION_TOML)
    b = tmp_path / "b.toml"
    b.write_text(QUESTION_TOML.replace('version = "3"', 'version = "99"'))
    assert load_question_set(a).fingerprint == load_question_set(b).fingerprint


def test_fingerprint_changes_when_the_question_changes(tmp_path, questions):
    other = tmp_path / "o.toml"
    other.write_text(QUESTION_TOML.replace("concerns PPP1CC", "concerns PPP2CA"))
    assert load_question_set(other).fingerprint != questions.fingerprint


def test_choice_without_an_escape_option_warns(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text(
        '[questions.q]\ntype = "choice"\ninstructions = "pick"\noptions = ["a", "b"]\n'
    )
    assert any("escape option" in w for w in load_question_set(path).warnings)


def test_choice_with_an_escape_option_does_not_warn(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text(
        '[questions.q]\ntype = "choice"\ninstructions = "pick"\n'
        'options = ["a", "none"]\n'
    )
    assert load_question_set(path).warnings == ()


@pytest.mark.parametrize(
    "body, match",
    [
        ('[questions.q]\ntype = "vibes"\ninstructions = "x"\n', "type must be"),
        ('[questions.q]\ntype = "noul"\ninstructions = "  "\n', "must not be empty"),
        ('[questions.q]\ntype = "choice"\ninstructions = "x"\n', "needs options"),
        ("name = 'x'\n", "no .questions"),
    ],
)
def test_invalid_question_sets_are_rejected(tmp_path, body, match):
    path = tmp_path / "s.toml"
    path.write_text(body)
    with pytest.raises(QuestionSetError, match=match):
        load_question_set(path)


# ---- scan ----


def test_scan_writes_one_line_per_record(tmp_path, questions, corpus):
    out = tmp_path / "r.jsonl"
    with _client() as client:
        manifest = scan(load_records(corpus), questions, client, out)
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert manifest.n_scanned == 2
    assert [line["id"] for line in lines] == ["1", "2"]
    assert lines[0]["answers"]["on_target"]["value"] == 0.8
    assert lines[0]["question_fingerprint"] == questions.fingerprint


def test_scan_resumes_and_skips_completed_ids(tmp_path, questions, corpus):
    out = tmp_path / "r.jsonl"
    with _client() as client:
        scan(load_records(corpus)[:1], questions, client, out)
    assert completed_ids(out) == {"1"}

    with _client() as client:
        manifest = scan(load_records(corpus), questions, client, out)
    assert manifest.n_scanned == 1
    assert manifest.n_skipped_existing == 1


def test_budget_stop_keeps_partial_results(tmp_path, questions, corpus):
    def expensive(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {"on_target": {"type": "noul", "noul": 0.5}},
                "usage": {"input_tokens": 400_000},
            },
        )

    out = tmp_path / "r.jsonl"
    with _client(Budget(max_usd=0.02), expensive) as client:
        manifest = scan(load_records(corpus), questions, client, out)

    assert manifest.stopped_early
    assert manifest.n_scanned == 1
    assert out.read_text().strip(), "partial results must survive the stop"
    assert manifest.spent_usd <= 0.02


def test_a_failing_record_does_not_abort_the_run(tmp_path, questions, corpus):
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(400, text="bad request")
        return httpx.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {"on_target": {"type": "noul", "noul": 0.1}},
                "usage": {"input_tokens": 100},
            },
        )

    out = tmp_path / "r.jsonl"
    with _client(handler=flaky) as client:
        manifest = scan(load_records(corpus), questions, client, out)
    assert manifest.n_failed == 1
    assert manifest.n_scanned == 1


def test_manifest_records_what_was_asked(tmp_path, questions, corpus):
    out = tmp_path / "r.jsonl"
    with _client() as client:
        manifest = scan(load_records(corpus), questions, client, out)
    manifest.write(tmp_path / "m.json")
    payload = json.loads((tmp_path / "m.json").read_text())
    assert payload["question_fingerprint"] == questions.fingerprint
    assert payload["question_set_version"] == "3"
    assert payload["model"] == "jev-1.14.0"
    assert payload["finished"]


# ---- cli ----


def test_validate_reports_a_good_set(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text(QUESTION_TOML)
    result = runner.invoke(app, ["validate", "-q", str(path)])
    assert result.exit_code == 0
    assert "test-set v3" in result.stdout


def test_validate_exits_nonzero_on_a_broken_set(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text("not = 'a question set'")
    assert runner.invoke(app, ["validate", "-q", str(path)]).exit_code == 1


def test_estimate_prices_without_sending(tmp_path, corpus):
    path = tmp_path / "s.toml"
    path.write_text(QUESTION_TOML)
    result = runner.invoke(app, ["estimate", "-a", str(corpus), "-q", str(path)])
    assert result.exit_code == 0
    assert "estimated" in result.stdout


def test_scan_rejects_a_nonpositive_budget(tmp_path, corpus):
    path = tmp_path / "s.toml"
    path.write_text(QUESTION_TOML)
    result = runner.invoke(
        app,
        [
            "scan",
            "-a",
            str(corpus),
            "-q",
            str(path),
            "-o",
            str(tmp_path / "r.jsonl"),
            "--budget",
            "0",
        ],
    )
    assert result.exit_code == 1


def test_scan_without_an_api_key_fails_cleanly(tmp_path, corpus, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    path = tmp_path / "s.toml"
    path.write_text(QUESTION_TOML)
    result = runner.invoke(
        app,
        [
            "scan",
            "-a",
            str(corpus),
            "-q",
            str(path),
            "-o",
            str(tmp_path / "r.jsonl"),
            "--budget",
            "1",
        ],
    )
    assert result.exit_code == 1
    assert "TYPESAFE_API_KEY" in result.stderr


# ---- json question sets (agent-generated) ----


def test_json_and_toml_question_sets_are_equivalent(tmp_path):
    """An agent emits JSON, a human writes TOML; both must fingerprint alike."""
    toml_path = tmp_path / "s.toml"
    toml_path.write_text(QUESTION_TOML)
    json_path = tmp_path / "s.json"
    json_path.write_text(
        json.dumps(
            {
                "name": "test-set",
                "version": "3",
                "questions": {
                    "on_target": {
                        "type": "noul",
                        "instructions": "The abstract concerns PPP1CC",
                    }
                },
            }
        )
    )
    assert (
        load_question_set(json_path).fingerprint
        == load_question_set(toml_path).fingerprint
    )


def test_malformed_json_question_set_is_rejected(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    with pytest.raises(QuestionSetError, match="not valid JSON"):
        load_question_set(path)


def test_json_array_question_set_is_rejected(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("[]")
    with pytest.raises(QuestionSetError, match="JSON object"):
        load_question_set(path)


def test_unsupported_question_set_suffix_is_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("name: x")
    with pytest.raises(QuestionSetError, match=r"\.toml or \.json"):
        load_question_set(path)


def test_json_question_set_validates_the_same_way(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "questions": {
                    "q": {
                        "type": "choice",
                        "instructions": "pick",
                        "options": ["a", "b"],
                    }
                }
            }
        )
    )
    assert any("escape option" in w for w in load_question_set(path).warnings)


# ---- agent guide ----


def test_guide_prints_the_procedure_and_the_schema():
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    assert "CHECK BACK WITH THE STUDENT" in result.stdout
    assert '"type": "noul"' in result.stdout


def test_guide_schema_only_omits_the_procedure():
    result = runner.invoke(app, ["guide", "--schema"])
    assert result.exit_code == 0
    assert "CHECK BACK WITH THE STUDENT" not in result.stdout
    assert "escape" in result.stdout


def test_guide_documents_every_question_type_the_loader_accepts():
    """The guide is the agent's only spec; it must not fall behind the code."""
    from abstract_scanner.questions import BUILDERS

    result = runner.invoke(app, ["guide", "--schema"])
    for kind in BUILDERS:
        assert f'"{kind}"' in result.stdout
