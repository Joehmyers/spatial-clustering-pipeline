"""Stage 4, cluster: grow the tree, cut it, and check the cut against others.

Ward's method merges the pair of clusters whose union least increases the
total variance within clusters. Constrained to the neighbour graph, it only
ever considers pairs that touch, so every cluster it builds is contiguous.

Two rules matter more than the method:

* **Check the graph is one piece first.** Some implementations quietly add
  links to finish a tree when the graph is not connected, inventing
  neighbours that do not exist. The run stops instead.
* **Cut by merge order, never by height.** A constrained tree can hold an
  inversion: a merge lower than one it contains. Cutting by height then gives
  the wrong number of clusters. Replaying the first n - k merges always gives
  exactly k, and the cuts nest inside each other.
"""

from __future__ import annotations

import heapq
from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from sklearn.cluster import ward_tree
from sklearn.metrics import adjusted_rand_score

from .errors import DisconnectedGraphError
from .inputs import POINT_ID
from .outputs import RunDirectory, read_csv, read_json, write_csv, write_json
from .runrecord import RunRecord
from .settings import Settings

STAGE = "cluster"


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Build the tree, save every cut, and run the diagnostics."""
    run_directory.prepare(STAGE)
    matrix = read_csv(run_directory.require("features", "matrix"))
    points = [str(name) for name in matrix[POINT_ID]]
    values = matrix.drop(columns=[POINT_ID]).to_numpy(dtype=float)
    columns = [str(name) for name in matrix.columns if name != POINT_ID]

    edges = read_csv(run_directory.require("graph", "neighbours"))
    graph_summary = read_json(run_directory.require("graph", "summary"))
    parts = [list(part) for part in graph_summary["connected_parts"]]
    if len(parts) > 1 and settings.graph.disconnected_parts != "fixed_regions":
        raise DisconnectedGraphError(
            f"the neighbour graph falls into {len(parts)} parts, so a single tree "
            "cannot be grown over it. Join them with graph.manual_links, or set "
            "graph.disconnected_parts = 'fixed_regions'."
        )

    connectivity = _connectivity(points, edges)
    merges, heights = constrained_tree(values, connectivity, points, parts)
    record.log(
        f"{STAGE}: grew a tree of {len(merges)} merges over {len(points)} points"
    )

    inversions = find_inversions(merges, heights, len(points))
    for inversion in inversions:
        record.notice(
            f"{STAGE}: merge {inversion['merge']} at height "
            f"{inversion['height']:.6f} sits below merge "
            f"{inversion['below_merge']} at {inversion['below_height']:.6f}, which "
            "it contains"
        )

    cuts = settings.cuts
    labels = {k: cut_by_merge_order(merges, points, k) for k in cuts}
    label_frame = (
        pd.DataFrame(
            [
                {"k": k, POINT_ID: point, "cluster": labels[k][point]}
                for k in cuts
                for point in points
            ]
        )
        .sort_values(["k", POINT_ID])
        .reset_index(drop=True)
    )

    headline = settings.cluster.number_of_regions
    diagnostics = _diagnostics(
        settings,
        values,
        columns,
        connectivity,
        points,
        parts,
        labels[headline],
        record,
    )
    diagnostics["inversions"] = inversions
    diagnostics["cuts"] = {
        str(k): {
            "clusters": sorted(set(labels[k].values())),
            "sizes": {
                name: int(sum(1 for value in labels[k].values() if value == name))
                for name in sorted(set(labels[k].values()))
            },
        }
        for k in cuts
    }
    diagnostics["headline_k"] = headline

    write_csv(_tree_frame(merges, heights, points), run_directory.path(STAGE, "tree"))
    write_csv(label_frame, run_directory.path(STAGE, "labels"))
    write_json(diagnostics, run_directory.path(STAGE, "diagnostics"))
    record.log(
        f"{STAGE}: saved cuts at k = {', '.join(str(k) for k in cuts)}; "
        f"{len(inversions)} inversion(s)"
    )
    return diagnostics


def _connectivity(points: list[str], edges: pd.DataFrame) -> coo_matrix:
    """The neighbour graph as the sparse matrix Ward needs, in point order."""
    position = {name: index for index, name in enumerate(points)}
    rows: list[int] = []
    columns: list[int] = []
    for _, edge in edges.iterrows():
        first, second = str(edge["point_a"]), str(edge["point_b"])
        if first not in position or second not in position:
            continue
        rows += [position[first], position[second]]
        columns += [position[second], position[first]]
    data = np.ones(len(rows))
    return coo_matrix((data, (rows, columns)), shape=(len(points), len(points)))


def constrained_tree(
    values: np.ndarray,
    connectivity: coo_matrix,
    points: list[str],
    parts: list[list[str]],
) -> tuple[list[tuple[int, int]], list[float]]:
    """Ward's tree over the neighbour graph, as a merge order and its heights.

    With one connected part this is a single tree. With several (which only
    happens when the settings say to keep them as fixed regions) each part
    grows its own tree and the merges interleave by height, so no merge ever
    joins two parts.
    """
    if len(parts) <= 1:
        children, components, _, _, heights = ward_tree(
            values, connectivity=connectivity.tocsr(), return_distance=True
        )
        if components != 1:
            raise DisconnectedGraphError(
                f"Ward found {components} connected parts in the neighbour graph. "
                "A tree over a graph in pieces is not a tree over the graph."
            )
        return [(int(a), int(b)) for a, b in children], [float(h) for h in heights]

    position = {name: index for index, name in enumerate(points)}
    streams: list[list[tuple[float, tuple[int, int]]]] = []
    for part in parts:
        rows = [position[name] for name in part]
        if len(rows) == 1:
            streams.append([])
            continue
        sub = connectivity.tocsr()[rows, :][:, rows]
        children, _, _, _, heights = ward_tree(
            values[rows, :], connectivity=sub, return_distance=True
        )
        streams.append(
            [
                (float(heights[index]), (int(left), int(right)))
                for index, (left, right) in enumerate(children)
            ]
        )

    return _interleave(streams, parts, position, len(points))


def _interleave(
    streams: list[list[tuple[float, tuple[int, int]]]],
    parts: list[list[str]],
    position: dict[str, int],
    leaves: int,
) -> tuple[list[tuple[int, int]], list[float]]:
    """Emit each part's merges in its own order, lowest height first overall."""
    local_maps = [
        {index: position[name] for index, name in enumerate(part)} for part in parts
    ]
    next_index = [0] * len(streams)
    queue: list[tuple[float, int]] = []
    for part_index, stream in enumerate(streams):
        if stream:
            heapq.heappush(queue, (stream[0][0], part_index))
    merges: list[tuple[int, int]] = []
    heights: list[float] = []
    while queue:
        height, part_index = heapq.heappop(queue)
        local_index = next_index[part_index]
        _, (left, right) = streams[part_index][local_index]
        mapping = local_maps[part_index]
        merges.append((mapping[left], mapping[right]))
        heights.append(height)
        mapping[len(parts[part_index]) + local_index] = leaves + len(merges) - 1
        next_index[part_index] += 1
        if next_index[part_index] < len(streams[part_index]):
            heapq.heappush(
                queue,
                (streams[part_index][next_index[part_index]][0], part_index),
            )
    return merges, heights


def cut_by_merge_order(
    merges: list[tuple[int, int]], points: list[str], k: int
) -> dict[str, str]:
    """Replay the first n - k merges. Never cuts by height (R6).

    Each cluster takes the name of the smallest point ID it holds, so two runs
    name the same cluster the same way and the name survives a rerun.
    """
    count = len(points)
    if k < 1 or k > count:
        raise ValueError(f"cannot cut {count} points into {k} clusters")
    if k < count - len(merges):
        raise ValueError(
            f"cannot reach {k} clusters: the tree holds only {len(merges)} merges "
            f"over {count} points, so the fewest it reaches is {count - len(merges)}"
        )
    parent = list(range(count + len(merges)))

    def root(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for step in range(count - k):
        left, right = merges[step]
        node = count + step
        parent[root(left)] = node
        parent[root(right)] = node

    members: dict[int, list[str]] = {}
    for index, name in enumerate(points):
        members.setdefault(root(index), []).append(name)
    labels: dict[str, str] = {}
    for group in members.values():
        name = min(group)
        for point in group:
            labels[point] = name
    return labels


def find_inversions(
    merges: list[tuple[int, int]], heights: list[float], leaves: int
) -> list[dict[str, Any]]:
    """Merges that sit lower than a merge they contain."""
    found: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(merges):
        for child in (left, right):
            if child < leaves:
                continue
            child_merge = child - leaves
            if heights[index] < heights[child_merge]:
                found.append(
                    {
                        "merge": index,
                        "height": round(heights[index], 9),
                        "below_merge": child_merge,
                        "below_height": round(heights[child_merge], 9),
                    }
                )
    return found


def _members(merges: list[tuple[int, int]], points: list[str]) -> list[list[str]]:
    """Leaf IDs under every node, leaves first, then each merge in order."""
    under: list[list[str]] = [[name] for name in points]
    for left, right in merges:
        under.append(sorted(under[left] + under[right]))
    return under


def _tree_frame(
    merges: list[tuple[int, int]], heights: list[float], points: list[str]
) -> pd.DataFrame:
    under = _members(merges, points)
    leaves = len(points)
    rows = []
    for index, (left, right) in enumerate(merges):
        members = under[leaves + index]
        rows.append(
            {
                "merge": index,
                "node": leaves + index,
                "left": left,
                "right": right,
                "height": heights[index],
                "size": len(members),
                "cluster": min(members),
                "leaf_ids": " ".join(members),
            }
        )
    return pd.DataFrame(rows)


def _diagnostics(
    settings: Settings,
    values: np.ndarray,
    columns: list[str],
    connectivity: coo_matrix,
    points: list[str],
    parts: list[list[str]],
    main: dict[str, str],
    record: RunRecord,
) -> dict[str, Any]:
    """Run the comparisons of R7 against the headline cut."""
    k = settings.cluster.number_of_regions
    comparisons: dict[str, Any] = {}

    if settings.cluster.unconstrained_diagnostic:
        tree = linkage(values, method="ward")
        merges = [(int(row[0]), int(row[1])) for row in tree]
        other = cut_by_merge_order(merges, points, k)
        comparisons["unconstrained_ward"] = _compare(main, other, points)
        record.log(
            f"{STAGE}: unconstrained Ward agrees with the constrained cut at "
            f"adjusted Rand index "
            f"{comparisons['unconstrained_ward']['adjusted_rand_index']:.3f}"
        )

    for name, variables in sorted(settings.cluster.sensitivity_sets.items()):
        keep = [
            index
            for index, column in enumerate(columns)
            if column.rsplit("_", 1)[0] in set(variables)
        ]
        if not keep:
            continue
        merges, _ = constrained_tree(values[:, keep], connectivity, points, parts)
        other = cut_by_merge_order(merges, points, k)
        comparisons[f"sensitivity_{name}"] = _compare(main, other, points)
        comparisons[f"sensitivity_{name}"]["variables"] = list(variables)

    return {"comparisons": comparisons}


def _compare(
    main: dict[str, str], other: dict[str, str], points: list[str]
) -> dict[str, Any]:
    """Agreement between two labellings, and the points they disagree on."""
    main_codes = _codes(main, points)
    other_codes = _codes(other, points)
    matched = _match_labels(main_codes, other_codes)
    differing = [
        point
        for index, point in enumerate(points)
        if matched[index] != main_codes[index]
    ]
    return {
        "adjusted_rand_index": round(
            float(adjusted_rand_score(main_codes, other_codes)), 6
        ),
        "points_differing": differing,
        "points_differing_count": len(differing),
        "labels": {point: other[point] for point in points},
    }


def _codes(labels: dict[str, str], points: list[str]) -> np.ndarray:
    names = sorted(set(labels.values()))
    lookup = {name: index for index, name in enumerate(names)}
    return np.array([lookup[labels[point]] for point in points])


def _match_labels(main: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Rename the other labelling to overlap the main one as much as it can.

    Without this, two identical groupings that happen to use different names
    would look completely different.
    """
    main_names = sorted(set(main.tolist()))
    other_names = sorted(set(other.tolist()))
    overlap = np.zeros((len(other_names), len(main_names)), dtype=int)
    for row, other_name in enumerate(other_names):
        for column, main_name in enumerate(main_names):
            overlap[row, column] = int(
                np.sum((other == other_name) & (main == main_name))
            )
    rows, columns = linear_sum_assignment(-overlap)
    mapping = {
        other_names[row]: main_names[column]
        for row, column in zip(rows, columns, strict=True)
    }
    unmatched = max(main_names) + 1
    renamed = []
    for value in other.tolist():
        if value in mapping:
            renamed.append(mapping[value])
        else:
            renamed.append(unmatched)
            unmatched += 1
    return np.array(renamed)
