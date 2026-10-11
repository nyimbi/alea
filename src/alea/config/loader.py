# SPDX-License-Identifier: MIT
"""Configuration loading, merging, and validation.

Precedence, highest first: CLI overrides, scenario overlay, environment file,
default file, model defaults. Merging is recursive over mappings; a sequence
replaces wholesale, because a scenario that sets a list means *that* list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from alea.config.models import Config
from alea.config.paths import default_config_path, resolve, scenario_path


class ConfigError(Exception):
	"""A configuration could not be loaded, merged, or validated."""


def _read(path: Path) -> dict[str, Any]:
	"""Read one YAML config layer.

	A missing default file is not an error (the model defaults apply); a missing
	file the caller named explicitly is, because the caller believed it existed.
	"""
	if not path.exists():
		return {}
	loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
	if loaded is None:
		return {}
	if not isinstance(loaded, dict):
		raise ConfigError(f"{path}: top level must be a mapping, got {type(loaded).__name__}")
	return loaded


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
	"""Recursive merge. Mappings merge; everything else replaces.

	A shallow merge would make a scenario that sets one key silently discard its
	siblings, which is the failure mode that produces a solve with the right
	carbon price and the default planning horizons.

	Sequences replace rather than concatenate. Merging two lists element-wise
	has no defensible meaning for a config (is ``clusters: [55]`` over
	``clusters: [10, 20]`` a prefix, an append, or an override?), so the
	explicit rule is that the overlay wins.
	"""
	out = dict(base)
	for key, value in overlay.items():
		existing = out.get(key)
		if isinstance(existing, dict) and isinstance(value, dict):
			out[key] = deep_merge(existing, value)
		else:
			out[key] = value
	return out


def _coerce(value: str) -> Any:
	"""Parse a ``--set key=value`` string into a Python value.

	YAML does the parsing, so ``--set solve.solver=highs`` gives a string,
	``--set scenario.base_year=2025`` gives an int, and
	``--set solve.transmission_losses=false`` gives a bool. Parsing by hand
	would make ``false`` the truthy string ``"false"``.
	"""
	try:
		return yaml.safe_load(value)
	except yaml.YAMLError:
		return value


def parse_override(text: str) -> dict[str, Any]:
	"""Turn ``a.b.c=value`` into ``{"a": {"b": {"c": value}}}``."""
	if "=" not in text:
		raise ConfigError(f"override {text!r} is not of the form key.path=value")
	key, _, raw = text.partition("=")
	parts = [p for p in key.strip().split(".") if p]
	if not parts:
		raise ConfigError(f"override {text!r} has an empty key")

	node: dict[str, Any] = {}
	cursor = node
	for part in parts[:-1]:
		nxt: dict[str, Any] = {}
		cursor[part] = nxt
		cursor = nxt
	cursor[parts[-1]] = _coerce(raw.strip())
	return node


def load_config(
	path: str | Path | None = None,
	*,
	scenario: str | None = None,
	overrides: list[str] | dict[str, Any] | None = None,
	require: bool = False,
) -> Config:
	"""Load, merge, and validate configuration.

	``path`` is the environment-specific file (``config.kenya.yaml``). ``require``
	makes a named-but-missing file an error, which is what a CLI wants: a user
	who typed ``--config config/typo.yaml`` should be told, not silently given
	the defaults.
	"""
	layers: list[tuple[str, dict[str, Any]]] = []

	default_path = default_config_path()
	layers.append((str(default_path), _read(default_path)))

	if path is not None:
		named = resolve(path)
		if require and not named.exists():
			raise ConfigError(f"config file not found: {named}")
		layers.append((str(named), _read(named)))

	if scenario is not None:
		overlay = scenario_path(scenario)
		if require and not overlay.exists():
			raise ConfigError(f"scenario not found: {overlay}")
		layers.append((str(overlay), _read(overlay)))

	merged: dict[str, Any] = {}
	for _, layer in layers:
		merged = deep_merge(merged, layer)

	if overrides:
		override_map: dict[str, Any] = {}
		if isinstance(overrides, dict):
			override_map = overrides
		else:
			for item in overrides:
				override_map = deep_merge(override_map, parse_override(item))
		merged = deep_merge(merged, override_map)

	try:
		return Config.model_validate(merged)
	except Exception as exc:  # pydantic ValidationError
		sources = ", ".join(name for name, layer in layers if layer)
		raise ConfigError(f"invalid configuration (from {sources or 'defaults'}):\n{exc}") from exc


__all__ = [
	"ConfigError",
	"deep_merge",
	"load_config",
	"parse_override",
]
