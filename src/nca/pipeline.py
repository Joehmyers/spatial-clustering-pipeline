"""The seven stages, in order, and the one function that runs them.

Each stage reads the saved outputs of the stages before it and saves its own,
so any stage can rerun alone. The order here is the only place that order is
written down.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import cluster, evaluate, features, geometry, graph, mapping, report
from .outputs import RunDirectory
from .runrecord import RunRecord
from .settings import Settings

STAGES: tuple[str, ...] = (
    "geometry",
    "graph",
    "features",
    "cluster",
    "mapping",
    "evaluate",
    "report",
)

_RUNNERS: dict[str, Callable[..., Any]] = {
    "geometry": geometry.run,
    "graph": graph.run,
    "features": features.run,
    "cluster": cluster.run,
    "mapping": mapping.run,
    "evaluate": evaluate.run,
    "report": report.run,
}


def run_stage(
    name: str,
    settings: Settings,
    run_directory: RunDirectory,
    record: RunRecord,
) -> Any:
    """Run one stage by name."""
    if name not in _RUNNERS:
        raise KeyError(f"no stage called '{name}'. The stages are: {', '.join(STAGES)}")
    result = _RUNNERS[name](settings, run_directory, record)
    record.stages_run.append(name)
    return result


def run_all(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Run all seven stages in order."""
    results: dict[str, Any] = {}
    for name in STAGES:
        results[name] = run_stage(name, settings, run_directory, record)
    return results
