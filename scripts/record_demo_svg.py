#!/usr/bin/env python3
"""Record ``assets/demo.svg`` from a real ``recallproof challenge`` run.

The SVG is not drawn: it is the actual terminal output, captured through rich's
recorder and written out with the same table renderer the CLI uses. Re-running
this script after a change to the tool is how the committed demo asset is
refreshed (``.github/workflows/demo.yml`` does exactly that).

    pip install -e .
    python scripts/record_demo_svg.py
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from recallproof.challenge import challenge
from recallproof.cli import render_table
from recallproof.ledger import load_memory_rows
from recallproof.transcript import load_transcript

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "examples" / "session.jsonl"
MEMORY = ROOT / "examples" / "memory_rows.jsonl"
OUT = ROOT / "assets" / "demo.svg"

# The table is 97 columns wide at these example paths, so 100 keeps every cell
# on one line and lands the image at roughly 900px: legible in a README.
WIDTH = 100
HEIGHT = 24

COMMAND = "recallproof challenge --session examples/session.jsonl --memory examples/memory_rows.jsonl"


def main() -> int:
    console = Console(
        record=True,
        width=WIDTH,
        height=HEIGHT,
        color_system="truecolor",
        highlight=False,
    )

    verdicts = challenge(load_transcript(SESSION), load_memory_rows(MEMORY))

    console.print(f"[bold green]$[/bold green] {COMMAND}")
    render_table(console, verdicts)
    console.print("[bold green]$[/bold green] echo $?")
    console.print("1")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    console.save_svg(str(OUT), title="recallproof challenge — one row DERIVED, one NOT DERIVABLE")
    size = OUT.stat().st_size
    print(f"recorded {OUT.relative_to(ROOT)} from a real run ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
