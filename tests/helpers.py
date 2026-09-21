"""Helpers more than one test needs."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "nca-regionalisation"
SETTINGS_FILE = FIXTURE_DIRECTORY / "settings.toml"


def copy_fixture(destination: Path) -> Path:
    """Copy the whole fixture folder, and return the copy's settings file.

    Every path in the settings file is relative to the file, so the copy works
    wherever it lands. Tests that change an input work on a copy, never on the
    committed fixture.
    """
    shutil.copytree(FIXTURE_DIRECTORY, destination)
    return destination / "settings.toml"
