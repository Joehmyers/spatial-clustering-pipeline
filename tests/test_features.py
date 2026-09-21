"""Features: the anomalies are regional, the scaling is build-window only."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from nca.features import DAYS_IN_NORMAL_YEAR, circular_moving_average, day_of_year_slot
from nca.outputs import read_csv, read_json

# The daily mean across points is subtracted, so what is left sums to zero up
# to floating-point noise on sums of a few dozen numbers.
ZERO_TOLERANCE = 1e-9

MISSING_DATE = "2024-03-15"


@pytest.fixture(scope="module")
def anomalies(full_run) -> pd.DataFrame:
    return read_csv(full_run.path("features", "anomalies"))


@pytest.fixture(scope="module")
def summary(full_run) -> dict:
    return read_json(full_run.path("features", "summary"))


def test_the_daily_mean_across_points_is_zero(anomalies):
    daily = anomalies.groupby(["variable", "date"])["regional_anomaly"].mean()
    assert float(daily.abs().max()) < ZERO_TOLERANCE


def test_build_window_z_scores_have_mean_zero_and_standard_deviation_one(anomalies):
    build = anomalies.loc[anomalies["window"] == "build"]
    grouped = build.groupby(["variable", "point_id"])["z_score"]
    assert float(grouped.mean().abs().max()) < ZERO_TOLERANCE
    # Population standard deviation, the one squared Euclidean distance on
    # z-scored rows depends on (see test_cluster.py).
    spread = grouped.std(ddof=0)
    assert float((spread - 1.0).abs().max()) < ZERO_TOLERANCE


def test_the_held_out_window_reuses_the_stored_parameters_unchanged(
    anomalies, full_run
):
    """The held-out z-scores are the stored mean and spread applied, not
    recomputed, so held-out values do not set their own scale."""
    parameters = read_csv(full_run.path("features", "parameters"))
    stored = parameters.loc[
        parameters["parameter"].isin(["build_mean", "build_standard_deviation"])
    ]
    lookup = {
        (row["point_id"], row["variable"], row["parameter"]): row["value"]
        for _, row in stored.iterrows()
    }
    held_out = anomalies.loc[anomalies["window"] == "held_out"]
    sample = held_out.head(500)
    for _, row in sample.iterrows():
        mean = lookup[(row["point_id"], row["variable"], "build_mean")]
        spread = lookup[(row["point_id"], row["variable"], "build_standard_deviation")]
        assert row["z_score"] == pytest.approx(
            (row["regional_anomaly"] - mean) / spread, rel=1e-9, abs=1e-9
        )


def test_the_normals_join_smoothly_at_the_year_end(full_run):
    """The smoothing wraps round the year, so 31 December's normal is no
    further from 1 January's than any other neighbouring pair is."""
    parameters = read_csv(full_run.path("features", "parameters"))
    normals = parameters.loc[parameters["parameter"] == "seasonal_normal"]
    for (_, _), group in normals.groupby(["point_id", "variable"]):
        series = group.sort_values("day_of_year")["value"].to_numpy()
        assert len(series) == DAYS_IN_NORMAL_YEAR
        steps = np.abs(np.diff(series))
        wrap = abs(series[0] - series[-1])
        assert wrap <= steps.max() * 1.0 + 1e-12, (
            "the normal jumps at the year end, so the smoothing did not wrap"
        )


def test_the_leap_day_uses_28_februarys_normal():
    assert day_of_year_slot(dt.date(2024, 2, 29)) == day_of_year_slot(
        dt.date(2024, 2, 28)
    )
    assert day_of_year_slot(dt.date(2023, 1, 1)) == 1
    assert day_of_year_slot(dt.date(2023, 12, 31)) == DAYS_IN_NORMAL_YEAR
    # After the leap day, a leap year's dates still land on their own slots.
    assert day_of_year_slot(dt.date(2024, 3, 1)) == day_of_year_slot(
        dt.date(2023, 3, 1)
    )


def test_the_leap_day_is_kept_and_carries_a_value(anomalies):
    leap_day = anomalies.loc[anomalies["date"] == "2024-02-29"]
    assert not leap_day.empty
    assert leap_day["z_score"].notna().all()


def test_the_missing_day_follows_the_drop_day_setting(anomalies, summary, full_run):
    assert summary["missing_data"] == "drop_day"
    assert any(MISSING_DATE in note for note in summary["missing_data_notes"])
    assert MISSING_DATE not in set(anomalies["date"]), (
        "the day was dropped at the point that was missing, not everywhere"
    )
    matrix = read_csv(full_run.path("features", "matrix"))
    assert not [name for name in matrix.columns if MISSING_DATE in str(name)]
    # A leap year of build days, less the one that was dropped.
    assert summary["build_days"] == 365
    assert summary["held_out_days"] == 365


def test_the_build_matrix_is_one_row_per_point_and_one_column_per_variable_day(
    summary, full_run
):
    matrix = read_csv(full_run.path("features", "matrix"))
    points, columns = summary["build_matrix_shape"]
    assert matrix.shape == (points, columns + 1)
    assert columns == len(summary["variables"]) * summary["build_days"]
    assert list(matrix.columns)[0] == "point_id"
    assert matrix.notna().all().all()


def test_the_circular_moving_average_wraps_round_the_year_end():
    values = np.zeros((1, 10))
    values[0, 0] = 10.0
    smoothed = circular_moving_average(values, 3)
    # The spike at slot 0 spreads into slot 9, which only wrapping reaches.
    assert smoothed[0, 9] == pytest.approx(10.0 / 3)
    assert smoothed[0, 1] == pytest.approx(10.0 / 3)
    assert smoothed.sum() == pytest.approx(values.sum())
