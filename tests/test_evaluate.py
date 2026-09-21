"""Evaluate: the statistics are right, and the new map beats today's."""

from __future__ import annotations

import numpy as np
import pytest

from nca.evaluate import eta_squared, random_contiguous_partition
from nca.geoutil import is_connected
from nca.outputs import read_csv, read_json

# A hand-worked case, computed by hand and checked here.
#
#   group A: 1, 3      group B: 6, 10      grand mean: 5
#   total sum of squares:   16 + 4 + 1 + 25 = 46
#   group means: 2 and 8
#   between-group sum of squares: 2*(2-5)^2 + 2*(8-5)^2 = 18 + 18 = 36
#   eta-squared: 36 / 46
HAND_WORKED_VALUES = np.array([1.0, 3.0, 6.0, 10.0])
HAND_WORKED_GROUPS = np.array(["A", "A", "B", "B"])
HAND_WORKED_ANSWER = 36.0 / 46.0


@pytest.fixture(scope="module")
def metrics(full_run) -> dict:
    return read_json(full_run.path("evaluate", "metrics"))


def test_eta_squared_matches_the_hand_worked_case():
    assert eta_squared(HAND_WORKED_VALUES, HAND_WORKED_GROUPS) == pytest.approx(
        HAND_WORKED_ANSWER
    )


def test_eta_squared_is_one_when_every_unit_matches_its_group_exactly():
    values = np.array([2.0, 2.0, 8.0, 8.0])
    groups = np.array(["A", "A", "B", "B"])
    assert eta_squared(values, groups) == pytest.approx(1.0)


def test_eta_squared_is_zero_when_the_groups_have_the_same_mean():
    values = np.array([1.0, 3.0, 3.0, 1.0])
    groups = np.array(["A", "A", "B", "B"])
    assert eta_squared(values, groups) == pytest.approx(0.0)


def test_eta_squared_is_not_a_number_when_nothing_varies():
    values = np.array([4.0, 4.0, 4.0, 4.0])
    assert np.isnan(eta_squared(values, np.array(["A", "A", "B", "B"])))


def test_random_partitions_are_contiguous_and_hold_k_regions():
    nodes = [f"N{index:02d}" for index in range(12)]
    edges = [(nodes[index], nodes[index + 1]) for index in range(11)]
    edges += [(nodes[index], nodes[index + 4]) for index in range(8)]
    generator = np.random.default_rng(3)
    for _ in range(100):
        for k in (2, 3, 5):
            partition = random_contiguous_partition(nodes, edges, k, generator)
            assert set(partition) == set(nodes)
            assert len(set(partition.values())) == k
            for region in set(partition.values()):
                members = [name for name in nodes if partition[name] == region]
                assert is_connected(members, edges)


def test_the_same_seed_gives_the_same_random_partitions():
    nodes = [f"N{index}" for index in range(8)]
    edges = [(nodes[index], nodes[index + 1]) for index in range(7)]
    first = [
        random_contiguous_partition(nodes, edges, 3, np.random.default_rng(11))
        for _ in range(5)
    ]
    second = [
        random_contiguous_partition(nodes, edges, 3, np.random.default_rng(11))
        for _ in range(5)
    ]
    assert first == second


def test_every_random_map_in_the_run_is_contiguous_with_k_regions(
    full_run, metrics, fixture_settings
):
    benchmark = read_csv(full_run.path("evaluate", "benchmark"))
    assert len(benchmark) == fixture_settings.evaluate.random_partitions
    assert benchmark["contiguous"].all()
    assert (benchmark["regions"] == fixture_settings.cluster.number_of_regions).all()
    assert metrics["benchmark"]["all_contiguous"] is True
    assert metrics["benchmark"]["seed"] == fixture_settings.evaluate.seed


def test_the_new_map_beats_the_fixtures_current_ncas_on_weather_and_demand(metrics):
    beats = metrics["new_map_beats_current"]
    assert beats["weather"]["new_is_higher"] is True
    assert beats["demand"]["new_is_higher"] is True
    # The fixture plants a west and east split that today's north and south
    # map cuts straight across, so the gap should be large, not marginal.
    assert beats["weather"]["new"] > 0.9
    assert beats["weather"]["current"] < 0.1
    assert beats["demand"]["new"] > 0.8
    assert beats["demand"]["current"] < 0.1


def test_the_new_map_beats_the_random_maps_too(metrics):
    placings = metrics["benchmark"]["placings"]
    assert placings["new"]["weather_percentile"] == 100.0
    assert placings["new"]["demand_percentile"] == 100.0
    assert (
        placings["new"]["weather_eta_squared"]
        > placings["current"]["weather_eta_squared"]
    )


def test_the_ceiling_bounds_what_any_map_of_whole_pgas_could_reach(metrics):
    ceiling = metrics["ceiling"]["weather_mean"]
    assert 0.0 <= ceiling["between_pga_share"] <= 1.0
    assert ceiling["between_pga_share"] + ceiling["within_pga_share"] == pytest.approx(
        1.0
    )
    for name in ("tmin", "tmax", "rain", "wind"):
        parts = metrics["ceiling"][name]
        assert parts["between_pga_share"] + parts["within_pga_share"] == pytest.approx(
            1.0
        )


def test_the_tree_is_judged_before_any_mapping(metrics):
    explained = metrics["point_variance_explained"]
    assert 0.0 <= explained["weather_mean"] <= 1.0
    assert explained["weather_mean"] > 0.8
    assert explained["clusters"] == ["P01", "P03"]


def test_pgas_in_one_new_nca_track_each_other_and_the_others_do_not(metrics):
    new = metrics["by_map"]["new"]["correlations"]["weather_mean"]
    current = metrics["by_map"]["current"]["correlations"]["weather_mean"]
    assert new["within_nca"] > new["between_nca"]
    # Today's map pairs a western PGA with an eastern one in each NCA, so its
    # within-NCA correlation is the one that comes out negative.
    assert current["within_nca"] < current["between_nca"]


def test_every_ra_is_a_misfit_under_todays_map_and_none_under_the_new_one(metrics):
    assert metrics["ra_misfits"]["new"] == []
    misfits = metrics["ra_misfits"]["current"]
    assert len(misfits) == 8
    for misfit in misfits:
        assert misfit["closer_correlation"] > misfit["own_correlation"]
        assert misfit["closer_nca"] != misfit["own_nca"]
