"""Leakage: changing held-out weather leaves the tree and the labels unchanged.

The normals and the z-score parameters come from the build window alone and
are stored. If a held-out reading could move them, every statistic the
evaluate stage reports would be measuring a map that had already seen the
data judging it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nca.outputs import RunDirectory, read_csv
from nca.pipeline import run_stage
from nca.runrecord import RunRecord
from nca.settings import Settings

from .helpers import copy_fixture

BUILD_STAGES = ("geometry", "graph", "features", "cluster")
HELD_OUT_START = "2024-09-01"


def _run_build_stages(settings_file, out) -> RunDirectory:
    settings = Settings.load(settings_file)
    run_directory = RunDirectory(out)
    record = RunRecord(settings=settings, run_directory=run_directory)
    for stage in BUILD_STAGES:
        run_stage(stage, settings, run_directory, record)
    return run_directory


def _scramble_held_out_weather(fixture_root) -> int:
    """Move every held-out reading by a large, varying amount."""
    changed = 0
    for path in sorted((fixture_root / "weather").glob("weather-*.csv")):
        frame = pd.read_csv(path)
        held_out = frame["date"] >= HELD_OUT_START
        points = [name for name in frame.columns if name != "date"]
        for offset, point in enumerate(points):
            frame.loc[held_out, point] = (
                frame.loc[held_out, point] + 7.0 + offset
            ).round(1)
        changed += int(held_out.sum()) * len(points)
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.1f")
    return changed


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("leakage")
    settings_file = copy_fixture(root / "fixture")
    before = _run_build_stages(settings_file, root / "before")
    changed = _scramble_held_out_weather(root / "fixture")
    after = _run_build_stages(settings_file, root / "after")
    return before, after, changed


def test_the_scramble_actually_changed_the_held_out_weather(two_runs):
    _, after, changed = two_runs
    assert changed > 10_000
    anomalies = read_csv(after.path("features", "anomalies"))
    held_out = anomalies.loc[anomalies["window"] == "held_out"]
    assert not held_out.empty


def test_the_tree_is_unchanged(two_runs):
    before, after, _ = two_runs
    assert (
        before.path("cluster", "tree").read_bytes()
        == after.path("cluster", "tree").read_bytes()
    )


def test_the_labels_are_unchanged(two_runs):
    before, after, _ = two_runs
    assert (
        before.path("cluster", "labels").read_bytes()
        == after.path("cluster", "labels").read_bytes()
    )


def test_the_build_matrix_is_unchanged(two_runs):
    before, after, _ = two_runs
    assert (
        before.path("features", "matrix").read_bytes()
        == after.path("features", "matrix").read_bytes()
    )


def test_the_stored_parameters_are_unchanged(two_runs):
    """Normals, means and standard deviations come from the build window only."""
    before, after, _ = two_runs
    assert (
        before.path("features", "parameters").read_bytes()
        == after.path("features", "parameters").read_bytes()
    )


def test_the_held_out_anomalies_did_change(two_runs):
    """The other half of the check: the scramble reached the held-out window,
    so the tests above are not passing because nothing happened."""
    before, after, _ = two_runs
    first = read_csv(before.path("features", "anomalies"))
    second = read_csv(after.path("features", "anomalies"))
    held_out_first = first.loc[first["window"] == "held_out", "z_score"]
    held_out_second = second.loc[second["window"] == "held_out", "z_score"]
    assert not held_out_first.equals(held_out_second)

    build_first = first.loc[first["window"] == "build"].reset_index(drop=True)
    build_second = second.loc[second["window"] == "build"].reset_index(drop=True)
    pd.testing.assert_frame_equal(build_first, build_second)
