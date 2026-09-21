"""Determinism: two runs with the same inputs and settings give the same files.

Every output R11 names is compared byte for byte, figures included. The run
record is compared too, apart from the timing block, which holds when the run
started and how long it took and is meant to differ.
"""

from __future__ import annotations

import pytest

from nca.outputs import OUTPUTS, RunDirectory, read_json
from nca.pipeline import STAGES, run_all
from nca.runrecord import RunRecord

ALL_OUTPUTS = [(stage, name) for stage in STAGES for name in OUTPUTS[stage]]

# What is meant to differ between two runs of the same thing.
VOLATILE = ("timing",)


@pytest.fixture(scope="module")
def second_run(tmp_path_factory, fixture_settings) -> RunDirectory:
    run_directory = RunDirectory(tmp_path_factory.mktemp("second-run"))
    record = RunRecord(settings=fixture_settings, run_directory=run_directory)
    run_all(fixture_settings, run_directory, record)
    record.write()
    return run_directory


@pytest.mark.parametrize(("stage", "name"), ALL_OUTPUTS)
def test_every_output_matches_byte_for_byte(stage, name, full_run, second_run):
    first = full_run.path(stage, name).read_bytes()
    second = second_run.path(stage, name).read_bytes()
    assert first == second, (
        f"{stage}/{name} differs between two runs with the same inputs and settings"
    )


def test_the_run_record_matches_apart_from_its_timing(full_run, second_run):
    first = read_json(full_run.run_record_path)
    second = read_json(second_run.run_record_path)
    for key in VOLATILE:
        first.pop(key)
        second.pop(key)
    assert first == second


def test_the_timing_is_the_only_thing_that_differs(full_run, second_run):
    first = read_json(full_run.run_record_path)
    second = read_json(second_run.run_record_path)
    assert first["timing"]["started_at"] != second["timing"]["started_at"]
