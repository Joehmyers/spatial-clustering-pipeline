"""The fixture set: still what its formulas produce, and still a fixture.

R17 says the set is written from fixed formulas, never fetched live, so every
run replays exactly. These tests hold that: regenerating the set must give the
committed files back byte for byte.
"""

from __future__ import annotations

import datetime as dt
import filecmp

import pandas as pd
import pytest

from nca import fixture

from .helpers import FIXTURE_DIRECTORY

MAXIMUM_FIXTURE_BYTES = 100 * 1024
EXPECTED_FILES = (
    "points.csv",
    "ra.geojson",
    "pga.geojson",
    "nca.geojson",
    "weather/weather-tmin.csv",
    "weather/weather-tmax.csv",
    "weather/weather-rain.csv",
    "weather/weather-wind.csv",
    "demand.csv",
    "cluster-labels-k2.expected.csv",
    "settings.toml",
    "README.md",
)


def test_regenerating_the_fixture_gives_the_committed_files_back(tmp_path):
    written = fixture.write(tmp_path)
    for path in written:
        relative = path.relative_to(tmp_path)
        assert filecmp.cmp(path, FIXTURE_DIRECTORY / relative, shallow=False), (
            f"{relative} no longer matches its formula. Regenerate it with "
            "'nca fixture --out tests/fixtures/nca-regionalisation' and review "
            "the change."
        )


def test_every_fixture_file_is_present_and_small_enough():
    for name in EXPECTED_FILES:
        path = FIXTURE_DIRECTORY / name
        assert path.is_file(), f"{name} is missing"
        assert path.stat().st_size < MAXIMUM_FIXTURE_BYTES, (
            f"{name} is over 100 KB, so it is data rather than a fixture"
        )


def test_the_weather_covers_two_years_and_holds_the_awkward_days():
    frame = pd.read_csv(FIXTURE_DIRECTORY / "weather" / "weather-tmax.csv")
    assert frame["date"].iloc[0] == "2023-09-01"
    assert frame["date"].iloc[-1] == "2025-08-31"
    assert len(frame) == 731
    assert "2024-02-29" in set(frame["date"]), "the leap day is missing"

    missing = frame.loc[frame["date"] == "2024-03-15", "P07"]
    assert missing.isna().all(), "the deliberate gap at P07 has been filled in"
    assert frame.drop(columns=["date"]).isna().sum().sum() == 1


def test_the_rain_holds_a_spell_of_zeros():
    frame = pd.read_csv(FIXTURE_DIRECTORY / "weather" / "weather-rain.csv")
    spell = frame.loc[(frame["date"] >= "2024-07-01") & (frame["date"] <= "2024-07-14")]
    assert len(spell) == 14
    assert (spell.drop(columns=["date"]) == 0.0).all().all()
    assert (frame.drop(columns=["date"]) >= 0).all().all()


def test_the_points_are_stored_as_latitude_and_longitude():
    frame = pd.read_csv(FIXTURE_DIRECTORY / "points.csv")
    assert list(frame.columns) == ["point_id", "latitude", "longitude"]
    assert len(frame) == 18  # 16 on the grid, one offshore, one on the island
    assert frame["latitude"].between(49.0, 61.0).all()
    assert frame["longitude"].between(-9.0, 2.0).all()


def test_the_planted_regimes_split_west_from_east():
    """On a day when the regime swing is at its strongest, the two halves must
    be far apart and each half close together."""
    frame = pd.read_csv(FIXTURE_DIRECTORY / "weather" / "weather-tmax.csv")
    # The regime swing peaks a quarter of its period in, and repeats.
    day = round(fixture.REGIME_PERIOD / 4)
    assert (
        frame["date"].iloc[day]
        == (fixture.FIRST_DATE + dt.timedelta(days=day)).isoformat()
    )
    strongest = frame.iloc[day]
    west, east = [], []
    for point_id, easting, _ in fixture.grid_points():
        if point_id == fixture.OFFSHORE_ID:
            continue
        (east if fixture.is_east(point_id, easting) else west).append(
            float(strongest[point_id])
        )
    # Sign convention: the east half carries +1 times the regime swing, so at
    # its peak every eastern point sits above every western one.
    assert min(east) - max(west) > 3.0
    assert max(west) - min(west) < 1.5
    assert max(east) - min(east) < 1.5


def test_the_expected_labels_are_the_planted_halves():
    labels = pd.read_csv(FIXTURE_DIRECTORY / "cluster-labels-k2.expected.csv")
    assert list(labels.columns) == ["point_id", "cluster"]
    assert len(labels) == 17  # the offshore point never reaches the tree
    assert set(labels["cluster"]) == {"P01", "P03"}
    assert labels.loc[labels["point_id"] == "P18", "cluster"].iloc[0] == "P03"
    assert (labels["cluster"] == "P01").sum() == 8
    assert (labels["cluster"] == "P03").sum() == 9


def test_the_demand_follows_the_same_west_and_east_swing():
    frame = pd.read_csv(FIXTURE_DIRECTORY / "demand.csv")
    assert set(frame.columns) == {"date", "PGA-NW", "PGA-NE", "PGA-SW", "PGA-SE"}
    assert frame["PGA-NW"].corr(frame["PGA-SW"]) > 0.9
    assert frame["PGA-NE"].corr(frame["PGA-SE"]) > 0.9
    assert frame["PGA-NW"].corr(frame["PGA-NE"]) < -0.9


@pytest.mark.parametrize("name", EXPECTED_FILES)
def test_no_fixture_file_carries_an_absolute_path(name):
    text = (FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")
    assert "/home/" not in text
    assert "C:\\" not in text
