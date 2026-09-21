"""One command that runs a single stage or all seven.

    nca run all --settings tests/fixtures/nca-regionalisation/settings.toml
    nca run cluster --settings <file> --out runs/current
    nca fixture --out tests/fixtures/nca-regionalisation

Settings problems stop the run before it touches any data, and every missing
required setting is listed at once (R2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import NcaError, SettingsError
from .outputs import RunDirectory
from .pipeline import STAGES, run_all, run_stage
from .runrecord import RunRecord
from .settings import Settings

DEFAULT_OUT = "runs/current"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nca",
        description="Build candidate National Climate Areas from weather alone.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one stage, or all seven")
    run.add_argument(
        "stage",
        choices=[*STAGES, "all"],
        help="the stage to run, or 'all' for the whole pipeline in order",
    )
    run.add_argument("--settings", required=True, help="path to a TOML settings file")
    run.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"folder for this run's outputs (default: {DEFAULT_OUT})",
    )

    make = commands.add_parser(
        "fixture", help="rewrite the test fixture set from its formulas"
    )
    make.add_argument("--out", required=True, help="folder to write the fixture into")

    commands.add_parser("stages", help="list the stages in order")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "stages":
        for position, name in enumerate(STAGES, start=1):
            print(f"{position}. {name}")
        return 0

    if arguments.command == "fixture":
        from . import fixture

        for path in fixture.write(arguments.out):
            print(path)
        return 0

    try:
        settings = Settings.load(arguments.settings)
    except SettingsError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    run_directory = RunDirectory(Path(arguments.out))
    run_directory.root.mkdir(parents=True, exist_ok=True)
    record = RunRecord(settings=settings, run_directory=run_directory)
    try:
        if arguments.stage == "all":
            run_all(settings, run_directory, record)
        else:
            run_stage(arguments.stage, settings, run_directory, record)
    except NcaError as problem:
        record.log(f"error: {problem}")
        record.write()
        print(f"error: {problem}", file=sys.stderr)
        return 1
    record.write()
    print(f"done. Outputs and the run record are in {run_directory.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
