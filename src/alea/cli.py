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
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from alea import __version__
from alea.config.loader import ConfigError, load_config
from alea.config.models import Config
from alea.logging import configure, get_logger, new_run_id
from alea.registry import registry, technologies, tier_counts

app = typer.Typer(
	no_args_is_help=True,
	add_completion=False,
	help="ALEA — African Light and Energy Analytics.",
)

config_app = typer.Typer(no_args_is_help=True, help="Inspect and validate configuration.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect the country and technology registries.")
quality_app = typer.Typer(no_args_is_help=True, help="Validation coverage and the unverified register.")
app.add_typer(config_app, name="config")
app.add_typer(registry_app, name="registry")
app.add_typer(quality_app, name="quality")

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
	from alea.scanning.review.queue import DEFAULT_QUEUE_PATH

	for label, relative, table in (
		("job store", loaded.api.job_store_path, "jobs"),
		("review queue", DEFAULT_QUEUE_PATH, "signal_versions"),
	):
		path = resolve(relative)
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


def main() -> None:
	"""Console-script entry point."""
	configure()
	try:
		app()
	except KeyboardInterrupt:  # pragma: no cover - interactive
		sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
	main()
