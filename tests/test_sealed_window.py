"""Sealed window: a request for a sealed date fails unless the override is set."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from nca.errors import SealedWindowError
from nca.inputs import DataSource

SEALED_DAY = dt.date(2025, 9, 1)
LAST_OPEN_DAY = dt.date(2025, 8, 31)


def test_a_window_reaching_the_sealed_start_is_refused(fixture_settings):
    source = DataSource.for_stage(fixture_settings, "features")
    with pytest.raises(SealedWindowError) as raised:
        source.check_window(dt.date(2024, 9, 1), SEALED_DAY)
    assert "2025-09-01" in str(raised.value)
    assert "sealed_override" in str(raised.value)


def test_a_window_stopping_before_it_is_allowed(fixture_settings):
    source = DataSource.for_stage(fixture_settings, "features")
    assert source.check_window(dt.date(2024, 9, 1), LAST_OPEN_DAY) is False


def test_the_override_lets_the_same_request_through(fixture_settings):
    windows = replace(fixture_settings.windows, sealed_override=True)
    settings = replace(fixture_settings, windows=windows)
    source = DataSource.for_stage(settings, "features")
    assert source.check_window(dt.date(2024, 9, 1), SEALED_DAY) is True


def test_reading_weather_into_the_sealed_window_is_refused(fixture_settings):
    source = DataSource.for_stage(fixture_settings, "features")
    with pytest.raises(SealedWindowError):
        source.read_weather(["tmin"], dt.date(2023, 9, 1), SEALED_DAY)


def test_reading_demand_into_the_sealed_window_is_refused(fixture_settings):
    source = DataSource.for_stage(fixture_settings, "evaluate")
    with pytest.raises(SealedWindowError):
        source.read_demand(dt.date(2024, 9, 1), SEALED_DAY)


def test_using_the_override_is_recorded(fixture_settings):
    windows = replace(fixture_settings.windows, sealed_override=True)
    settings = replace(fixture_settings, windows=windows)
    source = DataSource.for_stage(settings, "features")
    source.read_weather(["tmin"], dt.date(2023, 9, 1), SEALED_DAY)
    assert source.sealed_override_used is True
    assert source.reads[-1].sealed_override_used is True


def test_a_run_that_did_not_use_the_override_says_so(full_run_record):
    assert full_run_record["sealed_window_override_used"] is False
    assert all(
        read["sealed_override_used"] is False for read in full_run_record["reads"]
    )
