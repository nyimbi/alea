# SPDX-License-Identifier: MIT
"""Structured logging.

Every stage logs a run id on entry and exit, so a log line can be joined to the
artefacts the run produced. Console output is for a human reading a terminal;
``json_output`` is for a log shipper.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

from alea._uuid7 import uuid7str

_configured = False


def configure(level: str = "INFO", *, json_output: bool = False, force: bool = False) -> None:
	"""Configure structlog, once per process unless ``force``.

	WHY ``force`` exists: ``get_logger`` configures on first use, and every
	module calls it at import time -- so by the time ``cli.main`` has read the
	config, the process is already configured at whatever ``ALEA_LOG_LEVEL``
	held and ``logging.level: DEBUG`` in a config file reached nothing. The
	setting was declared, merged, validated and ignored; the only route to a
	debug run was an environment variable the config does not mention.

	The CLI therefore reads the config first and calls this with ``force=True``.
	Reconfiguring is safe after the fact: ``structlog.configure`` drops the
	logger cache, so a module that bound its logger at import picks up the new
	level and renderer on its next call.
	"""
	global _configured
	if _configured and not force:
		return
	_configured = True

	logging.basicConfig(
		format="%(message)s",
		stream=sys.stderr,
		level=getattr(logging, level.upper(), logging.INFO),
		force=True,
	)

	renderer: Any = (
		structlog.processors.JSONRenderer()
		if json_output
		else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
	)

	structlog.configure(
		processors=[
			structlog.contextvars.merge_contextvars,
			structlog.processors.add_log_level,
			structlog.processors.TimeStamper(fmt="iso", utc=True),
			structlog.processors.StackInfoRenderer(),
			structlog.processors.format_exc_info,
			renderer,
		],
		# structlog's default factory prints to stdout, which puts log records
		# inside the payload of any command that writes JSON there -- `alea
		# config show` emitted its own document with `{"event": "start", ...}`
		# lines spliced into it. Diagnostics belong on stderr, so stdout stays
		# what the command produced.
		logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
		wrapper_class=structlog.make_filtering_bound_logger(
			getattr(logging, level.upper(), logging.INFO)
		),
		cache_logger_on_first_use=True,
	)


def configure_from(config: Any) -> None:
	"""Configure logging from a loaded ``Config``'s own ``logging`` section.

	The seam between the config and this module. It takes the config object
	rather than its two fields so that a caller cannot pass one and forget the
	other -- which is the shape of the defect this closes.

	The environment still wins where it is set: ``ALEA_LOG_LEVEL`` is how a
	container overrides a level without editing a config file, and a config
	that silently beat it would make the override useless.
	"""
	assert config is not None, "config must not be None"
	level = os.environ.get("ALEA_LOG_LEVEL") or str(config.logging.level)
	configure(level, json_output=bool(config.logging.json_output), force=True)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
	"""A logger bound to a component name.

	Configures at ``ALEA_LOG_LEVEL`` on first use so that a library import
	produces usable logs without the caller doing anything. ``cli.main``
	overrides this from the config once the config is loaded.
	"""
	configure(os.environ.get("ALEA_LOG_LEVEL", "INFO"))
	return structlog.get_logger(name)


def new_run_id() -> str:
	"""A fresh run id.

	UUID7, so run ids sort by creation time and a directory listing is a
	chronology.
	"""
	return uuid7str()


__all__ = ["configure", "configure_from", "get_logger", "new_run_id"]
