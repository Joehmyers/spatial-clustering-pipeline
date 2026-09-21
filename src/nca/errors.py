"""Errors the pipeline raises, one class per guardrail it protects.

Each class names the rule that was broken, so a caller can catch exactly the
failure it knows how to handle instead of matching on message text.
"""

from __future__ import annotations


class NcaError(Exception):
    """Base class for every error this package raises."""


class SettingsError(NcaError):
    """A setting is missing, or holds a value the pipeline cannot use."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        body = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(
            f"{len(self.problems)} setting problem(s); fix all of them:\n{body}"
        )


class DemandFirewallError(NcaError):
    """A stage other than evaluate tried to read demand (R12).

    The map is built from weather and judged on demand. A build stage that
    could see demand would make that judgement worthless, so the read fails
    rather than returning data.
    """


class SealedWindowError(NcaError):
    """Data on or after the sealed window start was requested (R13).

    The sealed window is held back for a later, honest test. Set the
    sealed-window override to reach it; the run then records that it was used.
    """


class MissingDataError(NcaError):
    """Weather rows are missing and the missing-data setting says stop (R16)."""


class DisconnectedGraphError(NcaError):
    """The neighbour graph falls into more than one piece (R4, R6).

    Constrained Ward needs one connected graph. Some implementations quietly
    add links to finish the tree, which invents neighbours that do not exist,
    so this stops the run instead.
    """


class NestingError(NcaError):
    """The operational layers do not nest: an RA or PGA has no single parent."""


class RealInputsNotConnectedError(NcaError):
    """A real run reached a reader that has no schema yet.

    The real files' shapes are described in the settings and in the message
    this carries, but nobody has confirmed them. Inventing a schema here would
    produce a run that looks fine and reads the wrong columns.
    """
