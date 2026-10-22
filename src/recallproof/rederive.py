"""Re-derivation: the one pure function the product rests on.

``rederive(event_log, source_ref, expected_text)`` re-reads the pinned event,
slices the pinned character span out of the selected ``text`` block and compares
the slice with the row text byte-for-byte. No model call, no embedding, no
second opinion — the verdict is a property of the files, so it is the same on
every run and on every machine.

The verdict is one of three honest states:

``DERIVED``
    The pinned line still hashes to ``event_sha256`` and the span reproduces the
    row text byte-for-byte.
``NOT_DERIVABLE``
    The pinned event is gone, changed, or the span no longer reproduces the row
    text. This is the verdict for a counterfeit recall.
``UNSUPPORTED_DERIVATION``
    The row is not an extractive slice of any event (an AI-compressed summary,
    an embedding, a merge), or its only evidence sits in an excluded block. The
    tool refuses to guess rather than fall back to a judge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .ledger import SourceRef
from .transcript import TranscriptEvent


class Verdict(str, Enum):
    DERIVED = "DERIVED"
    NOT_DERIVABLE = "NOT_DERIVABLE"
    UNSUPPORTED_DERIVATION = "UNSUPPORTED_DERIVATION"

    @property
    def ok(self) -> bool:
        return self is Verdict.DERIVED


@dataclass(frozen=True, slots=True)
class Derivation:
    """The verdict plus everything a reader needs to check it by hand."""

    verdict: Verdict
    reason: str
    event: TranscriptEvent | None = None
    span: tuple[int, int] | None = None
    reproduced: str | None = None

    @property
    def ok(self) -> bool:
        return self.verdict.ok


def unsupported(reason: str) -> Derivation:
    return Derivation(verdict=Verdict.UNSUPPORTED_DERIVATION, reason=reason)


def rederive(
    event_log: Sequence[TranscriptEvent],
    source_ref: SourceRef,
    expected_text: str | None = None,
) -> Derivation:
    """Replay ``source_ref`` against ``event_log`` and return a verdict.

    Pure: the same ``event_log`` and ``source_ref`` always produce the same
    :class:`Derivation`. ``expected_text`` is optional so the function can also
    answer "does this pinned pointer still resolve?" on its own.
    """
    event = next(
        (
            candidate
            for candidate in event_log
            if candidate.line_index == source_ref.line_index
            and candidate.block_index == source_ref.block_index
        ),
        None,
    )
    if event is None:
        return Derivation(
            verdict=Verdict.NOT_DERIVABLE,
            reason=(
                f"no event at line {source_ref.line_index} "
                f"block {source_ref.block_index}"
            ),
            span=source_ref.span,
        )

    if event.sha256 != source_ref.event_sha256:
        return Derivation(
            verdict=Verdict.NOT_DERIVABLE,
            reason=f"line {source_ref.line_index} changed since it was pinned",
            event=event,
            span=source_ref.span,
        )

    if source_ref.source_uuid and event.uuid != source_ref.source_uuid:
        return Derivation(
            verdict=Verdict.NOT_DERIVABLE,
            reason=(
                f"line {source_ref.line_index} is now {event.uuid[:8]}, "
                f"pinned as {source_ref.source_uuid[:8]}"
            ),
            event=event,
            span=source_ref.span,
        )

    start, end = source_ref.span
    if start < 0 or end < start or end > len(event.text):
        return Derivation(
            verdict=Verdict.NOT_DERIVABLE,
            reason=f"span {start}:{end} outside a {len(event.text)}-char block",
            event=event,
            span=source_ref.span,
        )

    reproduced = event.text[start:end]
    if expected_text is not None and reproduced != expected_text:
        return Derivation(
            verdict=Verdict.NOT_DERIVABLE,
            reason="span no longer reproduces the row text",
            event=event,
            span=source_ref.span,
            reproduced=reproduced,
        )

    return Derivation(
        verdict=Verdict.DERIVED,
        reason=(
            f"line {event.line_index} block {event.block_index} "
            f"chars {start}:{end} reproduce the row text"
        ),
        event=event,
        span=source_ref.span,
        reproduced=reproduced,
    )
