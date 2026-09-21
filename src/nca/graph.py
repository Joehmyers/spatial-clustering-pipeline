"""Stage 2, graph: turn point coordinates into a neighbour graph.

Contiguity needs a graph, and the only thing the build is allowed to use is
the points themselves plus the outline of the area the AA serves. Voronoi
cells give exactly that: each cell is the ground nearer one point than any
other, so two points are neighbours when their cells share an edge.

Three details decide whether the graph is right:

* **Cells are matched to points by location, never by output order.** The
  Voronoi routine returns its cells in an order of its own.
* **A cell that clips away to nothing means an offshore point.** It is
  dropped and recorded, not quietly kept with an empty shape.
* **A shared corner is not a shared edge.** Two cells are neighbours only
  when the line between them is at least a metre long, so the diagonals of a
  regular grid do not become neighbours through rounding.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPoint, box
from shapely.ops import voronoi_diagram

from . import geoutil
from .errors import DisconnectedGraphError
from .inputs import DataSource
from .outputs import RunDirectory, read_geojson, write_csv, write_geojson, write_json
from .runrecord import RunRecord
from .settings import Settings

STAGE = "graph"

# Cells are built over ground wider than the outline so that the outermost
# points get a closed cell to clip, rather than one running off to infinity.
MARGIN_MULTIPLE = 1.0


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Build, clip and check the neighbour graph. Returns the graph summary."""
    source = DataSource.for_stage(settings, STAGE)
    run_directory.prepare(STAGE)

    outline_frame = read_geojson(run_directory.require("geometry", "outline"))
    outline = geoutil.repair(outline_frame.geometry.iloc[0])

    points = source.read_points()
    working = gpd.GeoDataFrame(
        {"point_id": points["point_id"].astype(str)},
        geometry=gpd.points_from_xy(points["longitude"], points["latitude"]),
        crs=settings.coordinates.input_crs,
    ).to_crs(settings.coordinates.working_crs)
    record.log(f"{STAGE}: {len(working)} points read, building Voronoi cells")

    cells = _voronoi_cells(working, outline)
    cells["clipped"] = [
        geoutil.repair(cell.intersection(outline)) for cell in cells["cell"]
    ]
    cells["area_square_metres"] = [shape.area for shape in cells["clipped"]]
    cells["parts"] = [geoutil.part_count(shape) for shape in cells["clipped"]]
    cells["inside_outline"] = [
        bool(outline.contains(point)) for point in cells.geometry
    ]
    cells["empty_after_clipping"] = [shape.is_empty for shape in cells["clipped"]]

    dropped = sorted(cells.loc[cells["empty_after_clipping"], "point_id"])
    for point_id in dropped:
        record.notice(
            f"{STAGE}: dropped point {point_id}: its cell clips away to nothing, so "
            "it sits offshore of the area the AA serves"
        )
    outside = sorted(
        cells.loc[~cells["inside_outline"] & ~cells["empty_after_clipping"], "point_id"]
    )
    for point_id in outside:
        record.notice(
            f"{STAGE}: point {point_id} lies outside the outline but keeps ground "
            "inside it"
        )
    split = sorted(cells.loc[cells["parts"] > 1, "point_id"])
    for point_id in split:
        record.notice(f"{STAGE}: the cell for point {point_id} is in several pieces")

    kept = cells.loc[~cells["empty_after_clipping"]].copy()
    kept = kept.sort_values("point_id").reset_index(drop=True)
    shapes = dict(zip(kept["point_id"], kept["clipped"], strict=True))

    computed = geoutil.adjacency(
        shapes,
        rule=settings.graph.neighbour_rule,
        minimum_metres=settings.graph.minimum_shared_edge_metres,
    )
    neighbours = [
        {
            "point_a": first,
            "point_b": second,
            "shared_edge_metres": round(metres, 3),
            "source": "computed",
        }
        for (first, second), metres in sorted(computed.items())
    ]
    neighbours += _manual_links(settings, shapes, set(computed), record)

    edges = [(row["point_a"], row["point_b"]) for row in neighbours]
    parts = geoutil.connected_parts(shapes, edges)
    if len(parts) > 1:
        neighbours, parts = _handle_disconnected(
            settings, kept, shapes, neighbours, parts, record
        )

    summary = _summarise(
        settings, cells, kept, neighbours, parts, dropped, outside, split
    )

    written = kept[["point_id", "area_square_metres", "parts", "inside_outline"]].copy()
    written["area_square_metres"] = written["area_square_metres"].round(2)
    written = gpd.GeoDataFrame(
        written, geometry=list(kept["clipped"]), crs=settings.coordinates.working_crs
    )
    write_geojson(written, run_directory.path(STAGE, "cells"))
    write_csv(
        pd.DataFrame(
            neighbours, columns=["point_a", "point_b", "shared_edge_metres", "source"]
        ),
        run_directory.path(STAGE, "neighbours"),
    )
    write_json(summary, run_directory.path(STAGE, "summary"))
    record.record_reads(source.reads)
    record.log(
        f"{STAGE}: kept {summary['points_kept']} points, dropped "
        f"{len(dropped)}, {summary['neighbour_pairs']} neighbour pairs, "
        f"{len(parts)} connected part(s)"
    )
    return summary


def _voronoi_cells(points: gpd.GeoDataFrame, outline) -> gpd.GeoDataFrame:
    """Voronoi cells, each matched to the point that falls inside it."""
    west, south, east, north = MultiPoint(list(points.geometry)).union(outline).bounds
    margin = MARGIN_MULTIPLE * math.hypot(east - west, north - south)
    envelope = box(west - margin, south - margin, east + margin, north + margin)
    diagram = voronoi_diagram(MultiPoint(list(points.geometry)), envelope=envelope)
    cells = gpd.GeoDataFrame(
        geometry=[geoutil.repair(cell) for cell in diagram.geoms], crs=points.crs
    )
    # Match by location. The diagram's own order is not the input order, and
    # relying on it would silently give every point someone else's cell.
    matched = gpd.sjoin(points, cells, how="left", predicate="within")
    if matched["index_right"].isna().any():
        lost = sorted(matched.loc[matched["index_right"].isna(), "point_id"])
        raise ValueError(
            f"no Voronoi cell contains point(s) {', '.join(lost)}; the envelope "
            "the cells were built over is too small"
        )
    matched = matched.sort_values("point_id").reset_index(drop=True)
    result = gpd.GeoDataFrame(
        {"point_id": matched["point_id"]},
        geometry=list(matched.geometry),
        crs=points.crs,
    )
    result["cell"] = [cells.geometry.iloc[int(i)] for i in matched["index_right"]]
    return result


def _manual_links(
    settings: Settings,
    shapes: dict,
    already: set[tuple[str, str]],
    record: RunRecord,
) -> list[dict[str, Any]]:
    """Links added by hand in the settings, for islands and the like."""
    added: list[dict[str, Any]] = []
    for first, second in settings.graph.manual_links:
        pair = tuple(sorted((first, second)))
        absent = [name for name in pair if name not in shapes]
        if absent:
            record.notice(
                f"{STAGE}: manual link {first}-{second} skipped: "
                f"{', '.join(absent)} not among the points the graph kept"
            )
            continue
        if pair in already:
            record.notice(
                f"{STAGE}: manual link {first}-{second} was already a computed "
                "neighbour"
            )
            continue
        record.notice(f"{STAGE}: added manual link {pair[0]}-{pair[1]}")
        added.append(
            {
                "point_a": pair[0],
                "point_b": pair[1],
                "shared_edge_metres": 0.0,
                "source": "manual",
            }
        )
    return added


def _handle_disconnected(
    settings: Settings,
    kept: gpd.GeoDataFrame,
    shapes: dict,
    neighbours: list[dict[str, Any]],
    parts: list[list[str]],
    record: RunRecord,
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """Apply the disconnected-parts setting (R4)."""
    action = settings.graph.disconnected_parts
    described = "; ".join(
        f"part {number}: {', '.join(part)}" for number, part in enumerate(parts, 1)
    )
    if action == "stop":
        raise DisconnectedGraphError(
            f"the neighbour graph falls into {len(parts)} parts ({described}). Add "
            "graph.manual_links joining them, set graph.disconnected_parts = "
            "'join_nearest' to link them by their closest pair, or "
            "'fixed_regions' to keep each part as a region of its own."
        )
    if action == "fixed_regions":
        record.notice(
            f"{STAGE}: keeping {len(parts)} disconnected parts as fixed regions "
            f"({described})"
        )
        return neighbours, parts

    centres = dict(zip(kept["point_id"], kept.geometry, strict=True))
    while len(parts) > 1:
        first, second, distance = _closest_pair(parts[0], parts[1:], centres)
        record.notice(
            f"{STAGE}: joined two parts by their closest pair {first}-{second}, "
            f"{round(distance)} metres apart"
        )
        neighbours.append(
            {
                "point_a": min(first, second),
                "point_b": max(first, second),
                "shared_edge_metres": 0.0,
                "source": "join_nearest",
            }
        )
        edges = [(row["point_a"], row["point_b"]) for row in neighbours]
        parts = geoutil.connected_parts(shapes, edges)
    neighbours.sort(key=lambda row: (row["point_a"], row["point_b"]))
    return neighbours, parts


def _closest_pair(
    part: list[str], others: list[list[str]], centres: dict
) -> tuple[str, str, float]:
    rest = [name for other in others for name in other]
    best = min(
        (
            (one, two, centres[one].distance(centres[two]))
            for one in part
            for two in rest
        ),
        key=lambda item: (item[2], item[0], item[1]),
    )
    return best


def _summarise(
    settings: Settings,
    cells: gpd.GeoDataFrame,
    kept: gpd.GeoDataFrame,
    neighbours: list[dict[str, Any]],
    parts: list[list[str]],
    dropped: list[str],
    outside: list[str],
    split: list[str],
) -> dict[str, Any]:
    counts: dict[str, int] = dict.fromkeys(kept["point_id"], 0)
    for row in neighbours:
        counts[row["point_a"]] += 1
        counts[row["point_b"]] += 1
    return {
        "neighbour_rule": settings.graph.neighbour_rule,
        "minimum_shared_edge_metres": settings.graph.minimum_shared_edge_metres,
        "points_read": int(len(cells)),
        "points_kept": int(len(kept)),
        "points_dropped_offshore": dropped,
        "points_outside_the_outline": outside,
        "cells_in_several_pieces": split,
        "neighbour_pairs": len(neighbours),
        "manual_links_used": [
            [row["point_a"], row["point_b"]]
            for row in neighbours
            if row["source"] != "computed"
        ],
        "neighbour_counts": {name: counts[name] for name in sorted(counts)},
        "fewest_neighbours": min(counts.values()) if counts else 0,
        "most_neighbours": max(counts.values()) if counts else 0,
        "connected_parts": parts,
        "connected": len(parts) == 1,
        "clipped_area_square_metres": round(float(kept["area_square_metres"].sum()), 2),
    }
