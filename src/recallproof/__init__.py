"""RecallProof — recall attestation for AI agent memory.

Every memory row gets a replayable pointer to the session event it came from,
so a suspect recall can be re-derived from the raw transcript and either proven
or flagged, instead of getting a second opinion from another model.
"""

from .challenge import RowVerdict, challenge, exit_code, verdicts_payload
from .ledger import (
    LedgerError,
    MemoryRow,
    PointerRecord,
    SourceRef,
    build_index,
    load_index,
    load_memory_rows,
    pin,
    write_index,
)
from .rederive import Derivation, Verdict, rederive
from .transcript import Transcript, TranscriptError, TranscriptEvent, load_transcript

__version__ = "0.1.0"

__all__ = [
    "Derivation",
    "LedgerError",
    "MemoryRow",
    "PointerRecord",
    "RowVerdict",
    "SourceRef",
    "Transcript",
    "TranscriptError",
    "TranscriptEvent",
    "Verdict",
    "__version__",
    "build_index",
    "challenge",
    "exit_code",
    "load_index",
    "load_memory_rows",
    "load_transcript",
    "pin",
    "rederive",
    "verdicts_payload",
    "write_index",
]
