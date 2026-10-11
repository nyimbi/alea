# SPDX-License-Identifier: MIT
"""Repository paths.

One place that knows where the repository root is. Every other module asks here
rather than counting ``..`` segments, because a path built from a module's own
depth breaks the moment the module moves.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_MARKERS = ("pyproject.toml", "Cargo.toml")


@lru_cache(maxsize=1)
def repo_root() -> Path:
	"""The repository root.

	Resolved by walking up from this file to the first directory containing
	``pyproject.toml``. ``ALEA_ROOT`` overrides it, which is what lets a test
	or a container run against a scratch tree without moving code.
	"""
	override = os.environ.get("ALEA_ROOT")
	if override:
		root = Path(override).expanduser().resolve()
		if not (root / "pyproject.toml").exists():
			raise RuntimeError(f"ALEA_ROOT={override!r} has no pyproject.toml")
		return root

	here = Path(__file__).resolve()
	for candidate in (here, *here.parents):
		if any((candidate / marker).exists() for marker in _MARKERS):
			return candidate
	raise RuntimeError(
		f"no repository root found above {here}; set ALEA_ROOT to override"
	)


def resolve(path: str | Path) -> Path:
	"""Resolve a config path against the repository root.

	An absolute path is returned unchanged. A relative one is joined to the
	root, so a config saying ``data/raw`` means the same thing regardless of
	the working directory a command was invoked from.
	"""
	p = Path(path).expanduser()
	return p if p.is_absolute() else repo_root() / p


def config_dir() -> Path:
	return repo_root() / "config"


def default_config_path() -> Path:
	return config_dir() / "config.default.yaml"


def scenario_path(name: str) -> Path:
	return config_dir() / "scenarios" / f"{name}.yaml"


__all__ = [
	"config_dir",
	"default_config_path",
	"repo_root",
	"resolve",
	"scenario_path",
]
