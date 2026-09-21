"""Report: the figures render offline and the summary carries the numbers."""

from __future__ import annotations

import pytest

from nca.outputs import read_json

FIGURES = (
    "current_map",
    "new_map",
    "point_clusters",
    "straddle",
    "misfits",
    "dendrogram",
    "eta_squared",
    "benchmark",
)


@pytest.mark.parametrize("name", FIGURES)
def test_each_figure_is_drawn(name, full_run):
    path = full_run.path("report", name)
    assert path.is_file()
    assert path.stat().st_size > 1000


def test_the_summary_reports_the_same_numbers_the_metrics_hold(full_run):
    metrics = read_json(full_run.path("evaluate", "metrics"))
    summary = full_run.path("report", "summary").read_text(encoding="utf-8")
    weather = metrics["by_map"]["new"]["eta_squared"]["weather_mean"]
    demand = metrics["by_map"]["new"]["eta_squared"]["demand"]
    assert f"{weather:.3f}" in summary
    assert f"{demand:.3f}" in summary
    assert f"{len(metrics['ra_misfits']['new'])}" in summary


def test_the_summary_fits_on_a_page(full_run):
    summary = full_run.path("report", "summary").read_text(encoding="utf-8")
    assert len(summary.splitlines()) < 80


# Everything the report stage is allowed to import. A web basemap library
# would have to appear here, so adding one fails this test.
ALLOWED_IMPORTS = {
    "__future__",
    "typing",
    "matplotlib",
    "matplotlib.pyplot",
    "numpy",
    "pandas",
    "scipy.cluster.hierarchy",
    "nca.outputs",
    "nca.runrecord",
    "nca.settings",
}


def test_the_report_imports_nothing_that_would_need_a_network():
    """It must run on a machine with no network, so no web basemap."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "nca" / "report.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "nca" if node.level else ""
            imported.add(f"{prefix}.{node.module}" if prefix else node.module)
    assert imported <= ALLOWED_IMPORTS, (
        f"report.py imports {sorted(imported - ALLOWED_IMPORTS)}, which is not on "
        "the offline list"
    )
