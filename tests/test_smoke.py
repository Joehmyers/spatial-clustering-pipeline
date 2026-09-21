"""Smoke: the full fixture run completes and writes every output R11 names."""

from __future__ import annotations

import pytest

from nca.outputs import OUTPUTS, read_csv, read_geojson, read_json
from nca.pipeline import STAGES

# The columns each table must hold. A table that quietly loses one fails here
# rather than three stages later.
EXPECTED_COLUMNS = {
    ("graph", "neighbours"): ["point_a", "point_b", "shared_edge_metres", "source"],
    ("features", "anomalies"): [
        "point_id",
        "date",
        "variable",
        "window",
        "regional_anomaly",
        "z_score",
    ],
    ("features", "parameters"): [
        "point_id",
        "variable",
        "parameter",
        "day_of_year",
        "value",
    ],
    ("cluster", "tree"): [
        "merge",
        "node",
        "left",
        "right",
        "height",
        "size",
        "cluster",
        "leaf_ids",
    ],
    ("cluster", "labels"): ["k", "point_id", "cluster"],
    ("mapping", "assignments"): [
        "k",
        "unit_type",
        "unit_id",
        "pga_id",
        "assigned_nca",
        "majority_cluster",
        "majority_share",
        "straddle_score",
    ],
    ("mapping", "moves"): [
        "k",
        "pga_id",
        "from_nca",
        "to_nca",
        "shared_boundary_metres",
        "reason",
    ],
    ("evaluate", "benchmark"): [
        "draw",
        "regions",
        "contiguous",
        "weather_eta_squared",
        "demand_eta_squared",
        "partition",
    ],
}

# The only table allowed to be empty: a fixture that needs no repair records
# no moves.
MAY_BE_EMPTY = {("mapping", "moves")}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

ALL_OUTPUTS = [(stage, name) for stage in STAGES for name in OUTPUTS[stage]]


def test_the_run_reports_every_stage(full_run_record):
    assert full_run_record["stages_run"] == list(STAGES)


@pytest.mark.parametrize(("stage", "name"), ALL_OUTPUTS)
def test_the_output_exists_and_is_not_empty(stage, name, full_run):
    path = full_run.path(stage, name)
    assert path.is_file(), f"{stage}/{name} was not written to {path}"
    assert path.stat().st_size > 0


@pytest.mark.parametrize(
    ("stage", "name"),
    [pair for pair in ALL_OUTPUTS if OUTPUTS[pair[0]][pair[1]].endswith(".csv")],
)
def test_each_table_has_the_expected_columns_and_no_nulls(stage, name, full_run):
    frame = read_csv(full_run.path(stage, name))
    expected = EXPECTED_COLUMNS.get((stage, name))
    if expected is not None:
        assert list(frame.columns) == expected
    if (stage, name) in MAY_BE_EMPTY:
        assert frame.isna().sum().sum() == 0
        return
    assert not frame.empty, f"{stage}/{name} holds no rows"
    nulls = frame.isna().sum()
    assert nulls.sum() == 0, (
        f"{stage}/{name} holds nulls in {sorted(nulls[nulls > 0].index)}"
    )


@pytest.mark.parametrize(
    ("stage", "name"),
    [pair for pair in ALL_OUTPUTS if OUTPUTS[pair[0]][pair[1]].endswith(".geojson")],
)
def test_each_layer_is_readable_and_in_the_working_coordinate_system(
    stage, name, full_run, fixture_settings
):
    frame = read_geojson(full_run.path(stage, name))
    assert not frame.empty
    assert frame.geometry.is_valid.all()
    assert frame.crs is not None
    assert frame.crs.to_string() == fixture_settings.coordinates.working_crs
    assert frame.drop(columns="geometry").isna().sum().sum() == 0


@pytest.mark.parametrize(
    ("stage", "name"),
    [pair for pair in ALL_OUTPUTS if OUTPUTS[pair[0]][pair[1]].endswith(".json")],
)
def test_each_report_is_readable_json_holding_something(stage, name, full_run):
    body = read_json(full_run.path(stage, name))
    assert isinstance(body, dict)
    assert body


@pytest.mark.parametrize(
    ("stage", "name"),
    [pair for pair in ALL_OUTPUTS if OUTPUTS[pair[0]][pair[1]].endswith(".png")],
)
def test_each_figure_is_a_png(stage, name, full_run):
    assert full_run.path(stage, name).read_bytes().startswith(PNG_MAGIC)


def test_the_summary_names_both_maps_and_the_verdict(full_run):
    summary = full_run.path("report", "summary").read_text(encoding="utf-8")
    for expected in (
        "Today's NCAs",
        "New NCAs",
        "eta-squared",
        "Ceiling",
        "RA misfits",
        "PGA-NW",
        "NCA-P01",
    ):
        assert expected in summary


def test_the_run_record_holds_what_a_rerun_would_need(full_run_record):
    assert full_run_record["settings"]["cluster"]["number_of_regions"] == 2
    assert full_run_record["code"]["commit"]
    assert full_run_record["libraries"]["numpy"]
    assert full_run_record["python"]["version"]
    assert full_run_record["random_seed"] == 20260921
    assert full_run_record["reads"]
    assert "timing" in full_run_record


def test_the_run_log_is_written(full_run):
    log = full_run.log_path.read_text(encoding="utf-8")
    for stage in STAGES:
        assert f"{stage}:" in log
