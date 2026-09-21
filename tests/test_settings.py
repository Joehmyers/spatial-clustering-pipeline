"""Settings: a real run refuses unset required settings and lists them all."""

from __future__ import annotations

import pytest

from nca.cli import main
from nca.errors import SettingsError
from nca.settings import Settings

# Every setting R2 marks required, by the name a problem message uses.
REQUIRED = (
    "layers.nca.path",
    "layers.nca.id_column",
    "layers.pga.path",
    "layers.pga.id_column",
    "layers.ra.path",
    "layers.ra.id_column",
    "inputs.points",
    "inputs.weather",
    "inputs.demand",
    "cluster.number_of_regions",
    "cluster.cuts_to_save",
)


def test_a_real_run_with_nothing_set_lists_every_missing_setting():
    with pytest.raises(SettingsError) as raised:
        Settings.from_mapping({"data_source": "real"})
    problems = "\n".join(raised.value.problems)
    for name in REQUIRED:
        assert name in problems, f"{name} was not reported as missing"
    assert len(raised.value.problems) == len(REQUIRED)


def test_the_command_stops_before_doing_any_work_and_says_what_is_missing(
    tmp_path, capsys
):
    settings_file = tmp_path / "real.toml"
    settings_file.write_text('data_source = "real"\n', encoding="utf-8")
    out = tmp_path / "out"

    arguments = ["run", "all", "--settings", str(settings_file), "--out", str(out)]
    assert main(arguments) == 2

    printed = capsys.readouterr().err
    for name in REQUIRED:
        assert name in printed
    assert not out.exists(), "the run created output before checking its settings"


def test_the_fixture_settings_load(fixture_settings):
    assert fixture_settings.data_source == "fixture"
    assert fixture_settings.cluster.number_of_regions == 2
    assert fixture_settings.cuts == (2, 3)
    assert fixture_settings.graph.manual_links == (("P18", "P12"),)
    assert fixture_settings.features.missing_data == "drop_day"
    assert fixture_settings.features.transforms["rain"] == "log1p"
    assert fixture_settings.features.transforms["tmin"] == "none"


def test_the_defaults_are_the_ones_the_spec_gives(fixture_settings):
    assert fixture_settings.coordinates.working_crs == "EPSG:27700"
    assert fixture_settings.coordinates.input_crs == "EPSG:4326"
    assert fixture_settings.graph.neighbour_rule == "rook"
    assert fixture_settings.graph.minimum_shared_edge_metres == 1.0
    assert fixture_settings.graph.clipping_outline == "ra"
    assert fixture_settings.features.normal_smoothing_days == 31
    assert fixture_settings.features.national_mean == "plain"
    assert fixture_settings.mapping.rule == "area_majority"
    assert fixture_settings.mapping.repair_stranded_pgas is True
    assert fixture_settings.cluster.unconstrained_diagnostic is True
    assert fixture_settings.evaluate.random_partitions == 500


def test_an_unknown_setting_is_refused_rather_than_ignored():
    with pytest.raises(SettingsError) as raised:
        Settings.from_mapping({"clustr": {"number_of_regions": 2}})
    assert any("clustr" in problem for problem in raised.value.problems)


def test_a_held_out_window_inside_the_build_window_is_refused():
    with pytest.raises(SettingsError) as raised:
        Settings.from_mapping({"windows": {"held_out_start": "2024-01-01"}})
    assert any("held_out_start" in problem for problem in raised.value.problems)
