# SPDX-License-Identifier: MIT
"""Canary: a proxy estimate must not print as a measured value.

A proxy is a stand-in -- nightlights for consumption, population for demand.
When a report prints a proxy number with no marker, the reader has no way to
know it is a substitute, and the number will be quoted as if it were metered.
The whole point of Layer 6's basis rule is that this is visible on the page.

`ReportValue.basis` is *derived* from the provenance record, never supplied by
the caller. If it were a field, a caller passing `basis=MEASURED` next to a
proxy's provenance would launder it -- and the caller would not be lying on
purpose, they would be filling in a required argument.
"""

from __future__ import annotations

import subprocess
import sys

from alea.provenance.models import Basis, Licence, Provenance
from alea.reporting.schemas import (
	MARKERS,
	MEASURED_MARKER,
	PROXY_MARKER,
	ReportValue,
	as_record,
)
from tests.ci.canaries import REPO, assert_raises, planted

SCHEMAS_PY = REPO / "src" / "alea" / "reporting" / "schemas.py"


def _provenance(basis: Basis, *, uncertainty: float = 0.0) -> Provenance:
	return Provenance(
		source_id="canary",
		source_url="https://example.org/canary",
		licence=Licence.CC_BY_4_0,
		basis=basis,
		uncertainty=uncertainty,
		uncertainty_basis="proxy" if uncertainty else "",
		notes="canary",
	)


def test_a_measured_value_prints_with_no_marker():
	value = ReportValue(value=1200.0, unit="MW", provenance=_provenance(Basis.MEASURED))
	assert value.marker == MEASURED_MARKER
	assert value.marked == "1,200"


def test_a_proxy_value_is_marked():
	value = ReportValue(
		value=1200.0, unit="MW", provenance=_provenance(Basis.PROXY, uncertainty=0.3)
	)
	assert value.basis is Basis.PROXY
	assert value.marker == PROXY_MARKER
	assert value.marked.endswith(PROXY_MARKER), (
		"a proxy printed with no marker; the reader cannot tell it is a substitute"
	)


def test_a_proxy_is_not_exact():
	"""The model refuses the claim at the source, so a report cannot make it."""
	# A lambda, not `assert_raises(ValueError, _provenance, Basis.PROXY)`:
	# arguments are evaluated before the helper is entered, so the raise would
	# escape the helper and fail the test for the wrong reason.
	assert_raises(ValueError, lambda: _provenance(Basis.PROXY))


def test_one_proxy_among_measured_inputs_makes_the_result_a_proxy():
	"""The weakest-basis rule: a result is at best its worst input.

	Taking the strongest would let a single measured input launder every proxy
	that went into the same number.
	"""
	record = as_record(
		(
			_provenance(Basis.MEASURED),
			_provenance(Basis.PROXY, uncertainty=0.4),
		)
	)
	assert record.basis is Basis.PROXY
	value = ReportValue(value=10.0, unit="MW", provenance=record)
	assert value.marker == PROXY_MARKER


def test_the_caller_cannot_supply_a_basis():
	"""If `basis` were a field, a proxy could be relabelled measured.

	The dataclass has no such field, and passing one is an error rather than a
	silent override -- which is what makes the derivation trustworthy.
	"""
	import dataclasses

	fields = {f.name for f in dataclasses.fields(ReportValue)}
	assert "basis" not in fields, (
		"ReportValue gained a `basis` field; a caller can now relabel a proxy"
	)
	assert_raises(
		TypeError,
		lambda: ReportValue(
			value=1200.0,
			unit="MW",
			provenance=_provenance(Basis.PROXY, uncertainty=0.3),
			basis=Basis.MEASURED,  # type: ignore[call-arg]  # the planted defect: `basis` is derived

		),
	)


def test_every_basis_has_a_marker():
	"""A missing entry is a KeyError at render time, on a published report."""
	for basis in Basis:
		assert basis in MARKERS, f"basis {basis.value} has no marker"


def test_the_basis_is_derived_not_supplied():
	"""Canary proper: make `basis` settable and watch the laundering go through.

	Run in a subprocess. The mutation is read fresh from disk, and no reloaded
	module is left behind for the tests that follow.
	"""
	source = SCHEMAS_PY.read_text()
	target = "def basis(self) -> Basis:\n\t\t\"\"\"The weakest basis among the inputs. Derived, never supplied.\"\"\"\n\t\treturn self.record.basis"
	assert target in source, "canary target not found: the derived basis moved"

	program = (
		"from alea.provenance.models import Basis, Provenance\n"
		"from alea.reporting.schemas import PROXY_MARKER, ReportValue\n"
		"p = Provenance(source_id='s', basis=Basis.PROXY, uncertainty=0.3,\n"
		"  uncertainty_basis='proxy')\n"
		"v = ReportValue(value=1.0, unit='MW', provenance=p)\n"
		"print(PROXY_MARKER if v.marker else 'unmarked')\n"
	)

	def marker() -> str:
		completed = subprocess.run(
			[sys.executable, "-c", program], capture_output=True, text=True, check=False
		)
		assert completed.returncode == 0, completed.stderr
		return completed.stdout.strip()

	assert marker() == PROXY_MARKER, "the proxy was unmarked before any mutation"

	# A basis that always reports measured is the laundering the canary plants.
	laundered = (
		"def basis(self) -> Basis:\n"
		"\t\t\"\"\"The weakest basis among the inputs. Derived, never supplied.\"\"\"\n"
		"\t\treturn Basis.MEASURED"
	)
	with planted(SCHEMAS_PY, target, laundered):
		assert marker() == "unmarked", (
			"a proxy still printed its marker under a basis that always returns "
			"measured; the canary did not reproduce the laundering"
		)

	# Restored: the proxy is marked again.
	assert marker() == PROXY_MARKER
