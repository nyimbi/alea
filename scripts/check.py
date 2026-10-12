#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The one place the checks are defined. Run everything locally.

    uv run python scripts/check.py            # everything
    uv run python scripts/check.py tests lint # just these groups
    uv run python scripts/check.py --list

CI calls this and nothing else. A second definition of "the checks" in a
workflow YAML drifts from this one, and the drift is invisible until a check
that passes locally fails on push for a reason nobody can reproduce.

Three properties this runner has to have, each because its absence failed
somewhere before:

* **It exits non-zero when a group fails.** A dispatcher that fails open is the
  one failure a gate may not have.
* **It reads the verdict from the process return code, never from parsed
  output.** `pytest | tail -N` returns tail's exit code and cuts the summary
  line, which is the last line. Output here goes to a log file and the console;
  the exit code is the verdict.
* **Its group list is not named `GROUPS`.** That is a special bash variable
  holding the caller's group IDs, so the assignment is silently ignored and the
  loop iterates numeric GIDs -- a runner that prints "all steps passed" having
  run none of them.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "tmp" / "check-logs"

# The six library crates. `alea-python` is an `extension-module` crate and does
# not link under a bare `cargo test` -- it needs maturin's `-undefined
# dynamic_lookup`.
RUST_CRATES = [
	"alea-common",
	"alea-rasters",
	"alea-dedup",
	"alea-series",
	"alea-losses",
	"alea-risk",
]


@dataclass
class Group:
	name: str
	argv: list[str]
	why: str
	env: dict[str, str] = field(default_factory=dict)


def _uv(*args: str) -> list[str]:
	"""Run through uv so the check uses the project environment, not the ambient one."""
	return ["uv", "run", *args]


def groups() -> list[Group]:
	"""Every check, in the order a failure should be seen.

	Cheap and structural first: a lint failure twenty seconds in is a better
	experience than the same failure after a four-minute solve.
	"""
	return [
		Group(
			"lint",
			_uv("ruff", "check", "src", "tests", "scripts"),
			"style and import order",
		),
		# No `ruff format --check` group, deliberately. `ruff format` always emits
		# spaces and this project's standard is tabs, so the check can never pass
		# on any file; the fix it offers would rewrite the whole tree against the
		# convention. `E101`/`W191` are ignored in `[tool.ruff.lint]` for the same
		# reason -- the tab convention is intentional, and a gate that cannot pass
		# teaches everyone to bypass it.
		Group(
			"rustfmt",
			["cargo", "fmt", "--all", "--check"],
			"Rust formatting",
		),
		Group(
			"clippy",
			["cargo", "clippy", "--workspace", "--all-targets", "--", "-D", "warnings"],
			"Rust lints; -D warnings so a warning is a failure",
		),
		Group(
			"rust",
			["cargo", "test", *[arg for c in RUST_CRATES for arg in ("-p", c)]],
			"the six Rust library crates",
		),
		Group(
			"types",
			_uv("pyright"),
			"type checking",
		),
		Group(
			"tests",
			_uv("pytest", "-q", "tests/ci"),
			"the CI suite",
		),
		Group(
			"canaries",
			_uv("pytest", "-q", "tests/ci/canaries"),
			"every gate must be seen to fail on its planted defect",
		),
		# `scripts/gate_register.py --check` belongs here and is deliberately not
		# yet: it currently reports 39 unimplemented and 20 uncanaried gates, and
		# wiring a group that cannot pass teaches everyone to bypass the runner.
		# It becomes a group the moment the register reports zero, which is the
		# same condition `12-quality.md` §9 criteria 2 and 7 name.
		Group(
			"determinism",
			[sys.executable, str(ROOT / "scripts" / "determinism.py")],
			"two separate processes must produce byte-identical output",
		),
	]


def run(group: Group, *, verbose: bool) -> tuple[bool, float, Path]:
	"""Run one group. Return (passed, seconds, log path)."""
	assert group.argv, f"group {group.name} has no command"
	LOGS.mkdir(parents=True, exist_ok=True)
	log_path = LOGS / f"{group.name}.log"
	env = {**os.environ, "PYTHONHASHSEED": "0", **group.env}
	start = time.perf_counter()
	with log_path.open("w") as handle:
		completed = subprocess.run(
			group.argv,
			cwd=ROOT,
			env=env,
			stdout=handle,
			stderr=subprocess.STDOUT,
			check=False,
		)
	seconds = time.perf_counter() - start
	# The verdict is the return code. Not a grep of the log: the log is for the
	# human who has to read what went wrong.
	passed = completed.returncode == 0
	if verbose or not passed:
		text = log_path.read_text(errors="replace")
		if not verbose:
			# On failure show the tail, which is where pytest and cargo put the
			# summary. `tail` here is safe because the verdict is already known.
			lines = text.splitlines()
			text = "\n".join(lines[-40:])
		sys.stdout.write(text)
		if text and not text.endswith("\n"):
			sys.stdout.write("\n")
	return passed, seconds, log_path


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("names", nargs="*", help="Groups to run; all of them when omitted.")
	parser.add_argument("--list", action="store_true", help="List the groups and exit.")
	parser.add_argument("-v", "--verbose", action="store_true", help="Stream every group's output.")
	parser.add_argument("--keep-going", action="store_true", default=True, help="Run every group even after a failure.")
	args = parser.parse_args(argv)

	all_groups = groups()
	if args.list:
		for group in all_groups:
			print(f"{group.name:14} {' '.join(group.argv)}")
		return 0

	selected = all_groups
	if args.names:
		by_name = {g.name: g for g in all_groups}
		unknown = [n for n in args.names if n not in by_name]
		if unknown:
			print(f"unknown group(s): {', '.join(unknown)}", file=sys.stderr)
			print(f"known: {', '.join(by_name)}", file=sys.stderr)
			return 2
		selected = [by_name[n] for n in args.names]

	if shutil.which("uv") is None:
		print("uv is not on PATH; install it first (see README)", file=sys.stderr)
		return 2

	print(f"running {len(selected)} group(s) from {ROOT}")
	failures: list[str] = []
	started = time.perf_counter()
	for group in selected:
		print(f"  {group.name:<14} ... ", end="", flush=True)
		passed, seconds, log_path = run(group, verbose=args.verbose)
		mark = "ok" if passed else "FAIL"
		print(f"{mark:>4}  {seconds:6.1f}s  {group.why}")
		if not passed:
			failures.append(group.name)
			print(f"       log: {log_path.relative_to(ROOT)}")
	total = time.perf_counter() - started

	print()
	if failures:
		print(f"FAILED ({len(failures)}/{len(selected)}): {', '.join(failures)}  [{total:.1f}s]")
		return 1
	print(f"all {len(selected)} group(s) passed  [{total:.1f}s]")
	return 0


if __name__ == "__main__":
	sys.exit(main())
