"""Every place the version is written down must say the same thing.

The tag is checked against VERSION by the release workflow, but nothing checked
the package metadata, the runtime ``__version__`` (which is what ``--version``
prints) or the recorded demo artifact. These tests make that drift a failure.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

import recallproof
from recallproof.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "VERSION"
DEMO_RESULTS = REPO_ROOT / "docs" / "demo-results.json"

runner = CliRunner()


def _version_file() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def test_version_surfaces_agree():
    version = _version_file()
    assert version.count(".") == 2 and version[0].isdigit(), version

    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert pyproject["project"]["version"] == version

    assert recallproof.__version__ == version

    demo = json.loads(DEMO_RESULTS.read_text(encoding="utf-8"))
    assert demo["version"] == version


def test_cli_version_flag_matches_the_package():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"recallproof {recallproof.__version__}"
