"""Where each stage saves its work, and how (R11).

Stages do not hand objects to each other. Each one saves files a reviewer can
open without this code (CSV, GeoJSON, JSON) and the next one reads them back,
so any stage can rerun alone.

Every writer here is deterministic: the same values produce the same bytes,
which is what lets the determinism test compare two runs file by file (R15).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

# The outputs R11 names, by stage. The smoke test walks this table, so an
# output that stops being written fails a test rather than going unnoticed.
OUTPUTS: dict[str, dict[str, str]] = {
    "geometry": {
        "nca_layer": "geometry/nca.geojson",
        "pga_layer": "geometry/pga.geojson",
        "ra_layer": "geometry/ra.geojson",
        "outline": "geometry/service-area-outline.geojson",
        "checks": "geometry/check-report.json",
    },
    "graph": {
        "cells": "graph/cells.geojson",
        "neighbours": "graph/neighbours.csv",
        "summary": "graph/graph-summary.json",
    },
    "features": {
        "anomalies": "features/regional-anomalies.csv",
        "parameters": "features/stored-parameters.csv",
        "matrix": "features/build-matrix.csv",
        "summary": "features/features-summary.json",
    },
    "cluster": {
        "tree": "cluster/tree.csv",
        "labels": "cluster/labels.csv",
        "diagnostics": "cluster/diagnostics.json",
    },
    "mapping": {
        "assignments": "mapping/assignments.csv",
        "moves": "mapping/moves.csv",
        "summary": "mapping/mapping-summary.json",
    },
    "evaluate": {
        "metrics": "evaluate/metrics.json",
        "benchmark": "evaluate/benchmark.csv",
    },
    "report": {
        "summary": "report/summary.md",
        "current_map": "report/map-current-ncas.png",
        "new_map": "report/map-new-ncas.png",
        "point_clusters": "report/map-point-clusters.png",
        "straddle": "report/map-straddle-scores.png",
        "misfits": "report/map-misfit-ras.png",
        "dendrogram": "report/dendrogram.png",
        "eta_squared": "report/eta-squared.png",
        "benchmark": "report/benchmark-histogram.png",
    },
}

RUN_RECORD = "run-record.json"
RUN_LOG = "run.log"

# Metres, rounded before writing so two runs cannot differ in the last bit of
# a coordinate. A centimetre is far below anything this pipeline measures.
COORDINATE_DECIMALS = 2


class RunDirectory:
    """One run's output folder, and the path of every file in it."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, stage: str, name: str) -> Path:
        return self.root / OUTPUTS[stage][name]

    def stage_directory(self, stage: str) -> Path:
        directory = self.root / stage
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def prepare(self, stage: str) -> None:
        self.stage_directory(stage)

    def require(self, stage: str, name: str) -> Path:
        """The path of an earlier stage's output, or a message saying to run it."""
        target = self.path(stage, name)
        if not target.exists():
            raise FileNotFoundError(
                f"{target} is missing. Run the '{stage}' stage first: "
                f"nca run {stage} --settings <file> --out {self.root}"
            )
        return target

    @property
    def run_record_path(self) -> Path:
        return self.root / RUN_RECORD

    @property
    def log_path(self) -> Path:
        return self.root / RUN_LOG


def write_csv(frame: pd.DataFrame, path: Path, float_format: str | None = None) -> Path:
    """Write a table the same way every time: Unix line endings, no index."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format=float_format)
    return path


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(path, **kwargs)


def write_geojson(frame: gpd.GeoDataFrame, path: Path) -> Path:
    """Write geometry with coordinates rounded to the centimetre."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # GeoJSON writers append to an existing file otherwise
    frame.to_file(path, driver="GeoJSON", coordinate_precision=COORDINATE_DECIMALS)
    return path


def read_geojson(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path)


def write_json(value: Any, path: Path) -> Path:
    """Write JSON with sorted keys, so two runs give the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
