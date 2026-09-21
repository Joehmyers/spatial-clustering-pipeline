"""Geometry: the layers nest, and a layer set that does not stops the run."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from nca.errors import NestingError
from nca.geometry import run as run_geometry
from nca.outputs import RunDirectory, read_geojson, read_json
from nca.runrecord import RunRecord
from nca.settings import Settings

WORKING_CRS = "EPSG:27700"


@pytest.fixture(scope="module")
def checks(full_run) -> dict:
    return read_json(full_run.path("geometry", "checks"))


def test_the_layers_nest_both_ways(checks):
    assert checks["passed"] is True
    assert checks["failures"] == []
    for key in ("ra_in_pga", "pga_in_nca"):
        by_id = checks["nesting_by_id"][key]
        assert by_id["checked"] is True
        assert by_id["without_a_parent"] == []
        assert by_id["naming_a_parent_that_does_not_exist"] == []
        by_overlay = checks["nesting_by_overlay"][key]
        assert by_overlay["units_split_across_parents"] == []


def test_the_id_columns_and_the_overlay_agree(checks, full_run, fixture_settings):
    """Two checks that fail differently: a mislabelled unit against a shape
    that moved. On a sound layer set they must give the same answer."""
    for child, parent in (("ra", "pga"), ("pga", "nca")):
        overlay = checks["nesting_by_overlay"][f"{child}_in_{parent}"]["best_parent"]
        layer = read_geojson(full_run.path("geometry", f"{child}_layer"))
        column = fixture_settings.layer(child).parent_id_column
        by_id = dict(zip(layer[f"{child}_id"], layer[column].astype(str), strict=True))
        assert by_id == overlay
        assert len(overlay) == checks["counts"][child]


def test_no_slivers_are_reported_for_layers_that_line_up(checks):
    assert checks["sliver_areas"] == []


def test_the_island_makes_its_ra_pga_and_nca_two_part_shapes(checks):
    flagged = {
        (row["layer"], row["unit"]): row["parts"] for row in checks["multi_part_units"]
    }
    assert flagged == {
        ("ra", "RA-NE-1"): 2,
        ("pga", "PGA-NE"): 2,
        ("nca", "NCA-N"): 2,
    }


def test_todays_ncas_are_contiguous_on_the_pga_graph(checks):
    for name, body in checks["current_nca_contiguity"].items():
        assert body["contiguous"] is True, name
        assert len(body["parts"]) == 1


def test_the_pga_graph_is_the_four_cycle_the_fixture_draws(checks):
    pairs = {(row["pga_a"], row["pga_b"]) for row in checks["pga_neighbours"]}
    assert pairs == {
        ("PGA-NE", "PGA-NW"),
        ("PGA-NE", "PGA-SE"),
        ("PGA-NW", "PGA-SW"),
        ("PGA-SE", "PGA-SW"),
    }
    # The two quadrants that meet at a single corner are not neighbours.
    assert ("PGA-NE", "PGA-SW") not in pairs


def test_the_outline_is_the_dissolved_ra_layer(full_run, checks):
    outline = read_geojson(full_run.path("geometry", "outline"))
    ras = read_geojson(full_run.path("geometry", "ra_layer"))
    assert len(outline) == 1
    assert outline.geometry.iloc[0].area == pytest.approx(ras.geometry.union_all().area)
    assert checks["service_area"]["parts"] == 2  # the mainland and the island


def _write_layers(root, ras, pgas, ncas) -> None:
    for name, shapes, id_column, parent_column, parents in (
        ("ra", ras, "RA_ID", "PGA_ID", True),
        ("pga", pgas, "PGA_ID", "NCA_ID", True),
        ("nca", ncas, "NCA_ID", "", False),
    ):
        columns = {id_column: [key for key, _, _ in shapes]}
        if parents:
            columns[parent_column] = [parent for _, parent, _ in shapes]
        gpd.GeoDataFrame(
            columns, geometry=[shape for _, _, shape in shapes], crs=WORKING_CRS
        ).to_crs("EPSG:4326").to_file(root / f"{name}.geojson", driver="GeoJSON")


def _settings_for(root) -> Settings:
    (root / "settings.toml").write_text(
        'data_source = "fixture"\n'
        "[layers]\n"
        'nca = { path = "nca.geojson", id_column = "NCA_ID" }\n'
        'pga = { path = "pga.geojson", id_column = "PGA_ID", '
        'parent_id_column = "NCA_ID" }\n'
        'ra = { path = "ra.geojson", id_column = "RA_ID", '
        'parent_id_column = "PGA_ID" }\n'
        "[inputs]\n"
        'points = "points.csv"\nweather = "weather"\ndemand = "demand.csv"\n'
        "[cluster]\nnumber_of_regions = 2\ncuts_to_save = [2]\n",
        encoding="utf-8",
    )
    return Settings.load(root / "settings.toml")


def test_an_ra_that_straddles_two_pgas_stops_the_run(tmp_path):
    """The overlay check, doing the job the ID columns cannot: this RA names
    one parent but its shape lies half in another."""
    _write_layers(
        tmp_path,
        ras=[
            ("RA-1", "PGA-A", box(0, 0, 100, 100)),
            ("RA-2", "PGA-A", box(0, 100, 100, 200)),
            # Named PGA-B, but half of it lies in PGA-A's ground.
            ("RA-3", "PGA-B", box(50, 200, 150, 300)),
            ("RA-4", "PGA-B", box(100, 0, 200, 200)),
        ],
        pgas=[
            ("PGA-A", "NCA-1", box(0, 0, 100, 300)),
            ("PGA-B", "NCA-1", box(100, 0, 200, 300)),
        ],
        ncas=[("NCA-1", "", box(0, 0, 200, 300))],
    )
    settings = _settings_for(tmp_path)
    run_directory = RunDirectory(tmp_path / "out")
    record = RunRecord(settings=settings, run_directory=run_directory)
    with pytest.raises(NestingError) as raised:
        run_geometry(settings, run_directory, record)
    assert "RA-3" in str(raised.value)

    report = read_json(run_directory.path("geometry", "checks"))
    assert report["passed"] is False
    split = report["nesting_by_overlay"]["ra_in_pga"]["units_split_across_parents"]
    assert [row["unit"] for row in split] == ["RA-3"]
    assert report["sliver_areas"], "the layers disagree, so a sliver is expected"


def test_an_ra_naming_a_pga_that_does_not_exist_stops_the_run(tmp_path):
    _write_layers(
        tmp_path,
        ras=[
            ("RA-1", "PGA-A", box(0, 0, 100, 300)),
            ("RA-2", "PGA-GHOST", box(100, 0, 200, 300)),
        ],
        pgas=[
            ("PGA-A", "NCA-1", box(0, 0, 100, 300)),
            ("PGA-B", "NCA-1", box(100, 0, 200, 300)),
        ],
        ncas=[("NCA-1", "", box(0, 0, 200, 300))],
    )
    settings = _settings_for(tmp_path)
    run_directory = RunDirectory(tmp_path / "out")
    record = RunRecord(settings=settings, run_directory=run_directory)
    with pytest.raises(NestingError) as raised:
        run_geometry(settings, run_directory, record)
    assert "RA-2" in str(raised.value)
