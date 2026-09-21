"""Build candidate National Climate Areas from weather alone (R1).

The pipeline clusters DTN virtual weather points into a tree, maps the
clusters onto whole Patrol Group Areas, and tests on held-out data whether
the result is more alike inside and more different between than today's map.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
