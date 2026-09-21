"""Cluster: the cuts are the right size, contiguous, nested and the planted one."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nca.cluster import cut_by_merge_order, find_inversions
from nca.geoutil import is_connected
from nca.outputs import read_csv, read_json


@pytest.fixture(scope="module")
def labels(full_run) -> pd.DataFrame:
    return read_csv(full_run.path("cluster", "labels"))


@pytest.fixture(scope="module")
def edges(full_run) -> list[tuple[str, str]]:
    frame = read_csv(full_run.path("graph", "neighbours"))
    return [(row["point_a"], row["point_b"]) for _, row in frame.iterrows()]


def test_each_cut_has_exactly_k_clusters(labels, fixture_settings):
    for k in fixture_settings.cuts:
        at_k = labels.loc[labels["k"] == k]
        assert at_k["cluster"].nunique() == k
        assert len(at_k) == at_k["point_id"].nunique()


def test_every_cluster_is_contiguous(labels, edges, fixture_settings):
    for k in fixture_settings.cuts:
        at_k = labels.loc[labels["k"] == k]
        for name, group in at_k.groupby("cluster"):
            members = sorted(group["point_id"].astype(str))
            assert is_connected(members, edges), (
                f"cluster {name} at k = {k} falls into more than one piece, so "
                "the tree merged points that are not neighbours"
            )


def test_each_cut_nests_inside_the_one_above(labels, fixture_settings):
    cuts = sorted(fixture_settings.cuts)
    for coarse, fine in zip(cuts, cuts[1:], strict=False):
        coarse_labels = dict(
            zip(
                *labels.loc[labels["k"] == coarse][["point_id", "cluster"]].values.T,
                strict=True,
            )
        )
        fine_labels = dict(
            zip(
                *labels.loc[labels["k"] == fine][["point_id", "cluster"]].values.T,
                strict=True,
            )
        )
        parent_of: dict[str, str] = {}
        for point, fine_name in fine_labels.items():
            coarse_name = coarse_labels[point]
            assert parent_of.setdefault(fine_name, coarse_name) == coarse_name, (
                f"cluster {fine_name} at k = {fine} spans two clusters at "
                f"k = {coarse}, so the cuts do not nest"
            )


def test_at_k_two_the_labels_match_the_planted_answer(labels, fixture_directory):
    expected = read_csv(fixture_directory / "cluster-labels-k2.expected.csv")
    got = (
        labels.loc[labels["k"] == 2, ["point_id", "cluster"]]
        .sort_values("point_id")
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(got, expected)


def test_the_diagnostics_compare_the_cut_with_the_unconstrained_and_sensitivity_runs(
    full_run,
):
    diagnostics = read_json(full_run.path("cluster", "diagnostics"))
    comparisons = diagnostics["comparisons"]
    assert "unconstrained_ward" in comparisons
    assert "sensitivity_temperature_only" in comparisons
    assert "sensitivity_all_variables" in comparisons
    for name, body in comparisons.items():
        assert -1.0 <= body["adjusted_rand_index"] <= 1.0, name
        assert body["points_differing_count"] == len(body["points_differing"])
    # The planted split is strong enough that every diagnostic finds it too.
    assert comparisons["unconstrained_ward"]["adjusted_rand_index"] == 1.0
    assert comparisons["unconstrained_ward"]["points_differing"] == []


def test_the_tree_holds_no_inversions_on_this_fixture(full_run):
    diagnostics = read_json(full_run.path("cluster", "diagnostics"))
    assert diagnostics["inversions"] == []


def test_an_inversion_is_found_when_one_is_there():
    """A merge below one it contains. Constrained trees can hold these, which
    is why the tree is cut by merge order and never by height (R6)."""
    merges = [(0, 1), (2, 3)]
    heights = [5.0, 2.0]
    assert find_inversions(merges, heights, leaves=4) == []

    merges = [(0, 1), (4, 2)]  # node 4 is the first merge
    heights = [5.0, 2.0]
    found = find_inversions(merges, heights, leaves=4)
    assert found == [{"merge": 1, "height": 2.0, "below_merge": 0, "below_height": 5.0}]


def test_cutting_by_merge_order_gives_exactly_k_clusters_named_by_smallest_id():
    points = ["P01", "P02", "P03", "P04"]
    merges = [(0, 1), (2, 3), (4, 5)]
    assert cut_by_merge_order(merges, points, 4) == {name: name for name in points}
    assert cut_by_merge_order(merges, points, 2) == {
        "P01": "P01",
        "P02": "P01",
        "P03": "P03",
        "P04": "P03",
    }
    assert set(cut_by_merge_order(merges, points, 1).values()) == {"P01"}


def test_cutting_below_what_the_tree_reaches_is_refused():
    with pytest.raises(ValueError, match="cannot cut"):
        cut_by_merge_order([(0, 1)], ["P01", "P02"], 3)


# -- the distance identity Ward depends on ----------------------------------


def test_squared_distance_between_z_scored_rows_is_two_n_one_minus_r():
    """On rows scaled to mean 0 and population standard deviation 1, squared
    Euclidean distance is 2n(1 - r). That is why Ward, which merges by
    squared distance, merges by day-aligned correlation."""
    generator = np.random.default_rng(7)
    length = 200
    for _ in range(20):
        first = generator.normal(size=length)
        second = 0.6 * first + 0.8 * generator.normal(size=length)
        first = (first - first.mean()) / first.std(ddof=0)
        second = (second - second.mean()) / second.std(ddof=0)
        correlation = float(np.corrcoef(first, second)[0, 1])
        squared = float(((first - second) ** 2).sum())
        assert squared == pytest.approx(2 * length * (1 - correlation))


def test_the_identity_holds_on_the_real_build_matrix(full_run, fixture_settings):
    matrix = read_csv(full_run.path("features", "matrix"))
    points = list(matrix["point_id"])
    for variable in fixture_settings.features.variables:
        columns = [
            name for name in matrix.columns if str(name).startswith(f"{variable}_")
        ]
        block = matrix[columns].to_numpy()
        length = len(columns)
        for first in range(len(points)):
            for second in range(first + 1, len(points)):
                one, other = block[first], block[second]
                correlation = float(np.corrcoef(one, other)[0, 1])
                squared = float(((one - other) ** 2).sum())
                assert squared == pytest.approx(
                    2 * length * (1 - correlation), rel=1e-9, abs=1e-6
                ), f"{variable}: {points[first]} against {points[second]}"
