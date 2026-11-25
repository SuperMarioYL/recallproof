"""The row and pointer files go through the same line split as the transcript."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recallproof import load_memory_rows
from recallproof.ledger import LedgerError, load_index


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085"])
def test_read_jsonl_accepts_unicode_line_separators(tmp_path: Path, separator: str):
    text = f"alpha{separator}beta"
    memory = tmp_path / "rows.jsonl"
    memory.write_text(
        json.dumps({"row_id": "r1", "text": text}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = load_memory_rows(memory)

    assert [row.text for row in rows] == [text]


def test_one_row_per_line_still_counts_the_file_lines(tmp_path: Path):
    """A separator inside one row must not split it into two rows."""
    memory = tmp_path / "rows.jsonl"
    memory.write_text(
        "\n".join(
            [
                json.dumps({"row_id": "r1", "text": "a\u2028b"}, ensure_ascii=False),
                json.dumps({"row_id": "r2", "text": "plain"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_memory_rows(memory)

    assert [row.row_id for row in rows] == ["r1", "r2"]


def test_a_really_broken_line_still_fails_loudly(tmp_path: Path):
    memory = tmp_path / "rows.jsonl"
    memory.write_bytes(b'{"row_id": "r1", "text":\n')

    with pytest.raises(LedgerError, match="invalid JSON"):
        load_memory_rows(memory)


def test_pointer_index_shares_the_split(tmp_path: Path):
    pointers = tmp_path / "pointers.jsonl"
    pointers.write_text(
        json.dumps({"row_id": "r\u2028one", "source_ref": None}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    assert [record.row_id for record in load_index(pointers)] == ["r\u2028one"]
