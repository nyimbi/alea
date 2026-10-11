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
from pathlib import Path
from typing import Annotated, Any

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
app.add_typer(config_app, name="config")
app.add_typer(registry_app, name="registry")

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


def _run(component: str, **context: Any) -> tuple[str, Any]:
	"""Log the entry line and return (run_id, logger).

	The run id appears on both entry and exit so a log can be joined to the
	artefacts a run produced even when the process dies in between.
	"""
	run_id = new_run_id()
	logger = get_logger(component).bind(run_id=run_id)
	logger.info("start", version=__version__, **context)
	return run_id, logger


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
	run_id, logger = _run("cli.config.validate", config=str(config))
	loaded = _load(config, scenario, set_)
	if not quiet:
		countries = ", ".join(loaded.scenario.countries)
		typer.echo(f"config ok: countries={countries}")
		typer.echo(f"  horizons: {loaded.scenario.planning_horizons}")
		typer.echo(f"  clusters: {loaded.scenario.clusters}")
		typer.echo(f"  solver:   {loaded.solve.solver} (losses={loaded.solve.transmission_losses})")
	logger.info("done", run_id=run_id)


@config_app.command("show")
def config_show(
	config: ConfigOption = None,
	scenario: ScenarioOption = None,
	set_: SetOption = None,
) -> None:
	"""Print the fully merged configuration as JSON."""
	_run("cli.config.show", config=str(config))
	loaded = _load(config, scenario, set_)
	typer.echo(json.dumps(loaded.model_dump(mode="json"), indent=2, sort_keys=True))


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


@registry_app.command("export")
def registry_export(out: OutOption) -> None:
	"""Write both registries to JSON."""
	run_id, logger = _run("cli.registry.export", out=str(out))
	payload = {
		"countries": [c.model_dump(mode="json") for c in registry().values()],
		"technologies": [t.model_dump(mode="json") for t in technologies().values()],
	}
	out.parent.mkdir(parents=True, exist_ok=True)
	out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
	logger.info("done", run_id=run_id, countries=len(payload["countries"]))
	typer.echo(f"wrote {len(payload['countries'])} countries to {out}")


@registry_app.command("check")
def registry_check() -> None:
	"""Assert the registry invariants and exit non-zero if any fails."""
	_run("cli.registry.check")
	counts = tier_counts()
	total = sum(counts.values())
	if total != 55:
		typer.secho(f"registry holds {total} countries, expected 55", fg=typer.colors.RED, err=True)
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

	run_id, logger = _run("cli.fetch", source=source_id)
	loaded = _load(config, None, None)
	root = out or Path(loaded.paths.raw)
	try:
		result = fetch_source(source_id, root, force=force, logger=logger)
	except KeyError as exc:
		typer.secho(f"unknown source: {exc}", fg=typer.colors.RED, err=True)
		raise typer.Exit(code=2) from exc
	logger.info("done", run_id=run_id, checksum=result.checksum)
	typer.echo(f"{source_id}: {result.checksum[:12]} ({result.bytes_written} bytes)")


@app.command()
def build(
	stage: Annotated[str, typer.Argument(help="Stage name, e.g. 'fleet', 'demand'.")],
	config: ConfigOption = None,
	out: OutOption = ...,
	force: ForceOption = False,
) -> None:
	"""Build one processed dataset from the raw layer."""
	from alea.io.pipeline import build_stage

	run_id, logger = _run("cli.build", stage=stage)
	loaded = _load(config, None, None)
	try:
		result = build_stage(stage, loaded, out, force=force, logger=logger)
	except KeyError as exc:
		typer.secho(f"unknown stage: {exc}", fg=typer.colors.RED, err=True)
		raise typer.Exit(code=2) from exc
	logger.info("done", run_id=run_id, checksum=result.checksum)
	typer.echo(f"{stage}: {result.checksum[:12]} -> {result.path}")


@app.command()
def solve(
	config: ConfigOption = None,
	network: Annotated[Path | None, typer.Option("--network", help="Input network.")] = None,
	out: OutOption = ...,
	horizon: Annotated[int | None, typer.Option("--horizon", help="Planning horizon year.")] = None,
) -> None:
	"""Solve a capacity-expansion problem."""
	from alea.planning.service import solve_scenario

	run_id, logger = _run("cli.solve", network=str(network), horizon=horizon)
	loaded = _load(config, None, None)
	result = solve_scenario(loaded, network=network, out=out, horizon=horizon, logger_=logger)
	logger.info("done", run_id=run_id, objective=result.objective)
	# No status check here: `solve_scenario` raises `ExpansionError` for anything
	# that is not optimal, so reaching this line means the status is one of the
	# accepted spellings and the objective is a real answer.
	typer.echo(f"solved: objective={result.objective:,.0f} in {result.seconds:.1f}s")


@app.command()
def report(
	kind: Annotated[str, typer.Argument(help="Report cadence: daily, weekly, monthly, quarterly, annual.")],
	config: ConfigOption = None,
	date: Annotated[str | None, typer.Option("--date", help="Report date, ISO 8601.")] = None,
	out: OutOption = ...,
) -> None:
	"""Generate a periodic report."""
	from alea.reporting.service import build_report

	run_id, logger = _run("cli.report", kind=kind, date=date)
	loaded = _load(config, None, None)
	result = build_report(kind, loaded, out, date=date, run_id=run_id)
	logger.info("done", run_id=run_id, report_id=result.report_id)
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

	run_id, logger = _run("cli.scan", source=source_id)
	loaded = _load(config, None, None)
	connectors = default_connectors()
	if source_id is not None:
		connectors = [c for c in connectors if c.source_name == source_id]
		if not connectors:
			known = ", ".join(sorted(c.source_name for c in default_connectors()))
			typer.secho(f"unknown source {source_id!r}; known: {known}", fg=typer.colors.RED, err=True)
			raise typer.Exit(code=2)

	async def _scan() -> Any:
		service = ScanningService(connectors, config=loaded)
		try:
			return await service.run()
		finally:
			await service.aclose()

	result = asyncio.run(_scan())
	logger.info("done", run_id=run_id, signals=result.signals_extracted)
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

	_run("cli.serve", host=host, port=port)
	loaded = _load(config, None, None)
	from alea.api.app import create_app

	uvicorn.run(create_app(loaded), host=host, port=port, reload=reload)


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
