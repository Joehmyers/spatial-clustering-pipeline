"""Shared test fixtures: one full pipeline run, shared by most tests.

The whole fixture run takes a few seconds, so it happens once per test
session and the tests read its outputs. Tests that need their own run (the
leakage and determinism tests) build one of their own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nca.outputs import RunDirectory
from nca.pipeline import run_all
from nca.runrecord import RunRecord
from nca.settings import Settings

from .helpers import FIXTURE_DIRECTORY, SETTINGS_FILE


@pytest.fixture(scope="session")
def fixture_directory() -> Path:
    return FIXTURE_DIRECTORY


@pytest.fixture(scope="session")
def fixture_settings() -> Settings:
    return Settings.load(SETTINGS_FILE)


@pytest.fixture(scope="session")
def full_run(tmp_path_factory, fixture_settings) -> RunDirectory:
    """Run all seven stages once, and hand back the folder they wrote to."""
    root = tmp_path_factory.mktemp("full-run")
    run_directory = RunDirectory(root)
    record = RunRecord(settings=fixture_settings, run_directory=run_directory)
    run_all(fixture_settings, run_directory, record)
    record.write()
    return run_directory


@pytest.fixture(scope="session")
def full_run_record(full_run) -> dict:
    from nca.outputs import read_json

    return read_json(full_run.run_record_path)
