"""Build the test fixture set from fixed formulas (R17).

Nothing here is random. Every weather value comes from a sum of sine waves of
fixed period, so regenerating the set reproduces it byte for byte and a test
can check the committed files still match the formulas.

The made-up map is a 4 by 4 grid of weather points at 25 km spacing over a
100 km square of land, plus two points off it: one offshore, whose Voronoi
cell clips away to nothing, and one on an island, which the graph reaches only
through a manual link. The land splits into eight Rostering Areas (RAs), which
group into four Patrol Group Areas (PGAs), which group into two "current"
National Climate Areas (NCAs) running north and south.

The weather splits west from east, so the planted answer cuts across today's
north and south map. A pipeline that works finds west and east.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, box
from shapely.ops import unary_union

WORKING_CRS = "EPSG:27700"  # British National Grid: eastings and northings in metres
OUTPUT_CRS = "EPSG:4326"  # WGS 84: what GeoJSON and the DTN point list use

# -- the made-up map --------------------------------------------------------

SPACING_METRES = 25_000
GRID_EASTINGS = (400_000.0, 425_000.0, 450_000.0, 475_000.0)
GRID_NORTHINGS = (300_000.0, 325_000.0, 350_000.0, 375_000.0)
HALF = SPACING_METRES / 2

# The land: the grid plus half a spacing of margin, so the 16 cells tile it.
LAND_WEST = GRID_EASTINGS[0] - HALF
LAND_EAST = GRID_EASTINGS[-1] + HALF
LAND_SOUTH = GRID_NORTHINGS[0] - HALF
LAND_NORTH = GRID_NORTHINGS[-1] + HALF
MID_EAST_WEST = (LAND_WEST + LAND_EAST) / 2
MID_NORTH_SOUTH = (LAND_SOUTH + LAND_NORTH) / 2

# The island: a 10 km square far enough east that no mainland cell reaches it.
ISLAND = (555_000.0, 335_000.0, 565_000.0, 345_000.0)
ISLAND_POINT = (560_000.0, 340_000.0)

# The offshore point: far enough south-east that its cell clips away to
# nothing. Every land location sits within 17.7 km of a grid point and at
# least 86 km from here, so this point wins no ground the outline keeps.
OFFSHORE_POINT = (560_000.0, 240_000.0)

OFFSHORE_ID = "P17"
ISLAND_ID = "P18"
MANUAL_LINK = (ISLAND_ID, "P12")  # the island's nearest point on the east edge

# -- the planted weather ----------------------------------------------------

FIRST_DATE = dt.date(2023, 9, 1)
LAST_DATE = dt.date(2025, 8, 31)

# A whole year is 365.25 days; 138 puts the warmest day in mid-July.
SEASON_PERIOD = 365.25
SEASON_OFFSET = 138
NATIONAL_PERIOD = 97  # the swing every point feels on the same day
REGIME_PERIOD = 53  # the west-against-east swing, the answer the tree must find
POINT_PERIOD = 29  # each point's own small wobble
POINT_PHASE_STEP = 7  # days of phase between one point and the next


@dataclass(frozen=True)
class VariableShape:
    """The fixed formula for one weather variable, in its own units."""

    base: float
    seasonal: float
    national: float
    regime: float
    point: float
    floor: float | None = None  # clamp below this, for rain


# Amplitudes chosen so the regime swing is six to seven times each point's own
# wobble: large enough that west and east separate cleanly, small enough that
# the points inside one half are not identical.
VARIABLE_SHAPES = {
    "tmin": VariableShape(base=5.0, seasonal=6.0, national=1.6, regime=2.4, point=0.35),
    "tmax": VariableShape(
        base=13.0, seasonal=8.0, national=2.0, regime=3.0, point=0.45
    ),
    "rain": VariableShape(
        base=3.0, seasonal=-1.0, national=0.8, regime=1.1, point=0.18, floor=0.0
    ),
    "wind": VariableShape(
        base=9.0, seasonal=-2.5, national=1.8, regime=2.2, point=0.30
    ),
}

# Deliberate awkward cases the tests check (R17).
ZERO_RAIN_SPELL = (dt.date(2024, 7, 1), dt.date(2024, 7, 14))
MISSING_POINT = "P07"
MISSING_VARIABLE = "tmax"
MISSING_DATE = dt.date(2024, 3, 15)

# Demand: a daily percentage deviation per PGA that follows the same west and
# east swing as the weather, so the planted map should explain it and today's
# north and south map should not.
DEMAND_REGIME_AMPLITUDE = 4.0
DEMAND_OWN_AMPLITUDE = 0.6
DEMAND_OWN_PERIOD = 37
DEMAND_PHASE_STEP = 11

PGA_NAMES = ("PGA-NW", "PGA-NE", "PGA-SW", "PGA-SE")
WEST_PGAS = ("PGA-NW", "PGA-SW")


def grid_points() -> list[tuple[str, float, float]]:
    """The 16 grid points, then the offshore point, then the island point."""
    points: list[tuple[str, float, float]] = []
    number = 1
    for northing in GRID_NORTHINGS:
        for easting in GRID_EASTINGS:
            points.append((f"P{number:02d}", easting, northing))
            number += 1
    points.append((OFFSHORE_ID, *OFFSHORE_POINT))
    points.append((ISLAND_ID, *ISLAND_POINT))
    return points


def is_east(point_id: str, easting: float) -> bool:
    """East of the planted weather boundary. The island counts as east."""
    if point_id == ISLAND_ID:
        return True
    return easting > MID_EAST_WEST


def dates() -> list[dt.date]:
    span = (LAST_DATE - FIRST_DATE).days
    return [FIRST_DATE + dt.timedelta(days=day) for day in range(span + 1)]


def weather_value(shape: VariableShape, day: int, east: bool, index: int) -> float:
    """One weather value: season, national swing, regime swing, own wobble."""
    value = (
        shape.base
        + shape.seasonal * math.sin(2 * math.pi * (day + SEASON_OFFSET) / SEASON_PERIOD)
        + shape.national * math.sin(2 * math.pi * day / NATIONAL_PERIOD)
        + shape.regime
        * (1.0 if east else -1.0)
        * math.sin(2 * math.pi * day / REGIME_PERIOD)
        + shape.point
        * math.sin(2 * math.pi * (day + POINT_PHASE_STEP * index) / POINT_PERIOD)
    )
    if shape.floor is not None:
        value = max(shape.floor, value)
    return value


def weather_frame(variable: str) -> pd.DataFrame:
    """One variable: a row per day, a column per point, to one decimal place."""
    shape = VARIABLE_SHAPES[variable]
    points = grid_points()
    all_dates = dates()
    columns: dict[str, list[float | None]] = {}
    for index, (point_id, easting, _) in enumerate(points):
        east = is_east(point_id, easting)
        values: list[float | None] = []
        for day, date in enumerate(all_dates):
            value = weather_value(shape, day, east, index)
            if variable == "rain" and ZERO_RAIN_SPELL[0] <= date <= ZERO_RAIN_SPELL[1]:
                value = 0.0
            values.append(round(value, 1))
        columns[point_id] = values
    frame = pd.DataFrame(columns, index=pd.Index(all_dates, name="date"))
    if variable == MISSING_VARIABLE:
        frame.loc[MISSING_DATE, MISSING_POINT] = None
    return frame.reset_index()


def demand_frame() -> pd.DataFrame:
    """Daily percentage deviation per PGA, following the west and east swing."""
    all_dates = dates()
    columns: dict[str, list[float]] = {}
    for index, name in enumerate(PGA_NAMES):
        sign = -1.0 if name in WEST_PGAS else 1.0
        columns[name] = [
            round(
                sign
                * DEMAND_REGIME_AMPLITUDE
                * math.sin(2 * math.pi * day / REGIME_PERIOD)
                + DEMAND_OWN_AMPLITUDE
                * math.sin(
                    2 * math.pi * (day + DEMAND_PHASE_STEP * index) / DEMAND_OWN_PERIOD
                ),
                1,
            )
            for day, _ in enumerate(all_dates)
        ]
    frame = pd.DataFrame(columns, index=pd.Index(all_dates, name="date"))
    return frame.reset_index()


def ra_shapes() -> dict[str, MultiPolygon]:
    """Eight RAs: each quadrant of the land split into a north and south band."""
    quarter = (LAND_NORTH - LAND_SOUTH) / 4
    band = [LAND_SOUTH + quarter * step for step in range(5)]
    west, middle, east = LAND_WEST, MID_EAST_WEST, LAND_EAST
    boxes = {
        "RA-SW-1": box(west, band[0], middle, band[1]),
        "RA-SW-2": box(west, band[1], middle, band[2]),
        "RA-SE-1": box(middle, band[0], east, band[1]),
        "RA-SE-2": box(middle, band[1], east, band[2]),
        "RA-NW-1": box(west, band[2], middle, band[3]),
        "RA-NW-2": box(west, band[3], middle, band[4]),
        "RA-NE-1": box(middle, band[2], east, band[3]),
        "RA-NE-2": box(middle, band[3], east, band[4]),
    }
    shapes = {name: MultiPolygon([shape]) for name, shape in boxes.items()}
    # The island joins the RA covering the same band on the mainland, which
    # makes that RA (and its PGA) a two-part shape on purpose: the geometry
    # stage must flag it and the graph stage must cope with it.
    shapes["RA-NE-1"] = MultiPolygon([*shapes["RA-NE-1"].geoms, box(*ISLAND)])
    return dict(sorted(shapes.items()))


def ra_to_pga(ra_id: str) -> str:
    """RA-NE-1 belongs to PGA-NE: the RA's name carries its quadrant."""
    return f"PGA-{ra_id.split('-')[1]}"


def pga_to_nca(pga_id: str) -> str:
    """Today's map splits north from south, cutting across the planted regimes."""
    return "NCA-N" if pga_id.split("-")[1].startswith("N") else "NCA-S"


def _dissolve(shapes: dict[str, MultiPolygon], group: dict[str, str]) -> dict:
    merged: dict[str, list] = {}
    for key, shape in shapes.items():
        merged.setdefault(group[key], []).append(shape)
    return {
        name: _as_multipolygon(unary_union(parts))
        for name, parts in sorted(merged.items())
    }


def _as_multipolygon(shape) -> MultiPolygon:
    return shape if isinstance(shape, MultiPolygon) else MultiPolygon([shape])


def expected_labels() -> pd.DataFrame:
    """The planted answer at k = 2: west against east, named by smallest ID."""
    rows = []
    for point_id, easting, _ in grid_points():
        if point_id == OFFSHORE_ID:
            continue  # the graph drops it, so it never reaches the tree
        cluster = "P03" if is_east(point_id, easting) else "P01"
        rows.append({"point_id": point_id, "cluster": cluster})
    return pd.DataFrame(rows).sort_values("point_id").reset_index(drop=True)


def write(out_directory: str | Path) -> list[Path]:
    """Write the whole fixture set. Returns the files written, in order."""
    out = Path(out_directory)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    points = grid_points()
    point_frame = gpd.GeoDataFrame(
        {"point_id": [point_id for point_id, _, _ in points]},
        geometry=gpd.points_from_xy(
            [easting for _, easting, _ in points],
            [northing for _, _, northing in points],
        ),
        crs=WORKING_CRS,
    ).to_crs(OUTPUT_CRS)
    point_csv = pd.DataFrame(
        {
            "point_id": point_frame["point_id"],
            "latitude": point_frame.geometry.y.round(7),
            "longitude": point_frame.geometry.x.round(7),
        }
    )
    written.append(_write_csv(point_csv, out / "points.csv"))

    ras = ra_shapes()
    pgas = _dissolve(ras, {name: ra_to_pga(name) for name in ras})
    ncas = _dissolve(pgas, {name: pga_to_nca(name) for name in pgas})
    parents = {
        "ra": ("RA_ID", "PGA_ID", ra_to_pga),
        "pga": ("PGA_ID", "NCA_ID", pga_to_nca),
        "nca": ("NCA_ID", "", None),
    }
    for name, shapes in (("ra", ras), ("pga", pgas), ("nca", ncas)):
        id_column, parent_column, parent_of = parents[name]
        columns = {id_column: list(shapes)}
        if parent_of is not None:
            columns[parent_column] = [parent_of(key) for key in shapes]
        frame = gpd.GeoDataFrame(
            columns,
            geometry=list(shapes.values()),
            crs=WORKING_CRS,
        ).to_crs(OUTPUT_CRS)
        path = out / f"{name}.geojson"
        frame.to_file(path, driver="GeoJSON", coordinate_precision=7)
        written.append(path)

    weather_directory = out / "weather"
    weather_directory.mkdir(exist_ok=True)
    for variable in VARIABLE_SHAPES:
        written.append(
            _write_csv(
                weather_frame(variable),
                weather_directory / f"weather-{variable}.csv",
                decimals=1,
            )
        )
    written.append(_write_csv(demand_frame(), out / "demand.csv", decimals=1))
    written.append(
        _write_csv(expected_labels(), out / "cluster-labels-k2.expected.csv")
    )
    return written


def _write_csv(frame: pd.DataFrame, path: Path, decimals: int | None = None) -> Path:
    """Write a CSV the same way every time: ISO dates, dots, Unix line endings."""
    out = frame.copy()
    for column in out.columns:
        if out[column].map(lambda value: isinstance(value, dt.date)).all():
            out[column] = [value.isoformat() for value in out[column]]
    out.to_csv(
        path,
        index=False,
        lineterminator="\n",
        float_format=None if decimals is None else f"%.{decimals}f",
    )
    return path
