# SPDX-License-Identifier: MIT
"""Entry point the CLI and the workflow layer call.

``alea.cli`` imports ``build_report`` from here, and the plan's module layout
puts the main logic in ``service.py``. This module is the seam between the
two: it re-exports the one function the CLI names so the command line does not
have to know the internal layout, and so a future change to where the logic
lives does not move the import the CLI depends on.
"""

from __future__ import annotations

from alea.reporting.service import (
	BuildResult,
	build_report,
	cadence_specs,
	validate_reporting_config,
)

__all__ = ["BuildResult", "build_report", "cadence_specs", "validate_reporting_config"]
