#!/usr/bin/env python3
"""Generate the README figure set: four compositions, each in light and dark.

One palette per project, defined once here and emitted into every file as CSS
custom properties. Each figure is self-contained: inline CSS animation only, no
``<script>``, no remote fonts or images, and a complete static frame — every
label, box and result is present and readable with animation stopped.

    python scripts/build_figures.py
"""

from __future__ import annotations

from pathlib import Path
from string import Template

OUT_DIR = Path(__file__).resolve().parents[1] / "assets"

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#070c18",
        "bg2": "#0e1729",
        "grid": "rgba(122,164,224,0.10)",
        "line": "rgba(150,182,232,0.30)",
        "text": "#e8eefb",
        "muted": "#8fa2c0",
        "primary": "#38d9f0",
        "secondary": "#8b7cf6",
        "good": "#3ddc97",
        "bad": "#ff6b6b",
        "warn": "#f5c451",
        "surface": "rgba(18,30,52,0.72)",
    },
    "light": {
        "bg": "#f6f9fd",
        "bg2": "#ffffff",
        "grid": "rgba(28,58,118,0.10)",
        "line": "rgba(24,54,110,0.24)",
        "text": "#0d1a2e",
        "muted": "#5b6f8c",
        "primary": "#0a7ea4",
        "secondary": "#6d3fd4",
        "good": "#0f8a5f",
        "bad": "#c0392b",
        "warn": "#9a6206",
        "surface": "rgba(255,255,255,0.88)",
    },
}

STYLE = Template(
    """
    :root {
      --bg: $bg; --bg2: $bg2; --grid: $grid; --line: $line;
      --text: $text; --muted: $muted; --primary: $primary; --secondary: $secondary;
      --good: $good; --bad: $bad; --warn: $warn; --surface: $surface;
    }
    .frame { fill: var(--bg); }
    .node { fill: var(--surface); stroke: var(--line); stroke-width: 1.2; }
    .node-accent { fill: var(--surface); stroke: var(--primary); stroke-width: 1.6; }
    .node-dashed { fill: var(--surface); stroke: var(--muted); stroke-width: 1.2; stroke-dasharray: 5 5; }
    .gridline { stroke: var(--grid); stroke-width: 1; fill: none; }
    .wire { stroke: var(--line); stroke-width: 1.4; fill: none; }
    .wire-strong { stroke: var(--primary); stroke-width: 1.6; fill: none; opacity: .8; }
    text { font-family: "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif; }
    .name { fill: var(--text); font-size: 46px; font-weight: 700; letter-spacing: -0.5px; }
    .sub { fill: var(--muted); font-size: 19px; }
    .adv { fill: var(--primary); font-size: 16px; font-weight: 600; }
    .h { fill: var(--text); font-size: 15px; font-weight: 700; }
    .t { fill: var(--text); font-size: 14px; }
    .m { fill: var(--muted); font-size: 13px; }
    .mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 13px; fill: var(--text); }
    .chip { font-size: 12px; font-weight: 700; letter-spacing: .4px; }
    .kicker { fill: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: 1.6px; }
    .kicker-tight { fill: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: 1px; }
    .dot { fill: var(--primary); }
    .dot-alt { fill: var(--secondary); }
    .particle { fill: var(--primary); opacity: .45; animation: converge 7s cubic-bezier(.5,0,.2,1) infinite; }
    .particle-b { fill: var(--secondary); opacity: .4; animation: converge 9s cubic-bezier(.5,0,.2,1) infinite; }
    @keyframes converge {
      0%   { transform: translate(var(--dx), var(--dy)); opacity: 0; }
      25%  { opacity: .8; }
      100% { transform: translate(0px, 0px); opacity: 0; }
    }
    .pulse { animation: travel 3.6s linear infinite; }
    @keyframes travel {
      0%   { transform: translate(var(--px0), var(--py0)); opacity: 0; }
      15%  { opacity: 1; }
      85%  { opacity: 1; }
      100% { transform: translate(var(--px1), var(--py1)); opacity: 0; }
    }
    .breathe { animation: breathe 4.5s ease-in-out infinite; }
    @keyframes breathe { 0%,100% { opacity: .3; } 50% { opacity: .8; } }
    .spin { animation: spin 30s linear infinite; transform-origin: center; transform-box: fill-box; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .crawl { stroke-dasharray: 5 7; animation: crawl 2.4s linear infinite; }
    @keyframes crawl { to { stroke-dashoffset: -24; } }
    .fade1 { animation: fade 5s ease-in-out infinite; }
    .fade2 { animation: fade 5s ease-in-out infinite; animation-delay: -1.7s; }
    .fade3 { animation: fade 5s ease-in-out infinite; animation-delay: -3.4s; }
    @keyframes fade { 0%,100% { opacity: .3; } 50% { opacity: 1; } }
    @media (prefers-reduced-motion: reduce) {
      .particle, .particle-b, .pulse, .breathe, .spin, .crawl,
      .fade1, .fade2, .fade3 { animation: none; }
      .particle, .particle-b { opacity: .4; }
      .pulse { opacity: .9; }
    }
"""
)


def head(width: int, height: int, theme: str, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{desc}">\n'
        f"  <title>{title}</title>\n  <desc>{desc}</desc>\n"
        f"  <style>{STYLE.substitute(THEMES[theme])}</style>\n"
        f"""  <defs>
    <linearGradient id="wash" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="var(--bg)"/><stop offset="1" stop-color="var(--bg2)"/>
    </linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path class="gridline" d="M32 0 L0 0 0 32"/>
    </pattern>
    <radialGradient id="glow">
      <stop offset="0" stop-color="var(--primary)" stop-opacity=".5"/>
      <stop offset="1" stop-color="var(--primary)" stop-opacity="0"/>
    </radialGradient>
  </defs>
"""
    )


def backdrop(width: int, height: int) -> str:
    return (
        f'  <rect class="frame" x="0" y="0" width="{width}" height="{height}"/>\n'
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#wash)"/>\n'
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#grid)"/>\n'
    )


FOOTER = "</svg>\n"


def box(
    x: int,
    y: int,
    w: int,
    h: int,
    lines: list[tuple[str, str]],
    *,
    accent: bool = False,
    dashed: bool = False,
) -> str:
    """A node box with a list of ``(css class, text)`` lines, offsets from the top."""
    cls = "node-accent" if accent else ("node-dashed" if dashed else "node")
    body = "".join(
        f'    <text class="{css}" x="16" y="{offset}">{text}</text>\n'
        for css, offset, text in lines
    )
    return (
        f'  <g transform="translate({x},{y})">\n'
        f'    <rect class="{cls}" x="0" y="0" width="{w}" height="{h}" rx="11"/>\n'
        f"{body}  </g>\n"
    )


# --------------------------------------------------------------------------- hero


def hero(theme: str) -> str:
    offsets = [
        (-240, -80), (-180, 66), (-130, -128), (-64, 112), (-290, 26), (-26, -102),
        (-220, 130), (-92, -36), (-276, -140), (-156, 8), (-54, 54), (-196, -54),
    ]
    particles = "".join(
        f'    <circle class="{"particle" if index % 2 else "particle-b"}" cx="700" cy="150" '
        f'r="{2.0 + (index % 3) * 0.7:.1f}" style="--dx:{dx}px;--dy:{dy}px;'
        f'animation-delay:-{index * 0.55:.2f}s"/>\n'
        for index, (dx, dy) in enumerate(offsets)
    )
    return (
        head(
            960,
            300,
            theme,
            "RecallProof — recall attestation for agent memory",
            "RecallProof name, one advantage line, and a memory row connected to the source event it replays to.",
        )
        + backdrop(960, 300)
        + f"""  <circle cx="800" cy="150" r="190" fill="url(#glow)" class="breathe"/>
  <g>
{particles}  </g>
  <g transform="translate(700,150)">
    <rect class="node" x="-88" y="-46" width="176" height="92" rx="14"/>
    <text class="kicker" x="-72" y="-24">MEMORY ROW</text>
    <rect x="-72" y="-14" width="144" height="9" rx="4.5" fill="var(--primary)" opacity=".85" class="fade1"/>
    <rect x="-72" y="2" width="116" height="9" rx="4.5" fill="var(--primary)" opacity=".55" class="fade2"/>
    <rect x="-72" y="18" width="86" height="9" rx="4.5" fill="var(--primary)" opacity=".35" class="fade3"/>
  </g>
  <g transform="translate(874,150)">
    <rect class="node-accent" x="-62" y="-34" width="124" height="68" rx="12"/>
    <text class="kicker-tight" x="-48" y="-12">SOURCE EVENT</text>
    <text class="m" x="-48" y="6">line 2 · block 1</text>
    <text class="m" x="-48" y="22">chars 109:202</text>
  </g>
  <path class="wire-strong" d="M788 150 H812"/>
  <circle class="dot pulse" r="4" cx="788" cy="150" style="--px0:0px;--py0:0px;--px1:24px;--py1:0px"/>
  <text class="kicker" x="56" y="86">RECALL ATTESTATION FOR AGENT MEMORY</text>
  <text class="name" x="56" y="146">RecallProof</text>
  <text class="sub" x="56" y="180">Make every recalled row prove its source event.</text>
  <rect x="56" y="200" width="54" height="3" rx="1.5" fill="var(--primary)"/>
  <text class="adv" x="56" y="232">Challenge a recall, get a machine-checkable verdict.</text>
  <text class="m" x="56" y="254">Re-derived from the raw transcript — no model call.</text>
"""
        + FOOTER
    )


# ------------------------------------------------------------------- architecture


def architecture(theme: str) -> str:
    modules = [
        ("transcript.py", "session JSONL → ordered event log", "read-only"),
        ("ledger.py", "pins each row to a SourceRef", "sha256 per line"),
        ("rederive.py", "pure (event, ref) → Verdict", "deterministic"),
        ("challenge.py + cli.py", "table, --json, exit code", "batch verdicts"),
    ]
    body = ""
    for index, (name, role, tag) in enumerate(modules):
        y = 96 + index * 68
        body += (
            f'  <g transform="translate(360,{y})">\n'
            f'    <rect class="node" x="0" y="0" width="300" height="56" rx="10"/>\n'
            f'    <text class="mono" x="16" y="24">{name}</text>\n'
            f'    <text class="m" x="16" y="43">{role}</text>\n'
            f'    <text class="chip" x="284" y="24" text-anchor="end" fill="var(--primary)">{tag}</text>\n'
            f"  </g>\n"
            f'  <path class="wire" d="M660 {y + 28} H700"/>\n'
        )
        if index < len(modules) - 1:
            body += f'  <path class="wire-strong" d="M505 {y + 60} l5 6 l5 -6"/>\n'
    outputs = [
        ("verdict table", "DERIVED · NOT_DERIVABLE"),
        ("challenge --json", "schema_version 1 · exit 0/1"),
        ("pointers.jsonl", "sidecar · no store written"),
        ("rederive &lt;row_id&gt;", "event + span, or exit non-zero"),
    ]
    for index, (title, detail) in enumerate(outputs):
        body += (
            f'  <g transform="translate(700,{96 + index * 68})">\n'
            f'    <rect class="node" x="0" y="0" width="204" height="56" rx="10"/>\n'
            f'    <text class="t" x="16" y="24">{title}</text>\n'
            f'    <text class="m" x="16" y="43">{detail}</text>\n'
            f"  </g>\n"
        )
    return (
        head(
            960,
            400,
            theme,
            "RecallProof architecture — one process, four modules, flat files",
            "Layer diagram: the session JSONL and memory rows feed transcript, ledger, rederive and "
            "challenge, which emit the verdict table, JSON, the pointer index and rederive.",
        )
        + backdrop(960, 400)
        + f"""  <text class="kicker" x="22" y="42">ONE PROCESS · FOUR MODULES · FLAT FILES</text>
{box(56, 86, 238, 124, [
        ("h", 30, "Claude Code session"),
        ("mono", 54, "~/.claude/projects/"),
        ("mono", 72, "&lt;slug&gt;/&lt;sessionId&gt;.jsonl"),
        ("m", 98, "the shared upstream that"),
        ("m", 114, "both memory stores read"),
    ], accent=True)}
{box(56, 238, 238, 76, [
        ("h", 30, "Memory rows"),
        ("m", 52, "row_id · text · derivation"),
        ("m", 70, "exported from any store"),
    ])}
  <path class="wire" d="M294 148 H330 V124 H360"/>
  <path class="wire" d="M294 276 H330 V192 H360"/>
  <path class="wire" d="M330 124 V276"/>
  <circle class="dot pulse" r="3.5" cx="330" cy="200" style="--px0:0px;--py0:-70px;--px1:0px;--py1:70px"/>
  <circle class="dot-alt pulse" r="3.5" cx="660" cy="124" style="--px0:0px;--py0:0px;--px1:40px;--py1:0px"/>
{body}  <text class="m" x="700" y="384">nothing is written back</text>
"""
        + FOOTER
    )


# ------------------------------------------------------------------------ process


def process(theme: str) -> str:
    stages = [
        ("1", "challenge", "one row at a time"),
        ("2", "resolve pointer", "exact text in a block"),
        ("3", "re-derive", "slice span, match bytes"),
        ("4", "verdict", "machine-checkable"),
    ]
    body = ""
    for index, (number, name, detail) in enumerate(stages):
        x = 56 + index * 224
        body += (
            f'  <g transform="translate({x},96)">\n'
            f'    <rect class="node-accent" x="0" y="0" width="192" height="84" rx="12"/>\n'
            f'    <circle cx="22" cy="21" r="11" fill="var(--primary)" opacity=".22"/>\n'
            f'    <text class="chip" x="22" y="25" text-anchor="middle" fill="var(--primary)">{number}</text>\n'
            f'    <text class="h" x="42" y="26">{name}</text>\n'
            f'    <text class="m" x="16" y="54">{detail}</text>\n'
            f"  </g>\n"
        )
        if index < len(stages) - 1:
            body += (
                f'  <path class="wire-strong" d="M{x + 192} 138 H{x + 216}"/>\n'
                f'  <circle class="dot pulse" r="3.5" cx="{x + 192}" cy="138" '
                f'style="--px0:0px;--py0:0px;--px1:24px;--py1:0px"/>\n'
            )
    branches = [
        (56, "abstractive row", "UNSUPPORTED_DERIVATION", "var(--warn)"),
        (280, "no matching event", "NOT_DERIVABLE", "var(--muted)"),
        (504, "span reproduces text", "DERIVED", "var(--good)"),
    ]
    for x, label, verdict, colour in branches:
        body += (
            f'  <path class="wire crawl" d="M{x + 96} 180 V236"/>\n'
            f'  <g transform="translate({x},240)">\n'
            f'    <rect class="node" x="0" y="0" width="192" height="60" rx="10"/>\n'
            f'    <text class="t" x="16" y="26" fill="{colour}">{label}</text>\n'
            f'    <text class="m" x="16" y="46">{verdict}</text>\n'
            f"  </g>\n"
        )
    return (
        head(
            960,
            380,
            theme,
            "RecallProof core process — four ordered stages and the branches they take",
            "Ordered stages: challenge, resolve pointer, re-derive, verdict, with branches to "
            "UNSUPPORTED_DERIVATION, NOT_DERIVABLE and DERIVED, and the unused judge lane.",
        )
        + backdrop(960, 380)
        + f"""  <text class="kicker" x="22" y="42">CORE PROCESS</text>
{body}  <path class="wire crawl" d="M828 180 V236"/>
  <g transform="translate(736,240)">
    <rect class="node-dashed" x="0" y="0" width="176" height="60" rx="10"/>
    <text class="t" x="16" y="26" fill="var(--muted)">LLM judge lane</text>
    <text class="m" x="16" y="46">not used — no model call</text>
  </g>
  <text class="kicker" x="22" y="330">BRANCHES — WHAT A ROW GETS INSTEAD OF A GUESS</text>
"""
        + FOOTER
    )


# ------------------------------------------------------------------- capabilities


def capabilities(theme: str) -> str:
    inputs = [
        ("Claude Code session JSONL", "read-only upstream"),
        ("memory rows JSONL", "row_id · text · derivation"),
        ("pointer index", "sidecar, yours to keep"),
    ]
    exports = [
        ("claude-mem export", "observations"),
        ("mem0 export", "extracted rows"),
        ("MemPalace export", "recalled rows"),
        ("challenge --json", "CI gate"),
        ("rederive &lt;row_id&gt;", "inspect one row"),
        ("gate --fixture", "determinism check"),
    ]
    body = ""
    for index, (name, detail) in enumerate(inputs):
        body += (
            f'  <g transform="translate(112,{136 + index * 72})">\n'
            f'    <rect class="node" x="0" y="0" width="244" height="56" rx="10"/>\n'
            f'    <text class="t" x="16" y="24">{name}</text>\n'
            f'    <text class="m" x="16" y="43">{detail}</text>\n'
            f"  </g>\n"
        )
    for index, (name, detail) in enumerate(exports):
        body += (
            f'  <g transform="translate(700,{90 + index * 46})">\n'
            f'    <rect class="node" x="0" y="0" width="220" height="40" rx="9"/>\n'
            f'    <text class="m" x="14" y="18">{name}</text>\n'
            f'    <text class="m" x="14" y="33" opacity=".75">{detail}</text>\n'
            f"  </g>\n"
        )
    return (
        head(
            960,
            440,
            theme,
            "RecallProof capabilities and integration",
            "Connected layout: read-only inputs and memory-store exports feed RecallProof, which "
            "exposes the verdict table, JSON, the pointer index and the gate.",
        )
        + backdrop(960, 440)
        + f"""  <text class="kicker" x="22" y="42">READ-ONLY INPUTS · READ-ONLY OUTPUTS</text>
  <circle class="spin" cx="478" cy="236" r="120" fill="none" stroke="var(--line)" stroke-dasharray="6 10"/>
  <circle class="spin" cx="478" cy="236" r="178" fill="none" stroke="var(--line)" stroke-dasharray="3 12" opacity=".55"/>
  <circle cx="478" cy="236" r="92" fill="url(#glow)" class="breathe"/>
  <g transform="translate(478,236)">
    <rect class="node-accent" x="-86" y="-52" width="172" height="104" rx="14"/>
    <text class="h" x="-70" y="-24">recallproof</text>
    <text class="m" x="-70" y="-4">one process</text>
    <text class="m" x="-70" y="14">no server, no database</text>
    <text class="chip" x="-70" y="38" fill="var(--primary)">READ-ONLY</text>
  </g>
  <path class="wire-strong" d="M356 236 H392"/>
  <path class="wire" d="M356 164 H374 V236"/>
  <path class="wire" d="M356 308 H374 V236"/>
  <circle class="dot pulse" r="3.5" cx="358" cy="236" style="--px0:0px;--py0:0px;--px1:30px;--py1:0px"/>
  <path class="wire-strong" d="M564 236 H700"/>
  <circle class="dot-alt pulse" r="3.5" cx="566" cy="236" style="--px0:0px;--py0:0px;--px1:128px;--py1:0px"/>
{body}  <text class="m" x="56" y="398">No write path: claude-mem, mem0 and MemPalace keep their own stores — RecallProof reads the exports and the session JSONL.</text>
  <text class="m" x="56" y="420">Abstractive rows from those exports return UNSUPPORTED_DERIVATION, never a fabricated verdict.</text>
"""
        + FOOTER
    )


FIGURES = {
    "hero": hero,
    "architecture": architecture,
    "process": process,
    "capabilities": capabilities,
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, build in FIGURES.items():
        for theme in THEMES:
            path = OUT_DIR / f"{name}-{theme}.svg"
            path.write_text(build(theme), encoding="utf-8")
            written.append(path.name)
    print(f"wrote {len(written)} figures: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
