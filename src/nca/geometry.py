"""Stage 1, geometry: read the operational layers and check they hang together.

Redrawing RAs and PGAs is out of scope: they are fixed operational units. This
stage only reads them, moves them into British National Grid so every length
is metres, repairs broken shapes, and writes down what it found wrong. It
checks nesting twice over, because the two checks fail in different ways: the
ID columns catch a mislabelled unit, and the overlay catches a shape that was
moved without relabelling.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

from . import geoutil
from .errors import NestingError
from .inputs import DataSource
from .outputs import RunDirectory, write_geojson, write_json
from .runrecord import RunRecord
from .settings import Settings

STAGE = "geometry"

# Below this, a disagreement between two layers is rounding, not a real gap.
# One square metre against units of tens of square kilometres.
SLIVER_TOLERANCE_SQUARE_METRES = 1.0

LEVELS = ("ra", "pga", "nca")


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Read, clean and check the three layers. Returns the check report."""
    source = DataSource.for_stage(settings, STAGE)
    run_directory.prepare(STAGE)
    record.log(f"{STAGE}: reading the NCA, PGA and RA layers")

    layers: dict[str, gpd.GeoDataFrame] = {}
    for level in LEVELS:
        frame = source.read_layer(level)
        frame = frame.to_crs(settings.coordinates.working_crs)
        broken = int((~frame.geometry.is_valid).sum())
        if broken:
            record.notice(
                f"{STAGE}: repaired {broken} invalid shape(s) in the "
                f"{level.upper()} layer"
            )
            frame["geometry"] = frame.geometry.map(geoutil.repair)
        frame["area_square_metres"] = frame.geometry.area.round(2)
        frame["parts"] = frame.geometry.map(geoutil.part_count)
        layers[level] = frame

    report: dict[str, Any] = {
        "working_crs": settings.coordinates.working_crs,
        "counts": {level: int(len(layers[level])) for level in LEVELS},
    }

    by_overlay = _nesting_by_overlay(layers)
    report["nesting_by_id"] = _nesting_by_id(settings, layers)
    report["nesting_by_overlay"] = by_overlay
    report["sliver_areas"] = _slivers(layers, by_overlay)
    report["multi_part_units"] = _multi_part(layers)

    outline = _outline(settings, layers)
    report["service_area"] = {
        "built_from": f"the dissolved {settings.graph.clipping_outline.upper()} layer",
        "area_square_metres": round(float(outline.area), 2),
        "parts": geoutil.part_count(outline),
    }

    pga_edges = geoutil.adjacency(
        dict(zip(layers["pga"]["pga_id"], layers["pga"].geometry, strict=True)),
        rule=settings.graph.neighbour_rule,
        minimum_metres=settings.graph.minimum_shared_edge_metres,
    )
    report["pga_neighbours"] = [
        {"pga_a": first, "pga_b": second, "shared_edge_metres": round(metres, 3)}
        for (first, second), metres in sorted(pga_edges.items())
    ]
    report["current_nca_contiguity"] = _contiguity(
        settings, layers, by_overlay, list(pga_edges)
    )

    failures = _failures(report)
    report["passed"] = not failures
    report["failures"] = failures

    for level in LEVELS:
        write_geojson(layers[level], run_directory.path(STAGE, f"{level}_layer"))
    write_geojson(
        gpd.GeoDataFrame(
            {"name": ["service-area"]},
            geometry=[outline],
            crs=settings.coordinates.working_crs,
        ),
        run_directory.path(STAGE, "outline"),
    )
    write_json(report, run_directory.path(STAGE, "checks"))
    record.record_reads(source.reads)
    record.log(
        f"{STAGE}: {report['counts']['ra']} RAs, {report['counts']['pga']} PGAs, "
        f"{report['counts']['nca']} NCAs; "
        + ("all checks passed" if report["passed"] else f"{len(failures)} failure(s)")
    )
    if failures:
        raise NestingError(
            "the operational layers do not hang together:\n"
            + "\n".join(f"  - {failure}" for failure in failures)
        )
    return report


def _parent_column(settings: Settings, level: str) -> str:
    return settings.layer(level).parent_id_column


def _nesting_by_id(
    settings: Settings, layers: dict[str, gpd.GeoDataFrame]
) -> dict[str, Any]:
    """Check each unit names exactly one parent, and that the parent exists."""
    result: dict[str, Any] = {}
    for child, parent in (("ra", "pga"), ("pga", "nca")):
        column = _parent_column(settings, child)
        if not column:
            result[f"{child}_in_{parent}"] = {
                "checked": False,
                "reason": f"layers.{child}.parent_id_column is not set",
            }
            continue
        frame = layers[child]
        parent_ids = set(layers[parent][f"{parent}_id"])
        missing = sorted(frame.loc[frame[column].isna(), f"{child}_id"])
        unknown = sorted(
            frame.loc[
                frame[column].notna() & ~frame[column].astype(str).isin(parent_ids),
                f"{child}_id",
            ]
        )
        result[f"{child}_in_{parent}"] = {
            "checked": True,
            "column": column,
            "without_a_parent": missing,
            "naming_a_parent_that_does_not_exist": unknown,
        }
    return result


def _nesting_by_overlay(layers: dict[str, gpd.GeoDataFrame]) -> dict[str, Any]:
    """Check each unit's area sits inside one parent, whatever its label says."""
    result: dict[str, Any] = {}
    for child, parent in (("ra", "pga"), ("pga", "nca")):
        shares = area_shares(
            layers[child], f"{child}_id", layers[parent], f"{parent}_id"
        )
        best = (
            shares.sort_values(["share"], ascending=False)
            .groupby(f"{child}_id", as_index=False)
            .first()
            .sort_values(f"{child}_id")
        )
        straddling = best.loc[best["share"] < 0.999]
        result[f"{child}_in_{parent}"] = {
            "checked": True,
            "units_split_across_parents": [
                {
                    "unit": row[f"{child}_id"],
                    "largest_parent": row[f"{parent}_id"],
                    "share_in_it": round(float(row["share"]), 6),
                }
                for _, row in straddling.iterrows()
            ],
            "best_parent": dict(
                zip(best[f"{child}_id"], best[f"{parent}_id"], strict=True)
            ),
        }
    return result


def _slivers(
    layers: dict[str, gpd.GeoDataFrame], by_overlay: dict[str, Any]
) -> list[dict[str, Any]]:
    """Area where a dissolved lower layer and the layer above disagree."""
    found: list[dict[str, Any]] = []
    for child, parent in (("ra", "pga"), ("pga", "nca")):
        best = by_overlay[f"{child}_in_{parent}"]["best_parent"]
        child_frame = layers[child]
        grouped: dict[str, list] = {}
        for _, row in child_frame.iterrows():
            grouped.setdefault(best[row[f"{child}_id"]], []).append(row.geometry)
        for _, row in layers[parent].iterrows():
            parent_id = row[f"{parent}_id"]
            pieces = grouped.get(parent_id, [])
            dissolved = unary_union(pieces) if pieces else None
            if dissolved is None:
                area = float(row.geometry.area)
            else:
                area = float(row.geometry.symmetric_difference(dissolved).area)
            if area > SLIVER_TOLERANCE_SQUARE_METRES:
                found.append(
                    {
                        "layer_above": parent,
                        "unit": parent_id,
                        "sliver_square_metres": round(area, 2),
                    }
                )
    return found


def _multi_part(layers: dict[str, gpd.GeoDataFrame]) -> list[dict[str, Any]]:
    """Units made of more than one piece. A flag, not a failure: an island is
    a real thing, and the stages below must cope with it."""
    found: list[dict[str, Any]] = []
    for level in LEVELS:
        frame = layers[level]
        for _, row in frame.loc[frame["parts"] > 1].iterrows():
            found.append(
                {"layer": level, "unit": row[f"{level}_id"], "parts": int(row["parts"])}
            )
    return found


def _outline(settings: Settings, layers: dict[str, gpd.GeoDataFrame]):
    """The area the AA serves: the chosen layer, dissolved into one shape."""
    level = settings.graph.clipping_outline
    return geoutil.repair(unary_union(list(layers[level].geometry)))


def _contiguity(
    settings: Settings,
    layers: dict[str, gpd.GeoDataFrame],
    by_overlay: dict[str, Any],
    pga_edges: list[tuple[str, str]],
) -> dict[str, Any]:
    """Are today's NCAs each one connected piece on the PGA neighbour graph?"""
    column = _parent_column(settings, "pga")
    if not column:
        best = by_overlay["pga_in_nca"]["best_parent"]
    else:
        frame = layers["pga"]
        best = dict(zip(frame["pga_id"], frame[column].astype(str), strict=True))
    groups: dict[str, list[str]] = {}
    for pga_id, nca_id in sorted(best.items()):
        groups.setdefault(nca_id, []).append(pga_id)
    result = {}
    for nca_id, members in sorted(groups.items()):
        parts = geoutil.connected_parts(members, pga_edges)
        result[nca_id] = {
            "pgas": members,
            "contiguous": len(parts) == 1,
            "parts": parts,
        }
    return result


def _failures(report: dict[str, Any]) -> list[str]:
    """Everything that must stop the run, in the order a reader should fix it."""
    failures: list[str] = []
    for key, body in report["nesting_by_id"].items():
        if not body.get("checked"):
            continue
        for unit in body["without_a_parent"]:
            failures.append(
                f"{key}: {unit} names no parent in column '{body['column']}'"
            )
        for unit in body["naming_a_parent_that_does_not_exist"]:
            failures.append(
                f"{key}: {unit} names a parent that is not in the layer above"
            )
    for key, body in report["nesting_by_overlay"].items():
        for split in body["units_split_across_parents"]:
            failures.append(
                f"{key}: {split['unit']} lies only {split['share_in_it']:.3f} inside "
                f"{split['largest_parent']}, so it sits in more than one"
            )
    for sliver in report["sliver_areas"]:
        failures.append(
            f"{sliver['unit']}: the layer below covers a different area, differing "
            f"by {sliver['sliver_square_metres']:.2f} square metres"
        )
    for nca_id, body in report["current_nca_contiguity"].items():
        if not body["contiguous"]:
            failures.append(
                f"{nca_id} is not contiguous: its PGAs fall into "
                f"{len(body['parts'])} separate pieces"
            )
    return failures


def area_shares(
    child: gpd.GeoDataFrame,
    child_id: str,
    parent: gpd.GeoDataFrame,
    parent_id: str,
) -> pd.DataFrame:
    """For each child unit, the share of its area lying in each parent unit."""
    overlay = gpd.overlay(
        child[[child_id, "geometry"]],
        parent[[parent_id, "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    overlay["overlap_square_metres"] = overlay.geometry.area
    grouped = overlay.groupby([child_id, parent_id], as_index=False)[
        "overlap_square_metres"
    ].sum()
    totals = grouped.groupby(child_id)["overlap_square_metres"].transform("sum")
    grouped["share"] = grouped["overlap_square_metres"] / totals
    return grouped.sort_values([child_id, parent_id]).reset_index(drop=True)
