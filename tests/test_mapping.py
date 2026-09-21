"""Mapping: each PGA gets one NCA, the NCAs are contiguous, moves are recorded."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from nca.geoutil import is_connected
from nca.mapping import _repair, _stranded
from nca.outputs import RunDirectory, read_csv, read_json
from nca.runrecord import RunRecord


@pytest.fixture(scope="module")
def assignments(full_run) -> pd.DataFrame:
    return read_csv(full_run.path("mapping", "assignments"))


@pytest.fixture(scope="module")
def summary(full_run) -> dict:
    return read_json(full_run.path("mapping", "summary"))


@pytest.fixture(scope="module")
def pga_edges(full_run) -> list[tuple[str, str]]:
    checks = read_json(full_run.path("geometry", "checks"))
    return [(row["pga_a"], row["pga_b"]) for row in checks["pga_neighbours"]]


def test_each_pga_gets_exactly_one_nca(assignments, fixture_settings):
    for k in fixture_settings.cuts:
        pgas = assignments.loc[
            (assignments["k"] == k) & (assignments["unit_type"] == "pga")
        ]
        assert len(pgas) == pgas["unit_id"].nunique()
        assert pgas["assigned_nca"].notna().all()


def test_each_ra_follows_its_own_pga(assignments, fixture_settings):
    for k in fixture_settings.cuts:
        at_k = assignments.loc[assignments["k"] == k]
        pga_nca = dict(
            zip(
                at_k.loc[at_k["unit_type"] == "pga", "unit_id"],
                at_k.loc[at_k["unit_type"] == "pga", "assigned_nca"],
                strict=True,
            )
        )
        ras = at_k.loc[at_k["unit_type"] == "ra"]
        for _, row in ras.iterrows():
            assert row["assigned_nca"] == pga_nca[row["pga_id"]]


def test_the_mapped_ncas_are_contiguous(summary, pga_edges, fixture_settings):
    for k in fixture_settings.cuts:
        cut = summary["cuts"][str(k)]
        assert cut["contiguous"] is True
        for name, members in cut["new_ncas"].items():
            assert is_connected(members, pga_edges), f"{name} at k = {k}"


def test_the_straddle_score_is_one_minus_the_majority_share(assignments):
    assert (
        (assignments["straddle_score"] + assignments["majority_share"] - 1.0)
        .abs()
        .max()
    ) < 1e-9
    assert (assignments["majority_share"] > 0).all()
    assert (assignments["straddle_score"] >= 0).all()


def test_at_the_headline_cut_the_map_is_west_against_east(summary):
    cut = summary["cuts"]["2"]
    assert cut["new_ncas"] == {
        "NCA-P01": ["PGA-NW", "PGA-SW"],
        "NCA-P03": ["PGA-NE", "PGA-SE"],
    }
    assert cut["highest_straddle_score"] == 0.0
    assert cut["clusters_winning_no_pga"] == []


def test_a_cut_that_splits_a_pga_gives_it_a_straddle_score(assignments):
    """At k = 3 the third cluster cuts through PGAs, which is what the
    straddle score is for."""
    at_three = assignments.loc[
        (assignments["k"] == 3) & (assignments["unit_type"] == "pga")
    ]
    assert float(at_three["straddle_score"].max()) > 0.4


def test_every_move_is_recorded(full_run, summary, fixture_settings):
    moves = read_csv(full_run.path("mapping", "moves"))
    assert list(moves.columns) == [
        "k",
        "pga_id",
        "from_nca",
        "to_nca",
        "shared_boundary_metres",
        "reason",
    ]
    recorded = sum(summary["cuts"][str(k)]["moves"] for k in fixture_settings.cuts)
    assert len(moves) == recorded


# -- the repair path, on a case built to need it ----------------------------


def _record(tmp_path, settings) -> RunRecord:
    return RunRecord(settings=settings, run_directory=RunDirectory(tmp_path))


def test_a_stranded_pga_moves_to_the_neighbour_it_shares_most_boundary_with(
    tmp_path, fixture_settings
):
    """Three PGAs in a line, with the two ends given one NCA and the middle
    the other. The far end is cut off from its own NCA and must move."""
    edges = {("A", "B"): 1000.0, ("B", "C"): 4000.0}
    assigned = {"A": "X", "B": "Y", "C": "X"}
    assert _stranded(assigned, edges) == ["C"]

    repaired, moves = _repair(
        fixture_settings,
        assigned,
        edges,
        k=2,
        record=_record(tmp_path, fixture_settings),
    )
    assert repaired == {"A": "X", "B": "Y", "C": "Y"}
    assert _stranded(repaired, edges) == []
    assert len(moves) == 1
    assert moves[0]["pga_id"] == "C"
    assert moves[0]["from_nca"] == "X"
    assert moves[0]["to_nca"] == "Y"
    assert moves[0]["shared_boundary_metres"] == 4000.0
    assert moves[0]["k"] == 2


def test_repair_leaves_a_map_alone_when_nothing_is_stranded(tmp_path, fixture_settings):
    edges = {("A", "B"): 1000.0, ("B", "C"): 4000.0}
    assigned = {"A": "X", "B": "X", "C": "Y"}
    repaired, moves = _repair(
        fixture_settings,
        assigned,
        edges,
        k=2,
        record=_record(tmp_path, fixture_settings),
    )
    assert repaired == assigned
    assert moves == []


def test_repair_off_leaves_the_map_stranded_and_moves_nothing(
    tmp_path, fixture_settings
):
    settings = replace(
        fixture_settings,
        mapping=replace(fixture_settings.mapping, repair_stranded_pgas=False),
    )
    edges = {("A", "B"): 1000.0, ("B", "C"): 4000.0}
    assigned = {"A": "X", "B": "Y", "C": "X"}
    repaired, moves = _repair(
        settings, assigned, edges, k=2, record=_record(tmp_path, settings)
    )
    assert repaired == assigned
    assert moves == []
