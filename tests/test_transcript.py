"""The transcript reader must count the file's real lines.

A JSON string may carry U+2028, U+2029 and U+0085 unescaped, and Claude Code
writes them that way. Splitting on anything but "\\n" cuts a record in half and
shifts every later ``line_index``, which is the identity a pinned pointer uses.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from recallproof import load_transcript


def _record(uuid: str, text: str, parent: str | None = None) -> dict:
    return {
        "parentUuid": parent,
        "type": "user",
        "uuid": uuid,
        "timestamp": "2026-11-26T09:00:00.000Z",
        "sessionId": "aaaa1111-2222-4333-8444-555566667777",
        "message": {"role": "user", "content": text},
    }


def test_load_transcript_accepts_unicode_line_separators(tmp_path: Path):
    text = "paste starts\u2028here\u2029then\u0085ends"
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(_record("aaaa1111-0000-4000-8000-000000000001", text), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    transcript = load_transcript(session)

    assert len(transcript.events) == 1
    assert transcript.events[0].text == text


def test_line_index_matches_physical_line_number(tmp_path: Path):
    """After a record carrying U+2028, later line_index values must not shift."""
    lines = [
        json.dumps({"type": "queue-operation", "sessionId": "s1", "content": "/plan"}),
        json.dumps(
            _record("aaaa1111-0000-4000-8000-000000000001", "first\u2028second"),
            ensure_ascii=False,
        ),
        json.dumps(
            _record(
                "aaaa1111-0000-4000-8000-000000000002",
                "third",
                parent="aaaa1111-0000-4000-8000-000000000001",
            ),
            ensure_ascii=False,
        ),
    ]
    session = tmp_path / "session.jsonl"
    session.write_text("\n".join(lines) + "\n", encoding="utf-8")

    physical = session.read_text(encoding="utf-8").split("\n")
    assert physical[1].startswith('{"parentUuid"')  # one record, one line
    assert physical[2].startswith('{"parentUuid"')

    transcript = load_transcript(session)

    assert [event.line_index for event in transcript.events] == [1, 2]
    assert transcript.events[0].text == "first\u2028second"
    assert transcript.event(2, 0) is not None
    assert transcript.event(2, 0).text == "third"


def test_crlf_transcript_drops_the_carriage_return(tmp_path: Path):
    """A CRLF file still hashes the text line, not the line ending."""
    line = json.dumps(
        _record("aaaa1111-0000-4000-8000-000000000001", "windows line"), ensure_ascii=False
    )
    session = tmp_path / "session.jsonl"
    session.write_bytes(f"{line}\r\n".encode("utf-8"))

    transcript = load_transcript(session)

    assert transcript.events[0].text == "windows line"
    assert transcript.events[0].sha256 == hashlib.sha256(line.encode("utf-8")).hexdigest()
