"""The one door every input comes through, and the two guards standing at it.

Every stage reads its data from a DataSource. That single door is what makes
the two guardrails enforceable rather than a matter of trust:

* **The demand firewall (R12).** A DataSource is built for one named stage.
  Only the evaluate stage's source will return demand; every other one raises
  DemandFirewallError. The map is built from weather and judged on demand, so
  a build stage that could see demand would make the judgement worthless.
* **The sealed window (R13).** Any read whose window reaches the sealed start
  fails, and any row that comes back dated on or after it fails too, unless
  the override is set. When the override lets a sealed read through, the
  source records it and the run record carries it.

Every read is logged on the source, so the run record can say exactly what the
run touched (R15, R16).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .errors import DemandFirewallError, RealInputsNotConnectedError, SealedWindowError
from .settings import Settings

# The only stage allowed to read demand. One name, in one place (R12).
DEMAND_STAGE = "evaluate"

# Columns the pipeline uses, whatever the file they came from calls them.
POINT_ID = "point_id"
DATE = "date"
VARIABLE = "variable"
VALUE = "value"
PGA_ID = "pga_id"
DEMAND = "demand"

# What a real weather file must hold. Printed when a real run reaches the
# reader, so whoever wired the settings sees the shape rather than a guess.
REAL_WEATHER_SHAPE = (
    "one row per point and date, with columns "
    f"'{POINT_ID}', '{DATE}' (ISO YYYY-MM-DD) and one column per weather "
    "variable named exactly as features.variables names it"
)
REAL_DEMAND_SHAPE = (
    "one row per PGA and creation date, with columns "
    f"'{PGA_ID}', '{DATE}' (ISO YYYY-MM-DD) and '{DEMAND}', already "
    "deduplicated and day-adjusted"
)
REAL_POINTS_SHAPE = (
    f"one row per DTN virtual point, with columns '{POINT_ID}', "
    "'latitude' and 'longitude' in WGS 84 degrees"
)


@dataclass
class ReadRecord:
    """One read a stage made: what it asked for, and what the guards did."""

    stage: str
    kind: str
    path: str
    window_start: str = ""
    window_end: str = ""
    rows: int = 0
    sealed_override_used: bool = False


@dataclass
class DataSource:
    """Reads inputs on behalf of one stage, under that stage's permissions."""

    settings: Settings
    stage: str
    reads: list[ReadRecord] = field(default_factory=list)

    @classmethod
    def for_stage(cls, settings: Settings, stage: str) -> DataSource:
        """Build the source a named stage is allowed to have."""
        return cls(settings=settings, stage=stage)

    @property
    def may_read_demand(self) -> bool:
        return self.stage == DEMAND_STAGE

    @property
    def sealed_override_used(self) -> bool:
        """True when the override let this source read a sealed date (R13)."""
        return any(read.sealed_override_used for read in self.reads)

    # -- guards -------------------------------------------------------------

    def check_window(self, start: dt.date | None, end: dt.date) -> bool:
        """Refuse a window that reaches the sealed start. Returns whether the
        override was needed to let it through (R13)."""
        sealed_start = self.settings.windows.sealed_start
        if end < sealed_start:
            return False
        if self.settings.windows.sealed_override:
            return True
        raise SealedWindowError(
            f"{self.stage}: asked for data up to {end.isoformat()}, but the sealed "
            f"window starts {sealed_start.isoformat()}. The sealed window is held "
            "back for a later test. Set windows.sealed_override = true to reach it; "
            "the run then records that it was used."
        )

    def _check_dates(self, dates: pd.Series, what: str) -> bool:
        """Refuse rows dated on or after the sealed start (R13)."""
        sealed_start = pd.Timestamp(self.settings.windows.sealed_start)
        sealed = dates >= sealed_start
        if not bool(sealed.any()):
            return False
        if self.settings.windows.sealed_override:
            return True
        first = dates[sealed].min().date().isoformat()
        raise SealedWindowError(
            f"{self.stage}: {what} holds rows dated {first} and later, on or after "
            f"the sealed start {sealed_start.date().isoformat()}. Set "
            "windows.sealed_override = true to read them."
        )

    # -- readers ------------------------------------------------------------

    def read_points(self) -> pd.DataFrame:
        """The DTN point list: point_id, latitude, longitude."""
        path = self.settings.resolve(self.settings.inputs.points)
        if self.settings.data_source == "real":
            raise RealInputsNotConnectedError(
                f"the real DTN point list at {path} is not connected yet. Expected "
                f"{REAL_POINTS_SHAPE}. Confirm the file's columns before wiring it "
                "up rather than guessing them."
            )
        frame = pd.read_csv(path, dtype={POINT_ID: str})
        _require_columns(frame, [POINT_ID, "latitude", "longitude"], path)
        frame = frame.sort_values(POINT_ID).reset_index(drop=True)
        self.reads.append(
            ReadRecord(
                self.stage, "points", _relative(path, self.settings), rows=len(frame)
            )
        )
        return frame

    def read_layer(self, name: str) -> gpd.GeoDataFrame:
        """One operational layer (nca, pga or ra), with its ID column renamed."""
        layer = self.settings.layer(name)
        path = self.settings.resolve(layer.path)
        if self.settings.data_source == "real":
            raise RealInputsNotConnectedError(
                f"the real {name.upper()} layer at {path} is not connected yet. "
                "Confirm the file format, its coordinate system and its ID column "
                f"('{layer.id_column}') before wiring it up."
            )
        frame = gpd.read_file(path)
        if layer.id_column not in frame.columns:
            raise KeyError(
                f"{path}: no column '{layer.id_column}'; it holds "
                f"{', '.join(frame.columns)}"
            )
        frame = frame.rename(columns={layer.id_column: f"{name}_id"})
        frame[f"{name}_id"] = frame[f"{name}_id"].astype(str)
        frame = frame.sort_values(f"{name}_id").reset_index(drop=True)
        self.reads.append(
            ReadRecord(
                self.stage,
                f"layer:{name}",
                _relative(path, self.settings),
                rows=len(frame),
            )
        )
        return frame

    def read_weather(
        self,
        variables: list[str],
        start: dt.date | None,
        end: dt.date,
    ) -> pd.DataFrame:
        """Daily weather as point_id, date, variable, value, within the window."""
        override = self.check_window(start, end)
        path = self.settings.resolve(self.settings.inputs.weather)
        if self.settings.data_source == "real":
            raise RealInputsNotConnectedError(
                f"the real DTN weather history at {path} is not connected yet. "
                f"Expected {REAL_WEATHER_SHAPE}. Confirm the columns, the units and "
                "whether snow and gusts are available before wiring it up."
            )
        frames = []
        for variable in variables:
            file_path = Path(path) / f"weather-{variable}.csv"
            if not file_path.is_file():
                raise FileNotFoundError(
                    f"no fixture weather file for '{variable}' at {file_path}"
                )
            wide = pd.read_csv(file_path)
            _require_columns(wide, [DATE], file_path)
            wide[DATE] = pd.to_datetime(wide[DATE], format="%Y-%m-%d")
            long = wide.melt(id_vars=[DATE], var_name=POINT_ID, value_name=VALUE)
            long[VARIABLE] = variable
            frames.append(long)
        weather = pd.concat(frames, ignore_index=True)
        weather[POINT_ID] = weather[POINT_ID].astype(str)
        override = self._check_dates(weather[DATE], "the weather history") or override
        keep = weather[DATE] <= pd.Timestamp(end)
        if start is not None:
            keep &= weather[DATE] >= pd.Timestamp(start)
        weather = weather.loc[keep].copy()
        weather = weather.sort_values([VARIABLE, DATE, POINT_ID]).reset_index(drop=True)
        self.reads.append(
            ReadRecord(
                self.stage,
                "weather",
                _relative(Path(path), self.settings),
                window_start=start.isoformat() if start else "earliest",
                window_end=end.isoformat(),
                rows=len(weather),
                sealed_override_used=override,
            )
        )
        return weather[[POINT_ID, DATE, VARIABLE, VALUE]]

    def read_demand(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Demand per PGA and day. Only the evaluate stage may call this (R12)."""
        if not self.may_read_demand:
            raise DemandFirewallError(
                f"stage '{self.stage}' tried to read demand. Only the "
                f"'{DEMAND_STAGE}' stage may: the map is built from weather and "
                "judged on demand, and a build stage that could see demand would "
                "make that judgement worthless."
            )
        override = self.check_window(start, end)
        path = self.settings.resolve(self.settings.inputs.demand)
        if self.settings.data_source == "real":
            raise RealInputsNotConnectedError(
                f"the real demand extract at {path} is not connected yet. Expected "
                f"{REAL_DEMAND_SHAPE}. Confirm the extract's columns and that it is "
                "already deduplicated and day-adjusted before wiring it up."
            )
        wide = pd.read_csv(path)
        _require_columns(wide, [DATE], path)
        wide[DATE] = pd.to_datetime(wide[DATE], format="%Y-%m-%d")
        long = wide.melt(id_vars=[DATE], var_name=PGA_ID, value_name=DEMAND)
        long[PGA_ID] = long[PGA_ID].astype(str)
        override = self._check_dates(long[DATE], "the demand extract") or override
        keep = (long[DATE] >= pd.Timestamp(start)) & (long[DATE] <= pd.Timestamp(end))
        long = long.loc[keep].sort_values([DATE, PGA_ID]).reset_index(drop=True)
        self.reads.append(
            ReadRecord(
                self.stage,
                "demand",
                _relative(path, self.settings),
                window_start=start.isoformat(),
                window_end=end.isoformat(),
                rows=len(long),
                sealed_override_used=override,
            )
        )
        return long


def _require_columns(frame: pd.DataFrame, needed: list[str], path: Path) -> None:
    absent = [column for column in needed if column not in frame.columns]
    if absent:
        raise KeyError(
            f"{path}: missing column(s) {', '.join(absent)}; it holds "
            f"{', '.join(map(str, frame.columns))}"
        )


def _relative(path: Path, settings: Settings) -> str:
    """Path as written in the run record: relative to the settings file if it can
    be, so no run record carries a machine-specific absolute path."""
    try:
        return str(Path(path).relative_to(settings.base_directory))
    except ValueError:
        return str(path)
