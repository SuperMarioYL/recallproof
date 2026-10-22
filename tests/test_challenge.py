"""The product surface: the verdict table's data, the JSON contract, the exits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from recallproof import (
    Verdict,
    build_index,
    challenge,
    exit_code,
    load_index,
    load_memory_rows,
    load_transcript,
    verdicts_payload,
    write_index,
)
from recallproof.cli import app
from recallproof.transcript import TranscriptError
from recallproof.transcript import load_transcript as load

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION = REPO_ROOT / "examples" / "session.jsonl"
MEMORY = REPO_ROOT / "examples" / "memory_rows.jsonl"
POINTERS = REPO_ROOT / "examples" / "pointers.jsonl"

runner = CliRunner()


@pytest.fixture(scope="module")
def verdicts():
    return challenge(load_transcript(SESSION), load_memory_rows(MEMORY))


def _index_into(tmp_path: Path) -> Path:
    """Write the shipped rows into a pointer index in ``tmp_path``."""
    out = tmp_path / "pointers.jsonl"
    runner.invoke(app, ["index", "-s", str(SESSION), "-m", str(MEMORY), "-o", str(out)])
    return out


def test_sample_session_has_one_derived_and_one_not_derivable(verdicts):
    by_id = {item.row_id: item for item in verdicts}
    assert by_id["row_0001"].verdict is Verdict.DERIVED
    assert by_id["row_0002"].verdict is Verdict.NOT_DERIVABLE
    assert by_id["row_0003"].verdict is Verdict.UNSUPPORTED_DERIVATION


def test_derived_row_carries_its_event_and_span(verdicts):
    derived = next(item for item in verdicts if item.verdict is Verdict.DERIVED)
    assert derived.source_ref is not None
    assert derived.event is not None
    assert derived.span is not None
    assert derived.pin_label != "-"
    start, end = derived.span
    assert derived.event.text[start:end] == derived.text


def test_not_derivable_row_claims_no_source(verdicts):
    flagged = next(item for item in verdicts if item.verdict is Verdict.NOT_DERIVABLE)
    assert flagged.source_ref is None
    assert flagged.span is None
    assert flagged.pin_label == "-"


def test_exit_code_is_non_zero_when_a_row_is_flagged(verdicts):
    assert exit_code(verdicts) == 1
    assert exit_code([item for item in verdicts if item.ok]) == 0


def test_json_payload_is_a_stable_contract(verdicts):
    payload = verdicts_payload(verdicts, SESSION, MEMORY)
    assert payload["schema_version"] == 1
    assert payload["counts"] == {
        "DERIVED": 1,
        "NOT_DERIVABLE": 1,
        "UNSUPPORTED_DERIVATION": 1,
    }
    assert json.loads(json.dumps(payload)) == payload
    derived = next(row for row in payload["rows"] if row["verdict"] == "DERIVED")
    assert derived["source_ref"]["span"] == list(derived["span"])
    assert derived["source_event"]["line_index"] == derived["source_ref"]["line_index"]
    assert len(derived["source_ref"]["event_sha256"]) == 64


def test_pointer_index_round_trips(tmp_path: Path):
    transcript = load_transcript(SESSION)
    rows = load_memory_rows(MEMORY)
    out = tmp_path / "pointers.jsonl"
    written = write_index(out, build_index(transcript, rows))
    assert written == len(rows)

    records = load_index(out)
    assert [record.row_id for record in records] == [row.row_id for row in rows]
    assert records[0].source_ref is not None
    assert records[1].source_ref is None
    assert records[2].source_ref is None

    # A pinned index yields the same verdicts as resolving now.
    pinned = challenge(transcript, rows, records)
    fresh = challenge(transcript, rows)
    assert [item.verdict for item in pinned] == [item.verdict for item in fresh]


def test_shipped_pointer_index_matches_the_shipped_examples():
    transcript = load_transcript(SESSION)
    rows = load_memory_rows(MEMORY)
    shipped = load_index(POINTERS)
    assert [record.model_dump() for record in shipped] == [
        record.model_dump() for record in build_index(transcript, rows)
    ]


def test_cli_challenge_prints_the_table_and_exits_one():
    result = runner.invoke(app, ["challenge", "-s", str(SESSION), "-m", str(MEMORY)])
    assert result.exit_code == 1
    assert "DERIVED" in result.stdout
    assert "NOT_DERIVABLE" in result.stdout
    assert "UNSUPPORTED_DERIVATION" in result.stdout


def test_cli_challenge_json_is_parseable():
    result = runner.invoke(
        app, ["challenge", "-s", str(SESSION), "-m", str(MEMORY), "--json"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["counts"]["DERIVED"] == 1
    assert [row["row_id"] for row in payload["rows"]] == ["row_0001", "row_0002", "row_0003"]


def test_cli_index_then_rederive(tmp_path: Path):
    out = tmp_path / "pointers.jsonl"
    indexed = runner.invoke(
        app, ["index", "-s", str(SESSION), "-m", str(MEMORY), "-o", str(out)]
    )
    assert indexed.exit_code == 0
    assert "1 pinned" in indexed.stdout

    good = runner.invoke(
        app,
        ["rederive", "row_0001", "-s", str(SESSION), "-m", str(MEMORY), "-p", str(out)],
    )
    assert good.exit_code == 0
    assert "DERIVED" in good.stdout
    assert "replay" in good.stdout

    bad = runner.invoke(
        app,
        ["rederive", "row_0002", "-s", str(SESSION), "-m", str(MEMORY), "-p", str(out)],
    )
    assert bad.exit_code == 1
    assert "NOT_DERIVABLE" in bad.stdout

    unknown = runner.invoke(
        app,
        ["rederive", "row_9999", "-s", str(SESSION), "-m", str(MEMORY), "-p", str(out)],
    )
    assert unknown.exit_code == 2
    assert "ROW_TEXT_UNAVAILABLE" in unknown.stdout


def test_cli_rederive_will_not_verdict_without_the_row_text(tmp_path: Path):
    """No ``--memory`` means no text to compare, so it must never print DERIVED."""
    out = _index_into(tmp_path)
    result = runner.invoke(app, ["rederive", "row_0001", "-s", str(SESSION), "-p", str(out)])
    assert result.exit_code == 2
    assert "DERIVED" not in result.stdout
    assert "--memory is required" in result.stdout


def test_cli_rederive_reports_a_row_it_has_no_text_for(tmp_path: Path):
    """A row absent from the memory file is unpinned, not silently DERIVED."""
    out = _index_into(tmp_path)
    other = tmp_path / "other_rows.jsonl"
    other.write_text(
        json.dumps({"row_id": "someone_elses_row", "text": "Ship it."}) + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["rederive", "row_0001", "-s", str(SESSION), "-m", str(other), "-p", str(out)]
    )
    assert result.exit_code == 2
    assert "ROW_TEXT_UNAVAILABLE" in result.stdout
    assert "DERIVED" not in result.stdout


def test_cli_rederive_fails_on_a_row_edited_after_indexing(tmp_path: Path):
    """The tampered-text case: the same pointer must not still print DERIVED."""
    out = _index_into(tmp_path)
    row = load_memory_rows(MEMORY)[0].model_dump()
    row["text"] = f"{row['text']} AND DELETE PROD."
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["rederive", "row_0001", "-s", str(SESSION), "-m", str(tampered), "-p", str(out)],
    )
    assert result.exit_code == 1
    assert "NOT_DERIVABLE" in result.stdout
    assert "span no longer reproduces the row text" in result.stdout


def test_cli_rederive_agrees_with_challenge_on_every_shipped_row(tmp_path: Path):
    """``challenge`` and ``rederive`` must return the same verdict for a row."""
    out = _index_into(tmp_path)
    pinned = {
        item.row_id: item
        for item in challenge(load_transcript(SESSION), load_memory_rows(MEMORY), load_index(out))
    }
    assert pinned["row_0003"].verdict is Verdict.UNSUPPORTED_DERIVATION

    for row_id, expected in pinned.items():
        result = runner.invoke(
            app,
            ["rederive", row_id, "-s", str(SESSION), "-m", str(MEMORY), "-p", str(out)],
        )
        assert result.exit_code == (0 if expected.verdict.ok else 1), row_id
        assert result.stdout.splitlines()[0].startswith(expected.verdict.value), row_id


def test_row_absent_from_a_partial_index_is_not_reported_as_counterfeit():
    """A row the index holds no pin for is unpinned, not a proven counterfeit."""
    transcript = load_transcript(SESSION)
    rows = load_memory_rows(MEMORY)
    in_transcript = rows[0].model_copy(update={"row_id": "not_in_the_index"})
    assert build_index(transcript, [in_transcript])[0].source_ref is not None

    partial = [record for record in build_index(transcript, rows) if record.row_id == "row_0001"]
    verdicts = {
        item.row_id: item for item in challenge(transcript, [in_transcript], partial)
    }
    missing = verdicts["not_in_the_index"]
    assert missing.verdict is Verdict.NOT_DERIVABLE
    assert missing.pinned_by == "missing"
    assert "pointer index" in missing.note
    assert "no session event reproduces" not in missing.reason


def test_cli_gate_passes_on_the_hand_built_fixture():
    result = runner.invoke(app, ["gate", "--runs", "5"])
    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_cli_gate_runs_on_the_sample_session():
    result = runner.invoke(
        app, ["gate", "-s", str(SESSION), "-m", str(MEMORY), "--runs", "3"]
    )
    assert result.exit_code == 0
    assert "byte-identical across 3/3 runs" in result.stdout


def test_cli_missing_input_is_an_error_not_a_traceback(tmp_path: Path):
    result = runner.invoke(
        app, ["challenge", "-s", str(tmp_path / "nope.jsonl"), "-m", str(MEMORY)]
    )
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_transcript_rejects_broken_json(tmp_path: Path):
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"type": "user", "message":\n', encoding="utf-8")
    with pytest.raises(TranscriptError):
        load(broken)
