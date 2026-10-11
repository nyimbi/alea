# SPDX-License-Identifier: MIT
"""The SMS adapter.

SMS is 160 characters, and unlike USSD it has a second option: a link. The
adapter spends its budget on the one number that matters and points at the API
for the rest, because a link costs about twenty characters and carries a
complete answer.

The same rule as USSD applies: no truncation. A message that reads
``"Kenya outage risk 24h: Nairobi 72%, Momb"`` is not a shorter message, it is a
different and false one. The formatter selects what fits and says so.
"""

from __future__ import annotations

from fastapi import APIRouter

from alea.api.adapters.ussd import format_ussd_forecast
from alea.api.deps import PublicDep, StateDep
from alea.api.views import SMS_MAX_CHARS, OutageForecastRowOut, SmsResponse

router = APIRouter(prefix="/adapters/sms", tags=["adapters"])

DEFAULT_LINK = "https://api.alea.africa/v1/reports/daily"
"""Where the message points. A config value in a full deployment."""


def format_sms_forecast(
	rows: list[OutageForecastRowOut],
	*,
	country: str = "",
	horizon_hours: int = 24,
	link: str = "",
	max_chars: int = SMS_MAX_CHARS,
) -> SmsResponse:
	"""Render a forecast as one SMS, complete within ``max_chars``.

	The link is reserved first, so the body is never cut to make room for it.
	"""
	assert max_chars > 0, "an SMS has a positive length"
	assert isinstance(rows, list), "rows is a list of forecast rows"
	reserved = len(link) + 1 if link else 0
	body_budget = max_chars - reserved
	if body_budget < 8:
		raise ValueError(
			f"the link ({len(link)} characters) leaves no room for a message in "
			f"{max_chars}; send the link alone or shorten it"
		)
	body = format_ussd_forecast(
		rows, country=country, horizon_hours=horizon_hours, max_chars=body_budget
	)
	return SmsResponse(text=body, link=link)


@router.post("", response_model=SmsResponse, summary="Render a forecast as one SMS")
async def sms_forecast(
	state: StateDep,
	principal: PublicDep,
	country: str | None = None,
	horizon_hours: int = 24,
	link: str = DEFAULT_LINK,
) -> SmsResponse:
	"""Render the current forecast as one SMS.

	A POST because it takes a body from the SMS gateway; the parameters are
	query-shaped because there is nothing complex here, but the gateway posts
	them and a GET with a body is the defect this layer exists to avoid.
	"""
	assert state is not None, "sms_forecast needs application state"
	subject = country or (state.config.scenario.countries[0] if state.config.scenario.countries else "")
	if not subject:
		return SmsResponse(text="ALEA: no country configured for this deployment.")
	rows = state.repository.outage_forecasts(country=subject, horizon_hours=horizon_hours)
	return format_sms_forecast(
		rows, country=subject, horizon_hours=horizon_hours, link=link
	)


__all__ = ["DEFAULT_LINK", "format_sms_forecast", "router"]
