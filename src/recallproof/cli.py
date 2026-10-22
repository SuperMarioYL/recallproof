"""``recallproof`` command line: challenge, index, rederive, gate.

Read-only over both inputs. No config file, no API key, no model call — the
verdict is a property of the two files on disk, so it is reproducible.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .challenge import (
    PIN_INDEX,
    RowVerdict,
    challenge,
    exit_code,
    judge_row,
    verdicts_payload,
)
from .ledger import (
    LedgerError,
    build_index,
    load_index,
    load_memory_rows,
    write_index,
)
from .rederive import Verdict
from .spike import DEFAULT_RUNS, FIXTURE_EXPECTATIONS, run_gate, write_fixture
from .transcript import TranscriptError, load_transcript

DEFAULT_SESSION = Path("examples/session.jsonl")
DEFAULT_MEMORY = Path("examples/memory_rows.jsonl")
DEFAULT_POINTERS = Path("examples/pointers.jsonl")

# ``rederive`` exits 2 when it has no row text to compare, so a "cannot replay"
# is never mistaken for the verdict ``NOT_DERIVABLE`` (exit 1).
EXIT_NO_ROW_TEXT = 2

VERDICT_STYLE = {
    Verdict.DERIVED: "bold green",
    Verdict.NOT_DERIVABLE: "bold red",
    Verdict.UNSUPPORTED_DERIVATION: "bold yellow",
}

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Make agent memory prove its source event.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"recallproof {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Recall attestation for AI agent memory."""


def _fail(console: Console, message: str, code: int = 2) -> NoReturn:
    console.print(f"[bold red]error:[/bold red] {message}")
    raise typer.Exit(code)


def _load_inputs(
    console: Console, session: Path, memory: Path, pointers: Path | None
):
    for label, path in (("session", session), ("memory", memory)):
        if not path.is_file():
            _fail(console, f"{label} file not found: {path}")
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    index = None
    if pointers is not None:
        if not pointers.is_file():
            _fail(console, f"pointer index not found: {pointers}")
        index = load_index(pointers)
    return transcript, rows, index


def render_table(console: Console, verdicts: list[RowVerdict]) -> None:
    """The verdict table. Shared by ``challenge`` and the demo recorder."""
    table = Table(
        title="recallproof challenge",
        title_justify="left",
        header_style="bold",
        border_style="dim",
        expand=False,
    )
    table.add_column("row", style="cyan", no_wrap=True)
    table.add_column("verdict", no_wrap=True)
    table.add_column("pinned event · span", no_wrap=True)
    table.add_column("what happened", no_wrap=True)
    for item in verdicts:
        table.add_row(
            item.row_id,
            f"[{VERDICT_STYLE[item.verdict]}]{item.verdict.value}[/]",
            item.pin_label,
            item.note,
        )
    console.print(table)
    tally = ", ".join(
        f"[{VERDICT_STYLE[verdict]}]{verdict.value}[/] {sum(1 for i in verdicts if i.verdict is verdict)}"
        for verdict in Verdict
    )
    console.print(f"{len(verdicts)} rows challenged — {tally}")


@app.command("challenge")
def challenge_cmd(
    session: Path = typer.Option(DEFAULT_SESSION, "--session", "-s", help="Claude Code session JSONL."),
    memory: Path = typer.Option(DEFAULT_MEMORY, "--memory", "-m", help="Memory rows as JSONL."),
    pointers: Path | None = typer.Option(
        None,
        "--pointers",
        "-p",
        help="Challenge against a pinned pointer index instead of resolving now.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable verdicts for CI."),
) -> None:
    """Print a DERIVED / NOT DERIVABLE verdict for every memory row.

    Exits 0 when every row re-derived, 1 when any row did not.
    """
    console = Console()
    transcript, rows, index = _load_inputs(console, session, memory, pointers)
    verdicts = challenge(transcript, rows, index)

    if json_output:
        typer.echo(json.dumps(verdicts_payload(verdicts, session, memory), indent=2))
    else:
        render_table(console, verdicts)
    raise typer.Exit(exit_code(verdicts))


@app.command("index")
def index_cmd(
    session: Path = typer.Option(DEFAULT_SESSION, "--session", "-s", help="Claude Code session JSONL."),
    memory: Path = typer.Option(DEFAULT_MEMORY, "--memory", "-m", help="Memory rows as JSONL."),
    out: Path = typer.Option(DEFAULT_POINTERS, "--out", "-o", help="Pointer index to write."),
) -> None:
    """Write the sidecar pointer index that pins each row to its source event."""
    console = Console()
    for label, path in (("session", session), ("memory", memory)):
        if not path.is_file():
            _fail(console, f"{label} file not found: {path}")
    transcript = load_transcript(session)
    rows = load_memory_rows(memory)
    records = build_index(transcript, rows)
    written = write_index(out, records)
    pinned = sum(1 for record in records if record.source_ref is not None)
    console.print(
        f"[bold]{written}[/bold] rows indexed — "
        f"[green]{pinned}[/green] pinned, [red]{written - pinned}[/red] unpinned → {out}"
    )


@app.command("rederive")
def rederive_cmd(
    row_id: str = typer.Argument(..., help="The memory row to replay."),
    session: Path = typer.Option(DEFAULT_SESSION, "--session", "-s", help="Claude Code session JSONL."),
    memory: Path | None = typer.Option(
        None,
        "--memory",
        "-m",
        help="Memory rows as JSONL. Required: the verdict compares the row text byte for byte, and the pointer index does not carry it.",
    ),
    pointers: Path = typer.Option(DEFAULT_POINTERS, "--pointers", "-p", help="Pointer index to read."),
) -> None:
    """Replay one row's pinned event and print the source span, or exit non-zero.

    Exits 0 on ``DERIVED``, 1 on a verdict that is not ``DERIVED``, and 2 when
    the row could not be replayed at all — no row text to compare, or no pin in
    the index.
    """
    console = Console()
    if memory is None:
        _fail(console, "--memory is required: rederive needs the row text to compare")
    for label, path in (("session", session), ("memory", memory), ("pointers", pointers)):
        if not path.is_file():
            _fail(console, f"{label} file not found: {path}")

    transcript = load_transcript(session)
    row = next((row for row in load_memory_rows(memory) if row.row_id == row_id), None)
    if row is None:
        console.print(
            f"[bold yellow]ROW_TEXT_UNAVAILABLE[/bold yellow] {row_id} — "
            f"{memory} has no row with this id, so there is no text to compare"
        )
        raise typer.Exit(EXIT_NO_ROW_TEXT)

    record = next((record for record in load_index(pointers) if record.row_id == row_id), None)
    if record is None:
        _fail(console, f"row {row_id} is not in {pointers}")

    verdict = judge_row(transcript, row, record.source_ref, PIN_INDEX)
    style = VERDICT_STYLE[verdict.verdict]
    console.print(f"[{style}]{verdict.verdict.value}[/] {row_id}")
    if record.source_ref is None:
        console.print(f"  reason   {verdict.reason}")
    else:
        console.print(f"  pinned   {record.source_ref.describe()}")
        console.print(f"  sha256   {record.source_ref.event_sha256}")
        console.print(f"  reason   {verdict.reason}")
        if verdict.event is not None:
            console.print(f"  role     {verdict.event.role}  depth {verdict.event.parent_depth}")
            console.print(f"  event    {verdict.event.text}")
        if verdict.verdict.ok:
            console.print(f"  replay   {verdict.text}")
    raise typer.Exit(0 if verdict.verdict.ok else 1)


@app.command("gate")
def gate(
    session: Path | None = typer.Option(None, "--session", "-s", help="Gate a real session JSONL."),
    memory: Path | None = typer.Option(None, "--memory", "-m", help="Memory rows for --session."),
    runs: int = typer.Option(100, "--runs", help="Repetitions for the determinism check."),
) -> None:
    """Prove re-derivation is byte-deterministic, on the fixture or on your own files."""
    if bool(session) != bool(memory):
        Console(stderr=True).print("[bold red]error:[/bold red] --session and --memory go together")
        raise typer.Exit(2)
    console = Console()
    if session and memory:
        if not session.is_file() or not memory.is_file():
            _fail(console, "session and memory must both exist")
        passed = run_gate(session, memory, runs, console)
    else:
        with tempfile.TemporaryDirectory(prefix="recallproof-gate-") as tmp:
            fixture_session, fixture_memory = write_fixture(Path(tmp))
            passed = run_gate(
                fixture_session,
                fixture_memory,
                runs or DEFAULT_RUNS,
                console,
                label="hand-built fixture — 1 extractive, 1 counterfeit, 1 abstractive row",
                expectations=FIXTURE_EXPECTATIONS,
            )
    raise typer.Exit(0 if passed else 1)


def main() -> None:
    try:
        app()
    except (TranscriptError, LedgerError) as exc:  # keep the CLI's errors short
        Console(stderr=True).print(f"[bold red]error:[/bold red] {exc}")
        raise SystemExit(2)


__all__ = ["app", "challenge_cmd", "gate", "index_cmd", "main", "rederive_cmd", "render_table"]
