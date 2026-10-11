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


def configure(level: str = "INFO", *, json_output: bool = False) -> None:
	"""Configure structlog once per process."""
	global _configured
	if _configured:
		return
	_configured = True

	logging.basicConfig(
		format="%(message)s",
		stream=sys.stderr,
		level=getattr(logging, level.upper(), logging.INFO),
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
		wrapper_class=structlog.make_filtering_bound_logger(
			getattr(logging, level.upper(), logging.INFO)
		),
		cache_logger_on_first_use=True,
	)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
	"""A logger bound to a component name."""
	configure(os.environ.get("ALEA_LOG_LEVEL", "INFO"))
	return structlog.get_logger(name)


def new_run_id() -> str:
	"""A fresh run id.

	UUID7, so run ids sort by creation time and a directory listing is a
	chronology.
	"""
	return uuid7str()


__all__ = ["configure", "get_logger", "new_run_id"]
