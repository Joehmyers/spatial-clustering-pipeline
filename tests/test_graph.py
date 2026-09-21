"""Graph: the cells tile the outline, and the neighbour rule counts edges only."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from nca.geoutil import adjacency, connected_parts, line_length, shared_edge_metres
from nca.outputs import read_csv, read_geojson, read_json

# The cells are clipped to an outline rebuilt from coordinates rounded to
# seven decimal places of latitude and longitude, so areas agree to about one
# part in ten million, not exactly.
AREA_TOLERANCE = 1e-6

# Two cells that do not overlap can still report a sliver of overlap from
# floating-point arithmetic. A square metre against tens of square kilometres.
OVERLAP_TOLERANCE_SQUARE_METRES = 1.0


@pytest.fixture(scope="module")
def cells(full_run) -> gpd.GeoDataFrame:
    return read_geojson(full_run.path("graph", "cells"))


@pytest.fixture(scope="module")
def summary(full_run) -> dict:
    return read_json(full_run.path("graph", "summary"))


def test_the_cells_tile_the_outline(cells, full_run):
    outline = read_geojson(full_run.path("geometry", "outline")).geometry.iloc[0]
    covered = float(cells.geometry.area.sum())
    assert covered == pytest.approx(outline.area, rel=AREA_TOLERANCE)


def test_no_two_cells_overlap(cells):
    shapes = list(cells.geometry)
    for first in range(len(shapes)):
        for second in range(first + 1, len(shapes)):
            overlap = shapes[first].intersection(shapes[second]).area
            assert overlap < OVERLAP_TOLERANCE_SQUARE_METRES


def test_each_cell_holds_its_own_point(cells, fixture_settings):
    points = gpd.GeoDataFrame(
        {"point_id": []}, geometry=[], crs=fixture_settings.coordinates.working_crs
    )
    source = read_csv(fixture_settings.resolve(fixture_settings.inputs.points))
    points = gpd.GeoDataFrame(
        {"point_id": source["point_id"].astype(str)},
        geometry=gpd.points_from_xy(source["longitude"], source["latitude"]),
        crs=fixture_settings.coordinates.input_crs,
    ).to_crs(fixture_settings.coordinates.working_crs)
    located = dict(zip(points["point_id"], points.geometry, strict=True))
    for _, row in cells.iterrows():
        assert row.geometry.covers(located[row["point_id"]]), (
            f"the cell saved for {row['point_id']} does not contain that point, so "
            "cells were matched to points by output order rather than by location"
        )


def test_the_offshore_point_is_dropped(cells, summary):
    assert summary["points_dropped_offshore"] == ["P17"]
    assert "P17" not in set(cells["point_id"])
    assert summary["points_read"] == 18
    assert summary["points_kept"] == 17


def test_the_island_joins_by_its_manual_link(summary):
    assert summary["manual_links_used"] == [["P12", "P18"]]
    assert summary["neighbour_counts"]["P18"] == 1
    assert summary["connected"] is True
    assert len(summary["connected_parts"]) == 1


def test_the_grid_gives_the_neighbour_counts_a_four_by_four_lattice_has(
    summary, full_run
):
    edges = read_csv(full_run.path("graph", "neighbours"))
    computed = edges.loc[edges["source"] == "computed"]
    counts: dict[str, int] = dict.fromkeys(summary["neighbour_counts"], 0)
    for _, edge in computed.iterrows():
        counts[edge["point_a"]] += 1
        counts[edge["point_b"]] += 1
    # A 4 by 4 lattice: four corners with two neighbours, eight edge points
    # with three, four inside points with four. The island has none of its own.
    assert sorted(counts.values()) == [0] + [2] * 4 + [3] * 8 + [4] * 4
    assert counts["P18"] == 0
    # 24 lattice edges plus the one manual link to the island.
    assert summary["neighbour_pairs"] == 25
    assert len(computed) == 24


def test_neighbours_carry_the_length_of_the_edge_they_share(full_run):
    edges = read_csv(full_run.path("graph", "neighbours"))
    computed = edges.loc[edges["source"] == "computed"]
    assert (computed["shared_edge_metres"] > 1.0).all()
    assert computed["shared_edge_metres"].min() == pytest.approx(25_000, rel=1e-3)


def test_a_shared_corner_is_not_a_shared_edge():
    """The rule the fixture's grid depends on, tested on its own."""
    lower_left = box(0, 0, 10, 10)
    upper_right = box(10, 10, 20, 20)
    side_by_side = box(10, 0, 20, 10)
    assert shared_edge_metres(lower_left, upper_right) == 0.0
    assert shared_edge_metres(lower_left, side_by_side) == pytest.approx(10.0)

    shapes = {"a": lower_left, "b": upper_right, "c": side_by_side}
    rook = adjacency(shapes, rule="rook", minimum_metres=1.0)
    assert set(rook) == {("a", "c"), ("b", "c")}
    queen = adjacency(shapes, rule="queen")
    assert set(queen) == {("a", "b"), ("a", "c"), ("b", "c")}


def test_an_overlap_is_not_counted_as_a_shared_edge():
    """Taking the length of an overlapping intersection would return a
    perimeter and call two overlapping shapes long-standing neighbours."""
    assert line_length(box(0, 0, 10, 10).intersection(box(5, 5, 15, 15))) == 0.0


def test_the_run_stops_when_the_island_has_no_manual_link(tmp_path):
    """The default for a graph in pieces is to stop: some Ward
    implementations quietly invent links to finish a tree over one (R4)."""
    from nca.errors import DisconnectedGraphError
    from nca.graph import run as run_graph
    from nca.outputs import RunDirectory
    from nca.pipeline import run_stage
    from nca.runrecord import RunRecord
    from nca.settings import Settings

    from .helpers import copy_fixture

    settings_file = copy_fixture(tmp_path / "fixture")
    text = settings_file.read_text(encoding="utf-8")
    settings_file.write_text(
        text.replace('manual_links = [["P18", "P12"]]', "manual_links = []"),
        encoding="utf-8",
    )
    settings = Settings.load(settings_file)
    run_directory = RunDirectory(tmp_path / "out")
    record = RunRecord(settings=settings, run_directory=run_directory)
    run_stage("geometry", settings, run_directory, record)

    with pytest.raises(DisconnectedGraphError) as raised:
        run_graph(settings, run_directory, record)
    assert "P18" in str(raised.value)
    assert "manual_links" in str(raised.value)


def test_joining_the_nearest_pair_reconnects_the_graph_and_records_it(tmp_path):
    from nca.outputs import RunDirectory, read_json
    from nca.pipeline import run_stage
    from nca.runrecord import RunRecord
    from nca.settings import Settings

    from .helpers import copy_fixture

    settings_file = copy_fixture(tmp_path / "fixture")
    text = settings_file.read_text(encoding="utf-8")
    settings_file.write_text(
        text.replace('manual_links = [["P18", "P12"]]', "manual_links = []").replace(
            'disconnected_parts = "stop"', 'disconnected_parts = "join_nearest"'
        ),
        encoding="utf-8",
    )
    settings = Settings.load(settings_file)
    run_directory = RunDirectory(tmp_path / "out")
    record = RunRecord(settings=settings, run_directory=run_directory)
    run_stage("geometry", settings, run_directory, record)
    run_stage("graph", settings, run_directory, record)

    summary = read_json(run_directory.path("graph", "summary"))
    assert summary["connected"] is True
    assert summary["manual_links_used"] == [["P12", "P18"]]
    assert any("closest pair" in notice for notice in record.notices)


def test_connected_parts_puts_the_largest_first():
    parts = connected_parts(
        ["a", "b", "c", "d", "e"], [("a", "b"), ("b", "c"), ("d", "e")]
    )
    assert parts == [["a", "b", "c"], ["d", "e"]]
