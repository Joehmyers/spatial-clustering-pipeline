"""Stage 6, evaluate: judge the new map against today's, on held-out data.

This is the only stage that may read demand (R12). The map was built from
weather with no sight of demand, so demand is an honest test of it rather
than a thing it was fitted to.

Everything here is measured on the held-out window alone, using the normals
and scaling stored from the build window, so no statistic can be flattered by
the data the tree grew from.

Six measures, each answering a different question:

1. **Variance explained between points.** Does the tree itself separate the
   weather, before any mapping onto PGAs?
2. **The ceiling.** How much of the RA-level weather variance lies between
   PGAs? No map made of whole PGAs can reach the part lying inside them.
3. **Eta-squared.** Of the variance across PGAs on a given day, how much
   lies between NCAs rather than inside them? Measured for each weather
   variable and for demand.
4. **Correlation within and between NCAs.** Are PGAs in one NCA more alike
   day to day than PGAs in different ones?
5. **The random benchmark.** Where do the two maps fall among random
   contiguous partitions of the PGA graph at the same count? A map that beats
   today's but not a coin toss has proved nothing.
6. **RA misfits.** Which RAs sit with the wrong NCA: their weather tracks a
   neighbouring NCA more closely than their own?
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import geoutil
from .geometry import area_shares
from .inputs import DATE, DEMAND, PGA_ID, POINT_ID, VARIABLE, DataSource
from .outputs import (
    RunDirectory,
    read_csv,
    read_geojson,
    read_json,
    write_csv,
    write_json,
)
from .runrecord import RunRecord
from .settings import Settings

STAGE = "evaluate"

# Below this, a day's spread across PGAs is numerically zero and the share of
# it lying between NCAs is not a meaningful number, so the day is skipped.
FLAT_DAY_TOLERANCE = 1e-12


def eta_squared(values: np.ndarray, groups: np.ndarray) -> float:
    """The share of variance lying between groups rather than inside them.

    Sum of squares between groups divided by the total sum of squares. Zero
    means the groups explain nothing; one means every unit matches its own
    group's mean exactly.
    """
    values = np.asarray(values, dtype=float)
    grand = values.mean()
    total = float(((values - grand) ** 2).sum())
    if total <= FLAT_DAY_TOLERANCE:
        return float("nan")
    between = 0.0
    for name in np.unique(groups):
        inside = values[groups == name]
        between += len(inside) * (inside.mean() - grand) ** 2
    return float(between / total)


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Compare today's map with the new one on the held-out window."""
    source = DataSource.for_stage(settings, STAGE)
    run_directory.prepare(STAGE)
    windows = settings.windows
    headline = settings.cluster.number_of_regions
    variables = list(settings.features.variables)

    cells = read_geojson(run_directory.require("graph", "cells"))
    pgas = read_geojson(run_directory.require("geometry", "pga_layer"))
    ras = read_geojson(run_directory.require("geometry", "ra_layer"))
    checks = read_json(run_directory.require("geometry", "checks"))
    labels = read_csv(run_directory.require("cluster", "labels"))
    assignments = read_csv(run_directory.require("mapping", "assignments"))
    anomalies = read_csv(run_directory.require("features", "anomalies"))

    held_out = anomalies.loc[anomalies["window"] == "held_out"]
    point_series = {
        variable: held_out.loc[held_out[VARIABLE] == variable]
        .pivot(index=DATE, columns=POINT_ID, values="z_score")
        .sort_index()
        for variable in variables
    }
    points = sorted(point_series[variables[0]].columns)
    record.log(
        f"{STAGE}: {len(point_series[variables[0]])} held-out days over "
        f"{len(points)} points"
    )

    pga_ids = sorted(pgas["pga_id"].astype(str))
    ra_ids = sorted(ras["ra_id"].astype(str))
    pga_weights = _weights(pgas, "pga_id", cells, points, pga_ids)
    ra_weights = _weights(ras, "ra_id", cells, points, ra_ids)
    pga_series = {
        variable: _weighted(point_series[variable], points, pga_weights, pga_ids)
        for variable in variables
    }
    ra_series = {
        variable: _weighted(point_series[variable], points, ra_weights, ra_ids)
        for variable in variables
    }

    current_map = _current_map(settings, pgas, checks, pga_ids)
    new_map = _new_map(assignments, headline, pga_ids)
    ra_parent = dict(
        zip(
            assignments.loc[assignments["unit_type"] == "ra", "unit_id"],
            assignments.loc[assignments["unit_type"] == "ra", "pga_id"],
            strict=True,
        )
    )
    pga_edges = {
        (row["pga_a"], row["pga_b"]): float(row["shared_edge_metres"])
        for row in checks["pga_neighbours"]
    }

    demand = source.read_demand(windows.held_out_start, windows.held_out_end)
    demand_series = demand.pivot(index=DATE, columns=PGA_ID, values=DEMAND).sort_index()
    demand_series = demand_series.reindex(columns=pga_ids)
    if demand_series.isna().any().any():
        missing = sorted(demand_series.columns[demand_series.isna().any()])
        raise KeyError(
            f"the demand extract has no readings for {', '.join(missing)} in the "
            "held-out window"
        )

    metrics: dict[str, Any] = {
        "held_out_window": [
            windows.held_out_start.isoformat(),
            windows.held_out_end.isoformat(),
        ],
        "number_of_regions": headline,
        "maps": {
            "current": _grouped(current_map),
            "new": _grouped(new_map),
        },
        "point_variance_explained": _point_variance(
            point_series, labels, headline, points, variables
        ),
        "ceiling": _ceiling(ra_series, ra_parent, ra_ids, variables),
    }

    per_map: dict[str, Any] = {}
    for name, mapping in (("current", current_map), ("new", new_map)):
        per_map[name] = {
            "eta_squared": _eta_by_variable(
                pga_series, demand_series, mapping, pga_ids, variables
            ),
            "correlations": _correlations(pga_series, mapping, pga_ids, variables),
        }
    metrics["by_map"] = per_map

    benchmark, standings = _benchmark(
        settings,
        pga_series,
        demand_series,
        pga_ids,
        pga_edges,
        variables,
        {"current": current_map, "new": new_map},
        headline,
        record,
    )
    metrics["benchmark"] = standings
    metrics["ra_misfits"] = {
        name: _misfits(ra_series, mapping, ra_parent, ra_ids, pga_edges, variables)
        for name, mapping in (("current", current_map), ("new", new_map))
    }
    metrics["new_map_beats_current"] = {
        "weather": _beats(per_map, "weather_mean"),
        "demand": _beats(per_map, DEMAND),
    }
    metrics["sealed_window_override_used"] = source.sealed_override_used

    write_json(metrics, run_directory.path(STAGE, "metrics"))
    write_csv(benchmark, run_directory.path(STAGE, "benchmark"))
    record.record_reads(source.reads)
    record.log(
        f"{STAGE}: eta-squared for weather, today's map "
        f"{per_map['current']['eta_squared']['weather_mean']:.3f} against the new "
        f"map {per_map['new']['eta_squared']['weather_mean']:.3f}; for demand "
        f"{per_map['current']['eta_squared'][DEMAND]:.3f} against "
        f"{per_map['new']['eta_squared'][DEMAND]:.3f}"
    )
    return metrics


def _weights(
    units: Any,
    unit_column: str,
    cells: Any,
    points: list[str],
    unit_ids: list[str],
) -> np.ndarray:
    """How much of each unit's area each point's cell covers, unit by unit.

    Returns a table of units by points whose rows each add to one, so a unit's
    series is the area-weighted mean of the point series under it.
    """
    shares = area_shares(units, unit_column, cells, POINT_ID)
    table = (
        shares.pivot(index=unit_column, columns=POINT_ID, values="share")
        .reindex(index=unit_ids, columns=points)
        .fillna(0.0)
        .to_numpy()
    )
    totals = table.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1.0
    return table / totals


def _weighted(
    series: pd.DataFrame, points: list[str], weights: np.ndarray, unit_ids: list[str]
) -> pd.DataFrame:
    """Each unit's daily series, as the area-weighted mean of its points."""
    values = series.reindex(columns=points).to_numpy()
    return pd.DataFrame(values @ weights.T, index=series.index, columns=unit_ids)


def _current_map(
    settings: Settings, pgas: Any, checks: dict[str, Any], pga_ids: list[str]
) -> dict[str, str]:
    """Today's NCA for each PGA: its own column when it has one, else overlay."""
    column = settings.layer("pga").parent_id_column
    if column and column in pgas.columns:
        found = dict(
            zip(pgas["pga_id"].astype(str), pgas[column].astype(str), strict=True)
        )
    else:
        found = checks["nesting_by_overlay"]["pga_in_nca"]["best_parent"]
    return {pga_id: found[pga_id] for pga_id in pga_ids}


def _new_map(
    assignments: pd.DataFrame, headline: int, pga_ids: list[str]
) -> dict[str, str]:
    rows = assignments.loc[
        (assignments["k"] == headline) & (assignments["unit_type"] == "pga")
    ]
    found = dict(zip(rows["unit_id"].astype(str), rows["assigned_nca"], strict=True))
    return {pga_id: found[pga_id] for pga_id in pga_ids}


def _grouped(mapping: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for unit, name in sorted(mapping.items()):
        groups.setdefault(name, []).append(unit)
    return dict(sorted(groups.items()))


def _point_variance(
    point_series: dict[str, pd.DataFrame],
    labels: pd.DataFrame,
    headline: int,
    points: list[str],
    variables: list[str],
) -> dict[str, Any]:
    """How much of the between-point weather variance the clusters explain.

    This judges the tree on its own, before any mapping onto PGAs, so a tree
    that works and a mapping that spoils it can be told apart.
    """
    at_k = labels.loc[labels["k"] == headline]
    lookup = dict(zip(at_k[POINT_ID].astype(str), at_k["cluster"], strict=True))
    groups = np.array([lookup[point] for point in points])
    result: dict[str, Any] = {}
    totals = []
    for variable in variables:
        values = point_series[variable].reindex(columns=points).to_numpy()
        shares = [eta_squared(row, groups) for row in values]
        share = float(np.nanmean(shares))
        result[variable] = round(share, 6)
        totals.append(share)
    result["weather_mean"] = round(float(np.mean(totals)), 6)
    result["clusters"] = sorted(set(groups.tolist()))
    return result


def _ceiling(
    ra_series: dict[str, pd.DataFrame],
    ra_parent: dict[str, str],
    ra_ids: list[str],
    variables: list[str],
) -> dict[str, Any]:
    """RA-level weather variance split into within-PGA and between-PGA parts.

    NCAs are made of whole PGAs, so the within-PGA part is out of reach of any
    NCA map. The between-PGA share is the highest eta-squared any map could
    reach at RA level.
    """
    groups = np.array([ra_parent[ra_id] for ra_id in ra_ids])
    result: dict[str, Any] = {}
    between_all = []
    for variable in variables:
        values = ra_series[variable].reindex(columns=ra_ids).to_numpy()
        between = float(np.nanmean([eta_squared(row, groups) for row in values]))
        result[variable] = {
            "between_pga_share": round(between, 6),
            "within_pga_share": round(1.0 - between, 6),
        }
        between_all.append(between)
    mean = float(np.mean(between_all))
    result["weather_mean"] = {
        "between_pga_share": round(mean, 6),
        "within_pga_share": round(1.0 - mean, 6),
    }
    result["note"] = (
        "the between-PGA share is the ceiling: no map made of whole PGAs can "
        "explain the variance lying inside a PGA"
    )
    return result


def _eta_by_variable(
    pga_series: dict[str, pd.DataFrame],
    demand_series: pd.DataFrame,
    mapping: dict[str, str],
    pga_ids: list[str],
    variables: list[str],
) -> dict[str, float]:
    """Eta-squared each day across PGAs with NCA as the group, then averaged."""
    groups = np.array([mapping[pga_id] for pga_id in pga_ids])
    result: dict[str, float] = {}
    weather = []
    for variable in variables:
        values = pga_series[variable].reindex(columns=pga_ids).to_numpy()
        share = float(np.nanmean([eta_squared(row, groups) for row in values]))
        result[variable] = round(share, 6)
        weather.append(share)
    result["weather_mean"] = round(float(np.mean(weather)), 6)
    demand_values = demand_series.reindex(columns=pga_ids).to_numpy()
    result[DEMAND] = round(
        float(np.nanmean([eta_squared(row, groups) for row in demand_values])), 6
    )
    return result


def _correlations(
    pga_series: dict[str, pd.DataFrame],
    mapping: dict[str, str],
    pga_ids: list[str],
    variables: list[str],
) -> dict[str, Any]:
    """Mean correlation of PGA series, within one NCA and between two."""
    result: dict[str, Any] = {}
    within_all, between_all = [], []
    for variable in variables:
        values = pga_series[variable].reindex(columns=pga_ids).to_numpy()
        correlation = np.corrcoef(values.T)
        within, between = [], []
        for first in range(len(pga_ids)):
            for second in range(first + 1, len(pga_ids)):
                pair = correlation[first, second]
                if mapping[pga_ids[first]] == mapping[pga_ids[second]]:
                    within.append(pair)
                else:
                    between.append(pair)
        result[variable] = {
            "within_nca": round(float(np.mean(within)), 6) if within else None,
            "between_nca": round(float(np.mean(between)), 6) if between else None,
        }
        within_all += within
        between_all += between
    result["weather_mean"] = {
        "within_nca": round(float(np.mean(within_all)), 6) if within_all else None,
        "between_nca": round(float(np.mean(between_all)), 6) if between_all else None,
    }
    return result


def random_contiguous_partition(
    nodes: list[str],
    edges: list[tuple[str, str]],
    k: int,
    generator: np.random.Generator,
) -> dict[str, int]:
    """Split a connected graph into k connected regions, grown from k seeds.

    Each region starts at one node and grows into a neighbour chosen at
    random, so every region ends up connected and every node ends up in one.
    """
    neighbours: dict[str, list[str]] = {node: [] for node in nodes}
    for first, second in edges:
        if first in neighbours and second in neighbours:
            neighbours[first].append(second)
            neighbours[second].append(first)
    seeds = generator.choice(len(nodes), size=k, replace=False)
    assigned: dict[str, int] = {}
    frontier: list[set[str]] = []
    for region, seed in enumerate(seeds):
        node = nodes[int(seed)]
        assigned[node] = region
        frontier.append(set())
    for node, region in list(assigned.items()):
        frontier[region].update(
            name for name in neighbours[node] if name not in assigned
        )
    while len(assigned) < len(nodes):
        live = [
            region
            for region, edge in enumerate(frontier)
            if any(name not in assigned for name in edge)
        ]
        region = int(generator.choice(live))
        choices = sorted(name for name in frontier[region] if name not in assigned)
        node = choices[int(generator.integers(len(choices)))]
        assigned[node] = region
        frontier[region].update(
            name for name in neighbours[node] if name not in assigned
        )
    return assigned


def _benchmark(
    settings: Settings,
    pga_series: dict[str, pd.DataFrame],
    demand_series: pd.DataFrame,
    pga_ids: list[str],
    pga_edges: dict[tuple[str, str], float],
    variables: list[str],
    maps: dict[str, dict[str, str]],
    headline: int,
    record: RunRecord,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score random contiguous maps at the same count, and place both maps."""
    generator = np.random.default_rng(settings.evaluate.seed)
    edges = list(pga_edges)
    rows: list[dict[str, Any]] = []
    for draw in range(settings.evaluate.random_partitions):
        partition = random_contiguous_partition(pga_ids, edges, headline, generator)
        mapping = {pga_id: f"R{partition[pga_id]}" for pga_id in pga_ids}
        scores = _eta_by_variable(
            pga_series, demand_series, mapping, pga_ids, variables
        )
        rows.append(
            {
                "draw": draw,
                "regions": headline,
                "contiguous": all(
                    geoutil.is_connected(members, edges)
                    for members in _grouped(mapping).values()
                ),
                "weather_eta_squared": scores["weather_mean"],
                "demand_eta_squared": scores[DEMAND],
                "partition": " ".join(
                    f"{pga_id}={mapping[pga_id]}" for pga_id in pga_ids
                ),
            }
        )
    benchmark = pd.DataFrame(rows)
    record.log(
        f"{STAGE}: scored {len(benchmark)} random contiguous maps at k = "
        f"{headline}, seed {settings.evaluate.seed}"
    )

    standings: dict[str, Any] = {
        "random_partitions": int(len(benchmark)),
        "seed": settings.evaluate.seed,
        "all_contiguous": bool(benchmark["contiguous"].all()),
        "weather": _spread(benchmark["weather_eta_squared"]),
        "demand": _spread(benchmark["demand_eta_squared"]),
        "placings": {},
    }
    for name, mapping in maps.items():
        scores = _eta_by_variable(
            pga_series, demand_series, mapping, pga_ids, variables
        )
        standings["placings"][name] = {
            "weather_eta_squared": scores["weather_mean"],
            "weather_percentile": _percentile(
                benchmark["weather_eta_squared"], scores["weather_mean"]
            ),
            "demand_eta_squared": scores[DEMAND],
            "demand_percentile": _percentile(
                benchmark["demand_eta_squared"], scores[DEMAND]
            ),
        }
    return benchmark, standings


def _spread(values: pd.Series) -> dict[str, float]:
    return {
        "lowest": round(float(values.min()), 6),
        "median": round(float(values.median()), 6),
        "highest": round(float(values.max()), 6),
        "mean": round(float(values.mean()), 6),
    }


def _percentile(values: pd.Series, score: float) -> float:
    """The share of random maps this score beats or matches, as a percentage."""
    return round(float((values <= score).mean() * 100.0), 3)


def _misfits(
    ra_series: dict[str, pd.DataFrame],
    mapping: dict[str, str],
    ra_parent: dict[str, str],
    ra_ids: list[str],
    pga_edges: dict[tuple[str, str], float],
    variables: list[str],
) -> list[dict[str, Any]]:
    """RAs whose weather tracks a neighbouring NCA better than their own.

    Each NCA's mean series leaves out the RA's own PGA, so the RA is never
    compared against a series it helped make. An RA whose NCA holds no other
    PGA has nothing to compare against and is skipped.
    """
    neighbours: dict[str, set[str]] = {}
    for first, second in pga_edges:
        neighbours.setdefault(first, set()).add(second)
        neighbours.setdefault(second, set()).add(first)
    by_nca: dict[str, list[str]] = {}
    for pga_id, nca in sorted(mapping.items()):
        by_nca.setdefault(nca, []).append(pga_id)

    found: list[dict[str, Any]] = []
    for ra_id in ra_ids:
        own_pga = ra_parent[ra_id]
        own_nca = mapping[own_pga]
        nearby = {
            mapping[other]
            for other in neighbours.get(own_pga, set())
            if mapping[other] != own_nca
        }
        scores: dict[str, float] = {}
        for nca in sorted({own_nca, *nearby}):
            others = [pga for pga in by_nca[nca] if pga != own_pga]
            if not others:
                continue
            scores[nca] = _mean_correlation(
                ra_series, ra_id, others, variables, ra_parent, ra_ids
            )
        if own_nca not in scores or len(scores) < 2:
            continue
        best = max(sorted(scores), key=lambda name: (scores[name], name))
        if best != own_nca:
            found.append(
                {
                    "ra_id": ra_id,
                    "pga_id": own_pga,
                    "own_nca": own_nca,
                    "own_correlation": round(scores[own_nca], 6),
                    "closer_nca": best,
                    "closer_correlation": round(scores[best], 6),
                }
            )
    return found


def _mean_correlation(
    ra_series: dict[str, pd.DataFrame],
    ra_id: str,
    other_pgas: list[str],
    variables: list[str],
    ra_parent: dict[str, str],
    ra_ids: list[str],
) -> float:
    """Correlation of one RA's series with the mean of some other PGAs' RAs."""
    members = [name for name in ra_ids if ra_parent[name] in other_pgas]
    scores = []
    for variable in variables:
        frame = ra_series[variable]
        own = frame[ra_id].to_numpy()
        other = frame[members].mean(axis=1).to_numpy()
        if own.std() == 0 or other.std() == 0:
            continue
        scores.append(float(np.corrcoef(own, other)[0, 1]))
    return float(np.mean(scores)) if scores else float("nan")


def _beats(per_map: dict[str, Any], key: str) -> dict[str, Any]:
    current = per_map["current"]["eta_squared"][key]
    new = per_map["new"]["eta_squared"][key]
    return {
        "current": current,
        "new": new,
        "new_is_higher": bool(new > current),
        "difference": round(new - current, 6),
    }
