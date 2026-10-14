# SPDX-License-Identifier: MIT
"""The ALEA command line.

AD-5: this is the only entry point the workflow layer calls. A Snakemake rule
shells out to ``alea <stage>``; it never imports a Python function from a stage
module, because a rule that imports code cannot be rerun against a different
environment and a rule that shells out can.

Every subcommand takes ``--config`` and ``--out``, logs a run id on entry and
exit, and exits non-zero on any error.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from alea import __version__
from alea.config.loader import ConfigError, load_config
from alea.config.models import Config
from alea.logging import configure, configure_from, get_logger, new_run_id
from alea.registry import registry, technologies, tier_counts

app = typer.Typer(
	no_args_is_help=True,
	add_completion=False,
	help="ALEA — African Light and Energy Analytics.",
)

config_app = typer.Typer(no_args_is_help=True, help="Inspect and validate configuration.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect the country and technology registries.")
quality_app = typer.Typer(no_args_is_help=True, help="Validation coverage and the unverified register.")
whatif_app = typer.Typer(no_args_is_help=True, help="What-if scenario cache maintenance.")
validate_app = typer.Typer(
	no_args_is_help=True,
	help="Measure an approximation and record it, so a gate can read the measurement.",
)
app.add_typer(config_app, name="config")
app.add_typer(registry_app, name="registry")
app.add_typer(quality_app, name="quality")
app.add_typer(whatif_app, name="whatif")
prg_app = typer.Typer(
	no_args_is_help=True,
	help="The Parameter Relationship Graph: consistency, propagation, equations.",
)
app.add_typer(validate_app, name="validate")
app.add_typer(prg_app, name="prg")
expr_app = typer.Typer(
	no_args_is_help=True,
	help="Write a formula once and create, render, differentiate, simplify or solve it.",
)
app.add_typer(expr_app, name="expr")

ConfigOption = Annotated[
	Path | None,
	typer.Option("--config", "-c", help="Environment config file, e.g. config/config.kenya.yaml."),
]
ScenarioOption = Annotated[
	str | None,
	typer.Option("--scenario", "-s", help="Scenario overlay name from config/scenarios/."),
]
SetOption = Annotated[
	list[str] | None,
	typer.Option("--set", help="Override a key: --set solve.solver=highs. Repeatable."),
]
OutOption = Annotated[Path, typer.Option("--out", "-o", help="Output path or directory.")]
ForceOption = Annotated[
	bool,
	typer.Option("--force", help="Rebuild even when the stage is already current."),
]


def _load(config: Path | None, scenario: str | None, overrides: list[str] | None) -> Config:
	"""Load configuration, turning a load failure into a clean CLI error."""
	try:
		return load_config(config, scenario=scenario, overrides=overrides, require=True)
	except ConfigError as exc:
		typer.secho(f"configuration error: {exc}", fg=typer.colors.RED, err=True)
		raise typer.Exit(code=2) from exc


class _Run:
	"""A pipeline invocation, recorded on entry and on exit.

	``alea.api.runs.RunLog`` reads ``results/runs.jsonl`` and its docstring says
	the CLI appends an entry line and closes it with an exit line. The CLI
	appended neither: ``_run`` bound a run id to a structlog logger and returned,
	so every ``GET /runs/{id}`` was a 404 for a run that had happened, and no
	artefact could be joined back to the invocation that produced it.

	Used as a context manager so the exit line is written on the way out of the
	``with``, including when the body raises -- a run that failed is a run, and
	the record's ``status`` is what says which. A process killed outright still
	writes no exit line, which the reader already handles by treating a record
	without one as ``running``.
	"""

	def __init__(self, component: str, **context: Any) -> None:
		self.component = component
		self.context = context
		self.run_id = new_run_id()
		self.logger = get_logger(component).bind(run_id=self.run_id)
		self.artefacts: list[str] = []
		self.started_at = datetime.now(UTC)

	def __enter__(self) -> _Run:
		self.logger.info("start", version=__version__, **self.context)
		self._append(status="running")
		return self

	def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Literal[False]:
		status = "failed" if exc_type is not None else "succeeded"
		self.logger.info("done", status=status)
		self._append(
			status=status,
			finished_at=datetime.now(UTC),
			detail="" if exc is None else f"{type(exc).__name__}: {exc}",
		)
		return False

	def record(self, *paths: Any) -> None:
		"""Name an artefact this run produced.

		Called by a command that knows its output; the join from a published
		number back to its run is the reason the log exists.
		"""
		self.artefacts.extend(str(path) for path in paths)

	def _append(self, *, status: str, finished_at: datetime | None = None, detail: str = "") -> None:
		"""Append one JSON-Lines record.

		Failure to write the log must not fail the run: the work is done and its
		artefacts are on disk, and losing the log line is a smaller loss than
		losing the result. It is logged and swallowed.
		"""
		record = {
			"run_id": self.run_id,
			"component": self.component,
			"status": status,
			"started_at": self.started_at.isoformat(),
			"finished_at": finished_at.isoformat() if finished_at else None,
			"artefacts": list(self.artefacts),
			"detail": detail,
			"version": __version__,
			"context": {key: str(value) for key, value in self.context.items()},
		}
		try:
			path = _run_log_path()
			path.parent.mkdir(parents=True, exist_ok=True)
			with path.open("a", encoding="utf-8") as handle:
				handle.write(json.dumps(record, sort_keys=True) + "\n")
		except OSError as write_exc:  # pragma: no cover - depends on the filesystem
			self.logger.warning("run_log_unwritable", error=str(write_exc))


def _run_log_path() -> Path:
	"""Where the run log lives, honouring ``--config``'s paths when loadable.

	Resolved from the config when one can be read and from the repository
	default otherwise: a ``config validate`` that fails because the config is
	broken must still record that it ran and failed, which is precisely the run
	a reader will look for.
	"""
	from alea.api.runs import RUN_LOG
	from alea.config.paths import resolve

	return resolve(RUN_LOG)


def _run(component: str, **context: Any) -> _Run:
	"""Begin a run. Use as ``with _run(...) as run:``."""
	return _Run(component, **context)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


@config_app.command("validate")
def config_validate(
	config: ConfigOption = None,
	scenario: ScenarioOption = None,
	set_: SetOption = None,
	quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print nothing on success.")] = False,
) -> None:
	"""Validate configuration and exit non-zero on any defect.

	Unknown keys are the point. A typo that reaches a solve costs hours; the
	loader forbids extras, so this names the key in a second.
	"""
	with _run("cli.config.validate", config=str(config)):
		loaded = _load(config, scenario, set_)
		if not quiet:
			# `ScenarioConfig` refuses a country that is None, so the `str` cast is
			# exact rather than a hope; `CountryIso` is `str | None` only because a
			# *signal* may arrive without one.
			countries = ", ".join(str(iso) for iso in loaded.scenario.countries)
			typer.echo(f"config ok: countries={countries}")
			typer.echo(f"  horizons: {loaded.scenario.planning_horizons}")
			typer.echo(f"  clusters: {loaded.scenario.clusters}")
			typer.echo(
				f"  solver:   {loaded.solve.solver} (losses={loaded.solve.transmission_losses})"
			)


@config_app.command("show")
def config_show(
	config: ConfigOption = None,
	scenario: ScenarioOption = None,
	set_: SetOption = None,
) -> None:
	"""Print the fully merged configuration as JSON."""
	with _run("cli.config.show", config=str(config)):
		loaded = _load(config, scenario, set_)
		typer.echo(json.dumps(loaded.model_dump(mode="json"), indent=2, sort_keys=True))


# --------------------------------------------------------------------------
# prg
# --------------------------------------------------------------------------


@prg_app.command("summary")
def prg_summary() -> None:
	"""Counts, the feedback loops, and the systems the library does not cover."""
	from alea.prg.service import graph_summary

	summary = graph_summary()
	typer.echo(
		f"parameters={summary['parameters']} equations={summary['equations']} "
		f"edges={summary['edges']} derived={summary['derived']}"
	)
	typer.echo(
		f"systems: {len(summary['systems'])} of {summary['systems_declared']} modelled"
	)
	for system_id, count in sorted(summary["systems"].items()):
		typer.echo(f"  {system_id:20s} {count} equation(s)")
	if summary["unmodelled_systems"]:
		typer.echo("not modelled:")
		for system_id in summary["unmodelled_systems"]:
			typer.echo(f"  {system_id}")
	if summary["feedback_loops"]:
		typer.echo("feedback loops:")
		for loop in summary["feedback_loops"]:
			typer.echo(f"  {loop}")
	# The engine-coverage line is printed unconditionally, because the number
	# is the finding: a reader who sees only the graph's own counts assumes the
	# engine is driven by all of it, and three of fifty-three is the truth.
	engine = summary["engine_translation"]
	typer.echo(
		f"engine: {engine['count']} of {engine['total']} settable parameters reach "
		f"a what-if knob ({engine['fraction']:.1%})"
	)
	# The reverse direction, and it is a different finding: a knob the graph
	# cannot speak to is a lever a scenario can pull that no audit will see.
	unreached = engine.get("engine_unreached") or ()
	if unreached:
		typer.echo(
			f"engine: {len(unreached)} knob(s) no PRG parameter names, so a "
			f"scenario pulling one cannot be audited against the graph: "
			f"{', '.join(unreached)}"
		)
	typer.echo(f"uncertainty: {summary['uncertainty'].summary()}")
	typer.echo(f"units: {summary['units'].summary()}")
	# The cross-validation register. Printed as ids rather than a count because
	# a count of rules that were *declared* says nothing about whether any of
	# them was evaluated -- the check that runs them is `prg check`.
	rules = summary["cross_validation_rules"]
	typer.echo(
		f"cross-validation: {len(rules)} rule(s) declared"
		+ (f": {', '.join(rules)}" if rules else "")
	)
	for issue in summary["structure_issues"]:
		typer.secho(f"structure: {issue}", fg=typer.colors.YELLOW, err=True)


@prg_app.command("equations")
def prg_equations(
	system: Annotated[
		str | None, typer.Option("--system", help="Only this equation system.")
	] = None,
	as_: Annotated[
		str, typer.Option("--as", help="unicode, latex, or source.")
	] = "unicode",
) -> None:
	"""Render the equation library."""
	from alea.prg.service import equation_report

	for equation_id, system_id, rendered in equation_report(as_=as_, system=system):
		typer.echo(f"{equation_id} [{system_id}]")
		typer.echo(f"    {rendered}")


@prg_app.command("check")
def prg_check(
	set_: SetOption = None,
	scenario: ScenarioOption = None,
	config: ConfigOption = None,
) -> None:
	"""Validate a parameter set, propagating the derived parameters first.

	Exits non-zero on any violation, so it can gate a scenario file. The
	unmodelled systems are printed too: a set that violates nothing is not the
	same as a set that is consistent, and a check that reported only the first
	would read as a clean bill of health for a graph that covers a third of the
	model.
	"""
	from alea.prg import load_graph
	from alea.prg.service import check_scenario

	with _run("cli.prg.check", scenario=str(scenario)):
		graph = load_graph()
		values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
		for override in set_ or []:
			key, _, raw = override.partition("=")
			if key not in graph.nodes:
				typer.secho(
					f"{key!r} is not a parameter in the graph", fg=typer.colors.RED, err=True
				)
				raise typer.Exit(code=2)
			if not graph.is_settable(key):
				equation = graph.determined_by(key)
				by = equation.id if equation is not None else "a feedback loop"
				typer.secho(
					f"{key!r} is computed by {by}, not set; the graph derives it "
					f"from the parameters it depends on",
					fg=typer.colors.RED,
					err=True,
				)
				raise typer.Exit(code=2)
			values[key] = float(raw)
		result = check_scenario(values, graph)
		for parameter, value in sorted(result.excursions.items()):
			node = graph.node(parameter)
			typer.secho(
				f"out of range: {parameter} = {value:.6g}, declared range "
				f"{node.range}",
				fg=typer.colors.RED,
				err=True,
			)
		for violation in result.violations:
			typer.secho(f"violation: {violation}", fg=typer.colors.RED, err=True)
		for entry in result.unmodelled:
			typer.secho(f"not modelled: {entry}", fg=typer.colors.YELLOW, err=True)
		# Cross-validation findings are printed with the equation violations,
		# because they are the other half of the same question. They are *not*
		# folded into `consistent`: a scenario can satisfy every equation and
		# still break a rule no equation states, and calling that inconsistent
		# would misname what failed.
		cross = result.cross_validation
		if cross is not None:
			for finding in cross.findings:
				colour = (
					typer.colors.RED
					if finding.severity.value == "error"
					else typer.colors.YELLOW
				)
				typer.secho(f"cross-validation: {finding}", fg=colour, err=True)
		typer.echo(result.summary())
		if not result.consistent:
			raise typer.Exit(code=1)
		# An `error`-severity rule is the one severity that gates: it is a
		# scenario a reviewer should refuse, and a check that exited zero on it
		# would be a gate that never fires. `warning` and `info` are printed
		# and do not block.
		if cross is not None and cross.blocks:
			raise typer.Exit(code=1)


@prg_app.command("propagate")
def prg_propagate(
	set_: SetOption = None,
) -> None:
	"""Set parameters and print what the change moved."""
	from alea.prg import load_graph
	from alea.prg.service import propagate_change

	with _run("cli.prg.propagate"):
		graph = load_graph()
		values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
		changes: dict[str, float] = {}
		for override in set_ or []:
			key, _, raw = override.partition("=")
			if key not in graph.nodes:
				typer.secho(
					f"{key!r} is not a parameter in the graph", fg=typer.colors.RED, err=True
				)
				raise typer.Exit(code=2)
			if not graph.is_settable(key):
				equation = graph.determined_by(key)
				by = equation.id if equation is not None else "a feedback loop"
				typer.secho(
					f"{key!r} is computed by {by}, not set; set the parameters it "
					f"depends on instead",
					fg=typer.colors.RED,
					err=True,
				)
				raise typer.Exit(code=2)
			changes[key] = float(raw)
		result = propagate_change(values, changes)
		for name, delta in sorted(result["changed"].items()):
			typer.echo(f"  {name:38s} {result['values'][name]:14.6f}  ({delta:+.6f})")
		for loop in result["loops"]:
			typer.echo(f"  loop {loop['loop']}: {loop['iterations']} turns")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


@registry_app.command("export")
def registry_export(out: OutOption) -> None:
	"""Write both registries to JSON."""
	with _run("cli.registry.export", out=str(out)) as run:
		payload = {
			"countries": [c.model_dump(mode="json") for c in registry().values()],
			"technologies": [t.model_dump(mode="json") for t in technologies().values()],
		}
		out.parent.mkdir(parents=True, exist_ok=True)
		out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
		run.record(out)
		typer.echo(f"wrote {len(payload['countries'])} countries to {out}")


@registry_app.command("check")
def registry_check() -> None:
	"""Assert the registry invariants and exit non-zero if any fails."""
	with _run("cli.registry.check"):
		counts = tier_counts()
		total = sum(counts.values())
		if total != 55:
			typer.secho(
				f"registry holds {total} countries, expected 55", fg=typer.colors.RED, err=True
			)
			raise typer.Exit(code=1)
		typer.echo(f"countries: {total}")
		for tier, count in sorted(counts.items(), key=lambda kv: kv[0].value):
			typer.echo(f"  {tier.value:9s} {count}")
		typer.echo(f"technologies: {len(technologies())}")


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------


@app.command()
def fetch(
	source_id: Annotated[str, typer.Argument(help="Source identifier from the source register.")],
	config: ConfigOption = None,
	out: Annotated[Path | None, typer.Option("--out", "-o", help="Raw lake root.")] = None,
	force: ForceOption = False,
) -> None:
	"""Retrieve one source into the immutable raw layer."""
	from alea.io.pipeline import fetch_source

	with _run("cli.fetch", source=source_id) as run:
		loaded = _load(config, None, None)
		root = out or Path(loaded.paths.raw)
		try:
			result = fetch_source(source_id, root, force=force, logger=run.logger)
		except KeyError as exc:
			typer.secho(f"unknown source: {exc}", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=2) from exc
		run.record(result.path)
		typer.echo(f"{source_id}: {result.checksum[:12]} ({result.bytes_written} bytes)")


@app.command()
def build(
	stage: Annotated[str, typer.Argument(help="Stage name, e.g. 'fleet', 'demand'.")],
	out: OutOption,
	config: ConfigOption = None,
	force: ForceOption = False,
	input_: Annotated[
		list[str] | None,
		typer.Option(
			"--input",
			help=(
				"An artefact this stage reads: a path, or a raw lake checksum "
				"directory name. Repeatable. These are what the idempotence check "
				"compares, so a stage run without them cannot be recognised as "
				"current and rebuilds every time."
			),
		),
	] = None,
	set_: Annotated[
		list[str] | None,
		typer.Option(
			"--set",
			help=(
				"Stage parameter, KEY=VALUE. Repeatable. Values parse as JSON "
				"where they can and stay strings where they cannot, so "
				"--set alpha=0.7 is a float and --set cutout_path=/data/x.nc is a "
				"path. These reach the builder's BuildContext, not the config."
			),
		),
	] = None,
) -> None:
	"""Build one processed dataset from the raw layer.

	``--set`` carries the parameters a builder reads off its context: the
	powerplantmatching export path, the disaggregation ``alpha``, a cutout path.
	They are deliberately *not* config keys -- a config that grows a key per
	stage parameter is a config nobody can validate -- and they are recorded in
	the artefact's provenance either way, which is what makes the run
	reproducible.

	``--input`` is the other half of that: what the artefact was derived from.
	Without it ``build_stage`` sees an empty declaration, its idempotence check
	short-circuits, and every `alea build` rebuilds -- so ``02-data-pipeline.md``
	§4.1 and Stage A1's criterion 8 were unenforceable from the CLI, which is
	the only entry point the workflow has (AD-5). A path is hashed; a bare
	checksum directory name is passed through as the raw layer already recorded
	it.
	"""
	from alea.io.pipeline import build_stage

	with _run("cli.build", stage=stage) as run:
		loaded = _load(config, None, None)
		try:
			result = build_stage(
				stage,
				loaded,
				out,
				inputs=_resolve_inputs(input_),
				force=force,
				logger=run.logger,
				parameters=_parse_parameters(set_),
			)
		except KeyError as exc:
			typer.secho(f"unknown stage: {exc}", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=2) from exc
		run.record(result.path)
		typer.echo(f"{stage}: {result.checksum[:12]} -> {result.path}")


def _resolve_inputs(declared: list[str] | None) -> list[str]:
	"""``--input`` values as the checksums a stage's provenance records.

	A path that exists is hashed, so ``--input data/processed/topology.parquet``
	and a rule passing the same file agree on one value. Anything else is passed
	through unchanged: the raw lake addresses a payload by its checksum
	directory, and a rule that names one is naming a value the layer already
	computed -- re-hashing the file inside it would produce a different string
	for the same bytes.
	"""
	if not declared:
		return []
	from alea.io.artefacts import sha256_file

	resolved: list[str] = []
	for value in declared:
		path = Path(value)
		resolved.append(sha256_file(path) if path.is_file() else value)
	return resolved


def _parse_parameters(pairs: list[str] | None) -> dict[str, Any]:
	"""``["alpha=0.7", "cutout_path=/x.nc"]`` as a dict.

	A value parses as JSON when it can, so ``alpha=0.7`` is a float,
	``bounds=[1,2,3,4]`` a list, and ``cutout_path=/x.nc`` a string -- JSON has
	no bare ``/x.nc``. A malformed pair raises rather than being dropped: a
	parameter a rule meant to pass and did not is a stage built with the default
	and reported as the requested one.
	"""
	if not pairs:
		return {}
	parameters: dict[str, Any] = {}
	for pair in pairs:
		key, separator, raw = pair.partition("=")
		if not separator or not key.strip():
			raise typer.BadParameter(f"--set expects KEY=VALUE, got {pair!r}")
		try:
			parameters[key.strip()] = json.loads(raw)
		except ValueError:
			parameters[key.strip()] = raw
	return parameters


@app.command()
def solve(
	out: OutOption,
	config: ConfigOption = None,
	network: Annotated[Path | None, typer.Option("--network", help="Input network.")] = None,
	horizon: Annotated[int | None, typer.Option("--horizon", help="Planning horizon year.")] = None,
) -> None:
	"""Solve a capacity-expansion problem."""
	from alea.planning.service import solve_scenario

	with _run("cli.solve", network=str(network), horizon=horizon) as run:
		loaded = _load(config, None, None)
		result = solve_scenario(
			loaded, network=network, out=out, horizon=horizon, logger_=run.logger
		)
		run.record(out)
		# No status check here: `solve_scenario` raises `ExpansionError` for
		# anything that is not optimal, so reaching this line means the status is
		# one of the accepted spellings and the objective is a real answer.
		typer.echo(f"solved: objective={result.objective:,.0f} in {result.seconds:.1f}s")


@app.command()
def dispatch(
	out: OutOption,
	config: ConfigOption = None,
	network: Annotated[Path | None, typer.Option("--network", help="Solved network.")] = None,
) -> None:
	"""Solve hourly dispatch on a network with fixed capacity.

	A separate subcommand from ``solve`` rather than a flag on it, because the
	two answer different questions and one feeds the other: ``solve`` chooses
	capacity over a horizon, ``dispatch`` asks how a chosen mix operates hour by
	hour. AD-5 makes the CLI the only entry point a Snakemake rule calls, so a
	rule that needs dispatch needs this subcommand and not a longer shell
	string.
	"""
	from alea.planning.service import dispatch_scenario

	with _run("cli.dispatch", network=str(network)) as run:
		loaded = _load(config, None, None)
		result = dispatch_scenario(loaded, network=network, out=out, logger_=run.logger)
		run.record(out)
		typer.echo(
			f"dispatched: objective={result.objective:,.0f} in {result.seconds:.1f}s, "
			f"curtailment={result.curtailment_share * 100:.2f}%"
		)


@app.command()
def project(
	cadence: Annotated[str, typer.Argument(help="Report cadence the section belongs to.")],
	slug: Annotated[str, typer.Argument(help="Section slug, e.g. 'capacity_update'.")],
	source: Annotated[Path, typer.Option("--source", help="The artefact the stage wrote.")],
	config: ConfigOption = None,
	date: Annotated[str | None, typer.Option("--date", help="Report date, ISO 8601.")] = None,
) -> None:
	"""Land a produced artefact at the dated path its report section reads.

	A stage writes ``data/processed/<stage>.<suffix>``; a section reads
	``results/<dir>/{date}.parquet``. Nothing bridged the two, so a slug in
	``reporting.producers.PRODUCERS`` recorded that a *function* exists rather
	than that a section is deliverable -- `alea report monthly` failed with
	"no artefact" while the producing rule exited 0.

	The destination is the section's own declared path and the date is the
	cadence's own period end, so this command cannot write a file no report
	looks for.
	"""
	from alea.reporting.projection import project_section

	with _run("cli.project", cadence=cadence, slug=slug) as run:
		loaded = _load(config, None, None)
		as_of = _as_date_or_today(date)
		target = project_section(cadence, slug, source, loaded, as_of=as_of)
		run.record(target)
		typer.echo(f"{slug}: {source} -> {target}")


def _as_date_or_today(value: str | None) -> date:
	"""A CLI date option, defaulting to today in UTC."""
	if value is None:
		return datetime.now(UTC).date()
	return date.fromisoformat(value)


@app.command()
def report(
	kind: Annotated[str, typer.Argument(help="Report cadence: daily, weekly, monthly, quarterly, annual.")],
	out: OutOption,
	config: ConfigOption = None,
	date: Annotated[str | None, typer.Option("--date", help="Report date, ISO 8601.")] = None,
) -> None:
	"""Generate a periodic report."""
	from alea.reporting.service import build_report

	with _run("cli.report", kind=kind, date=date) as run:
		loaded = _load(config, None, None)
		result = build_report(kind, loaded, out, date=date, run_id=run.run_id)
		run.record(*result.paths.values())
		for path in result.paths:
			typer.echo(f"{kind}: {path}")
		for warning in result.warnings:
			typer.secho(f"warning: {warning}", fg=typer.colors.YELLOW, err=True)


@whatif_app.command("gc")
def whatif_gc(
	keep_days: Annotated[
		float | None,
		typer.Option(
			"--keep-days",
			help=(
				"Remove cache entries last written more than this many days ago. "
				"Omitted means remove nothing, not everything."
			),
		),
	] = None,
	dry_run: Annotated[
		bool,
		typer.Option("--dry-run", help="Report what would be removed and remove nothing."),
	] = False,
	cache_root: Annotated[
		Path | None,
		typer.Option("--cache-root", help="Override the solve-cache directory."),
	] = None,
) -> None:
	"""Garbage-collect the what-if solve cache.

	`08-layer5-whatif.md` §2.4: the cache is content-addressed and therefore
	never *invalidated* -- a changed network produces a new key -- so old entries
	are collected only by this explicit command, "never by age-based eviction
	during a run, because eviction during a sweep changes which scenarios are
	computed and therefore the frontier".

	The command is the other half of that sentence. `SolveCache.garbage_collect`
	was written, documented as CLI-driven, and called by nothing: the method's own
	docstring and the plan both name `alea whatif gc --keep-days N`, and the CLI
	had no `whatif` group at all. A cache with no eviction path grows without
	bound, and the plan's rule that eviction must not happen during a run is only
	enforceable while there is somewhere else for it to happen.

	**`--keep-days` omitted removes nothing.** That is `garbage_collect`'s own
	guard, not a default invented here: a missing window read as "older than now"
	would erase the whole cache, and a maintenance command whose no-argument form
	is the destructive one is a command someone runs by accident.
	"""
	from alea.config.paths import resolve
	from alea.whatif.cache import DEFAULT_CACHE_ROOT, SolveCache

	with _run("cli.whatif.gc", keep_days=keep_days, dry_run=dry_run):
		root = cache_root or resolve(DEFAULT_CACHE_ROOT)
		cache = SolveCache(root)
		before = len(cache.keys())
		removed = cache.garbage_collect(keep_days=keep_days, dry_run=dry_run)

		if keep_days is None:
			typer.secho(
				"no --keep-days given, so nothing was removed; pass a window to "
				"collect",
				fg=typer.colors.YELLOW,
				err=True,
			)
		verb = "would remove" if dry_run else "removed"
		typer.echo(f"{verb} {len(removed)} of {before} entries under {root}")
		for key in removed:
			typer.echo(f"  {key[:12]}")


@validate_app.command("aggregation")
def validate_aggregation(
	network: Annotated[Path, typer.Option("--network", help="Solved network at full resolution.")],
	periods: Annotated[
		int,
		typer.Option("--periods", help="Representative periods to aggregate to."),
	],
	config: ConfigOption = None,
	out: Annotated[
		Path | None,
		typer.Option("--out", "-o", help="Directory for the validation artefact."),
	] = None,
	period_length: Annotated[
		int | None,
		typer.Option(
			"--period-length",
			help="Timesteps per representative period. Default: a week (168 h), or the "
			"period count itself when the periods are meant to be single timesteps.",
		),
	] = None,
	seed: Annotated[int, typer.Option("--seed", help="Aggregation seed.")] = 0,
) -> None:
	"""Measure what aggregating a network costs, and record it (AD-9).

	The remedy `require_aggregation_validation` names in its own refusal, and
	which did not exist: the gate's error string says "Run `alea validate
	aggregation` first", `04-layer1-planning.md` §7 quotes the same string, and
	the CLI had no `validate` group. A gate whose remedy cannot be run is a gate
	whose failure has no next step, which is how an operator ends up writing a
	validation artefact by hand.

	Solves the network twice -- once at full resolution and once aggregated --
	and writes the measured errors to ``results/aggregation/<network id>.json``,
	which is where the gate reads them. The artefact is written **even when the
	measurement fails**: a failing measurement on disk is how an operator learns
	the fast path is 8% off, and refusing to write it leaves the gate reporting
	"no artefact" instead of "artefact says 8%".

	``--period-length`` defaults to a week rather than to ``snapshots / periods``.
	The latter is not a default at all: 8760 / 12 is 730, and 12 periods of 730
	hours is 8760 hours -- the whole year, so the "aggregated" network is the
	full-resolution one and the measurement reports a flawless 0.00%. That is a
	vacuous validation, and it is exactly the shape the gate exists to refuse.

	The network must already be solved. Measuring an unsolved one would compare
	two zeros and report a perfect aggregation, the same failure by another route.
	"""
	import pypsa

	from alea.planning.aggregation import (
		aggregate_network,
		validate_aggregation_artefact,
		write_validation,
	)

	with _run("cli.validate.aggregation", network=str(network), periods=periods) as run:
		if not network.exists():
			typer.secho(f"network {network} does not exist", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=2)
		solved = pypsa.Network(str(network))
		if not solved.is_solved:
			typer.secho(
				f"network {network} is not solved; run `alea solve` first. Measuring an "
				"unsolved network compares two zeros and reports a perfect aggregation.",
				fg=typer.colors.RED,
				err=True,
			)
			raise typer.Exit(code=2)

		# A week, or the period count when the periods are single timesteps. Both
		# are real reductions; `snapshots // periods` is not, as the docstring says.
		length = period_length or min(168, max(1, len(solved.snapshots) // periods))
		if periods * length >= len(solved.snapshots):
			typer.secho(
				f"{periods} periods of {length} hours cover the whole "
				f"{len(solved.snapshots)}-hour series, so the 'aggregated' network is "
				"the full-resolution one and the measurement would report a flawless "
				"zero. Pass a smaller --period-length or fewer --periods.",
				fg=typer.colors.RED,
				err=True,
			)
			raise typer.Exit(code=2)
		aggregated = aggregate_network(solved, n_periods=periods, period_length=length, seed=seed)
		aggregated.optimize(solver_name=_load(config, None, None).solve.solver, log_to_console=False)

		validation = validate_aggregation_artefact(
			solved, aggregated, n_periods=periods, period_length=length
		)
		written = write_validation(
			validation,
			root=out or "results/aggregation",
			inputs=[f"sha256:network:{validation.network_id}"],
		)
		run.record(written)

		typer.echo(
			f"cost error {validation.cost_error_pct:+.3f}% (tolerance "
			f"{validation.tolerance_cost_pct}%), mix error "
			f"{validation.capacity_mix_l1_error_pct:.3f}% (tolerance "
			f"{validation.tolerance_mix_pct}%), {validation.speedup:.1f}x fewer snapshots"
		)
		typer.echo(f"artefact: {written}")
		if not validation.passes:
			typer.secho(
				"the aggregation is OUTSIDE tolerance; the artefact records it and "
				"`solve` will refuse this level for this network",
				fg=typer.colors.YELLOW,
				err=True,
			)


@app.command()
def scan(
	source_id: Annotated[str | None, typer.Argument(help="Restrict to one source.")] = None,
	config: ConfigOption = None,
) -> None:
	"""Run one intelligence-scanning pass.

	``--source`` narrows the run to one connector by name. The connectors that
	need a credential are skipped unless the credential is in the environment,
	rather than failing the whole run: a news pass with no NewsAPI key is a
	smaller pass, not a broken one.
	"""
	import asyncio

	from alea.scanning.connectors import default_connectors
	from alea.scanning.service import ScanningService

	with _run("cli.scan", source=source_id):
		loaded = _load(config, None, None)
		connectors = default_connectors()
		if source_id is not None:
			connectors = [c for c in connectors if c.source_name == source_id]
			if not connectors:
				known = ", ".join(sorted(c.source_name for c in default_connectors()))
				typer.secho(
					f"unknown source {source_id!r}; known: {known}",
					fg=typer.colors.RED,
					err=True,
				)
				raise typer.Exit(code=2)

		async def _scan() -> Any:
			service = ScanningService(connectors, config=loaded)
			try:
				return await service.run()
			finally:
				await service.aclose()

		result = asyncio.run(_scan())
		typer.echo(
			f"scan: {result.signals_extracted} signals from {result.documents_kept} documents, "
			f"{result.signals_enqueued} queued for review"
		)


@app.command()
def serve(
	config: ConfigOption = None,
	host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
	port: Annotated[int, typer.Option("--port")] = 8000,
	reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
	"""Serve the REST API."""
	import uvicorn

	# The run record is written before the server starts and its exit line when
	# the server stops, so the log says a serve is in progress for as long as it
	# is -- which is the fact a reader asking "what is running" wants.
	with _run("cli.serve", host=host, port=port):
		loaded = _load(config, None, None)
		from alea.api.app import create_app

		uvicorn.run(create_app(loaded), host=host, port=port, reload=reload)


@app.command()
def health(
	config: ConfigOption = None,
	quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print nothing; exit with the verdict.")] = False,
) -> None:
	"""Check the local stores, and exit non-zero when one is unusable.

	This is what the container's ``HEALTHCHECK`` runs (`13-deployment.md` §3.1),
	so it must work without the API being up: an orchestrator probing a process
	that is in the middle of restarting needs an answer from the process, not
	from an HTTP client that will time out.

	§6.2 asks ``/health`` to report the API, the job store, the artefact store
	and the last successful pipeline run. The API is not part of this check --
	the process running this command *is* the check -- so the three stores are
	what is probed here, and the route adds the API's own liveness on top.
	"""
	import sqlite3

	from alea.config.paths import resolve

	loaded = _load(config, None, None)
	problems: list[str] = []

	# The job store and the review queue are the two SQLite databases. Opening
	# each and counting a table is a real read: a file that exists but cannot be
	# queried is a store that is not usable, and an existence check would call
	# that healthy.
	from alea.scanning.review.queue import queue_path

	for label, path, table in (
		("job store", resolve(loaded.api.job_store_path), "jobs"),
		# Through the same helper the stage uses, so the doctor probes the file
		# the pipeline actually writes rather than one that happens to match.
		("review queue", queue_path(loaded.paths.results), "signal_versions"),
	):
		if not path.exists():
			# Not a problem on a first boot: the store is created on first use.
			continue
		try:
			connection = sqlite3.connect(path)
			try:
				connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
			finally:
				connection.close()
		except sqlite3.Error as exc:
			problems.append(f"{label} at {path} is unreadable: {exc}")

	results = resolve(loaded.paths.results)
	if not results.exists():
		problems.append(f"results root {results} does not exist")

	from alea.api.runs import RunLog

	runs = RunLog(loaded).list(limit=1)
	last = runs[0] if runs else None

	if problems:
		for problem in problems:
			typer.secho(f"unhealthy: {problem}", fg=typer.colors.RED, err=True)
		raise typer.Exit(code=1)
	if not quiet:
		countries = ", ".join(str(c) for c in loaded.scenario.countries)
		typer.echo(f"ok: {countries}")
		typer.echo(f"  results: {results}")
		typer.echo(f"  last run: {last.run_id if last else 'none'}")


@quality_app.command("claims")
def quality_claims(
	milestone: Annotated[
		str | None,
		typer.Option("--milestone", "-m", help="Run the review as of this milestone, e.g. M2."),
	] = None,
	quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print nothing; exit with the verdict.")] = False,
) -> None:
	"""The `[UNVERIFIED]` register, and the review §9 criterion 5 asks for.

	`12-quality.md` §9: "the `[UNVERIFIED]` register is reviewed at every
	milestone". The review lists the claims whose milestone has arrived and that
	are still unresolved, because -- in the plan's own words -- "a claim that
	stays in the codebase unverified past its milestone is a claim that will be
	quoted."

	With ``--milestone`` it exits non-zero when anything is due, so a milestone
	check can gate on it. Without, it prints the register.
	"""
	from alea.quality.claims import REGISTER, review

	if milestone:
		result = review(milestone)
		if result.due:
			for claim in result.due:
				typer.secho(
					f"due at {claim.milestone}: #{claim.number} {claim.claim} "
					f"({claim.resolution})",
					fg=typer.colors.YELLOW,
					err=True,
				)
			if not quiet:
				typer.echo(f"{len(result.due)} claim(s) unresolved at {milestone}")
			raise typer.Exit(code=1)
		if not quiet:
			typer.echo(f"{milestone}: every claim due by now is resolved")
		return

	for claim in REGISTER:
		status = "resolved" if claim.resolved else "UNVERIFIED"
		typer.echo(f"{claim.number:2d}  {claim.milestone}  {status:10s}  {claim.claim}")


@app.command()
def version() -> None:
	"""Print the version."""
	typer.echo(__version__)


def _provisional_config() -> Config | None:
	"""The config the invoked command is about to run with, before typer parses it.

	Logging has to be configured before ``app()`` -- every module binds its
	logger at import, so by the time a command body runs the process is already
	configured -- but the config file that names the level arrives as a flag
	typer has not parsed yet. This reads the same flags off ``sys.argv``, which
	is the only source available at that point, and returns ``None`` when there
	is nothing to read rather than guessing.

	WHY it does not simply call ``load_config()`` bare: that reads
	``config.default.yaml`` and nothing else, so ``--config`` could never change
	the log level. ``logging.level`` and ``logging.json_output`` were declared
	in every config file, merged and validated, and reached nothing.

	WHY a failure here is not fatal: ``main`` falls back to the environment and
	the defaults, and ``_load`` reports a genuinely broken config properly once
	typer has parsed the flags. A logging setup that exited here would replace
	that message with a traceback about YAML.
	"""
	assert isinstance(sys.argv, list), "sys.argv is not a list; this is not a normal interpreter"
	argv = sys.argv[1:]
	config: str | None = None
	scenario: str | None = None
	overrides: list[str] = []
	index = 0
	while index < len(argv):
		token = argv[index]
		# `--flag=value` and `--flag value` are both how typer accepts these.
		name, _, inline = token.partition("=")
		if name in ("--config", "-c"):
			value = inline or (argv[index + 1] if index + 1 < len(argv) else "")
			config = value or None
			index += 1 if inline else 2
			continue
		if name in ("--scenario", "-s"):
			value = inline or (argv[index + 1] if index + 1 < len(argv) else "")
			scenario = value or None
			index += 1 if inline else 2
			continue
		if name == "--set":
			value = inline or (argv[index + 1] if index + 1 < len(argv) else "")
			if value:
				overrides.append(value)
			index += 1 if inline else 2
			continue
		index += 1
	if config is None and scenario is None and not overrides:
		return None
	return load_config(config, scenario=scenario, overrides=overrides, require=False)


def main() -> None:
	"""Console-script entry point.

	Logging is configured from the config file the command will actually run
	with, not from this function's defaults. ``configure()`` bare left
	``logging.level`` and ``logging.json_output`` declared in every config file
	and read by nothing, so a config asking for DEBUG produced an INFO run and
	the only way to get a debug log was an environment variable the config does
	not mention.
	"""
	provisional = None
	try:
		provisional = _provisional_config()
	except Exception:  # noqa: BLE001 - a broken config is reported by the command, not here
		provisional = None
	if provisional is not None:
		configure_from(provisional)
	else:
		configure()
	try:
		app()
	except KeyboardInterrupt:  # pragma: no cover - interactive
		sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
	main()

@expr_app.command("render")
def expr_render(
	formula: Annotated[str, typer.Argument(help="The formula, in the DSL.")],
	as_: Annotated[
		str, typer.Option("--as", help="unicode, latex, mathml, or source.")
	] = "unicode",
	values: SetOption = None,
) -> None:
	"""Render a formula. The created and rendered forms are the same object.

	Rendering does not evaluate, so a formula with free parameters renders
	without values. Passing ``--set`` substitutes them first, which is how a
	general relation is turned into the specific one a report quotes.
	"""
	from alea.prg.dsl import parse

	with _run("cli.expr.render"):
		expression = parse(formula)
		for override in values or []:
			key, _, raw = override.partition("=")
			expression = expression.subs({key: float(raw)})
		rendered = {
			"unicode": expression.unicode,
			"latex": expression.latex,
			"mathml": expression.mathml,
			"source": expression.source,
		}
		if as_ not in rendered:
			typer.secho(
				f"--as must be one of {sorted(rendered)}, got {as_!r}",
				fg=typer.colors.RED,
				err=True,
			)
			raise typer.Exit(code=2)
		typer.echo(rendered[as_]())


@expr_app.command("eval")
def expr_eval(
	formula: Annotated[str, typer.Argument(help="The formula, in the DSL.")],
	values: SetOption = None,
) -> None:
	"""Evaluate a formula against a parameter set."""
	from alea.prg.dsl import parse

	with _run("cli.expr.eval"):
		expression = parse(formula)
		scoped: dict[str, float] = {}
		for override in values or []:
			key, _, raw = override.partition("=")
			scoped[key] = float(raw)
		missing = sorted(expression.symbols - set(scoped))
		if missing:
			typer.secho(
				f"the formula names {missing}, which --set does not provide; an "
				f"expression with free parameters has no single value",
				fg=typer.colors.RED,
				err=True,
			)
			raise typer.Exit(code=2)
		typer.echo(f"{expression.eval(scoped):.10g}")


@expr_app.command("diff")
def expr_diff(
	formula: Annotated[str, typer.Argument(help="The formula, in the DSL.")],
	with_respect_to: Annotated[str, typer.Argument(help="The symbol to differentiate by.")],
	as_: Annotated[str, typer.Option("--as", help="unicode, latex, or source.")] = "source",
) -> None:
	"""Differentiate a formula symbolically."""
	from alea.prg.dsl import parse

	with _run("cli.expr.diff"):
		expression = parse(formula)
		if with_respect_to not in expression.symbols:
			typer.secho(
				f"{with_respect_to!r} does not appear in the formula, so the "
				f"derivative is identically zero and says nothing",
				fg=typer.colors.RED,
				err=True,
			)
			raise typer.Exit(code=2)
		derivative = expression.diff(with_respect_to)
		typer.echo(
			{"unicode": derivative.unicode, "latex": derivative.latex, "source": derivative.source}[
				as_
			]()
		)


@expr_app.command("simplify")
def expr_simplify(
	formula: Annotated[str, typer.Argument(help="The formula, in the DSL.")],
) -> None:
	"""Simplify a formula, keeping it a formula."""
	from alea.prg.dsl import parse

	with _run("cli.expr.simplify"):
		typer.echo(parse(formula).simplify().source())


@expr_app.command("solve")
def expr_solve(
	formula: Annotated[str, typer.Argument(help="The formula, in the DSL.")],
	unknown: Annotated[str, typer.Argument(help="The symbol to solve for.")],
	bracket: Annotated[
		str,
		typer.Option("--bracket", help="Search interval, as LOW,HIGH."),
	],
	values: SetOption = None,
	equals: Annotated[float, typer.Option("--equals", help="The value the formula takes.")] = 0.0,
) -> None:
	"""Solve a formula for one unknown, numerically, within a bracket.

	The bracket is required and not guessed. Only the caller knows the range
	the answer is admissible over: a capacity factor lives in ``[0, 1]`` and a
	carbon price does not, and a solver handed a wide interval finds whichever
	root it meets first -- which is how a learning curve yields a negative cost.
	"""
	from alea.prg.dsl import parse, solve_for

	with _run("cli.expr.solve"):
		low_raw, _, high_raw = bracket.partition(",")
		if not high_raw:
			typer.secho(
				f"--bracket needs LOW,HIGH, got {bracket!r}", fg=typer.colors.RED, err=True
			)
			raise typer.Exit(code=2)
		scoped: dict[str, float] = {}
		for override in values or []:
			key, _, raw = override.partition("=")
			scoped[key] = float(raw)
		try:
			answer = solve_for(
				parse(formula),
				unknown,
				scoped,
				bracket=(float(low_raw), float(high_raw)),
				residual=equals,
			)
		except Exception as exc:
			typer.secho(f"cannot solve: {exc}", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=1) from exc
		typer.echo(f"{answer:.10g}")


@prg_app.command("conflicts")
def prg_conflicts(
	set_: SetOption = None,
	rank: Annotated[
		int, typer.Option("--rank", help="Corrections to show per conflict.")
	] = 3,
) -> None:
	"""Why a scenario is inconsistent, and what to move to fix it.

	`check` says *which equations fail*. This says *what a person should do
	about it*: which kind of inconsistency it is, which input is responsible,
	and by how much it would have to move. Exits non-zero on any conflict, so
	it gates the same way `check` does.
	"""
	from alea.prg import load_graph
	from alea.prg.conflicts import detect_conflicts

	with _run("cli.prg.conflicts"):
		graph = load_graph()
		values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
		supplied = dict(values)
		for override in set_ or []:
			key, _, raw = override.partition("=")
			if key not in graph.nodes:
				typer.secho(
					f"{key!r} is not a parameter in the graph", fg=typer.colors.RED, err=True
				)
				raise typer.Exit(code=2)
			# A derived parameter *is* accepted here, unlike in `check`: setting
			# one is exactly the over-determination this command exists to
			# report, and refusing it would hide the conflict the caller has.
			values[key] = float(raw)
			supplied[key] = float(raw)
		result = graph.propagate(values)
		report = detect_conflicts(
			graph, result.values, supplied=supplied, rank=rank
		)
		for conflict in report.ranked():
			typer.secho(str(conflict), fg=typer.colors.RED, err=True)
		typer.echo(report.summary())
		if not report.consistent:
			raise typer.Exit(code=1)


@prg_app.command("sensitivity")
def prg_sensitivity(
	parameter: Annotated[
		str, typer.Argument(help="The derived parameter to differentiate.")
	],
	set_: SetOption = None,
	top: Annotated[
		int, typer.Option("--top", help="Inputs to show, by magnitude.")
	] = 10,
	elastic: Annotated[
		bool, typer.Option("--elasticity", help="Show dimensionless elasticity.")
	] = False,
) -> None:
	"""How much a derived parameter moves when each input moves.

	Exact forward-mode derivatives, not finite differences: the graph's
	equations are differentiable expressions and it knows the order they are
	computed in, so the derivative is a chain along that path. A difference
	quotient carries a truncation error that has to be tuned per parameter, and
	the tuning is what makes a sensitivity report irreproducible.
	"""
	from alea.prg import load_graph
	from alea.prg.sensitivity import elasticity, sensitivity

	with _run("cli.prg.sensitivity", parameter=parameter):
		graph = load_graph()
		values = {k: n.default for k, n in graph.nodes.items() if n.default is not None}
		for override in set_ or []:
			key, _, raw = override.partition("=")
			if key not in graph.nodes:
				typer.secho(
					f"{key!r} is not a parameter in the graph", fg=typer.colors.RED, err=True
				)
				raise typer.Exit(code=2)
			values[key] = float(raw)
		propagated = graph.propagate(values)
		row = sensitivity(graph, parameter, propagated.values)
		if elastic:
			weights = elasticity(graph, parameter, propagated.values)
			for name, weight in sorted(
				weights.items(), key=lambda kv: abs(kv[1]), reverse=True
			)[:top]:
				typer.echo(f"  {name:38s} {weight:+12.6g}")
		else:
			for name, value in row.largest(top):
				typer.echo(f"  {name:38s} {value:+12.6g}")
		typer.echo(f"{parameter} = {propagated.values.get(parameter):.6g} ({row.method})")


@prg_app.command("units")
def prg_units() -> None:
	"""Check every equation's two sides for a shared dimension.

	Exits non-zero when an equation is inconsistent, so it gates the graph the
	way `check` gates a scenario. The dimensional claim was a stated gap in
	`views.py` -- and it is not academic: the graph makes the error in several
	equations, on identities the carbon budget and the debt schedule are built
	from. An equation the walker cannot decide is printed separately and does
	not count as a pass.
	"""
	from alea.prg import load_graph
	from alea.prg.units import check_graph

	with _run("cli.prg.units"):
		report = check_graph(load_graph())
		for check in report.inconsistent:
			typer.secho(check.summary(), fg=typer.colors.RED, err=True)
		for check in report.undecidable:
			typer.secho(check.summary(), fg=typer.colors.YELLOW, err=True)
		typer.echo(report.summary())
		if report.inconsistent:
			raise typer.Exit(code=1)


@prg_app.command("audit")
def prg_audit(
	name: Annotated[str, typer.Argument(help="Stored scenario name.")],
	version: Annotated[
		str | None, typer.Option("--version", help="Version; defaults to the latest.")
	] = None,
) -> None:
	"""Audit a stored scenario's solved result against the graph.

	Exits non-zero on any violation, so it can gate a result the way `check`
	gates a parameter set. The two ask different questions: `check` asks whether
	the parameters a caller hands in are self-consistent, and this asks whether
	the answer the optimiser returned is one the graph's identities accept. A
	scenario can pass the first and fail the second, which is the whole reason
	the seam exists.
	"""
	from alea.prg.audit import audit_scenario_result, fleet_intensity_gap
	from alea.whatif.store import latest_version, load_scenario

	with _run("cli.prg.audit", scenario=name):
		resolved = version or latest_version(name)
		if resolved is None:
			typer.secho(f"no stored scenario named {name!r}", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=2)
		record = load_scenario(name, resolved)
		audit = audit_scenario_result(record.result)
		for violation in audit.violations:
			typer.secho(f"violation: {violation}", fg=typer.colors.RED, err=True)
		for parameter, value in sorted(audit.excursions.items()):
			typer.secho(
				f"out of range: {parameter} = {value:.6g}", fg=typer.colors.RED, err=True
			)
		gap = fleet_intensity_gap(record.result)
		typer.echo(f"{name} {resolved}: {audit.summary()}")
		typer.echo(
			f"fleet intensity {gap['engine_intensity']:.6g} t/MWh against the "
			f"graph's {gap['graph_factor']:.6g} (ratio {gap['ratio']:.4g})"
		)
		if not audit.consistent:
			raise typer.Exit(code=1)
