# SPDX-License-Identifier: MIT
"""Every layer section is reachable from the root config, through its stage.

`07-layer4` §2.1 calls the detection parameters "three parameters, all config,
all recorded", and `01-foundations` §1.6 generalises it: "Every layer that owns
parameters owns a section, and the root `Config` declares it."

The defect this file gates is not a missing feature. It is a config that reads
like one: the section is declared on the layer's own model, documented, carried
into provenance -- and absent from the root `Config`, so `extra="forbid"` turns
the section in YAML into a *load error* and the stage constructs the class
defaults instead. Every value is then pinned while the provenance records it as
the run's parameter. Three instances shipped:

* ``predictive`` -- the VZA bin size, baseline quantile, detection threshold and
  cloud ceiling were unreachable, and a ``predictive:`` block was rejected;
* ``losses`` -- the price a mitigation payback divides by was unreachable, so
  the only reachable payback was `NaN` over zero savings;
* ``resilience`` -- the interruption threshold was unreachable, so the SAIDI the
  platform published could not be matched to a utility's own figure even in
  principle, while §8 says the threshold "is config, recorded, and reported".

**Through the stage, not through the config object.** A stage that reads
``config.resilience`` and a stage that constructs ``ResilienceConfig()`` are
indistinguishable on the root model, and only the second is the defect. So each
check below runs the *shipped* stage entry point against a scratch tree and
reads the parameters out of the written artefact's provenance sidecar -- which
is the same object a reader of the result would consult. A field-existence
assertion would pass a root model that declared the section and a stage that
ignored it; these do not.

Where a parameter is load-bearing rather than merely recorded, the assertion is
on the *number*: the threshold check adds an event below it and requires the
excluded count to move.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from alea.config.base import AleaConfig
from alea.config.loader import load_config
from alea.config.models import Config
from alea.io.pipeline import build_stage

#: The sections the layers own, and the module each layer declares its model in.
#: The root composes these rather than re-declaring them, which is exactly why a
#: section can go missing: adding a parameter means editing the layer's model,
#: and nothing forces the corresponding root field into existence.
LAYER_SECTIONS = {
	"predictive": "alea.outages.views",
	"losses": "alea.losses.views",
	"resilience": "alea.resilience.views",
}


def _sidecar_parameters(path: Path) -> dict[str, Any]:
	"""The ``parameters`` mapping an artefact's provenance recorded."""
	sidecar = path.with_suffix(path.suffix + ".provenance.json")
	assert sidecar.exists(), f"no provenance sidecar beside {path}"
	return json.loads(sidecar.read_text(encoding="utf-8"))["parameters"]


def _config_in(tmp_path: Path, **sections: Any) -> Config:
	"""A config whose ``paths.processed`` is a scratch tree and whose layer
	sections are overridden.

	``paths.processed`` is absolute so ``resolve`` returns it unchanged: the
	stage's conventional input paths land under ``tmp_path`` without moving the
	repository root, which is ``lru_cache``d and read once per process.
	"""
	overrides = [f"paths.processed={tmp_path}"]
	for section, values in sections.items():
		for key, value in values.items():
			overrides.append(f"{section}.{key}={value}")
	return load_config(overrides=overrides)


def _fixture_provenance(source_id: str, notes: str) -> Any:
	from alea.provenance.models import Basis, DerivedProvenance

	return DerivedProvenance(
		source_id=source_id,
		inputs=["<fixture>"],
		code_version="test",
		run_id="test",
		parameters={},
		basis=Basis.MODELLED,
		notes=notes,
	)


def _write_network(tmp_path: Path) -> None:
	"""A three-bus, two-branch radial line, as the tlens stage reads it.

	Written through the artefact layer rather than with a bare
	``to_parquet``/``write_text``: ``read_artefact`` verifies a checksum against
	the provenance sidecar and refuses a payload without one, so a fixture
	written any other way fails at read with a message about provenance rather
	than at the assertion under test.
	"""
	from alea.io.artefacts import write_artefact
	from alea.losses.flow import Network, susceptance_matrix
	from alea.losses.service import network_to_payload

	branch_from = np.array([0, 1], dtype=np.uint32)
	branch_to = np.array([1, 2], dtype=np.uint32)
	branch_susceptance = np.array([10.0, 10.0])
	network = Network(
		susceptance=susceptance_matrix(branch_from, branch_to, branch_susceptance, 3),
		branch_from=branch_from,
		branch_to=branch_to,
		branch_susceptance=branch_susceptance,
		resistance_ohm=np.array([0.5, 0.5]),
		voltage_kv=np.array([132.0, 132.0]),
		ratings_mw=np.array([100.0, 100.0]),
		branch_names=("L0", "L1"),
	)
	write_artefact(
		tmp_path / "network_arrays.json",
		network_to_payload(network),
		_fixture_provenance("network_arrays", "fixture network for the reachability gate"),
		format="json",
	)


def _write_dispatch(tmp_path: Path) -> None:
	"""Four snapshots of a 50 MW transfer from bus 0 to bus 2."""
	from alea.io.artefacts import write_artefact

	row = np.array([50.0, 0.0, -50.0])
	frame = pd.DataFrame(np.tile(row, (4, 1)), columns=["bus_0", "bus_1", "bus_2"])
	write_artefact(
		tmp_path / "dispatch.parquet",
		frame,
		_fixture_provenance("dispatch", "fixture dispatch for the reachability gate"),
		format="parquet",
	)


# --------------------------------------------------------------------------
# The mechanism: the root composes the layer's own model
# --------------------------------------------------------------------------


def test_the_root_config_composes_every_layer_section():
	"""A missing root field is the defect; a re-declared type is the next one.

	Presence alone is the weaker half -- the plan says so -- but a section that
	is absent *cannot* be reached at all, and a section re-declared in
	``alea.config.models`` rather than imported from the layer is a copy that
	drifts from the model the stage reads. Both are asserted here; the tests
	below assert the reachability presence is not enough for.
	"""
	import importlib

	for section, module_name in LAYER_SECTIONS.items():
		assert section in Config.model_fields, (
			f"the root Config declares no `{section}` section, so a `{section}:` "
			f"block in YAML is a load error and the stage silently runs the "
			f"class defaults ({module_name})"
		)
		declared = importlib.import_module(module_name)
		field_type = Config.model_fields[section].annotation
		assert issubclass(field_type, AleaConfig), (
			f"Config.{section} is {field_type!r}, not an AleaConfig subclass"
		)
		# The type is the *layer's* class, not a second definition of it: the
		# class the root names must be the one the layer module exports.
		assert getattr(declared, field_type.__name__) is field_type, (
			f"Config.{section} names {field_type.__qualname__}, which is not the "
			f"class {module_name} exports; the root has re-declared the section"
		)


def _config_sections(model: type[AleaConfig], prefix: str = "") -> dict[type[AleaConfig], str]:
	"""Every ``AleaConfig`` reachable from ``model``, keyed by class, with its path.

	Recursive, so a section nested two deep is covered without anyone naming it:
	``predictive.ensemble`` is a section an operator sets, and a check that
	enumerated only the root's own fields would not know it exists.
	"""
	out: dict[type[AleaConfig], str] = {}
	for name, field in model.model_fields.items():
		annotation = field.annotation
		if not (isinstance(annotation, type) and issubclass(annotation, AleaConfig)):
			continue
		path = f"{prefix}.{name}" if prefix else name
		out[annotation] = path
		out.update(_config_sections(annotation, path))
	return out


def test_every_declared_config_section_is_settable():
	"""Each nested section the root reaches can be named in an override.

	Presence is not reachability. A section is reachable when YAML can *spell*
	its path and the loader resolves it, and there are two ways for that to fail
	while the field exists: the root composes a class the layer does not export
	(so the path leads to a second definition), or a validator rejects the
	merged result. This walks the tree from the root and sets a probe value in
	every section it finds, so the check is over the shape of the config rather
	than over the three parameters that were actually unreachable.
	"""
	import importlib

	reachable = _config_sections(Config)
	assert reachable, "the root Config reaches no nested section at all"
	for section, module_name in LAYER_SECTIONS.items():
		layer = getattr(
			importlib.import_module(module_name),
			Config.model_fields[section].annotation.__name__,
		)
		for model, path in _config_sections(layer, section).items():
			assert reachable.get(model) == path, (
				f"{model.__qualname__} is a section of the {section} layer at "
				f"{path!r} but the root Config does not reach it there; a "
				f"`{path}:` block in YAML would be a load error"
			)
			probe = _first_scalar(model)
			if probe is None:
				continue
			name, value = probe
			loaded = load_config(overrides=[f"{path}.{name}={value}"])
			resolved = getattr(getattr(getattr(loaded, path.split(".")[0]), *_path_rest(path)), name)
			assert resolved == value, (
				f"{path}.{name} resolved to {resolved!r} from an override of "
				f"{value!r}; the section exists but its parameters cannot be set"
			)


def _path_rest(path: str) -> tuple[str, ...]:
	return tuple(path.split(".")[1:])


_PROBES: dict[type, Any] = {bool: True, int: 7, float: 2.5, str: "probe"}
"""A probe value per scalar type, and the whole of what these checks can spell.

``bool`` is in the map so a boolean field is *recognised* -- but a probe of
``true`` is the default for several of them, so an assertion on it would pass
whether or not the override applied. Booleans are therefore skipped rather than
probed, and the section walk below picks the next
field instead.
"""


def _scalar_probe(field: Any) -> Any:
	"""A value for ``field`` if it takes a plain scalar, else ``None``.

	Anything with a type origin -- ``tuple[str, ...]``, ``Literal``, a mapping,
	a nested model -- is refused rather than unwrapped. Unwrapping
	``tuple[str, ...]`` to ``str`` and probing it as a bare string is a probe the
	field rejects, and the resulting failure is about the probe rather than the
	field: the canary did not reproduce the defect it claims to.
	"""
	import typing

	annotation = field.annotation
	if annotation is None or typing.get_origin(annotation) is not None:
		return None
	if annotation not in _PROBES:
		return None
	return _inside_the_bounds(field.metadata, _PROBES[annotation])


def _first_scalar(model: type[AleaConfig]) -> tuple[str, Any] | None:
	"""A field of ``model`` a probe value can actually exercise, or ``None``."""
	for name, field in model.model_fields.items():
		value = _scalar_probe(field)
		if value is None or isinstance(value, bool):
			continue
		return name, value
	return None


def test_every_scalar_layer_parameter_is_settable_by_name():
	"""Every scalar field of every layer section survives a YAML override.

	The per-section tests below exercise the three parameters that were
	actually unreachable. This sweeps the *rest*, because the defect is a
	property of a field's reachability rather than of those three: a parameter
	added to a layer model tomorrow is reachable only if the root still composes
	that model by reference, and a field whose name YAML cannot spell -- a
	reserved word, a validator that rejects the parsed value -- is unreachable
	in a way no amount of root-field presence fixes.

	Scalars only. A nested model, a ``Literal``, a tuple or a mapping needs a
	value invented for it, and an assertion built on an invention tests the
	invention; the sections that carry those are covered by the tests below.
	"""
	import importlib

	for section, module_name in LAYER_SECTIONS.items():
		model = getattr(
			importlib.import_module(module_name),
			Config.model_fields[section].annotation.__name__,
		)
		for name, field in model.model_fields.items():
			value = _scalar_probe(field)
			if value is None or isinstance(value, bool):
				continue
			resolved = getattr(
				getattr(load_config(overrides=[f"{section}.{name}={value}"]), section), name
			)
			assert resolved == value, (
				f"{section}.{name} resolved to {resolved!r} from an override of "
				f"{value!r}; the field exists but cannot be set"
			)


def _inside_the_bounds(metadata: list[Any], value: Any) -> Any:
	"""A probe that satisfies the field's own constraints.

	``electrification_rate`` is a fraction, so the generic ``2.5`` is rejected by
	its ``le=1`` and the failure is about the *probe*, not the field -- a canary
	that never applied its patch reported as a gate that did not fire. The
	probe is clamped into the declared interval instead, and a field whose
	interval admits no integer gets the bound itself.
	"""
	import annotated_types

	lower = upper = None
	for constraint in metadata:
		if isinstance(constraint, annotated_types.Ge):
			lower = constraint.ge
		elif isinstance(constraint, annotated_types.Gt):
			lower = constraint.gt
		elif isinstance(constraint, annotated_types.Le):
			upper = constraint.le
		elif isinstance(constraint, annotated_types.Lt):
			upper = constraint.lt
	if lower is None and upper is None:
		return value
	if isinstance(value, int) and not isinstance(value, bool):
		candidate = int(value)
		if lower is not None:
			candidate = max(candidate, int(np.ceil(lower)))
		if upper is not None:
			candidate = min(candidate, int(np.floor(upper)))
		return candidate
	if lower is not None and value <= lower:
		value = (lower + upper) / 2 if upper is not None else lower + 1.0
	if upper is not None and value > upper:
		value = (lower + upper) / 2 if lower is not None else upper - 0.5
	return value


# --------------------------------------------------------------------------
# §2.1 predictive -- the resolver the stage actually calls
# --------------------------------------------------------------------------


def test_the_predictive_section_reaches_the_stage_resolver():
	"""`07-layer4` §2.1: three parameters, all config, all recorded.

	The resolver is the service's own function, so a stage that read a different
	attribute would fail here even with the root field present.
	"""
	from alea.outages.service import detection_parameters_for, predictive_config

	config = load_config(
		overrides=[
			"predictive.viirs.bin_size_deg=3.0",
			"predictive.viirs.detection_threshold=0.45",
			"predictive.weather.month_encoding=integer",
		]
	)
	resolved = predictive_config(config)
	assert resolved.viirs.bin_size_deg == 3.0
	assert resolved.viirs.detection_threshold == 0.45
	assert resolved.weather.month_encoding == "integer"
	# And the same values are what the artefact records, which is what §2.5
	# means by reproducible.
	recorded = detection_parameters_for(config)
	assert recorded["bin_size_deg"] == 3.0
	assert recorded["detection_threshold"] == 0.45


# --------------------------------------------------------------------------
# §7 losses -- through the shipped tlens stage
# --------------------------------------------------------------------------


def test_the_losses_section_reaches_the_tlens_stage(tmp_path: Path):
	"""`07-layer4` §7: the price a payback divides by, and the timestep.

	`_stage_tlens` used to build ``LossConfig(slack_bus=...)`` and drop
	everything else, so ``price_usd_per_mwh`` and ``snapshot_hours`` were
	unreachable: every published payback used a price of zero, and every loss
	was MWh only by the accident of an hourly index. The assertion is on the
	provenance sidecar the stage wrote, which is the record a reader consults.
	"""
	_write_network(tmp_path)
	_write_dispatch(tmp_path)
	config = _config_in(tmp_path, losses={"price_usd_per_mwh": 85.0, "snapshot_hours": 0.25})

	out = tmp_path / "tlens.json"
	build_stage("tlens", config, out, inputs=[], force=True)

	parameters = _sidecar_parameters(out)
	assert parameters["price_usd_per_mwh"] == 85.0, (
		"the configured lost-MWh price did not reach the tlens artefact; every "
		"mitigation payback would divide by the default 0.0"
	)
	assert parameters["snapshot_hours"] == 0.25, (
		"the configured snapshot length did not reach the tlens artefact; every "
		"`*_mwh` field would be a MW sum labelled as energy"
	)


# --------------------------------------------------------------------------
# §8 resilience -- through the shipped stage, and on the number
# --------------------------------------------------------------------------


def _write_resilience_inputs(tmp_path: Path) -> None:
	"""Two interruptions: one above the default threshold, one below it."""
	from alea.io.artefacts import write_artefact

	frame = pd.DataFrame(
		{
			"zone": ["nairobi", "nairobi"],
			"started_at": pd.to_datetime(["2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z"]),
			"duration_minutes": [120.0, 1.0],
			"load_mw": [50.0, 50.0],
		}
	)
	write_artefact(
		tmp_path / "interruptions.parquet",
		frame,
		_fixture_provenance("interruptions", "two events: one above the default threshold"),
		format="parquet",
	)
	write_artefact(
		tmp_path / "zone_population.parquet",
		pd.DataFrame({"zone": ["nairobi"], "population": [4_400_000.0]}),
		_fixture_provenance("zone_population", "a population denominator, therefore a proxy"),
		format="parquet",
	)


def test_the_resilience_section_reaches_the_stage(tmp_path: Path):
	"""`07-layer4` §8: "The threshold is config, recorded, and reported".

	``_stage_resilience`` used to construct ``ResilienceConfig()``, so the
	recorded threshold was a constant the operator could not move -- and two
	SAIDI figures at different thresholds are different quantities sharing a
	name. Both halves are asserted: the threshold reaches the provenance, and it
	*changes the number*, which is why §8 calls it config rather than a
	documentation note.

	Both thresholds below differ from the default (5.0). Asserting the default
	would pass against a stage that ignored the section entirely, which is the
	defect -- and it is the mistake this test made in its first form.
	"""
	_write_resilience_inputs(tmp_path)
	config = _config_in(tmp_path, resilience={"interruption_threshold_minutes": 30.0})

	out = tmp_path / "resilience.json"
	build_stage("resilience", config, out, inputs=[], force=True)
	parameters = _sidecar_parameters(out)
	assert parameters["interruption_threshold_minutes"] == 30.0, (
		"the configured interruption threshold did not reach the artefact"
	)
	# The 1-minute event is a reclosure at 30 minutes and an interruption at 0.5.
	assert parameters["n_events_below_threshold"] == 1

	loose = _config_in(tmp_path, resilience={"interruption_threshold_minutes": 0.5})
	loose_out = tmp_path / "resilience_loose.json"
	build_stage("resilience", loose, loose_out, inputs=[], force=True)
	loose_parameters = _sidecar_parameters(loose_out)
	assert loose_parameters["interruption_threshold_minutes"] == 0.5
	assert loose_parameters["n_events_below_threshold"] == 0, (
		"the threshold did not change which events count as interruptions, so "
		"it is recorded but not load-bearing"
	)
	assert loose_parameters["n_events"] > parameters["n_events"], (
		"the loose threshold counted no more events than the strict one; the "
		"threshold is not reaching the metric computation"
	)


def test_the_losses_slack_bus_still_comes_from_the_solve_options(tmp_path: Path):
	"""The one field where the section is *not* the right source.

	``slack_bus`` is a property of the network the solve produced, so
	``solve.solver_options['slack_bus']`` wins over a loss-section default --
	and an explicit ``losses.slack_bus`` wins over both. Pinned here because the
	generalised gate above would otherwise be satisfied by a stage that read the
	section for every field, which would break the reference bus.
	"""
	_write_network(tmp_path)
	_write_dispatch(tmp_path)
	config = _config_in(tmp_path, losses={})
	config = config.model_copy(
		update={"solve": config.solve.model_copy(update={"solver_options": {"slack_bus": 2}})}
	)
	out = tmp_path / "tlens_slack.json"
	build_stage("tlens", config, out, inputs=[], force=True)
	assert _sidecar_parameters(out)["slack_bus"] == 2

	explicit = _config_in(tmp_path, losses={"slack_bus": 1})
	explicit = explicit.model_copy(
		update={"solve": explicit.solve.model_copy(update={"solver_options": {"slack_bus": 2}})}
	)
	explicit_out = tmp_path / "tlens_explicit.json"
	build_stage("tlens", explicit, explicit_out, inputs=[], force=True)
	assert _sidecar_parameters(explicit_out)["slack_bus"] == 1, (
		"an explicit losses.slack_bus did not win over the solve option"
	)


if __name__ == "__main__":  # pragma: no cover
	raise SystemExit(pytest.main([__file__, "-q"]))
