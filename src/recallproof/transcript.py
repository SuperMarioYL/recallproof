"""Read a Claude Code session JSONL into an ordered event log.

The on-disk transcript is the shared upstream that agent memory stores consume:
``~/.claude/projects/<project-slug>/<sessionId>.jsonl``. One JSON object per
line. The reader is strictly read-only and keeps only ``user`` / ``assistant``
records and their ``text`` blocks, because those are the records that carry
memory-bearing prose.

Two shape facts drive this module, both measured on real transcripts:

* ``message.content`` is polymorphic on *both* roles. It is either a plain
  string or an array of typed blocks (``text``, ``thinking``, ``tool_use``,
  ``tool_result``). A plain string is treated as a single implicit ``text``
  block at ``block_index`` 0.
* There is no ``seq`` field. Order comes from file line order, the
  ``parentUuid`` chain and ``timestamp``, never from an invented counter.

Every record type other than ``user`` / ``assistant`` is metadata, and every
block type other than ``text`` is excluded from the event log. Text found only
in excluded evidence is still recorded, so a memory row whose sole support is a
thinking block or a tool result can be reported honestly instead of guessed at.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

MEMORY_ROLES = frozenset({"user", "assistant"})
TEXT_BLOCK = "text"
EXCLUDED_BLOCK_TYPES = frozenset({"thinking", "tool_use", "tool_result"})


class TranscriptError(Exception):
    """The transcript file could not be read as a session JSONL."""


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    """One selected ``text`` block of one ``user`` / ``assistant`` record."""

    session_id: str
    uuid: str
    line_index: int
    parent_uuid: str | None
    parent_depth: int
    role: str
    block_index: int
    text: str
    sha256: str

    @property
    def key(self) -> tuple[int, int]:
        return (self.line_index, self.block_index)

    @property
    def label(self) -> str:
        return f"{self.uuid[:8]}:{self.line_index}:{self.block_index}"


@dataclass(frozen=True, slots=True)
class ExcludedEvidence:
    """Text that exists in the transcript but is not a memory-bearing block."""

    line_index: int
    role: str
    block_type: str
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    """An ordered event log plus the excluded evidence it skipped."""

    path: Path
    session_id: str
    events: tuple[TranscriptEvent, ...] = ()
    excluded: tuple[ExcludedEvidence, ...] = ()
    record_types: tuple[tuple[str, int], ...] = field(default=())

    def event(self, line_index: int, block_index: int) -> TranscriptEvent | None:
        for event in self.events:
            if event.line_index == line_index and event.block_index == block_index:
                return event
        return None

    def locate(self, text: str) -> TranscriptEvent | None:
        """First event, in file order, whose text block contains ``text``."""
        for event in self.events:
            if text in event.text:
                return event
        return None

    def span_of(self, text: str) -> tuple[TranscriptEvent, tuple[int, int]] | None:
        """The first event and the character span of ``text`` inside it."""
        event = self.locate(text)
        if event is None:
            return None
        start = event.text.index(text)
        return event, (start, start + len(text))

    def has_excluded_evidence(self, text: str) -> bool:
        return any(text in item.text for item in self.excluded)

    def as_event_log(self) -> tuple[TranscriptEvent, ...]:
        return self.events


def _line_digest(raw: str) -> str:
    """sha256 of the raw JSONL line, without its trailing newline."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text_blocks(role: str, content: Any) -> Iterator[tuple[int, str]]:
    """Yield ``(block_index, text)`` for every selectable ``text`` block."""
    if isinstance(content, str):
        if content:
            yield 0, content
        return
    if not isinstance(content, list):
        return
    for index, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != TEXT_BLOCK:
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            yield index, text


def _excluded_blocks(role: str, content: Any) -> Iterator[tuple[str, str]]:
    """Yield ``(block_type, text)`` for blocks and strings we do not index."""
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "unknown")
        if block_type == TEXT_BLOCK:
            continue
        for key in ("text", "thinking", "content"):
            value = block.get(key)
            if isinstance(value, str) and value:
                yield block_type, value
                break


def _plain_strings(record: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Yield string payloads of a record we do not treat as an event."""
    record_type = str(record.get("type") or "unknown")
    for key in ("content", "text"):
        value = record.get(key)
        if isinstance(value, str) and value:
            yield record_type, value
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content:
            yield record_type, content
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                for key in ("text", "thinking", "content"):
                    value = block.get(key)
                    if isinstance(value, str) and value:
                        yield record_type, value
                        break


def _parent_depths(records: list[dict[str, Any]]) -> dict[str, int]:
    """Depth along the ``parentUuid`` chain, computed over every record."""
    parents: dict[str, str | None] = {}
    for record in records:
        uuid = record.get("uuid")
        if isinstance(uuid, str):
            parent = record.get("parentUuid")
            parents[uuid] = parent if isinstance(parent, str) else None

    depths: dict[str, int] = {}

    def depth_of(uuid: str, seen: frozenset[str] = frozenset()) -> int:
        if uuid in depths:
            return depths[uuid]
        if uuid in seen or uuid not in parents:
            return 0
        parent = parents[uuid]
        value = 0 if parent is None else depth_of(parent, seen | {uuid}) + 1
        depths[uuid] = value
        return value

    for uuid in parents:
        depth_of(uuid)
    return depths


def load_transcript(path: str | Path) -> Transcript:
    """Read a Claude Code session JSONL into a :class:`Transcript`."""
    path = Path(path)
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TranscriptError(f"cannot read transcript {path}: {exc}") from exc

    records: list[tuple[int, dict[str, Any], str]] = []
    for line_index, raw in enumerate(raw_lines):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranscriptError(f"{path}:{line_index + 1}: invalid JSON: {exc}") from exc
        if isinstance(record, dict):
            records.append((line_index, record, raw))

    depths = _parent_depths([record for _, record, _ in records])

    events: list[TranscriptEvent] = []
    excluded: list[ExcludedEvidence] = []
    type_counts: dict[str, int] = {}
    session_id = ""

    for line_index, record, raw in records:
        record_type = str(record.get("type") or "unknown")
        type_counts[record_type] = type_counts.get(record_type, 0) + 1
        if not session_id:
            value = record.get("sessionId")
            if isinstance(value, str):
                session_id = value

        message = record.get("message")
        role = record_type
        content: Any = None
        if isinstance(message, dict):
            role = str(message.get("role") or record_type)
            content = message.get("content")

        if record_type not in MEMORY_ROLES:
            for block_type, text in _plain_strings(record):
                excluded.append(
                    ExcludedEvidence(
                        line_index=line_index,
                        role=record_type,
                        block_type=f"record:{block_type}",
                        text=text,
                    )
                )
            continue

        uuid = record.get("uuid")
        parent = record.get("parentUuid")
        digest = _line_digest(raw)
        for block_index, text in _text_blocks(role, content):
            events.append(
                TranscriptEvent(
                    session_id=session_id,
                    uuid=uuid if isinstance(uuid, str) else "",
                    line_index=line_index,
                    parent_uuid=parent if isinstance(parent, str) else None,
                    parent_depth=depths.get(uuid, 0) if isinstance(uuid, str) else 0,
                    role=role,
                    block_index=block_index,
                    text=text,
                    sha256=digest,
                )
            )
        for block_type, text in _excluded_blocks(role, content):
            excluded.append(
                ExcludedEvidence(
                    line_index=line_index,
                    role=role,
                    block_type=block_type,
                    text=text,
                )
            )

    return Transcript(
        path=path,
        session_id=session_id,
        events=tuple(events),
        excluded=tuple(excluded),
        record_types=tuple(sorted(type_counts.items())),
    )
