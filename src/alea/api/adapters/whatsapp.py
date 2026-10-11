# SPDX-License-Identifier: MIT
"""The WhatsApp adapter.

WhatsApp is the least constrained of the messaging adapters -- 4096 characters
in a message body, rich formatting, and buttons -- so its job is not to fit a
screen but to shape an answer for a chat client.

Two things the Meta Business API imposes and this adapter respects:

* **A webhook must answer within a few seconds or the message is retried.** So
  the handler formats from what is already computed and never triggers a solve;
  a long-running request would be retried and answered twice.
* **A template message is the only kind that can start a conversation.** The
  free-form reply here is valid only inside the 24-hour window a user message
  opens, which is why the inbound webhook is the entry point.

The reply is a JSON payload in the shape the Cloud API expects, so a deployment
points the webhook at this endpoint and forwards the body unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from alea.api.deps import PublicDep, StateDep

router = APIRouter(prefix="/adapters/whatsapp", tags=["adapters"])

MAX_BODY_CHARS = 4096


class WhatsAppInbound(BaseModel):
	"""The subset of the Cloud API's webhook body this adapter reads.

	Extra keys are permitted here, unlike every other model in the package: Meta
	owns this schema and adds fields without notice, and forbidding extras would
	break the webhook on their next release.
	"""

	model_config = ConfigDict(extra="allow")

	from_number: str = ""
	text: str = ""


class WhatsAppReply(BaseModel):
	"""The reply payload, in the Cloud API's shape."""

	model_config = ConfigDict(extra="forbid")

	messaging_product: str = "whatsapp"
	to: str
	type: str = "text"
	text: dict[str, str]


def format_whatsapp_forecast(rows: list, *, country: str = "", horizon_hours: int = 24) -> str:
	"""Render a forecast for a chat client, longest-horizon detail included.

	The whole list is rendered, because the medium fits it: a WhatsApp message
	that omitted zones to save characters would be doing so for no reason.
	"""
	assert isinstance(rows, list), "rows is a list of forecast rows"
	if not rows:
		return f"No outage risk data for {country or 'this area'} in the next {horizon_hours}h."
	lines = [f"*{country or 'Outage'} risk, next {horizon_hours}h*"]
	for row in rows:
		percent = round(row.probability.value * 100)
		marker = "!" if percent >= 50 else "-"
		lines.append(f"{marker} {row.grid_zone}: {percent}%")
	body = "\n".join(lines)
	if len(body) > MAX_BODY_CHARS:  # pragma: no cover - a national fleet is small
		raise ValueError(
			f"WhatsApp body is {len(body)} characters, limit {MAX_BODY_CHARS}; "
			f"select a prefix of zones rather than truncating"
		)
	return body


@router.post("", response_model=WhatsAppReply, summary="One WhatsApp turn")
async def whatsapp_turn(
	state: StateDep, principal: PublicDep, request: WhatsAppInbound
) -> WhatsAppReply:
	"""Answer one WhatsApp message with the current forecast."""
	assert state is not None, "whatsapp_turn needs application state"
	country = state.config.scenario.countries[0] if state.config.scenario.countries else ""
	rows = state.repository.outage_forecasts(country=country, horizon_hours=24) if country else []
	body = format_whatsapp_forecast(rows, country=country or "This area")
	return WhatsAppReply(to=request.from_number, text={"body": body})


__all__ = ["MAX_BODY_CHARS", "WhatsAppInbound", "WhatsAppReply", "format_whatsapp_forecast", "router"]
