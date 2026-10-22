"""The grounded memory row, and the sidecar pointer index that pins it.

A memory row is the unit under challenge. It is the same row a memory store
hands back — ``row_id`` plus the recalled ``text`` — with one addition: a
``derivation`` class saying whether the row claims to be an extractive slice of a
session event, or an AI-compressed abstraction.

The pointer index is a sidecar JSONL file. Each record carries the
:class:`SourceRef` for one row, referencing the session JSONL by
``line_index`` / ``source_uuid`` / ``event_sha256``. Nothing is written into
claude-mem's or mem0's SQLite stores: those stores are not opened, and the index
lives next to the memory export the user already has.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .transcript import Transcript

DerivationClass = Literal["extractive", "abstractive"]


class LedgerError(Exception):
    """A memory row file or pointer index could not be read."""


class SourceRef(BaseModel):
    """A replayable pointer to the session event a row was derived from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    source_uuid: str
    line_index: int = Field(ge=0)
    parent_depth: int = Field(ge=0)
    event_sha256: str = Field(min_length=64, max_length=64)
    block_index: int = Field(ge=0)
    span: tuple[int, int]
    derivation: Literal["extractive"] = "extractive"

    def describe(self) -> str:
        start, end = self.span
        return (
            f"line {self.line_index} block {self.block_index} "
            f"chars {start}:{end} uuid {self.source_uuid[:8]}"
        )


class MemoryRow(BaseModel):
    """A recalled row as exported by a memory store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_id: str
    text: str
    derivation: DerivationClass = "extractive"
    source_ref: SourceRef | None = None


class PointerRecord(BaseModel):
    """One line of the sidecar pointer index."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_id: str
    source_ref: SourceRef | None = None


def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LedgerError(f"cannot read {path}: {exc}") from exc
    rows: list[dict] = []
    for number, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise LedgerError(f"{path}:{number}: expected a JSON object")
        rows.append(record)
    return rows


def load_memory_rows(path: str | Path) -> list[MemoryRow]:
    """Read memory rows from a JSONL export."""
    rows: list[MemoryRow] = []
    for number, record in enumerate(read_jsonl(path), start=1):
        try:
            rows.append(MemoryRow.model_validate(record))
        except ValidationError as exc:
            raise LedgerError(f"{path}: row {number}: {exc}") from exc
    return rows


def load_index(path: str | Path) -> list[PointerRecord]:
    """Read a sidecar pointer index."""
    records: list[PointerRecord] = []
    for number, record in enumerate(read_jsonl(path), start=1):
        try:
            records.append(PointerRecord.model_validate(record))
        except ValidationError as exc:
            raise LedgerError(f"{path}: record {number}: {exc}") from exc
    return records


def write_index(path: str | Path, records: Iterable[PointerRecord]) -> int:
    """Write a sidecar pointer index; returns the number of records written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [record.model_dump_json(exclude_none=False) for record in records]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return len(lines)


def pin(transcript: Transcript, row: MemoryRow) -> SourceRef | None:
    """Resolve ``row`` to a replayable pointer, or ``None`` if it cannot be.

    Resolution is deliberately narrow: the row text must appear verbatim inside
    a single selected ``text`` block of a ``user`` / ``assistant`` record. If it
    does not, the row is not extractively derivable, and no pointer is invented.
    """
    found = transcript.span_of(row.text)
    if found is None:
        return None
    event, span = found
    return SourceRef(
        session_id=event.session_id,
        source_uuid=event.uuid,
        line_index=event.line_index,
        parent_depth=event.parent_depth,
        event_sha256=event.sha256,
        block_index=event.block_index,
        span=span,
    )


def build_index(transcript: Transcript, rows: Iterable[MemoryRow]) -> list[PointerRecord]:
    """Pin every row; unresolved rows are recorded with ``source_ref`` null."""
    return [PointerRecord(row_id=row.row_id, source_ref=pin(transcript, row)) for row in rows]
