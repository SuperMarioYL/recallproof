# Changelog

All notable changes to this project are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-23

The first release. Extractive, turn-level memory rows only.

### Added

- `recallproof challenge` — a `DERIVED` / `NOT_DERIVABLE` /
  `UNSUPPORTED_DERIVATION` verdict for every memory row, with the source event
  and character span behind a `DERIVED`. `--json` emits a versioned document for
  CI, and the command exits non-zero when any row failed to prove itself.
- `recallproof index` — writes the sidecar pointer index that pins each row to
  its source event by `line_index`, `source_uuid` and `event_sha256`. Rows that
  cannot be pinned are recorded with a null pointer rather than a guess, and an
  `abstractive` row is never pinned even when its text appears verbatim in the
  transcript — the index does not carry a pointer for a row the verdict layer
  refuses to judge.
- `recallproof rederive <row_id>` — replays one row's pinned event and prints
  the event, the span and the reproduced slice. It requires `--memory`, because
  the verdict is the byte-for-byte comparison between the row text and the
  sliced span, and the pointer index does not carry the row text; without it the
  command exits `2` rather than reporting a `DERIVED` it never checked, and a
  row id the row file does not hold is reported as `ROW_TEXT_UNAVAILABLE`, also
  with exit `2`. Exits `0` on `DERIVED`, `1` on a verdict that is not `DERIVED`.
  `rederive` decides through the same `judge_row` as `challenge`, so the two
  cannot disagree about a row.
- `recallproof gate` and `python -m recallproof.spike --fixture` — the
  milestone-one gate: re-derivation is byte-identical across 100/100 runs, a
  shortened span and a changed line both fail instead of matching loosely, and an
  abstractive row is never judged.
- `transcript.py` reads a Claude Code session JSONL into an ordered event log.
  It handles `message.content` being polymorphic on both roles (a plain string or
  an array of typed blocks), filters to `user`/`assistant` records and `text`
  blocks, recovers ordering from file line order and the `parentUuid` chain
  instead of an invented sequence number, and records the excluded evidence it
  skipped so a row supported only by a thinking block or tool result is reported
  honestly.
- `pinned_by: "missing"` in the `challenge` verdict and the `--json` document:
  a row an explicit pointer index holds no pin for is reported as unpinned, not
  as a counterfeit whose text no event reproduces.
- `ledger.py` — the `MemoryRow`, `SourceRef` and `PointerRecord` models, plus
  pinning, index read/write and validation.
- `rederive.py` — the pure `(event_log, source_ref) -> Verdict` function. No
  model call, no embedding, no second opinion.
- Bilingual README (`README.md`, `README.zh-CN.md`), four animated figure pairs
  in light and dark, and `assets/demo.svg` recorded from a real run.
- Synthetic fixtures in `examples/`: a session JSONL shaped exactly like a real
  Claude Code transcript, three memory rows covering all three verdicts, and the
  generated pointer index. No real transcript is shipped.

### Notes

- Read-only over both inputs. Nothing is written into a claude-mem, mem0 or
  MemPalace store, and no memory store is opened.
- Abstractive rows return `UNSUPPORTED_DERIVATION` by design. A row that cannot
  be checked is not a row that passed, and the tool refuses to guess rather than
  fall back to the LLM judge it exists to replace. `rederive` and `challenge`
  agree on this because both route through `judge_row`.
- `DERIVED` is only ever emitted after the sliced span was compared with the row
  text byte for byte. There is no code path that returns it from a pointer alone.
- Duplicate matches resolve to the first matching event in file order, and that
  is the event re-derivation replays. The README states the same rather than
  claiming an ambiguity check the code does not perform.
- The demand half of the milestone-one gate is still open: two distinct users in
  120 days describing confabulated memory in their own words. Until that closes,
  this is a working mechanism behind a well-framed hypothesis.

[0.1.0]: https://github.com/SuperMarioYL/recallproof/releases/tag/v0.1.0
