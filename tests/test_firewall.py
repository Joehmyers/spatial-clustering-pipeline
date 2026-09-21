"""Firewall: no stage but evaluate can reach the demand input (R12).

Two checks, because they catch different mistakes. The first proves a build
stage that tried to read demand would fail at run time. The second proves no
build stage even mentions the reader, so the failure can never be reached by
a path nobody thought to test.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from nca.errors import DemandFirewallError
from nca.inputs import DEMAND_STAGE, DataSource
from nca.pipeline import STAGES

BUILD_STAGES = tuple(name for name in STAGES if name != DEMAND_STAGE)
SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src" / "nca"

# Names that reach demand. A build stage must not use any of them.
DEMAND_NAMES = ("read_demand", "inputs.demand")


@pytest.mark.parametrize("stage", BUILD_STAGES)
def test_a_build_stage_cannot_read_demand_at_run_time(stage, fixture_settings):
    source = DataSource.for_stage(fixture_settings, stage)
    assert source.may_read_demand is False
    with pytest.raises(DemandFirewallError) as raised:
        source.read_demand(dt.date(2024, 9, 1), dt.date(2025, 8, 31))
    assert stage in str(raised.value)
    assert source.reads == [], "a refused read must not be recorded as a read"


def test_the_evaluate_stage_can(fixture_settings):
    source = DataSource.for_stage(fixture_settings, DEMAND_STAGE)
    assert source.may_read_demand is True
    demand = source.read_demand(dt.date(2024, 9, 1), dt.date(2025, 8, 31))
    assert not demand.empty


@pytest.mark.parametrize("stage", BUILD_STAGES)
def test_a_build_stage_never_mentions_the_demand_reader(stage):
    text = (SOURCE_DIRECTORY / f"{stage}.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    for name in DEMAND_NAMES:
        assert name not in code, (
            f"{stage}.py mentions '{name}'. Only the {DEMAND_STAGE} stage may "
            "reach demand (R12)."
        )


def test_the_full_run_reads_demand_once_and_only_from_evaluate(full_run_record):
    demand_reads = [
        read for read in full_run_record["reads"] if read["kind"] == "demand"
    ]
    assert len(demand_reads) == 1
    assert demand_reads[0]["stage"] == DEMAND_STAGE
