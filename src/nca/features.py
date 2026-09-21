"""Stage 3, features: turn raw weather into each point's regional departure.

Four steps, in this order, and the order is the point of the stage:

1. **Transform.** Rain goes through log(1 + x); the rest arrive as they are.
2. **Anomaly.** Subtract each point's own smoothed seasonal normal, so what
   is left is the departure from a normal day of the year, not the season.
3. **Regional anomaly.** Subtract each day's mean anomaly across points, so a
   nationwide warm spell leaves nothing behind. What is left is each point's
   departure from the country that day, which is the thing NCAs are for.
4. **Scale.** Convert each point and variable to z-scores, so a variable
   measured in degrees does not outweigh one measured in millimetres.

Normals, means and standard deviations come from the build window alone and
are stored. The held-out window reuses them unchanged, so nothing the tree
learns can have come from the data used to judge it (R14).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from .errors import MissingDataError
from .inputs import DATE, POINT_ID, VALUE, VARIABLE, DataSource
from .outputs import RunDirectory, read_geojson, read_json, write_csv, write_json
from .runrecord import RunRecord
from .settings import Settings

STAGE = "features"

# Days in the normal year. 29 February shares 28 February's slot, so a normal
# exists for every calendar day without a leap year having its own thin one.
DAYS_IN_NORMAL_YEAR = 365

# A standard deviation at or below this counts as "this series never moves",
# which cannot be z-scored.
FLAT_SERIES_TOLERANCE = 1e-12


def day_of_year_slot(date: dt.date) -> int:
    """The normal-year slot, 1 to 365. 29 February uses 28 February's (R2)."""
    month, day = date.month, date.day
    if (month, day) == (2, 29):
        day = 28
    return dt.date(2001, month, day).timetuple().tm_yday


def circular_moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Smooth a year of daily values, wrapping round the year end.

    Works along the last axis. The window must be odd, so it sits evenly
    either side of the day it smooths, and 31 December's window reaches into
    January rather than running out of data.
    """
    half = window // 2
    padded = np.concatenate([values[..., -half:], values, values[..., :half]], axis=-1)
    kernel = np.ones(window) / window
    return np.apply_along_axis(
        lambda row: np.convolve(row, kernel, mode="valid"), -1, padded
    )


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Build the regional anomalies and the build matrix."""
    source = DataSource.for_stage(settings, STAGE)
    run_directory.prepare(STAGE)

    cells = read_geojson(run_directory.require("graph", "cells"))
    kept = sorted(cells["point_id"].astype(str))
    areas = dict(
        zip(cells["point_id"].astype(str), cells["area_square_metres"], strict=True)
    )
    graph_summary = read_json(run_directory.require("graph", "summary"))

    windows = settings.windows
    variables = list(settings.features.variables)
    weather = source.read_weather(variables, windows.build_start, windows.held_out_end)
    weather = weather.loc[weather[POINT_ID].isin(kept)]
    record.log(
        f"{STAGE}: {len(weather)} weather readings for {len(kept)} points, "
        f"{len(variables)} variables"
    )

    wide = {
        variable: weather.loc[weather[VARIABLE] == variable]
        .pivot(index=DATE, columns=POINT_ID, values=VALUE)
        .reindex(columns=kept)
        .sort_index()
        for variable in variables
    }
    wide, missing_notes = _handle_missing(settings, wide, run_directory, record)

    for variable in variables:
        if settings.features.transforms[variable] == "log1p":
            wide[variable] = np.log1p(wide[variable])

    dates = wide[variables[0]].index
    build_mask = dates <= pd.Timestamp(windows.build_end)
    if windows.build_start is not None:
        build_mask &= dates >= pd.Timestamp(windows.build_start)
    if not build_mask.any():
        raise MissingDataError(
            f"no weather falls in the build window ending "
            f"{windows.build_end.isoformat()}"
        )

    weights = _national_weights(settings, kept, areas)
    normals: dict[str, pd.DataFrame] = {}
    regional: dict[str, pd.DataFrame] = {}
    scaling: list[dict[str, Any]] = []
    z_scores: dict[str, pd.DataFrame] = {}

    slots = np.array([day_of_year_slot(date.date()) for date in dates])
    for variable in variables:
        values = wide[variable]
        normal = _seasonal_normals(
            values.loc[build_mask], slots[build_mask], settings, kept
        )
        normals[variable] = normal
        anomaly = values - normal.to_numpy()[slots - 1, :]
        national = pd.Series(
            anomaly.to_numpy() @ weights, index=anomaly.index, name="national"
        )
        departure = anomaly.sub(national, axis=0)
        regional[variable] = departure
        build_values = departure.loc[build_mask]
        mean = build_values.mean(axis=0)
        deviation = build_values.std(axis=0, ddof=0)
        flat = [name for name in kept if deviation[name] <= FLAT_SERIES_TOLERANCE]
        if flat:
            raise MissingDataError(
                f"{variable}: the regional anomaly never moves at "
                f"{', '.join(flat)} over the build window, so it cannot be "
                "z-scored. Check the input for a constant column."
            )
        z_scores[variable] = (departure - mean) / deviation
        for name in kept:
            scaling.append(
                {
                    "point_id": name,
                    "variable": variable,
                    "parameter": "build_mean",
                    "day_of_year": 0,
                    "value": float(mean[name]),
                }
            )
            scaling.append(
                {
                    "point_id": name,
                    "variable": variable,
                    "parameter": "build_standard_deviation",
                    "day_of_year": 0,
                    "value": float(deviation[name]),
                }
            )

    anomalies = _long_frame(regional, z_scores, windows)
    matrix = _build_matrix(z_scores, dates, build_mask, kept, variables)
    parameters = _parameter_frame(normals, scaling, kept, variables)

    summary = {
        "points": kept,
        "variables": variables,
        "transforms": dict(settings.features.transforms),
        "national_mean": settings.features.national_mean,
        "normal_smoothing_days": settings.features.normal_smoothing_days,
        "leap_day": settings.features.leap_day,
        "missing_data": settings.features.missing_data,
        "missing_data_notes": missing_notes,
        "build_days": int(build_mask.sum()),
        "held_out_days": int((~build_mask).sum()),
        "build_window": [
            str(dates[build_mask].min().date()),
            str(dates[build_mask].max().date()),
        ],
        "held_out_window": [
            str(dates[~build_mask].min().date()),
            str(dates[~build_mask].max().date()),
        ],
        "build_matrix_shape": [int(matrix.shape[0]), int(matrix.shape[1] - 1)],
        "sealed_window_override_used": source.sealed_override_used,
        "graph_points_kept": graph_summary["points_kept"],
    }

    write_csv(anomalies, run_directory.path(STAGE, "anomalies"))
    write_csv(parameters, run_directory.path(STAGE, "parameters"))
    write_csv(matrix, run_directory.path(STAGE, "matrix"))
    write_json(summary, run_directory.path(STAGE, "summary"))
    record.record_reads(source.reads)
    record.log(
        f"{STAGE}: build matrix is {summary['build_matrix_shape'][0]} points by "
        f"{summary['build_matrix_shape'][1]} variable-days"
    )
    return summary


def _handle_missing(
    settings: Settings,
    wide: dict[str, pd.DataFrame],
    run_directory: RunDirectory,
    record: RunRecord,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Apply the missing-data setting, and record whatever it did (R16)."""
    found: set[tuple[str, str, str]] = set()
    for variable, frame in wide.items():
        rows, columns = np.where(frame.isna().to_numpy())
        for row, column in zip(rows, columns, strict=True):
            found.add(
                (variable, str(frame.index[row].date()), str(frame.columns[column]))
            )
    holes = sorted(found)
    if not holes:
        return wide, []

    action = settings.features.missing_data
    described = ", ".join(
        f"{point} {variable} on {date}" for variable, date, point in holes[:10]
    )
    if len(holes) > 10:
        described += f", and {len(holes) - 10} more"
    if action == "stop":
        raise MissingDataError(
            f"{len(holes)} weather reading(s) are missing: {described}. Set "
            "features.missing_data to 'drop_day' to drop those dates everywhere, "
            "or 'fill_from_neighbours' to fill each from its neighbours."
        )

    notes: list[str] = []
    if action == "drop_day":
        dropped = sorted({date for _, date, _ in holes})
        for variable in wide:
            wide[variable] = wide[variable].loc[
                ~wide[variable].index.isin([pd.Timestamp(date) for date in dropped])
            ]
        note = (
            f"dropped {len(dropped)} date(s) at every point and variable because a "
            f"reading was missing: {', '.join(dropped)}"
        )
        record.notice(f"{STAGE}: {note}")
        notes.append(note)
        return wide, notes

    neighbours = _neighbour_map(run_directory)
    for variable, date, point in holes:
        frame = wide[variable]
        row = frame.loc[pd.Timestamp(date)]
        nearby = [name for name in neighbours.get(point, []) if name in frame.columns]
        values = row[nearby].dropna()
        if values.empty:
            raise MissingDataError(
                f"{point} {variable} on {date} is missing and none of its "
                "neighbours has a reading that day, so it cannot be filled"
            )
        frame.loc[pd.Timestamp(date), point] = float(values.mean())
        note = (
            f"filled {point} {variable} on {date} from the mean of "
            f"{len(values)} neighbour(s)"
        )
        record.notice(f"{STAGE}: {note}")
        notes.append(note)
    return wide, notes


def _neighbour_map(run_directory: RunDirectory) -> dict[str, list[str]]:
    edges = pd.read_csv(run_directory.require("graph", "neighbours"))
    found: dict[str, list[str]] = {}
    for _, row in edges.iterrows():
        found.setdefault(str(row["point_a"]), []).append(str(row["point_b"]))
        found.setdefault(str(row["point_b"]), []).append(str(row["point_a"]))
    return {name: sorted(values) for name, values in found.items()}


def _national_weights(
    settings: Settings, kept: list[str], areas: dict[str, float]
) -> np.ndarray:
    """How each point counts towards the national mean. Never demand (R1)."""
    if settings.features.national_mean == "cell_area_weighted":
        weights = np.array([float(areas[name]) for name in kept])
        return weights / weights.sum()
    return np.full(len(kept), 1.0 / len(kept))


def _seasonal_normals(
    build_values: pd.DataFrame,
    build_slots: np.ndarray,
    settings: Settings,
    kept: list[str],
) -> pd.DataFrame:
    """Each point's normal for every day of the year, smoothed and wrapped."""
    raw = np.full((DAYS_IN_NORMAL_YEAR, len(kept)), np.nan)
    values = build_values.to_numpy()
    for slot in range(1, DAYS_IN_NORMAL_YEAR + 1):
        rows = build_slots == slot
        if rows.any():
            raw[slot - 1, :] = values[rows, :].mean(axis=0)
    # A build window shorter than a year leaves days with no reading at all.
    # Fill them by wrapping round, so the smoothing has something to work on.
    filled = pd.DataFrame(raw).interpolate(limit_direction="both").to_numpy()
    smoothed = circular_moving_average(
        filled.T, settings.features.normal_smoothing_days
    ).T
    return pd.DataFrame(smoothed, index=range(1, DAYS_IN_NORMAL_YEAR + 1), columns=kept)


def _long_frame(
    regional: dict[str, pd.DataFrame],
    z_scores: dict[str, pd.DataFrame],
    windows: Any,
) -> pd.DataFrame:
    """Regional anomalies for both windows, one row per point, date, variable."""
    rows = []
    for variable, frame in regional.items():
        long = frame.stack().rename("regional_anomaly").reset_index()
        long.columns = [DATE, POINT_ID, "regional_anomaly"]
        long["z_score"] = z_scores[variable].stack().to_numpy()
        long[VARIABLE] = variable
        rows.append(long)
    out = pd.concat(rows, ignore_index=True)
    out["window"] = np.where(
        out[DATE] <= pd.Timestamp(windows.build_end), "build", "held_out"
    )
    out[DATE] = out[DATE].dt.strftime("%Y-%m-%d")
    return (
        out[[POINT_ID, DATE, VARIABLE, "window", "regional_anomaly", "z_score"]]
        .sort_values([VARIABLE, DATE, POINT_ID])
        .reset_index(drop=True)
    )


def _build_matrix(
    z_scores: dict[str, pd.DataFrame],
    dates: pd.Index,
    build_mask: np.ndarray,
    kept: list[str],
    variables: list[str],
) -> pd.DataFrame:
    """One row per point, one column per variable-day, build window only."""
    blocks = []
    for variable in variables:
        block = z_scores[variable].loc[build_mask].T
        block.columns = [
            f"{variable}_{date.date().isoformat()}" for date in dates[build_mask]
        ]
        blocks.append(block)
    matrix = pd.concat(blocks, axis=1).reindex(index=kept)
    matrix.index.name = POINT_ID
    return matrix.reset_index()


def _parameter_frame(
    normals: dict[str, pd.DataFrame],
    scaling: list[dict[str, Any]],
    kept: list[str],
    variables: list[str],
) -> pd.DataFrame:
    """Every stored parameter in one table (R11).

    day_of_year runs 1 to 365 for a seasonal normal and is 0 for the build-
    window mean and standard deviation, which cover the whole window.
    """
    rows: list[dict[str, Any]] = []
    for variable in variables:
        frame = normals[variable]
        for slot in frame.index:
            for name in kept:
                rows.append(
                    {
                        "point_id": name,
                        "variable": variable,
                        "parameter": "seasonal_normal",
                        "day_of_year": int(slot),
                        "value": float(frame.loc[slot, name]),
                    }
                )
    rows.extend(scaling)
    return (
        pd.DataFrame(rows)
        .sort_values(["variable", "parameter", "point_id", "day_of_year"])
        .reset_index(drop=True)
    )
