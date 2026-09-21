"""Shared geometry helpers: repairing shapes, shared edges, connected parts.

Two rules live here because three stages depend on them agreeing:

* **A shared edge is a line, not a corner.** Two shapes count as neighbours
  under the rook rule when the line they share is at least a set length,
  by default 1 metre. On a regular grid, diagonal cells touch at a single
  corner; floating-point arithmetic can turn that corner into a line a few
  centimetres long. The length rule throws those away.
* **Connected parts come from the graph, never from the geometry.** Once a
  neighbour list exists, contiguity is a graph question.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping

from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry


def repair(geometry: BaseGeometry) -> BaseGeometry:
    """Return a valid version of a shape, unchanged when it is already valid."""
    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.is_valid:
        return geometry
    return geometry.buffer(0) if geometry.buffer(0).is_valid else geometry.make_valid()


def line_length(geometry: BaseGeometry | None) -> float:
    """Total length of the line parts of a shape, in the shape's own units.

    An intersection of two polygons can come back as a point, a line, a
    polygon or a mix. Only lines are a shared edge, so only lines are counted:
    taking .length of a polygon would return its perimeter and call an overlap
    a very long shared edge.
    """
    if geometry is None or geometry.is_empty:
        return 0.0
    if isinstance(geometry, LineString | MultiLineString):
        return float(geometry.length)
    parts = getattr(geometry, "geoms", None)
    if parts is None:
        return 0.0
    return sum(line_length(part) for part in parts)


def shared_edge_metres(first: BaseGeometry, second: BaseGeometry) -> float:
    """Length of the edge two shapes share, in metres. Zero when they only
    touch at a corner, or do not touch at all."""
    if not first.intersects(second):
        return 0.0
    return line_length(first.intersection(second))


def adjacency(
    shapes: Mapping[str, BaseGeometry],
    rule: str = "rook",
    minimum_metres: float = 1.0,
) -> dict[tuple[str, str], float]:
    """Every neighbouring pair, with the length of the edge it shares.

    Under the rook rule a pair needs a shared edge of at least
    minimum_metres. Under the queen rule any contact counts, including a
    single corner, whose shared edge is recorded as zero.
    """
    names = sorted(shapes)
    found: dict[tuple[str, str], float] = {}
    for position, first in enumerate(names):
        for second in names[position + 1 :]:
            one, other = shapes[first], shapes[second]
            if not one.intersects(other):
                continue
            metres = line_length(one.intersection(other))
            if rule == "queen" or metres >= minimum_metres:
                found[(first, second)] = metres
    return found


def connected_parts(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> list[list[str]]:
    """Split nodes into connected groups, largest first, then alphabetically.

    The order is fixed so two runs name the same part the same way.
    """
    neighbours: dict[str, set[str]] = {node: set() for node in nodes}
    for first, second in edges:
        if first in neighbours and second in neighbours:
            neighbours[first].add(second)
            neighbours[second].add(first)
    seen: set[str] = set()
    parts: list[list[str]] = []
    for start in sorted(neighbours):
        if start in seen:
            continue
        group: list[str] = []
        queue = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            group.append(node)
            for neighbour in sorted(neighbours[node]):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        parts.append(sorted(group))
    parts.sort(key=lambda group: (-len(group), group[0]))
    return parts


def is_connected(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    """True when every node reaches every other through the edges given."""
    node_list = list(nodes)
    if len(node_list) <= 1:
        return True
    return len(connected_parts(node_list, edges)) == 1


def part_count(geometry: BaseGeometry) -> int:
    """How many separate pieces a shape is made of."""
    if geometry is None or geometry.is_empty:
        return 0
    parts = getattr(geometry, "geoms", None)
    return 1 if parts is None else len(parts)
