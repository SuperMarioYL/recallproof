"""Re-derivation must be a property of the files, not of the moment it ran.

These tests are the m1 gate in pytest form: a pinned pointer re-derives
byte-identically across runs, and every way of losing that property produces
``NOT_DERIVABLE`` rather than a guess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recallproof import (
    Verdict,
    build_index,
    challenge,
    load_memory_rows,
    load_transcript,
    pin,
    rederive,
)
from recallproof.spike import (
    ABSTRACTIVE_TEXT,
    COUNTERFEIT_TEXT,
    EXTRACTIVE_TEXT,
    write_fixture,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION = REPO_ROOT / "examples" / "session.jsonl"
MEMORY = REPO_ROOT / "examples" / "memory_rows.jsonl"


@pytest.fixture(scope="module")
def transcript():
    return load_transcript(SESSION)


@pytest.fixture(scope="module")
def derived_ref(transcript):
    row = load_memory_rows(MEMORY)[0]
    source_ref = pin(transcript, row)
    assert source_ref is not None
    return row, source_ref


def test_extractive_row_rederives_byte_identically_100_times(transcript, derived_ref):
    """The gate: same inputs, same verdict, every single run."""
    row, source_ref = derived_ref
    digests = set()
    for _ in range(100):
        fresh = load_transcript(SESSION)
        derivation = rederive(fresh.events, source_ref, row.text)
        assert derivation.verdict is Verdict.DERIVED
        assert derivation.reproduced == row.text
        digests.add(
            json.dumps(
                {
                    "verdict": derivation.verdict.value,
                    "span": derivation.span,
                    "uuid": derivation.event.uuid,
                    "sha256": derivation.event.sha256,
                },
                sort_keys=True,
            )
        )
    assert len(digests) == 1


def test_span_is_a_slice_of_the_pinned_block(transcript, derived_ref):
    row, source_ref = derived_ref
    event = transcript.event(source_ref.line_index, source_ref.block_index)
    assert event is not None
    start, end = source_ref.span
    assert event.text[start:end] == row.text
    assert len(event.sha256) == 64


def test_changed_line_fails_re_derivation(transcript, derived_ref):
    row, source_ref = derived_ref
    stale = source_ref.model_copy(update={"event_sha256": "0" * 64})
    derivation = rederive(transcript.events, stale, row.text)
    assert derivation.verdict is Verdict.NOT_DERIVABLE
    assert "changed since it was pinned" in derivation.reason


def test_shortened_span_fails_instead_of_matching_loosely(transcript, derived_ref):
    row, source_ref = derived_ref
    shifted = source_ref.model_copy(
        update={"span": (source_ref.span[0], source_ref.span[1] - 1)}
    )
    derivation = rederive(transcript.events, shifted, row.text)
    assert derivation.verdict is Verdict.NOT_DERIVABLE


def test_span_outside_the_block_fails(transcript, derived_ref):
    row, source_ref = derived_ref
    overrun = source_ref.model_copy(update={"span": (0, 10_000)})
    derivation = rederive(transcript.events, overrun, row.text)
    assert derivation.verdict is Verdict.NOT_DERIVABLE
    assert "outside a" in derivation.reason


def test_missing_event_fails(transcript, derived_ref):
    row, source_ref = derived_ref
    ghost = source_ref.model_copy(update={"line_index": 9_999})
    derivation = rederive(transcript.events, ghost, row.text)
    assert derivation.verdict is Verdict.NOT_DERIVABLE
    assert derivation.event is None


def test_wrong_uuid_fails(transcript, derived_ref):
    row, source_ref = derived_ref
    swapped = source_ref.model_copy(update={"source_uuid": "0" * 36})
    derivation = rederive(transcript.events, swapped, row.text)
    assert derivation.verdict is Verdict.NOT_DERIVABLE
    assert "is now" in derivation.reason


def test_pointer_resolution_without_row_text(transcript, derived_ref):
    """``rederive`` also answers "does this pointer still resolve?" on its own."""
    _, source_ref = derived_ref
    assert rederive(transcript.events, source_ref).verdict is Verdict.DERIVED


def test_abstractive_row_is_never_judged(tmp_path: Path):
    session, memory = write_fixture(tmp_path)
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    verdicts = {item.row_id: item for item in challenge(transcript, rows)}
    abstractive = verdicts["fixture_abstractive"]
    assert abstractive.verdict is Verdict.UNSUPPORTED_DERIVATION
    assert abstractive.source_ref is None
    assert abstractive.span is None
    assert abstractive.text == ABSTRACTIVE_TEXT


def test_counterfeit_row_is_not_derivable(tmp_path: Path):
    session, memory = write_fixture(tmp_path)
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    verdicts = {item.row_id: item for item in challenge(transcript, rows)}
    counterfeit = verdicts["fixture_counterfeit"]
    assert counterfeit.verdict is Verdict.NOT_DERIVABLE
    assert counterfeit.text == COUNTERFEIT_TEXT
    assert counterfeit.source_ref is None


def test_extractive_fixture_row_is_derivable(tmp_path: Path):
    session, memory = write_fixture(tmp_path)
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    verdicts = {item.row_id: item for item in challenge(transcript, rows)}
    assert verdicts["fixture_derived"].verdict is Verdict.DERIVED
    assert verdicts["fixture_derived"].text == EXTRACTIVE_TEXT


def test_evidence_in_an_excluded_block_is_unsupported_not_guessed(tmp_path: Path):
    """A thinking block is not a memory-bearing event: say so, do not guess."""
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "parentUuid": None,
                "type": "assistant",
                "uuid": "aaaa1111-0000-4000-8000-000000000001",
                "timestamp": "2026-10-19T09:00:00.000Z",
                "sessionId": "aaaa1111-2222-4333-8444-555566667777",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "the deploy target is eu-west-1"}
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    memory = tmp_path / "rows.jsonl"
    memory.write_text(
        json.dumps({"row_id": "r1", "text": "the deploy target is eu-west-1"}) + "\n",
        encoding="utf-8",
    )
    verdicts = challenge(load_transcript(session), load_memory_rows(memory))
    assert verdicts[0].verdict is Verdict.UNSUPPORTED_DERIVATION
    assert "excluded" in verdicts[0].reason


def test_pinned_index_reports_a_row_edited_after_indexing(transcript):
    """A row whose text was changed after indexing must fail, not silently match."""
    row = load_memory_rows(MEMORY)[0]
    records = build_index(transcript, [row])
    assert records[0].source_ref is not None

    tampered = row.model_copy(update={"text": "One transaction covers the enqueue path only"})
    verdicts = challenge(transcript, [tampered], records)
    assert verdicts[0].verdict is Verdict.NOT_DERIVABLE
    assert verdicts[0].pinned_by == "index"
    assert verdicts[0].source_ref is not None
