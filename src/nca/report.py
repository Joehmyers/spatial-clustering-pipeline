"""Stage 7, report: draw the maps and charts, and write the one-page summary.

Every figure is drawn from the saved outputs of the stages before it, with no
web basemap, so the report runs on a machine with no network. Colours come
from one fixed list keyed by name, so a cluster keeps its colour across every
figure in a run.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")  # draw to files, never to a screen

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.cluster.hierarchy import dendrogram  # noqa: E402

from .outputs import (  # noqa: E402
    RunDirectory,
    read_csv,
    read_geojson,
    read_json,
    write_text,
)
from .runrecord import RunRecord  # noqa: E402
from .settings import Settings  # noqa: E402

STAGE = "report"

FIGURE_SIZE = (7.0, 7.0)
CHART_SIZE = (8.0, 4.5)
DOTS_PER_INCH = 110

# A fixed list, so the same group gets the same colour in every figure and in
# every rerun. Chosen to stay apart in greyscale as well as in colour.
PALETTE = (
    "#4878a8",
    "#d1893f",
    "#6a9a5b",
    "#b4585f",
    "#8172b3",
    "#937860",
    "#da8bc3",
    "#8c8c8c",
    "#ccb974",
    "#64b5cd",
)
ABOVE_THE_CUT = "#bfbfbf"

# PNG files carry a Software tag by default, which would make two identical
# runs differ. Passing None drops it (R15).
NO_METADATA = {"Software": None}


def run(
    settings: Settings, run_directory: RunDirectory, record: RunRecord
) -> dict[str, Any]:
    """Draw every figure and write the summary."""
    run_directory.prepare(STAGE)
    headline = settings.cluster.number_of_regions

    cells = read_geojson(run_directory.require("graph", "cells"))
    pgas = read_geojson(run_directory.require("geometry", "pga_layer"))
    ras = read_geojson(run_directory.require("geometry", "ra_layer"))
    labels = read_csv(run_directory.require("cluster", "labels"))
    tree = read_csv(run_directory.require("cluster", "tree"))
    assignments = read_csv(run_directory.require("mapping", "assignments"))
    metrics = read_json(run_directory.require("evaluate", "metrics"))
    benchmark = read_csv(run_directory.require("evaluate", "benchmark"))
    graph_summary = read_json(run_directory.require("graph", "summary"))
    mapping_summary = read_json(run_directory.require("mapping", "summary"))

    pga_rows = assignments.loc[
        (assignments["k"] == headline) & (assignments["unit_type"] == "pga")
    ]
    new_map = dict(zip(pga_rows["unit_id"], pga_rows["assigned_nca"], strict=True))
    straddle = dict(zip(pga_rows["unit_id"], pga_rows["straddle_score"], strict=True))
    current_map = {
        pga_id: nca
        for nca, members in metrics["maps"]["current"].items()
        for pga_id in members
    }

    _map_figure(
        pgas,
        "pga_id",
        current_map,
        f"Today's NCAs ({len(metrics['maps']['current'])} areas)",
        run_directory.path(STAGE, "current_map"),
    )
    _map_figure(
        pgas,
        "pga_id",
        new_map,
        f"New NCAs from weather alone (k = {headline})",
        run_directory.path(STAGE, "new_map"),
    )
    _cluster_figure(
        cells, labels, headline, run_directory.path(STAGE, "point_clusters")
    )
    _straddle_figure(pgas, straddle, run_directory.path(STAGE, "straddle"))
    _misfit_figure(
        ras,
        assignments,
        headline,
        metrics["ra_misfits"],
        run_directory.path(STAGE, "misfits"),
    )
    _dendrogram_figure(tree, labels, headline, run_directory.path(STAGE, "dendrogram"))
    _eta_figure(metrics, run_directory.path(STAGE, "eta_squared"))
    _benchmark_figure(benchmark, metrics, run_directory.path(STAGE, "benchmark"))

    summary = _summary(settings, metrics, graph_summary, mapping_summary, headline)
    write_text(summary, run_directory.path(STAGE, "summary"))
    record.log(f"{STAGE}: wrote 8 figures and the one-page summary")
    return {"figures": 8, "summary_characters": len(summary)}


def _colours(names: list[str]) -> dict[str, str]:
    return {
        name: PALETTE[index % len(PALETTE)] for index, name in enumerate(sorted(names))
    }


def _finish(figure: plt.Figure, path) -> None:
    figure.savefig(path, dpi=DOTS_PER_INCH, metadata=NO_METADATA, bbox_inches="tight")
    plt.close(figure)


def _bare_axes(axes: plt.Axes, title: str) -> None:
    axes.set_title(title)
    axes.set_aspect("equal")
    axes.set_axis_off()


def _map_figure(
    units, id_column: str, groups: dict[str, str], title: str, path
) -> None:
    """Polygons coloured by the group each belongs to."""
    colours = _colours(sorted(set(groups.values())))
    figure, axes = plt.subplots(figsize=FIGURE_SIZE)
    frame = units.copy()
    frame["group"] = frame[id_column].map(groups)
    for name, part in frame.groupby("group"):
        part.plot(
            ax=axes, color=colours[name], edgecolor="white", linewidth=1.2, label=name
        )
    for _, row in frame.iterrows():
        point = row.geometry.representative_point()
        axes.annotate(
            row[id_column],
            (point.x, point.y),
            ha="center",
            va="center",
            fontsize=8,
            color="white",
        )
    axes.legend(title="NCA", loc="upper left", fontsize=8, title_fontsize=8)
    _bare_axes(axes, title)
    _finish(figure, path)


def _cluster_figure(cells, labels: pd.DataFrame, headline: int, path) -> None:
    """Point clusters drawn over the Voronoi cells they were built from."""
    at_k = labels.loc[labels["k"] == headline]
    lookup = dict(zip(at_k["point_id"].astype(str), at_k["cluster"], strict=True))
    colours = _colours(sorted(set(lookup.values())))
    figure, axes = plt.subplots(figsize=FIGURE_SIZE)
    frame = cells.copy()
    frame["cluster"] = frame["point_id"].astype(str).map(lookup)
    for name, part in frame.groupby("cluster"):
        part.plot(
            ax=axes,
            color=colours[name],
            edgecolor="white",
            linewidth=0.8,
            label=f"cluster {name}",
        )
    centres = frame.geometry.representative_point()
    axes.scatter(centres.x, centres.y, s=10, color="black", zorder=3)
    axes.legend(loc="upper left", fontsize=8)
    _bare_axes(axes, f"Point clusters over their cells (k = {headline})")
    _finish(figure, path)


def _straddle_figure(pgas, straddle: dict[str, float], path) -> None:
    """How far each PGA sits across a weather boundary."""
    figure, axes = plt.subplots(figsize=FIGURE_SIZE)
    frame = pgas.copy()
    frame["straddle_score"] = frame["pga_id"].map(straddle)
    frame.plot(
        ax=axes,
        column="straddle_score",
        cmap="YlOrRd",
        vmin=0.0,
        vmax=0.5,
        edgecolor="white",
        linewidth=1.2,
        legend=True,
        legend_kwds={"label": "straddle score (1 - majority share)", "shrink": 0.6},
    )
    for _, row in frame.iterrows():
        point = row.geometry.representative_point()
        axes.annotate(
            f"{row['pga_id']}\n{row['straddle_score']:.2f}",
            (point.x, point.y),
            ha="center",
            va="center",
            fontsize=8,
        )
    _bare_axes(axes, "How far each PGA straddles a weather boundary")
    _finish(figure, path)


def _misfit_figure(
    ras, assignments: pd.DataFrame, headline: int, misfits: dict[str, Any], path
) -> None:
    """RAs whose weather tracks a neighbouring NCA better than their own."""
    ra_rows = assignments.loc[
        (assignments["k"] == headline) & (assignments["unit_type"] == "ra")
    ]
    assigned = dict(zip(ra_rows["unit_id"], ra_rows["assigned_nca"], strict=True))
    flagged = {row["ra_id"] for row in misfits.get("new", [])}
    figure, axes = plt.subplots(figsize=FIGURE_SIZE)
    frame = ras.copy()
    frame["assigned_nca"] = frame["ra_id"].map(assigned)
    colours = _colours(sorted(set(assigned.values())))
    for name, part in frame.groupby("assigned_nca"):
        part.plot(
            ax=axes, color=colours[name], edgecolor="white", linewidth=0.8, label=name
        )
    misfitting = frame.loc[frame["ra_id"].isin(flagged)]
    if not misfitting.empty:
        misfitting.plot(
            ax=axes,
            facecolor="none",
            edgecolor="black",
            linewidth=2.5,
            hatch="//",
            label="misfit",
        )
    axes.legend(loc="upper left", fontsize=8)
    _bare_axes(
        axes,
        f"RA misfits under the new map: {len(flagged)} of {len(frame)}",
    )
    _finish(figure, path)


def _dendrogram_figure(
    tree: pd.DataFrame, labels: pd.DataFrame, headline: int, path
) -> None:
    """The tree, with everything above the cut drawn in grey."""
    leaf_ids = sorted({name for row in tree["leaf_ids"] for name in str(row).split()})
    linkage = np.column_stack(
        [
            tree["left"].to_numpy(dtype=float),
            tree["right"].to_numpy(dtype=float),
            tree["height"].to_numpy(dtype=float),
            tree["size"].to_numpy(dtype=float),
        ]
    )
    at_k = labels.loc[labels["k"] == headline]
    lookup = dict(zip(at_k["point_id"].astype(str), at_k["cluster"], strict=True))
    colours = _colours(sorted(set(lookup.values())))
    below_the_cut = len(leaf_ids) - headline
    cluster_of_link = {
        len(leaf_ids) + index: lookup[str(row["cluster"])]
        for index, row in tree.iterrows()
        if index < below_the_cut and str(row["cluster"]) in lookup
    }

    def link_colour(node: int) -> str:
        return colours.get(cluster_of_link.get(node, ""), ABOVE_THE_CUT)

    figure, axes = plt.subplots(figsize=CHART_SIZE)
    dendrogram(
        linkage,
        ax=axes,
        labels=leaf_ids,
        link_color_func=link_colour,
        above_threshold_color=ABOVE_THE_CUT,
    )
    axes.set_title(
        f"Constrained Ward tree, cut at k = {headline} (grey links sit above the cut)"
    )
    axes.set_ylabel("Ward merge height")
    axes.tick_params(axis="x", labelsize=7)
    _finish(figure, path)


def _eta_figure(metrics: dict[str, Any], path) -> None:
    """Side-by-side bars: today's map against the new one."""
    current = metrics["by_map"]["current"]["eta_squared"]
    new = metrics["by_map"]["new"]["eta_squared"]
    names = [key for key in current if key != "weather_mean"]
    positions = np.arange(len(names))
    figure, axes = plt.subplots(figsize=CHART_SIZE)
    axes.bar(
        positions - 0.2,
        [current[name] for name in names],
        width=0.4,
        label="today's NCAs",
        color=PALETTE[7],
    )
    axes.bar(
        positions + 0.2,
        [new[name] for name in names],
        width=0.4,
        label="new NCAs",
        color=PALETTE[0],
    )
    ceiling = metrics["ceiling"]["weather_mean"]["between_pga_share"]
    axes.axhline(
        ceiling,
        color=PALETTE[3],
        linestyle="--",
        linewidth=1.2,
        label=f"ceiling ({ceiling:.3f})",
    )
    axes.set_xticks(positions)
    axes.set_xticklabels(names)
    axes.set_ylim(0, 1.05)
    axes.set_ylabel("eta-squared (share of variance between NCAs)")
    axes.set_title("Held-out eta-squared, by variable and for demand")
    axes.legend(fontsize=8)
    _finish(figure, path)


def _benchmark_figure(benchmark: pd.DataFrame, metrics: dict[str, Any], path) -> None:
    """Where both maps fall among random contiguous maps at the same count."""
    placings = metrics["benchmark"]["placings"]
    figure, axes = plt.subplots(figsize=CHART_SIZE)
    axes.hist(
        benchmark["weather_eta_squared"], bins=25, color=PALETTE[8], edgecolor="white"
    )
    for name, colour in (("current", PALETTE[7]), ("new", PALETTE[0])):
        score = placings[name]["weather_eta_squared"]
        axes.axvline(
            score,
            color=colour,
            linewidth=2.0,
            label=f"{name}: {score:.3f} "
            f"({placings[name]['weather_percentile']:.0f}th "
            "percentile)",
        )
    axes.set_xlabel("eta-squared for weather")
    axes.set_ylabel("random contiguous maps")
    axes.set_title(
        f"{len(benchmark)} random contiguous maps at k = {metrics['number_of_regions']}"
    )
    axes.legend(fontsize=8)
    _finish(figure, path)


def _summary(
    settings: Settings,
    metrics: dict[str, Any],
    graph_summary: dict[str, Any],
    mapping_summary: dict[str, Any],
    headline: int,
) -> str:
    """The one page a reader should be able to decide from."""
    current = metrics["by_map"]["current"]
    new = metrics["by_map"]["new"]
    placings = metrics["benchmark"]["placings"]
    ceiling = metrics["ceiling"]["weather_mean"]["between_pga_share"]
    cut = mapping_summary["cuts"][str(headline)]
    lines = [
        f"# New NCAs from weather alone, at k = {headline}",
        "",
        f"Built from {graph_summary['points_kept']} weather points "
        f"({len(graph_summary['points_dropped_offshore'])} dropped offshore), "
        f"on weather up to {settings.windows.build_end.isoformat()}. Judged on "
        f"{metrics['held_out_window'][0]} to {metrics['held_out_window'][1]}, "
        "which the build never saw.",
        "",
        "## The verdict",
        "",
        "| Measure | Today's NCAs | New NCAs | Ceiling |",
        "| --- | --- | --- | --- |",
        f"| Weather, eta-squared | {current['eta_squared']['weather_mean']:.3f} "
        f"| {new['eta_squared']['weather_mean']:.3f} | {ceiling:.3f} |",
        f"| Demand, eta-squared | {current['eta_squared']['demand']:.3f} "
        f"| {new['eta_squared']['demand']:.3f} | |",
        f"| Correlation within an NCA | "
        f"{current['correlations']['weather_mean']['within_nca']:.3f} "
        f"| {new['correlations']['weather_mean']['within_nca']:.3f} | |",
        f"| Correlation between NCAs | "
        f"{current['correlations']['weather_mean']['between_nca']:.3f} "
        f"| {new['correlations']['weather_mean']['between_nca']:.3f} | |",
        f"| RA misfits | {len(metrics['ra_misfits']['current'])} "
        f"| {len(metrics['ra_misfits']['new'])} | |",
        f"| Place among {metrics['benchmark']['random_partitions']} random maps "
        f"| {placings['current']['weather_percentile']:.0f}th percentile "
        f"| {placings['new']['weather_percentile']:.0f}th percentile | |",
        "",
        "Eta-squared is the share of the spread across PGAs on a given day that "
        "lies between NCAs rather than inside them. Higher is better: it means "
        "an NCA's PGAs feel the same weather on the same day.",
        "",
        "The ceiling is the share of RA-level weather variance lying between "
        f"PGAs ({ceiling:.3f}). No map made of whole PGAs can reach the "
        f"{1 - ceiling:.3f} lying inside them.",
        "",
        "## The new map",
        "",
        "| New NCA | PGAs |",
        "| --- | --- |",
    ]
    for name, members in cut["new_ncas"].items():
        lines.append(f"| {name} | {', '.join(members)} |")
    lines += [
        "",
        f"Highest straddle score: {cut['highest_straddle_score']:.3f}. A PGA's "
        "straddle score is 1 minus the share of its area in the cluster it was "
        "given, so 0 means it sits squarely in one cluster.",
        "",
        f"PGAs moved to keep the new NCAs contiguous: {cut['moves']}.",
        "",
        "## Before the tree",
        "",
        f"Cluster membership explains "
        f"{metrics['point_variance_explained']['weather_mean']:.3f} of the "
        "between-point weather variance on the held-out window. That judges the "
        "tree on its own, before any mapping onto whole PGAs.",
        "",
        "## Figures",
        "",
        "- `map-current-ncas.png`, `map-new-ncas.png`: the two maps",
        "- `map-point-clusters.png`: the clusters over the cells they came from",
        "- `map-straddle-scores.png`: how far each PGA straddles a boundary",
        "- `map-misfit-ras.png`: RAs closer to a neighbouring NCA",
        "- `dendrogram.png`: the tree, with the cut marked",
        "- `eta-squared.png`, `benchmark-histogram.png`: the two charts above",
        "",
    ]
    return "\n".join(lines)
