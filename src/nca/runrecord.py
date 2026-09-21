"""What each run writes down about itself (R15, R16).

A run that cannot be reproduced is an opinion, not a result. The record holds
the settings the run used, the code it ran, the libraries underneath it, the
random seed, every read it made, every change it made without being asked
(dropped points, links added, PGAs moved, days dropped) and the log.

Two fields change between identical runs by design: when the run started and
how long it took. They sit under 'timing', which the determinism test ignores
and compares everything else byte for byte.
"""

from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .outputs import RunDirectory, write_json, write_text
from .settings import Settings

# The libraries whose version changes an answer. Recorded every run.
TRACKED_LIBRARIES = (
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "shapely",
    "geopandas",
    "pyproj",
    "matplotlib",
)


def _library_versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in TRACKED_LIBRARIES:
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            found[name] = "not installed"
    return found


def _git(*arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def code_version() -> dict[str, Any]:
    """The commit this ran from, and whether the working tree was dirty."""
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "commit": commit or "unknown (not a git checkout)",
        "uncommitted_changes": bool(status),
        "changed_files": sorted(line[3:] for line in status.splitlines() if line[3:]),
    }


@dataclass
class RunRecord:
    """The record one run builds up as it goes, then writes out."""

    settings: Settings
    run_directory: RunDirectory
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    log_lines: list[str] = field(default_factory=list)
    stages_run: list[str] = field(default_factory=list)
    reads: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Add one line to the run's log, and print it so a run is watchable."""
        self.log_lines.append(message)
        print(message, flush=True)

    def notice(self, message: str) -> None:
        """Record a change the run made that nobody asked for (R16)."""
        self.notices.append(message)
        self.log(f"notice: {message}")

    def record_reads(self, reads: list[Any]) -> None:
        for read in reads:
            self.reads.append(vars(read).copy())

    def to_mapping(self) -> dict[str, Any]:
        finished = dt.datetime.now(dt.UTC)
        return {
            "settings": self.settings.to_mapping(),
            "settings_file": self.settings.source_file,
            "stages_run": list(self.stages_run),
            "code": code_version(),
            "python": {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
                "executable": sys.executable,
            },
            "libraries": _library_versions(),
            "random_seed": self.settings.evaluate.seed,
            "sealed_window_override_used": self.settings.windows.sealed_override,
            "reads": self.reads,
            "notices": list(self.notices),
            "timing": {
                "started_at": self.started_at.isoformat(),
                "finished_at": finished.isoformat(),
                "seconds": round((finished - self.started_at).total_seconds(), 3),
            },
        }

    def write(self) -> None:
        write_json(self.to_mapping(), self.run_directory.run_record_path)
        write_text("\n".join(self.log_lines) + "\n", self.run_directory.log_path)
