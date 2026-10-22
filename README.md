**English** | [简体中文](./README.zh-CN.md)

<p align="center">
  <a href="https://github.com/SuperMarioYL/recallproof"><img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=900&color=38D9F0&center=true&vCenter=true&width=780&lines=Make+every+recalled+row+prove+its+source+event;DERIVED+%7C+NOT_DERIVABLE+%7C+UNSUPPORTED_DERIVATION;No+model+call.+No+second+opinion." alt="RecallProof — make every recalled row prove its source event"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/hero-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/hero-light.svg">
    <img src="./assets/hero-light.svg" alt="RecallProof: a memory row connected to the source event it replays to" width="100%">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/SuperMarioYL/recallproof/actions/workflows/ci.yml"><img src="https://github.com/SuperMarioYL/recallproof/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/verdicts-DERIVED%20%7C%20NOT__DERIVABLE-38d9f0" alt="Verdicts: DERIVED or NOT DERIVABLE">
  <img src="https://img.shields.io/badge/model%20calls-zero-8b7cf6" alt="Zero model calls">
</p>

<h1 align="center">RecallProof</h1>

<p align="center"><b>Recall attestation for AI agent memory: replay each recalled row to the source event it came from.</b></p>

Three LLM judges could not tell a real agent memory from a counterfeit one. RecallProof gives every memory row a replayable pointer to its source event, so you can challenge a suspect recall and get a machine-checkable verdict instead of a second opinion.

```console
$ recallproof challenge --session examples/session.jsonl --memory examples/memory_rows.jsonl
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ row      ┃ verdict                ┃ pinned event · span      ┃ what happened                 ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ row_0001 │ DERIVED                │ 7c4a1e02 L2/B1 · 109:202 │ span reproduces the row text  │
│ row_0002 │ NOT_DERIVABLE          │ -                        │ no event reproduces this text │
│ row_0003 │ UNSUPPORTED_DERIVATION │ -                        │ abstractive row — not judged  │
└──────────┴────────────────────────┴──────────────────────────┴───────────────────────────────┘
3 rows challenged — DERIVED 1, NOT_DERIVABLE 1, UNSUPPORTED_DERIVATION 1
```

`row_0001` re-derived from line 2 of the transcript, characters 109 to 202. `row_0002` claims to be a decision from that session and no event reproduces it — the row that no judge and no memory system in our probe can flag today. `row_0003` is an AI-compressed summary, so the tool refuses to score it.

**Read-only. No config file, no API key, no model call, no write path into any memory store.**

---

## Contents

- [Why](#why)
- [How it works](#how-it-works)
- [Install](#install)
- [Quickstart](#quickstart)
- [Demo](#demo)
- [Usage](#usage)
- [Capabilities](#capabilities)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why

Agent memory is load-bearing now. A recalled row — "we agreed to use Postgres", "the incident was a stale token" — is increasingly the reason a decision gets attributed to a session, a postmortem, or a change review. Nothing in that row records whether it was derived from a real session event or confabulated by the model that wrote it.

The only check anyone has tried is an LLM judge, and [the one published attempt](https://kairos-experiment.com/checks.html) failed: three judges, no separation between a real memory and a counterfeit one. That failure is structural rather than a tuning problem. A judge reads the same ungrounded text the memory system produced, so it can only agree or disagree with the first model — it can never attest that a row came from an event.

What is missing is a machine-checkable signal, and there are only three honest answers a row can give:

| Verdict | What it means | How it is computed |
| --- | --- | --- |
| `DERIVED` | The row is a slice of a real session event, byte for byte. | Re-read the pinned line, slice the pinned character span, compare. |
| `NOT_DERIVABLE` | The row claims to come from the session and no event reproduces it. | The same replay fails: no matching event, a line that changed since it was pinned, or a span that no longer reproduces the text. |
| `UNSUPPORTED_DERIVATION` | The row is not a slice of any event (an AI-compressed summary, an embedding, a merge), or its only evidence is a block this tool does not index. | No replay is attempted. The tool refuses to guess rather than fall back to the judge it rejects. |

That third state is a feature, not a gap: a tool that answers "plausible" when it cannot check is exactly the second opinion RecallProof exists to replace.

## How it works

The primitive is the **grounded memory row**: a recalled row that carries a replayable pointer to the session event it was derived from, plus a verdict computed by re-derivation rather than by a judge.

```python
MemoryRow = { row_id: str, text: str, derivation: "extractive" | "abstractive" }
SourceRef = { session_id,          # the source JSONL's camelCase `sessionId`
              source_uuid,         # the record's top-level `uuid`
              line_index,          # 0-based line number in the session JSONL
              parent_depth,        # position along the `parentUuid` chain
              event_sha256,        # sha256 of the raw JSONL line
              block_index,         # index of the selected text block in message.content
              span: [int, int],    # char offsets within THAT block's text
              derivation: "extractive" }
```

The attach point is the **shared upstream**: the on-disk Claude Code session transcript at `~/.claude/projects/<slug>/<sessionId>.jsonl`. It is the one artifact that agent memory stores consume as input, so it is the honest place to resolve a pointer — and it means nothing has to be installed inside a memory store to use this.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/architecture-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/architecture-light.svg">
    <img src="./assets/architecture-light.svg" alt="One process, four modules: transcript.py, ledger.py, rederive.py and challenge.py" width="100%">
  </picture>
</p>

One Python process, four modules, flat JSONL files. No server, no database, no second binary.

| Module | Responsibility |
| --- | --- |
| `transcript.py` | Reads a session JSONL into an ordered event log `{uuid, line_index, parent_uuid, parent_depth, role, block_index, text, sha256}`, keeping only `user`/`assistant` records and their `text` blocks. |
| `ledger.py` | Builds and validates the sidecar pointer index of `SourceRef` pointers, pinning each referenced line by sha256. |
| `rederive.py` | The pure function `(event_log, source_ref) -> Verdict`. Deterministic, no model call. This invariant is the product. |
| `challenge.py` + `cli.py` | Batch verdicts; table or JSON output; exit codes. |

Two shape facts about real transcripts drive the reader, and both are implementation bugs if ignored:

- **`message.content` is polymorphic on both roles.** It is a plain string or an array of typed blocks (`text`, `thinking`, `tool_use`, `tool_result`), regardless of whether the record is a `user` or an `assistant` record. Measured on this host's 34 session files (3,116 `user`/`assistant` records): 2,068/2,068 `assistant` records and 953/1,048 `user` records are block arrays; 95 `user` records are plain strings. A span is therefore only well-defined relative to a *selected* `text` block: `span` is char offsets within that block's text, and `block_index` names the block. A plain string is treated as one implicit `text` block at `block_index` 0.
- **There is no `seq` field.** Order comes from file line order, the `parentUuid` chain and `timestamp`. Nothing invents a sequence number.

Seven record types coexist in these files (`user`, `assistant`, `attachment`, `last-prompt`, `custom-title`, `queue-operation`, `system`). Only `user` and `assistant` carry memory-bearing prose; the rest are metadata. Blocks of type `thinking`, `tool_use` and `tool_result` are excluded. A row whose only evidence is an excluded block or record type is `UNSUPPORTED_DERIVATION` — not a guess.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/process-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/process-light.svg">
    <img src="./assets/process-light.svg" alt="Four ordered stages: challenge, resolve pointer, re-derive, verdict — with the unused LLM judge lane" width="100%">
  </picture>
</p>

## Install

Python 3.12 or newer.

```bash
git clone https://github.com/SuperMarioYL/recallproof
cd recallproof
uv venv && uv pip install -e .        # or: python -m venv .venv && .venv/bin/pip install -e .
```

No-clone run, straight from git:

```bash
uvx --from git+https://github.com/SuperMarioYL/recallproof recallproof challenge \
  --session examples/session.jsonl --memory examples/memory_rows.jsonl
```

## Quickstart

Both inputs ship with the repository, so the first result is one command away:

```bash
recallproof challenge --session examples/session.jsonl --memory examples/memory_rows.jsonl
```

Then point it at your own session and your own rows:

```bash
# 1. Any Claude Code session you already have. Read-only; nothing is written.
ls ~/.claude/projects/*/*.jsonl

# 2. Your recalled rows, one JSON object per line:
#    {"row_id": "row_0001", "text": "<the recalled text>", "derivation": "extractive"}
recallproof challenge --session ~/.claude/projects/<slug>/<sessionId>.jsonl --memory my_rows.jsonl

# 3. Pin the pointers once, then replay a single row whenever you want.
recallproof index    --session ~/.claude/projects/<slug>/<sessionId>.jsonl --memory my_rows.jsonl --out pointers.jsonl
recallproof rederive row_0001 --session ~/.claude/projects/<slug>/<sessionId>.jsonl --memory my_rows.jsonl --pointers pointers.jsonl

# 4. Gate a CI job on it.
recallproof challenge --session session.jsonl --memory rows.jsonl --json
```

`challenge` and `index` default `--session` and `--memory` to the two files in `examples/`, so running them from the repository root needs no arguments at all. `rederive` always needs `--memory`, because its verdict is a comparison against the row text. Every step finishes in under a second; there is no config file, no API key and no network call.

## Demo

<p align="center">
  <img src="./assets/demo.svg" alt="Terminal recording of recallproof challenge: row_0001 DERIVED with its source event and span, row_0002 NOT_DERIVABLE in red" width="100%">
</p>

That is a real recording of the command above, captured through the terminal renderer rather than drawn by hand — `python scripts/record_demo_svg.py` reproduces it, and `docs/demo-results.json` holds the raw output of every step in this README, each recorded at `COLUMNS=100`.

The verdict is inspectable rather than asserted. `rederive` prints the event and the span it sliced:

```console
$ recallproof rederive row_0001 --memory examples/memory_rows.jsonl
DERIVED row_0001
  pinned   line 2 block 1 chars 109:202 uuid 7c4a1e02
  sha256   981858fbc1d114dbef050300738ce0df6c8e79ee5d65ee206646b38d873244b5
  reason   line 2 block 1 chars 109:202 reproduce the row text
  role     assistant  depth 1
  event    Decision recorded: the job queue moves to Postgres. One transaction covers enqueue and
the row it schedules, which removes the Redis/Postgres dual-write failure mode behind the 03:40
duplicate shipments.
  replay   which removes the Redis/Postgres dual-write failure mode behind the 03:40 duplicate
shipments
```

and exits non-zero for a row that has nothing to replay:

```console
$ recallproof rederive row_0002 --memory examples/memory_rows.jsonl
NOT_DERIVABLE row_0002
  reason   no session event reproduces this text
$ echo $?
1
```

`--memory` is required here, and that is the point: the verdict is the comparison between the row text and the slice of the pinned event, so a run without the row text has nothing to compare and refuses to answer (exit `2`) rather than printing a `DERIVED` it cannot back up.

## Usage

### `recallproof challenge`

Verdicts for every row. Exits `0` when every row re-derived and `1` when any row did not — including `UNSUPPORTED_DERIVATION`, because a row that cannot be checked is not a row that passed.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--session`, `-s` | `examples/session.jsonl` | The Claude Code session JSONL to resolve pointers against. |
| `--memory`, `-m` | `examples/memory_rows.jsonl` | The recalled rows to challenge. |
| `--pointers`, `-p` | unset | Challenge against a pinned pointer index instead of resolving now. A row edited after indexing then fails re-derivation instead of silently matching a fresh slice. |
| `--json` | off | Print the machine-readable document below instead of the table. |

```console
$ recallproof challenge --session examples/session.jsonl --memory examples/memory_rows.jsonl --json
{
  "schema_version": 1,
  "session": "examples/session.jsonl",
  "memory": "examples/memory_rows.jsonl",
  "counts": { "DERIVED": 1, "NOT_DERIVABLE": 1, "UNSUPPORTED_DERIVATION": 1 },
  "rows": [
    {
      "row_id": "row_0001",
      "verdict": "DERIVED",
      "reason": "line 2 block 1 chars 109:202 reproduce the row text",
      "pinned_by": "resolved",
      "source_ref": {
        "session_id": "3f6c1d90-8a24-4f77-9c3e-5b1d7e0a4c21",
        "source_uuid": "7c4a1e02-0006-4b06-9a06-1a2b3c4d5e06",
        "line_index": 2,
        "parent_depth": 1,
        "event_sha256": "981858fbc1d114dbef050300738ce0df6c8e79ee5d65ee206646b38d873244b5",
        "block_index": 1,
        "span": [109, 202],
        "derivation": "extractive"
      },
      "source_event": { "uuid": "7c4a1e02-0006-4b06-9a06-1a2b3c4d5e06", "role": "assistant", "line_index": 2, "block_index": 1, "parent_depth": 1, "sha256": "981858fbc1d1..." },
      "span": [109, 202]
    }
  ]
}
```

`pinned_by` is `resolved` when the pointer was resolved in this run, `index` when it came from `--pointers`, `missing` when an explicit index holds no pin for that row, and `none` when there was nothing to pin.

### `recallproof index`

```console
$ recallproof index --session examples/session.jsonl --memory examples/memory_rows.jsonl
3 rows indexed — 1 pinned, 2 unpinned → examples/pointers.jsonl
```

Writes the sidecar pointer index: one record per row, `{"row_id": ..., "source_ref": {...}}`, with `source_ref: null` for a row that could not be pinned — including every `abstractive` row, which is never pinned. Nothing is annotated in place and no memory store is opened — claude-mem and mem0 are SQLite, so there is no memory file to copy and write onto.

### `recallproof rederive <row_id>`

Replays one row's pinned event and prints the source event, the span and the reproduced slice.

| Exit | Meaning |
| --- | --- |
| `0` | `DERIVED` — the slice reproduces the row text byte for byte. |
| `1` | A verdict that is not `DERIVED` (`NOT_DERIVABLE` or `UNSUPPORTED_DERIVATION`). |
| `2` | The row could not be replayed at all: no row text to compare, or no pin in the index. |

`--memory` is required. The pointer index carries the pointer, not the row text, so `rederive` reads the text from the row file and compares it against the pinned span — the same comparison `challenge` makes. A row id that is not in the row file is reported as `ROW_TEXT_UNAVAILABLE` and exits `2` instead of being judged against whatever text it could find.

The verdict comes from the same `judge_row` the table uses, so `challenge` and `rederive` cannot disagree about a row: an `abstractive` row is `UNSUPPORTED_DERIVATION` in both, never `DERIVED`.

### `recallproof gate`

The milestone-one gate as a command. It re-loads and re-derives the same rows 100 times and checks that the verdict, span, event uuid and sha256 are identical every time, that a shortened span and a changed line both fail instead of matching loosely, and that an abstractive row is never judged.

```console
$ recallproof gate
recallproof gate  hand-built fixture — 1 extractive, 1 counterfeit, 1 abstractive row
  PASS  re-derivation is byte-identical across 100/100 runs  (3/3 rows produced one digest each)
  PASS  fixture_derived: extractive row → DERIVED  (DERIVED — b1f0c4d2 L2/B1 · 0:166)
  PASS  fixture_counterfeit: extractive row → NOT_DERIVABLE  (NOT_DERIVABLE (no session event 
reproduces this text))
  PASS  fixture_abstractive: abstractive row → UNSUPPORTED_DERIVATION  (UNSUPPORTED_DERIVATION (row 
is an abstraction, not a slice of any session event))
  PASS  a pure re-derivation of the pinned pointer returns DERIVED  (line 2 block 1 chars 0:166 uuid
b1f0c4d2)
  PASS  a shortened span fails instead of matching loosely  (span 0:165)
  PASS  a line that changed since it was pinned fails  (pinned sha256 no longer matches the line)
PASS  7/7 checks
```

`python -m recallproof.spike --fixture` is the same run, and `recallproof gate --session <file> --memory <rows>` points it at your own files. The other half of the m1 gate — two users in 120 days describing confabulated memory in their own words — is a research question, not something a CLI can prove. It is tracked in the roadmap rather than asserted here.

## Capabilities

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/capabilities-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./assets/capabilities-light.svg">
    <img src="./assets/capabilities-light.svg" alt="Read-only inputs, memory-store exports, and the verdict table, JSON, pointer index and gate outputs" width="100%">
  </picture>
</p>

The division of responsibility is deliberate. Memory stores own recall quality, compression and portability; RecallProof owns one question about a row that already exists.

| | Recall quality | Cross-harness portability | Per-row source pointer | Replay a row from the transcript |
| --- | --- | --- | --- | --- |
| Memory stores (claude-mem, mem0, MemPalace and similar) | yes | varies | not in the row schema | no |
| LLM-as-judge validation | no | no | no | no — it reads the row, not the event |
| RAG citation checkers | n/a | n/a | verifies a quote against an external document | no |
| A bare sha256 check | no | no | pins the event | no — it cannot reproduce the row text |
| **RecallProof** | no | no | yes, as a sidecar index | **yes — the span slice is compared byte for byte** |

**Integration.** The input is the session JSONL your agent already writes, and the row file is a JSONL export of whatever store you use. Rows exported from claude-mem's `observations` or mem0's extracted memories are AI-compressed, so they arrive as `derivation: "abstractive"` and return `UNSUPPORTED_DERIVATION` — the honest answer, and the reason this is a challenge layer over existing formats rather than a rival memory format. RecallProof never opens their SQLite stores and never writes to them.

The same space is moving quickly: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) is an agent framework where a per-row grounding primitive would ship, and [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) is a memory system the challenge layer can sit over. Neither is affiliated with this project and neither endorses it; they are where the surrounding **Agent** infrastructure is heading, and the reason a row-level check has somewhere to plug in.

## Configuration

There is nothing to configure. No config file, no environment variables, no network access, no model provider.

| Concern | How it is handled |
| --- | --- |
| Where pointers live | Wherever you pass `--out` / `--pointers`. `examples/pointers.jsonl` is just a default. |
| Ordering | File line order plus the `parentUuid` chain. No invented sequence numbers. |
| Duplicate matches | The first match in file order wins, and that is the event re-derivation replays. A row that spans two blocks is not pinned at all, because no single block contains it. |
| Abstractive rows | Never pinned, even when the text happens to appear verbatim in the transcript. The index does not carry a pointer for a row the verdict layer refuses to judge. |
| Line endings | The pinned sha256 is over the JSONL line without its trailing newline, so the same file re-derives on any platform. |
| What it will not do | Write to a memory store, call a model, fall back to similarity, or invent a verdict it cannot compute. |

## Roadmap

v0.1.0 ships the three milestones from the plan, all of them working:

- **m1 — determinism and demand.** `rederive` is byte-deterministic on extractive rows across 100/100 runs, and abstractive rows return `UNSUPPORTED_DERIVATION`. `recallproof gate` proves the determinism half on a hand-built fixture or on your own transcript. The demand half — two distinct users in 120 days describing confabulated memory in their own words — is open; until it closes, this is a well-framed hypothesis with a working mechanism, not a validated product.
- **m2 — attach pointers and re-derive.** `recallproof index` writes the sidecar pointer index, and `recallproof rederive <row_id>` replays one row or exits non-zero.
- **m3 — challenge and demo.** `recallproof challenge` prints the verdict table, `--json` for CI, and `assets/demo.svg` is recorded from that run.

Not planned for v0.1, listed so the boundary is explicit: a web UI or TUI beyond the terminal table; any LLM-judge or embedding-similarity fallback; abstractive rows scored rather than refused; writing into claude-mem, mem0 or MemPalace; a hosted or tamper-evident attestation log; a portable cross-harness memory format; an MCP server or per-harness plugins; tamper-evidence beyond one sha256 per pinned event.

Next, in rough order: a read-only adapter that accepts a claude-mem or mem0 export directly, so `index` does not need a hand-written row file; and `--json` output for the gate, so a CI job can record the determinism check rather than only pass or fail it.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
python -m pytest                       # 33 tests
python scripts/record_demo_svg.py      # re-record assets/demo.svg from a real run
python scripts/build_figures.py        # regenerate the four figure pairs
```

## License

MIT. See [LICENSE](./LICENSE).

<p align="center"><sub><a href="./LICENSE">MIT</a> © 2026 SuperMarioYL</sub></p>
