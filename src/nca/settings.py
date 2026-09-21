"""Every setting the pipeline reads, with the default the spec gives it (R2).

Nothing in the pipeline hard-codes a value that appears here. A settings file
is TOML; it overrides these defaults key by key. Settings marked required have
no default: a run refuses to start until they are set, and it lists every
missing one at once rather than failing on the first.

Paths in a settings file are read relative to the file's own folder, so a
settings file and the data it points at move together and no absolute path is
ever committed.
"""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .errors import SettingsError

# The variables the spec names, in the order every output uses.
DEFAULT_VARIABLES = ("tmin", "tmax", "rain", "wind")

# Transforms applied before anything else. Rain is heavily skewed, so it goes
# through log(1 + x); the others are used as they arrive.
DEFAULT_TRANSFORMS = {"tmin": "none", "tmax": "none", "rain": "log1p", "wind": "none"}

TRANSFORM_NAMES = ("none", "log1p")
NEIGHBOUR_RULES = ("rook", "queen")
DISCONNECTED_ACTIONS = ("stop", "join_nearest", "fixed_regions")
MISSING_DATA_ACTIONS = ("stop", "drop_day", "fill_from_neighbours")
NATIONAL_MEAN_RULES = ("plain", "cell_area_weighted")
LEAP_DAY_RULES = ("use_28_february",)
MAPPING_RULES = ("area_majority",)
DATA_SOURCES = ("fixture", "real")
CLIPPING_OUTLINES = ("ra", "pga", "nca")

_REQUIRED = object()


def _parse_date(value: Any, where: str, problems: list[str]) -> dt.date | None:
    """Read an ISO date (YYYY-MM-DD), or record why it could not be read."""
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        problems.append(f"{where}: '{value}' is not an ISO date (YYYY-MM-DD)")
        return None


def _check_choice(
    value: Any, allowed: tuple[str, ...], where: str, problems: list[str]
) -> None:
    if value not in allowed:
        problems.append(f"{where}: '{value}' is not one of {', '.join(allowed)}")


@dataclass(frozen=True)
class LayerSetting:
    """One operational layer: its file, its ID column, and its parent's ID.

    parent_id_column names the column that says which unit above this one each
    shape belongs to: the PGA an RA sits in, the NCA a PGA sits in. Leave it
    empty when the layer does not carry it; the geometry stage then checks
    nesting by overlay alone and says so in its report.
    """

    path: str = ""
    id_column: str = ""
    parent_id_column: str = ""


@dataclass(frozen=True)
class Layers:
    """The three operational layers. Real runs need all three (R2)."""

    nca: LayerSetting = field(default_factory=LayerSetting)
    pga: LayerSetting = field(default_factory=LayerSetting)
    ra: LayerSetting = field(default_factory=LayerSetting)


@dataclass(frozen=True)
class Inputs:
    """Where the data lives. Demand is read by the evaluate stage alone (R12)."""

    points: str = ""
    weather: str = ""
    demand: str = ""


@dataclass(frozen=True)
class Coordinates:
    """Points arrive in latitude and longitude; every length is metres (R2)."""

    input_crs: str = "EPSG:4326"
    working_crs: str = "EPSG:27700"


@dataclass(frozen=True)
class Windows:
    """The three date windows. Normals and scaling come from the build window."""

    build_start: dt.date | None = None  # None means "earliest data"
    build_end: dt.date = dt.date(2024, 8, 31)
    held_out_start: dt.date = dt.date(2024, 9, 1)
    held_out_end: dt.date = dt.date(2025, 8, 31)
    sealed_start: dt.date = dt.date(2025, 9, 1)
    sealed_override: bool = False


@dataclass(frozen=True)
class GraphSettings:
    """How Voronoi cells become a neighbour graph (R4)."""

    neighbour_rule: str = "rook"
    minimum_shared_edge_metres: float = 1.0
    clipping_outline: str = "ra"
    disconnected_parts: str = "stop"
    manual_links: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FeatureSettings:
    """How raw weather becomes a regional anomaly, z-scored per point (R5)."""

    variables: tuple[str, ...] = DEFAULT_VARIABLES
    transforms: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TRANSFORMS))
    normal_smoothing_days: int = 31
    leap_day: str = "use_28_february"
    national_mean: str = "plain"
    missing_data: str = "stop"


@dataclass(frozen=True)
class ClusterSettings:
    """The tree, where to cut it, and the diagnostics to run beside it (R6, R7)."""

    number_of_regions: int = 0  # required: today's NCA count
    cuts_to_save: tuple[int, ...] = ()  # required
    unconstrained_diagnostic: bool = True
    sensitivity_sets: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "temperature_only": ("tmin", "tmax"),
            "all_variables": DEFAULT_VARIABLES,
        }
    )


@dataclass(frozen=True)
class MappingSettings:
    """How point clusters become whole PGAs (R8)."""

    rule: str = "area_majority"
    repair_stranded_pgas: bool = True


@dataclass(frozen=True)
class EvaluateSettings:
    """The held-out comparison, and the random benchmark it sits against (R9)."""

    demand_measure: str = "created_demand_deduplicated"
    random_partitions: int = 500
    seed: int = 20260921


@dataclass(frozen=True)
class Settings:
    """The whole configuration for one run."""

    data_source: str = "fixture"
    layers: Layers = field(default_factory=Layers)
    inputs: Inputs = field(default_factory=Inputs)
    coordinates: Coordinates = field(default_factory=Coordinates)
    windows: Windows = field(default_factory=Windows)
    graph: GraphSettings = field(default_factory=GraphSettings)
    features: FeatureSettings = field(default_factory=FeatureSettings)
    cluster: ClusterSettings = field(default_factory=ClusterSettings)
    mapping: MappingSettings = field(default_factory=MappingSettings)
    evaluate: EvaluateSettings = field(default_factory=EvaluateSettings)
    # Folder the settings file sat in; every relative path hangs off it.
    base_directory: Path = field(default_factory=Path)
    source_file: str = ""

    # -- construction -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> Settings:
        """Read a TOML settings file and check it. Raises SettingsError."""
        settings_path = Path(path).resolve()
        if not settings_path.is_file():
            raise SettingsError([f"settings file not found: {settings_path}"])
        with settings_path.open("rb") as handle:
            raw = tomllib.load(handle)
        return cls.from_mapping(
            raw,
            base_directory=settings_path.parent,
            source_file=settings_path.name,
        )

    @classmethod
    def from_mapping(
        cls,
        raw: dict[str, Any],
        base_directory: Path | None = None,
        source_file: str = "",
    ) -> Settings:
        """Build settings from a plain dictionary, then check them."""
        problems: list[str] = []
        known_top = {f.name for f in fields(cls)} - {"base_directory", "source_file"}
        for key in raw:
            if key not in known_top:
                problems.append(f"unknown setting section or key: '{key}'")

        data_source = raw.get("data_source", "fixture")
        _check_choice(data_source, DATA_SOURCES, "data_source", problems)

        layers = cls._read_layers(raw.get("layers", {}), problems)
        inputs = Inputs(
            **_only_known(Inputs, raw.get("inputs", {}), "inputs", problems)
        )
        coordinates = Coordinates(
            **_only_known(
                Coordinates, raw.get("coordinates", {}), "coordinates", problems
            )
        )
        windows = cls._read_windows(raw.get("windows", {}), problems)
        graph = cls._read_graph(raw.get("graph", {}), problems)
        features = cls._read_features(raw.get("features", {}), problems)
        cluster = cls._read_cluster(raw.get("cluster", {}), features, problems)
        mapping_raw = _only_known(
            MappingSettings, raw.get("mapping", {}), "mapping", problems
        )
        mapping = MappingSettings(**mapping_raw)
        _check_choice(mapping.rule, MAPPING_RULES, "mapping.rule", problems)
        evaluate = EvaluateSettings(
            **_only_known(
                EvaluateSettings, raw.get("evaluate", {}), "evaluate", problems
            )
        )
        if evaluate.random_partitions < 1:
            problems.append("evaluate.random_partitions: must be 1 or more")

        settings = cls(
            data_source=str(data_source),
            layers=layers,
            inputs=inputs,
            coordinates=coordinates,
            windows=windows,
            graph=graph,
            features=features,
            cluster=cluster,
            mapping=mapping,
            evaluate=evaluate,
            base_directory=Path(base_directory or Path.cwd()).resolve(),
            source_file=source_file,
        )
        problems.extend(settings._missing_required())
        problems.extend(settings._window_problems())
        if problems:
            raise SettingsError(problems)
        return settings

    @staticmethod
    def _read_layers(raw: dict[str, Any], problems: list[str]) -> Layers:
        parts: dict[str, LayerSetting] = {}
        for name in ("nca", "pga", "ra"):
            body = raw.get(name, {})
            if not isinstance(body, dict):
                problems.append(
                    f"layers.{name}: expected a table with path and id_column"
                )
                body = {}
            parts[name] = LayerSetting(
                **_only_known(LayerSetting, body, f"layers.{name}", problems)
            )
        for key in raw:
            if key not in ("nca", "pga", "ra"):
                problems.append(f"unknown setting: layers.{key}")
        return Layers(**parts)

    @staticmethod
    def _read_windows(raw: dict[str, Any], problems: list[str]) -> Windows:
        body = _only_known(Windows, raw, "windows", problems)
        defaults = Windows()
        for name in (
            "build_start",
            "build_end",
            "held_out_start",
            "held_out_end",
            "sealed_start",
        ):
            if name in body:
                parsed = _parse_date(body[name], f"windows.{name}", problems)
                if parsed is None and name != "build_start":
                    body[name] = getattr(defaults, name)
                else:
                    body[name] = parsed
        if "sealed_override" in body and not isinstance(body["sealed_override"], bool):
            problems.append("windows.sealed_override: must be true or false")
            body["sealed_override"] = False
        return Windows(**body)

    @staticmethod
    def _read_graph(raw: dict[str, Any], problems: list[str]) -> GraphSettings:
        body = _only_known(GraphSettings, raw, "graph", problems)
        links = body.get("manual_links", ())
        pairs: list[tuple[str, str]] = []
        for index, link in enumerate(links):
            if not isinstance(link, (list, tuple)) or len(link) != 2:
                problems.append(
                    f"graph.manual_links[{index}]: expected a pair of point IDs"
                )
                continue
            first, second = str(link[0]), str(link[1])
            if first == second:
                problems.append(
                    f"graph.manual_links[{index}]: a point cannot link to itself"
                )
                continue
            pairs.append((first, second))
        body["manual_links"] = tuple(pairs)
        graph = GraphSettings(**body)
        _check_choice(
            graph.neighbour_rule, NEIGHBOUR_RULES, "graph.neighbour_rule", problems
        )
        _check_choice(
            graph.disconnected_parts,
            DISCONNECTED_ACTIONS,
            "graph.disconnected_parts",
            problems,
        )
        _check_choice(
            graph.clipping_outline,
            CLIPPING_OUTLINES,
            "graph.clipping_outline",
            problems,
        )
        if graph.minimum_shared_edge_metres <= 0:
            problems.append("graph.minimum_shared_edge_metres: must be above zero")
        return graph

    @staticmethod
    def _read_features(raw: dict[str, Any], problems: list[str]) -> FeatureSettings:
        body = _only_known(FeatureSettings, raw, "features", problems)
        if "variables" in body:
            body["variables"] = tuple(str(name) for name in body["variables"])
        variables = body.get("variables", DEFAULT_VARIABLES)
        transforms = dict(DEFAULT_TRANSFORMS)
        given = body.get("transforms", {})
        transforms.update({str(k): str(v) for k, v in given.items()})
        body["transforms"] = {name: transforms.get(name, "none") for name in variables}
        features = FeatureSettings(**body)
        if not features.variables:
            problems.append("features.variables: at least one variable is needed")
        for name, transform in features.transforms.items():
            _check_choice(
                transform, TRANSFORM_NAMES, f"features.transforms.{name}", problems
            )
        _check_choice(features.leap_day, LEAP_DAY_RULES, "features.leap_day", problems)
        _check_choice(
            features.national_mean,
            NATIONAL_MEAN_RULES,
            "features.national_mean",
            problems,
        )
        _check_choice(
            features.missing_data,
            MISSING_DATA_ACTIONS,
            "features.missing_data",
            problems,
        )
        smoothing = features.normal_smoothing_days
        if smoothing < 1 or smoothing % 2 == 0:
            problems.append(
                "features.normal_smoothing_days: must be an odd number of days, so "
                "the window sits evenly either side of the day it smooths"
            )
        return features

    @staticmethod
    def _read_cluster(
        raw: dict[str, Any], features: FeatureSettings, problems: list[str]
    ) -> ClusterSettings:
        body = _only_known(ClusterSettings, raw, "cluster", problems)
        if "cuts_to_save" in body:
            body["cuts_to_save"] = tuple(sorted({int(k) for k in body["cuts_to_save"]}))
        if "sensitivity_sets" in body:
            body["sensitivity_sets"] = {
                str(name): tuple(str(v) for v in values)
                for name, values in body["sensitivity_sets"].items()
            }
        cluster = ClusterSettings(**body)
        if any(k < 2 for k in cluster.cuts_to_save):
            problems.append("cluster.cuts_to_save: every cut must be 2 or more")
        known = set(features.variables)
        for name, values in cluster.sensitivity_sets.items():
            unknown = [v for v in values if v not in known]
            if unknown:
                problems.append(
                    f"cluster.sensitivity_sets.{name}: "
                    f"{', '.join(unknown)} not in features.variables"
                )
        return cluster

    # -- checks -------------------------------------------------------------

    def _missing_required(self) -> list[str]:
        """List every required setting still unset, so one run reports them all."""
        missing: list[str] = []
        for name in ("nca", "pga", "ra"):
            layer: LayerSetting = getattr(self.layers, name)
            if not layer.path:
                missing.append(
                    f"layers.{name}.path is required (the {name.upper()} layer file)"
                )
            if not layer.id_column:
                missing.append(
                    f"layers.{name}.id_column is required (the column "
                    f"holding each {name.upper()} ID)"
                )
        if not self.inputs.points:
            missing.append("inputs.points is required (point ID, latitude, longitude)")
        if not self.inputs.weather:
            missing.append("inputs.weather is required (daily weather per point)")
        if not self.inputs.demand:
            missing.append(
                "inputs.demand is required (read by the evaluate stage alone)"
            )
        if self.cluster.number_of_regions < 2:
            missing.append(
                "cluster.number_of_regions is required: today's NCA count, 2 or more"
            )
        if not self.cluster.cuts_to_save:
            missing.append(
                "cluster.cuts_to_save is required: the cuts to save, for "
                "example today's count plus or minus 2"
            )
        return missing

    def _window_problems(self) -> list[str]:
        problems: list[str] = []
        windows = self.windows
        if windows.build_start and windows.build_start > windows.build_end:
            problems.append("windows.build_start is after windows.build_end")
        if windows.held_out_start <= windows.build_end:
            problems.append(
                "windows.held_out_start must fall after windows.build_end, or the "
                "held-out window is not held out"
            )
        if windows.held_out_end < windows.held_out_start:
            problems.append("windows.held_out_end is before windows.held_out_start")
        if windows.sealed_start <= windows.held_out_end:
            problems.append("windows.sealed_start must fall after windows.held_out_end")
        return problems

    # -- use ----------------------------------------------------------------

    def resolve(self, path: str) -> Path:
        """Turn a settings path into an absolute one, relative to the file."""
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return (self.base_directory / candidate).resolve()

    def layer(self, name: str) -> LayerSetting:
        return getattr(self.layers, name)

    @property
    def cuts(self) -> tuple[int, ...]:
        """Every cut to save, with today's NCA count always among them.

        The headline cut is what the evaluate stage compares today's map
        against, so it is saved whether or not the settings list it.
        """
        asked_for = set(self.cluster.cuts_to_save)
        asked_for.add(self.cluster.number_of_regions)
        return tuple(sorted(asked_for))

    def to_mapping(self) -> dict[str, Any]:
        """A plain dictionary of every setting, for the run record (R15)."""
        return _to_plain(self)


def _only_known(cls: type, raw: Any, where: str, problems: list[str]) -> dict[str, Any]:
    """Copy the keys a dataclass knows; record every key it does not."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected a table of settings")
        return {}
    known = {f.name for f in fields(cls)}
    body: dict[str, Any] = {}
    for key, value in raw.items():
        if key in known:
            body[key] = value
        else:
            problems.append(f"unknown setting: {where}.{key}")
    return body


def _to_plain(value: Any) -> Any:
    """Turn dataclasses, dates, tuples and paths into JSON-ready values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    return value
