# SPDX-License-Identifier: MIT
"""Canary: a signal that has not been reviewed must not reach a model.

The scanning layer's human-in-the-loop principle is one line of enforcement:
`integrate` refuses any signal whose `requires_review` is true. `requires_review`
defaults to `True`, so the default is the safe one and the refusal is the only
thing standing between a model and an unreviewed claim from a news article.

Delete that branch and every extracted signal flows into the model on the next
pipeline run. Nothing downstream can tell -- a proposal is a proposal, and the
staged artefact records a source that was never confirmed.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime

from alea.scanning.integrate import UnreviewedSignalError, integrate
from alea.signals.models import Signal, SignalType
from tests.ci.canaries import REPO, assert_raises, planted

INTEGRATE_PY = REPO / "src" / "alea" / "scanning" / "integrate.py"


def _signal(**overrides: object) -> Signal:
	base: dict[str, object] = {
		"signal_type": SignalType.GENERATION_INVESTMENT,
		"confidence": 0.8,
		"source_document_id": "doc-1",
		"source_url": "https://example.org/plant",
		"source_name": "example.org",
		"country_iso": "KE",
		"capacity_mw": 200.0,
		"technology": "solar",
		"requires_review": False,
	}
	base.update(overrides)
	return Signal(**base)


def test_the_default_is_to_require_review():
	"""The safe default is what makes the refusal the only enforcement point.

	If `requires_review` defaulted False, every signal built without thinking
	about it would be integrable and the gate below would never fire in practice.
	"""
	signal = _signal(requires_review=True)
	assert signal.requires_review is True
	assert Signal.model_fields["requires_review"].default is True


def test_an_unreviewed_signal_is_refused():
	error = assert_raises(UnreviewedSignalError, integrate, _signal(requires_review=True))
	message = str(error)
	assert "has not been reviewed" in message
	assert "signal_id" in message or "signal" in message


def test_a_reviewed_signal_is_integrated():
	"""The control. Without this, the refusal above could be a broken function."""
	proposal = integrate(_signal(requires_review=False))
	assert proposal.status in {"staged", "conflict", "refused"}
	assert proposal.signal_id


def test_a_conflicting_signal_is_not_staged():
	"""The second gate: a news figure must not overwrite a curated dataset."""
	proposal = integrate(
		_signal(requires_review=False, capacity_mw=500.0),
		known_values={"capacity_mw": 200.0},
	)
	assert proposal.status == "conflict", (
		"a signal 150% above the dataset was not recorded as a conflict; "
		"auto-applying it degrades the model invisibly"
	)


def test_the_review_check_is_what_refuses():
	"""Canary proper: remove the branch and watch the refusal go blind.

	Run in a **subprocess**, not with `importlib.reload`. Reloading rebinds the
	module's exception classes, so the `UnreviewedSignalError` this test module
	imported is no longer the one the reloaded module raises, and every later
	test comparing against the imported name fails for a reason that has nothing
	to do with the gate. A subprocess is also the honest shape: the mutation is
	read fresh from disk by an interpreter that never saw the original.
	"""
	source = INTEGRATE_PY.read_text()
	target = "\tif signal.requires_review:"
	assert target in source, "canary target not found: the review branch moved"

	program = (
		"import json,sys\n"
		"from alea.scanning.integrate import integrate\n"
		"from alea.signals.models import Signal, SignalType\n"
		"signal = Signal(signal_type=SignalType.GENERATION_INVESTMENT, confidence=0.8,\n"
		"  source_document_id='doc-1', source_url='https://example.org/p',\n"
		"  source_name='example.org', country_iso='KE', capacity_mw=200.0,\n"
		"  requires_review=True)\n"
		"print(integrate(signal).signal_id)\n"
	)

	def run() -> subprocess.CompletedProcess[str]:
		return subprocess.run(
			[sys.executable, "-c", program],
			capture_output=True,
			text=True,
			check=False,
		)

	before = run()
	assert before.returncode != 0, (
		"an unreviewed signal was integrated before any mutation; the gate was "
		"already blind"
	)
	assert "has not been reviewed" in before.stderr

	with planted(INTEGRATE_PY, target, "\tif False:  # canary"):
		during = run()
		assert during.returncode == 0, (
			f"the unreviewed signal was still refused with the branch removed: "
			f"{during.stderr}"
		)
		assert during.stdout.strip(), "no proposal id was printed"

	# Restored: the gate works again, in a fresh interpreter.
	after = run()
	assert after.returncode != 0, "the gate did not come back after the canary was restored"
	assert "has not been reviewed" in after.stderr


def test_the_gate_reads_the_flag_rather_than_the_clock():
	"""An old signal is not a reviewed one.

	Time is not review. A gate that admitted anything extracted more than a day
	ago would pass a news figure through on the strength of its date.
	"""
	old = _signal(requires_review=True, extracted_at=datetime(2019, 1, 1))
	assert_raises(UnreviewedSignalError, integrate, old)
