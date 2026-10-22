"""Batch verdicts over memory rows: the table, the JSON, and the exit code.

``challenge`` is the demo moment. It walks every recalled row, resolves its
pointer against the session JSONL, re-derives it, and prints what happened. The
interesting output is not the green row — it is the red one, because no LLM
judge and no memory store in the probe can produce that verdict today.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .ledger import MemoryRow, PointerRecord, SourceRef, build_index
from .rederive import Derivation, Verdict, rederive, unsupported
from .transcript import Transcript, TranscriptEvent

SCHEMA_VERSION = 1

# ``pinned_by`` values. ``MISSING`` is the honest state for a row an explicit
# pointer index holds no pin for: the row was never resolved, so its verdict
# cannot claim that no event reproduces its text.
PIN_RESOLVED = "resolved"
PIN_INDEX = "index"
PIN_MISSING = "missing"
PIN_NONE = "none"


@dataclass(frozen=True, slots=True)
class RowVerdict:
    """One challenged row: the verdict plus the evidence behind it."""

    row_id: str
    text: str
    verdict: Verdict
    reason: str
    source_ref: SourceRef | None = None
    event: TranscriptEvent | None = None
    span: tuple[int, int] | None = None
    pinned_by: str = PIN_NONE
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict.ok

    @property
    def source_label(self) -> str:
        if self.source_ref is None:
            return "-"
        return (
            f"{self.source_ref.source_uuid[:8]} "
            f"L{self.source_ref.line_index}/B{self.source_ref.block_index}"
        )

    @property
    def span_label(self) -> str:
        if self.span is None:
            return "-"
        return f"{self.span[0]}:{self.span[1]}"

    @property
    def pin_label(self) -> str:
        """The pinned event and span, in one cell."""
        if self.source_ref is None:
            return "-"
        return f"{self.source_label} · {self.span_label}"


def _from_derivation(
    row: MemoryRow,
    derivation: Derivation,
    source_ref: SourceRef | None,
    pinned_by: str,
    note: str = "",
) -> RowVerdict:
    if not note and derivation.verdict is Verdict.DERIVED:
        note = "span reproduces the row text"
    return RowVerdict(
        row_id=row.row_id,
        text=row.text,
        verdict=derivation.verdict,
        reason=derivation.reason,
        source_ref=source_ref,
        event=derivation.event,
        span=derivation.span if derivation.span is not None else (source_ref.span if source_ref else None),
        pinned_by=pinned_by,
        note=note or derivation.reason,
    )


def judge_row(
    transcript: Transcript,
    row: MemoryRow,
    source_ref: SourceRef | None,
    pinned_by: str,
) -> RowVerdict:
    """Compute the verdict for a single row.

    This is the one place a row's verdict is decided, so ``challenge`` and
    ``rederive`` cannot disagree about the same row.
    """
    if row.is_abstractive:
        return _from_derivation(
            row,
            unsupported("row is an abstraction, not a slice of any session event"),
            None,
            PIN_NONE,
            note="abstractive row — not judged",
        )

    if source_ref is not None:
        return _from_derivation(
            row,
            rederive(transcript.events, source_ref, row.text),
            source_ref,
            pinned_by,
        )

    if transcript.has_excluded_evidence(row.text):
        return _from_derivation(
            row,
            unsupported(
                "the only matching evidence sits in an excluded block or record type"
            ),
            None,
            PIN_NONE,
            note="evidence sits in an excluded block",
        )

    if pinned_by == PIN_MISSING:
        return RowVerdict(
            row_id=row.row_id,
            text=row.text,
            verdict=Verdict.NOT_DERIVABLE,
            reason="the pointer index holds no pin for this row",
            pinned_by=PIN_MISSING,
            note="row is not in the pointer index — index it to challenge it",
        )

    return RowVerdict(
        row_id=row.row_id,
        text=row.text,
        verdict=Verdict.NOT_DERIVABLE,
        reason="no session event reproduces this text",
        pinned_by=PIN_NONE,
        note="no event reproduces this text",
    )


def challenge(
    transcript: Transcript,
    rows: Sequence[MemoryRow],
    index: Sequence[PointerRecord] | None = None,
) -> list[RowVerdict]:
    """Challenge every row.

    With ``index=None`` pointers are resolved from the transcript in memory,
    which is what a first run does. Pass a loaded pointer index to challenge
    against pins recorded earlier — a row edited after indexing then fails
    re-derivation instead of silently matching a fresh slice, and a row the
    index holds no pin for is reported as unpinned rather than as a counterfeit.
    """
    if index is None:
        pinned = {
            record.row_id: (record.source_ref, PIN_RESOLVED)
            for record in build_index(transcript, rows)
        }
    else:
        pinned = {record.row_id: (record.source_ref, PIN_INDEX) for record in index}
    verdicts: list[RowVerdict] = []
    for row in rows:
        source_ref, pinned_by = pinned.get(row.row_id, (None, PIN_MISSING))
        verdicts.append(judge_row(transcript, row, source_ref, pinned_by))
    return verdicts


def counts(verdicts: Iterable[RowVerdict]) -> dict[str, int]:
    tally = {verdict.value: 0 for verdict in Verdict}
    for item in verdicts:
        tally[item.verdict.value] += 1
    return tally


def exit_code(verdicts: Sequence[RowVerdict]) -> int:
    """``0`` when every row re-derived; ``1`` when any row did not."""
    return 0 if all(item.verdict.ok for item in verdicts) else 1


def _event_payload(event: TranscriptEvent | None) -> dict | None:
    if event is None:
        return None
    return {
        "uuid": event.uuid,
        "role": event.role,
        "line_index": event.line_index,
        "block_index": event.block_index,
        "parent_depth": event.parent_depth,
        "sha256": event.sha256,
        "text": event.text,
    }


def verdicts_payload(
    verdicts: Sequence[RowVerdict],
    session: str | Path,
    memory: str | Path,
) -> dict:
    """The ``--json`` document, for CI and for other tools."""
    return {
        "schema_version": SCHEMA_VERSION,
        "session": str(session),
        "memory": str(memory),
        "counts": counts(verdicts),
        "rows": [
            {
                "row_id": item.row_id,
                "verdict": item.verdict.value,
                "reason": item.reason,
                "note": item.note,
                "pinned_by": item.pinned_by,
                "source_ref": item.source_ref.model_dump(mode="json") if item.source_ref else None,
                "source_event": _event_payload(item.event),
                "span": list(item.span) if item.span else None,
                "text": item.text,
            }
            for item in verdicts
        ],
    }
