"""The m1 gate: prove re-derivation is byte-deterministic, or say so out loud.

Milestone one is a gate, not a feature. Before any UI exists, this spike answers
one question on a hand-built fixture shaped exactly like a real Claude Code
session JSONL:

1. does an extractive row re-derive byte-identically on every run, and
2. does an abstractive row return ``UNSUPPORTED_DERIVATION`` instead of a
   fabricated verdict.

If the first half fails, the primitive collapses back into the LLM judge it
rejects, and the honest answer is to publish the write-up instead of shipping.

    python -m recallproof.spike --fixture
    python -m recallproof.spike --session ~/.claude/projects/<slug>/<id>.jsonl \\
        --memory my_rows.jsonl
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from .challenge import RowVerdict, challenge
from .ledger import load_memory_rows, pin
from .rederive import Verdict, rederive
from .transcript import load_transcript

DEFAULT_RUNS = 100

FIXTURE_SESSION_ID = "0f1c9a52-6d31-4d0e-9d7c-2b5a6f4c1e88"

# A hand-built session, shaped exactly like a real transcript: camelCase
# `sessionId`, a `parentUuid` chain, no `seq`, polymorphic `message.content` on
# both roles (a plain string on one user turn, typed blocks everywhere else),
# plus the metadata record types a real file interleaves.
FIXTURE_LINES: list[dict] = [
    {
        "type": "queue-operation",
        "operation": "enqueue",
        "sessionId": FIXTURE_SESSION_ID,
        "timestamp": "2026-10-19T09:12:03.114Z",
        "content": "/plan the queue migration",
    },
    {
        "parentUuid": None,
        "isSidechain": False,
        "type": "user",
        "uuid": "b1f0c4d2-1111-4a11-8a11-000000000001",
        "timestamp": "2026-10-19T09:12:04.001Z",
        "sessionId": FIXTURE_SESSION_ID,
        "message": {
            "role": "user",
            "content": "Settle the queue: we are moving off Redis onto Postgres, right?",
        },
    },
    {
        "parentUuid": "b1f0c4d2-1111-4a11-8a11-000000000001",
        "isSidechain": False,
        "type": "assistant",
        "uuid": "b1f0c4d2-2222-4a22-8a22-000000000002",
        "timestamp": "2026-10-19T09:12:09.402Z",
        "sessionId": FIXTURE_SESSION_ID,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "The user wants the queue backend decision confirmed.",
                },
                {
                    "type": "text",
                    "text": (
                        "Decision recorded: the job queue moves to Postgres. "
                        "One transaction covers enqueue and the row it schedules, "
                        "which removes the Redis/Postgres dual-write failure mode."
                    ),
                },
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "Edit",
                    "input": {"file_path": "docs/adr/0007-queue-backend.md"},
                },
            ],
        },
    },
    {
        "parentUuid": "b1f0c4d2-2222-4a22-8a22-000000000002",
        "isSidechain": False,
        "type": "user",
        "uuid": "b1f0c4d2-3333-4a33-8a33-000000000003",
        "timestamp": "2026-10-19T09:12:10.118Z",
        "sessionId": FIXTURE_SESSION_ID,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_01",
                    "content": "File created: docs/adr/0007-queue-backend.md",
                }
            ],
        },
    },
    {
        "type": "last-prompt",
        "sessionId": FIXTURE_SESSION_ID,
        "timestamp": "2026-10-19T09:12:11.002Z",
        "content": "Settle the queue: we are moving off Redis onto Postgres, right?",
    },
    {
        "parentUuid": "b1f0c4d2-3333-4a33-8a33-000000000003",
        "isSidechain": False,
        "type": "assistant",
        "uuid": "b1f0c4d2-4444-4a44-8a44-000000000004",
        "timestamp": "2026-10-19T09:12:14.771Z",
        "sessionId": FIXTURE_SESSION_ID,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "The stale-token incident was a clock-skew problem, not a "
                        "queue problem: the token expired 40ms before the request "
                        "was signed on a machine 900ms behind."
                    ),
                }
            ],
        },
    },
]

EXTRACTIVE_TEXT = (
    "Decision recorded: the job queue moves to Postgres. "
    "One transaction covers enqueue and the row it schedules, "
    "which removes the Redis/Postgres dual-write failure mode."
)
# Plausible, confidently phrased, and never said in this session.
COUNTERFEIT_TEXT = "We agreed to keep Redis Streams as the job queue backend."
# AI-compressed: a summary of the session, not a slice of any single event.
ABSTRACTIVE_TEXT = (
    "Session summary: the team moved the job queue to Postgres and root-caused "
    "a stale-token incident to clock skew."
)


# What the hand-built fixture is supposed to prove, row by row.
FIXTURE_EXPECTATIONS: dict[str, Verdict] = {
    "fixture_derived": Verdict.DERIVED,
    "fixture_counterfeit": Verdict.NOT_DERIVABLE,
    "fixture_abstractive": Verdict.UNSUPPORTED_DERIVATION,
}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def write_fixture(directory: Path) -> tuple[Path, Path]:
    session = directory / "session.jsonl"
    session.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in FIXTURE_LINES),
        encoding="utf-8",
    )
    rows = [
        {"row_id": "fixture_derived", "text": EXTRACTIVE_TEXT},
        {"row_id": "fixture_counterfeit", "text": COUNTERFEIT_TEXT},
        {
            "row_id": "fixture_abstractive",
            "text": ABSTRACTIVE_TEXT,
            "derivation": "abstractive",
        },
    ]
    memory = directory / "memory_rows.jsonl"
    memory.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return session, memory


def _digest(verdict: RowVerdict) -> str:
    """Everything that would change if re-derivation were non-deterministic."""
    event = verdict.event
    return json.dumps(
        {
            "row_id": verdict.row_id,
            "verdict": verdict.verdict.value,
            "reason": verdict.reason,
            "span": list(verdict.span) if verdict.span else None,
            "uuid": event.uuid if event else None,
            "line_index": event.line_index if event else None,
            "block_index": event.block_index if event else None,
            "sha256": event.sha256 if event else None,
        },
        sort_keys=True,
    )


def check_determinism(
    session: Path,
    memory: Path,
    runs: int,
    expectations: dict[str, Verdict] | None = None,
) -> list[Check]:
    """Re-load and re-derive the same rows ``runs`` times; compare digests."""
    checks: list[Check] = []
    rows = load_memory_rows(memory)

    seen: dict[str, set[str]] = {}
    verdicts: dict[str, RowVerdict] = {}
    for _ in range(runs):
        transcript = load_transcript(session)
        for item in challenge(transcript, rows):
            seen.setdefault(item.row_id, set()).add(_digest(item))
            verdicts[item.row_id] = item

    stable = [row_id for row_id, digests in seen.items() if len(digests) == 1]
    checks.append(
        Check(
            name=f"re-derivation is byte-identical across {runs}/{runs} runs",
            passed=len(stable) == len(seen) and len(seen) == len(rows),
            detail=f"{len(stable)}/{len(rows)} rows produced one digest each",
        )
    )

    for row in rows:
        verdict = verdicts[row.row_id]
        expected = (
            Verdict.UNSUPPORTED_DERIVATION
            if row.is_abstractive
            else (expectations or {}).get(row.row_id)
        )
        if expected is None:
            checks.append(_consistency_check(verdict))
        else:
            checks.append(
                Check(
                    name=f"{row.row_id}: {row.derivation} row → {expected.value}",
                    passed=verdict.verdict is expected,
                    detail=(
                        f"{verdict.verdict.value} — {verdict.pin_label}"
                        if verdict.ok
                        else f"{verdict.verdict.value} ({verdict.reason})"
                    ),
                )
            )
    return checks


def _consistency_check(verdict: RowVerdict) -> Check:
    """On rows whose verdict is not known in advance, check it is self-consistent."""
    if verdict.verdict is Verdict.DERIVED:
        passed = verdict.event is not None and verdict.span is not None
        detail = f"pinned {verdict.pin_label}"
    else:
        passed = verdict.span is None or verdict.verdict is Verdict.NOT_DERIVABLE
        detail = verdict.reason
    return Check(
        name=f"{verdict.row_id}: {verdict.verdict.value} is self-consistent",
        passed=passed,
        detail=detail,
    )


def check_purity(session: Path, memory: Path) -> list[Check]:
    """A wrong span and a changed line must both fail, not be forgiven."""
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    extractive = rows[0]
    source_ref = pin(transcript, extractive)
    if source_ref is None:
        return [Check("pin an extractive row", False, "no pointer resolved")]

    checks = [
        Check(
            "a pure re-derivation of the pinned pointer returns DERIVED",
            rederive(transcript.events, source_ref, extractive.text).verdict
            is Verdict.DERIVED,
            source_ref.describe(),
        )
    ]

    shifted = source_ref.model_copy(update={"span": (source_ref.span[0], source_ref.span[1] - 1)})
    checks.append(
        Check(
            "a shortened span fails instead of matching loosely",
            rederive(transcript.events, shifted, extractive.text).verdict
            is Verdict.NOT_DERIVABLE,
            f"span {shifted.span[0]}:{shifted.span[1]}",
        )
    )

    stale = source_ref.model_copy(update={"event_sha256": "0" * 64})
    checks.append(
        Check(
            "a line that changed since it was pinned fails",
            rederive(transcript.events, stale, extractive.text).verdict
            is Verdict.NOT_DERIVABLE,
            "pinned sha256 no longer matches the line",
        )
    )
    return checks


def run_gate(
    session: Path,
    memory: Path,
    runs: int = DEFAULT_RUNS,
    console: Console | None = None,
    label: str | None = None,
    expectations: dict[str, Verdict] | None = None,
) -> bool:
    """Run every check and print PASS / FAIL. Returns True when the gate passes."""
    console = console or Console()
    console.print(f"[bold]recallproof gate[/bold]  {label or f'session={session}  memory={memory}'}")
    checks = check_determinism(session, memory, runs, expectations) + check_purity(
        session, memory
    )
    for check in checks:
        mark = "[green]PASS[/green]" if check.passed else "[red]FAIL[/red]"
        console.print(f"  {mark}  {check.name}  [dim]({check.detail})[/dim]")
    passed = all(check.passed for check in checks)
    summary = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
    console.print(f"[bold]{summary}[/bold]  {sum(c.passed for c in checks)}/{len(checks)} checks")
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m recallproof.spike",
        description="m1 gate: byte-deterministic re-derivation on extractive rows.",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="run the gate on the hand-built fixture (default when no session is given)",
    )
    parser.add_argument("--session", type=Path, help="a real session JSONL to gate")
    parser.add_argument("--memory", type=Path, help="memory rows for --session")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="repetitions (default 100)")
    args = parser.parse_args(argv)

    if bool(args.session) != bool(args.memory):
        parser.error("--session and --memory must be given together")
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    if args.session and args.memory and not args.fixture:
        return 0 if run_gate(args.session, args.memory, args.runs) else 1

    with tempfile.TemporaryDirectory(prefix="recallproof-gate-") as tmp:
        session, memory = write_fixture(Path(tmp))
        passed = run_gate(
            session,
            memory,
            args.runs,
            label="hand-built fixture — 1 extractive, 1 counterfeit, 1 abstractive row",
            expectations=FIXTURE_EXPECTATIONS,
        )
        return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
