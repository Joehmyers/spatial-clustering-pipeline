"""Stage 5, mapping: turn point clusters into whole PGAs.

The clusters are drawn on weather alone and pay no attention to operational
boundaries, so a cluster boundary can run through the middle of a PGA. PGAs
are fixed units, so each one goes whole to the cluster holding most of its
area. How much of a PGA sat on the other side is worth knowing, so each one
carries a straddle score: 1 minus its majority share. A score of 0 means the
PGA sits squarely in one cluster; 0.5 means it is cut in half.

Whole PGAs can leave a new NCA in two pieces. When repair is on, each
stranded PGA moves to the neighbouring NCA it shares the most boundary with,
and every move is written down (R16).
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

from . import geoutil
from .geometry import area_shares
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

STAGE = "mapping"

# New NCAs are named after the cluster they came from, which is named after
# the smallest point ID in it. "NCA-P01" is the NCA grown from cluster P01.
NEW_NCA_PREFIX = "NCA-"

# Moving PGAs can strand others, so repair runs again. This caps it, so a map
# that cannot be repaired stops rather than looping.
MAXIMUM_REPAIR_ROUNDS = 20


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Map every saved cut onto whole PGAs, and repair what it strands."""
    run_directory.prepare(STAGE)
    cells = read_geojson(run_directory.require("graph", "cells"))
    pgas = read_geojson(run_directory.require("geometry", "pga_layer"))
    ras = read_geojson(run_directory.require("geometry", "ra_layer"))
    labels = read_csv(run_directory.require("cluster", "labels"))
    checks = read_json(run_directory.require("geometry", "checks"))

    pga_edges = {
        (row["pga_a"], row["pga_b"]): float(row["shared_edge_metres"])
        for row in checks["pga_neighbours"]
    }
    ra_to_pga = _ra_to_pga(settings, ras, pgas)

    assignments: list[pd.DataFrame] = []
    moves: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"cuts": {}, "rule": settings.mapping.rule}

    for k in settings.cuts:
        at_k = labels.loc[labels["k"] == k]
        clusters = _cluster_shapes(cells, at_k)
        pga_share = area_shares(pgas, "pga_id", clusters, "cluster")
        ra_share = area_shares(ras, "ra_id", clusters, "cluster")
        pga_best = _majority(pga_share, "pga_id")
        ra_best = _majority(ra_share, "ra_id")

        assigned = {
            row["pga_id"]: NEW_NCA_PREFIX + row["cluster"]
            for _, row in pga_best.iterrows()
        }
        repaired, cut_moves = _repair(settings, assigned, pga_edges, k, record)
        moves.extend(cut_moves)

        unused = sorted(
            set(at_k["cluster"])
            - {name.removeprefix(NEW_NCA_PREFIX) for name in repaired.values()}
        )
        for cluster in unused:
            record.notice(
                f"{STAGE}: at k = {k}, cluster {cluster} wins no PGA, so it "
                "disappears from the mapped map"
            )

        assignments.append(_rows(k, pga_best, ra_best, repaired, ra_to_pga))
        groups: dict[str, list[str]] = {}
        for pga_id, nca in sorted(repaired.items()):
            groups.setdefault(nca, []).append(pga_id)
        summary["cuts"][str(k)] = {
            "new_ncas": {name: members for name, members in sorted(groups.items())},
            "clusters_winning_no_pga": unused,
            "contiguous": all(
                geoutil.is_connected(members, list(pga_edges))
                for members in groups.values()
            ),
            "highest_straddle_score": round(float(pga_best["straddle_score"].max()), 6),
            "mean_straddle_score": round(float(pga_best["straddle_score"].mean()), 6),
            "moves": len([move for move in cut_moves if move["k"] == k]),
        }

    frame = pd.concat(assignments, ignore_index=True)
    write_csv(frame, run_directory.path(STAGE, "assignments"))
    write_csv(
        pd.DataFrame(
            moves,
            columns=[
                "k",
                "pga_id",
                "from_nca",
                "to_nca",
                "shared_boundary_metres",
                "reason",
            ],
        ),
        run_directory.path(STAGE, "moves"),
    )
    write_json(summary, run_directory.path(STAGE, "summary"))
    record.log(
        f"{STAGE}: mapped {len(settings.cuts)} cut(s) onto "
        f"{len(pgas)} PGAs; {len(moves)} PGA(s) moved to repair contiguity"
    )
    return summary


def _ra_to_pga(
    settings: Settings, ras: gpd.GeoDataFrame, pgas: gpd.GeoDataFrame
) -> dict[str, str]:
    """Which PGA each RA belongs to: its own column when it has one, else the
    PGA holding most of its area."""
    column = settings.layer("ra").parent_id_column
    if column and column in ras.columns:
        return dict(zip(ras["ra_id"], ras[column].astype(str), strict=True))
    best = _majority(area_shares(ras, "ra_id", pgas, "pga_id"), "ra_id")
    return dict(zip(best["ra_id"], best["pga_id"], strict=True))


def _cluster_shapes(cells: gpd.GeoDataFrame, labels: pd.DataFrame) -> gpd.GeoDataFrame:
    """Colour each cell by its cluster and merge the cells of one colour."""
    lookup = dict(zip(labels["point_id"].astype(str), labels["cluster"], strict=True))
    coloured = cells.copy()
    coloured["cluster"] = coloured["point_id"].astype(str).map(lookup)
    coloured = coloured.loc[coloured["cluster"].notna()]
    merged = coloured.dissolve(by="cluster", as_index=False)[["cluster", "geometry"]]
    return merged.sort_values("cluster").reset_index(drop=True)


def _majority(shares: pd.DataFrame, unit_column: str) -> pd.DataFrame:
    """The winning group for each unit, with its share and straddle score.

    Ties break on the winner's name, so two runs pick the same one.
    """
    ordered = shares.sort_values(["share", shares.columns[1]], ascending=[False, True])
    best = ordered.groupby(unit_column, as_index=False).first()
    best["majority_share"] = best["share"]
    best["straddle_score"] = 1.0 - best["share"]
    return best.sort_values(unit_column).reset_index(drop=True)


def _repair(
    settings: Settings,
    assigned: dict[str, str],
    pga_edges: dict[tuple[str, str], float],
    k: int,
    record: RunRecord,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Move stranded PGAs until every new NCA is one connected piece (R8)."""
    current = dict(assigned)
    moves: list[dict[str, Any]] = []
    if not settings.mapping.repair_stranded_pgas:
        return current, moves

    for _ in range(MAXIMUM_REPAIR_ROUNDS):
        stranded = _stranded(current, pga_edges)
        if not stranded:
            return current, moves
        moved_any = False
        for pga_id in stranded:
            target, metres = _best_neighbouring_nca(pga_id, current, pga_edges)
            if target is None:
                continue
            moves.append(
                {
                    "k": k,
                    "pga_id": pga_id,
                    "from_nca": current[pga_id],
                    "to_nca": target,
                    "shared_boundary_metres": round(metres, 3),
                    "reason": "stranded: it was cut off from the rest of its NCA",
                }
            )
            record.notice(
                f"{STAGE}: at k = {k}, moved {pga_id} from {current[pga_id]} to "
                f"{target}, the neighbouring NCA it shares the most boundary with "
                f"({round(metres)} metres)"
            )
            current[pga_id] = target
            moved_any = True
        if not moved_any:
            break
    remaining = _stranded(current, pga_edges)
    if remaining:
        record.notice(
            f"{STAGE}: at k = {k}, {', '.join(remaining)} stayed stranded: no "
            "neighbouring NCA to move them to"
        )
    return current, moves


def _stranded(
    assigned: dict[str, str], pga_edges: dict[tuple[str, str], float]
) -> list[str]:
    """PGAs sitting in a piece of their NCA that is not its largest."""
    groups: dict[str, list[str]] = {}
    for pga_id, nca in sorted(assigned.items()):
        groups.setdefault(nca, []).append(pga_id)
    cut_off: list[str] = []
    for members in groups.values():
        parts = geoutil.connected_parts(members, list(pga_edges))
        for part in parts[1:]:  # connected_parts puts the largest first
            cut_off.extend(part)
    return sorted(cut_off)


def _best_neighbouring_nca(
    pga_id: str,
    assigned: dict[str, str],
    pga_edges: dict[tuple[str, str], float],
) -> tuple[str | None, float]:
    """The neighbouring NCA this PGA shares the most boundary with."""
    totals: dict[str, float] = {}
    for (first, second), metres in pga_edges.items():
        if first == pga_id:
            other = second
        elif second == pga_id:
            other = first
        else:
            continue
        nca = assigned.get(other)
        if nca is None or nca == assigned[pga_id]:
            continue
        totals[nca] = totals.get(nca, 0.0) + metres
    if not totals:
        return None, 0.0
    best = max(sorted(totals), key=lambda name: (totals[name], name))
    return best, totals[best]


def _rows(
    k: int,
    pga_best: pd.DataFrame,
    ra_best: pd.DataFrame,
    assigned: dict[str, str],
    ra_to_pga: dict[str, str],
) -> pd.DataFrame:
    """One row per PGA and per RA, for this cut."""
    rows: list[dict[str, Any]] = []
    for _, row in pga_best.iterrows():
        rows.append(
            {
                "k": k,
                "unit_type": "pga",
                "unit_id": row["pga_id"],
                "pga_id": row["pga_id"],
                "assigned_nca": assigned[row["pga_id"]],
                "majority_cluster": row["cluster"],
                "majority_share": round(float(row["majority_share"]), 6),
                "straddle_score": round(float(row["straddle_score"]), 6),
            }
        )
    for _, row in ra_best.iterrows():
        pga_id = ra_to_pga[row["ra_id"]]
        rows.append(
            {
                "k": k,
                "unit_type": "ra",
                "unit_id": row["ra_id"],
                "pga_id": pga_id,
                # An RA follows its PGA: NCAs are made of whole PGAs.
                "assigned_nca": assigned[pga_id],
                "majority_cluster": row["cluster"],
                "majority_share": round(float(row["majority_share"]), 6),
                "straddle_score": round(float(row["straddle_score"]), 6),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["k", "unit_type", "unit_id"])
        .reset_index(drop=True)
    )
