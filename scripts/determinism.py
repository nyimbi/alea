#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the determinism fixture twice, in two processes, and diff the output.

Separate processes is the point, not an implementation detail. Every defect this
catches is interpreter-state-dependent:

* `hash()` of a string is salted per process, so a cache keyed on it agrees
  within a run and disagrees across runs.
* An unseeded MinHash agrees within a run for the same reason.
* Iterating a set agrees within a run only because the set was built the same
  way in that interpreter.

A same-process test -- call the function twice, compare -- passes against all
three. The only way to see them is two interpreters.

`PYTHONHASHSEED=0` is pinned as well. It does not fix those defects, it stops
*unrelated* set-ordering noise from making the diff fail for a reason that is
not a defect, which would train everyone to ignore it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_once(out: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
	assert out, "an output directory is required"
	return subprocess.run(
		[sys.executable, "-m", "tests.determinism.run", "--out", str(out)],
		cwd=ROOT,
		env=env,
		capture_output=True,
		text=True,
		check=False,
	)


def main() -> int:
	env = {**os.environ, "PYTHONHASHSEED": "0"}
	work = Path(tempfile.mkdtemp(prefix="alea-determinism-"))
	first, second = work / "run1", work / "run2"
	try:
		for label, out in (("run1", first), ("run2", second)):
			result = run_once(out, env)
			if result.returncode != 0:
				sys.stderr.write(f"{label} failed (exit {result.returncode}):\n{result.stdout}{result.stderr}\n")
				return 1
			print(f"  {label}: {result.stdout.strip()[:200]}")

		# `diff -r` on the two trees. Any difference at all is a failure: the
		# point of the check is that the bytes match, and a tolerance here would
		# have to be argued for each field separately, which is how a
		# nondeterminism gets grandfathered in.
		diff = subprocess.run(
			["diff", "-r", str(first), str(second)],
			capture_output=True,
			text=True,
			check=False,
		)
		if diff.returncode != 0:
			sys.stderr.write(
				"two runs of the same fixture differ; a published number is not "
				f"reproducible\n{diff.stdout}{diff.stderr}\n"
			)
			return 1
		print("  identical across two processes")
		return 0
	finally:
		shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
	sys.exit(main())
