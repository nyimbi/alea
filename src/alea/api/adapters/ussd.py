# SPDX-License-Identifier: MIT
"""The USSD adapter.

USSD is a 182-character screen. That is the whole engineering problem: a
forecast that renders as a table must render as a sentence, and the sentence
must be complete.

**Truncation is not acceptable.** A truncated forecast is a wrong forecast --
it drops the zones that did not fit and reads as though they were not at risk.
The adapter instead selects the top-N zones by probability and states how many
it omitted, so the message is complete at its own resolution: a reader learns
that there are more zones and how many, which is a true statement, where
``"Zone A 72%, Zone B 4"`` is not.

The limit is enforced twice: the formatter never emits more than
:data:`~alea.api.views.USSD_MAX_CHARS`, and :class:`UssdResponse` refuses to
construct with more. The gate reads the same constant the formatter does.

USSD sessions are stateless at the protocol level -- the aggregator sends the
whole concatenated input on every turn -- so the menu is a pure function of
``text`` and needs no session store.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from alea.api.deps import PublicDep, StateDep
from alea.api.views import USSD_MAX_CHARS, OutageForecastRowOut, UssdRequest, UssdResponse

router = APIRouter(prefix="/adapters/ussd", tags=["adapters"])

DEFAULT_ZONE_LIMIT = 4
"""How many zones to try to fit. The formatter fits fewer when they are long."""

MENU = "ALEA\n1 Outage risk\n2 Power price\n3 System status\n0 Exit"


def format_ussd_forecast(
	rows: list[OutageForecastRowOut],
	*,
	country: str = "",
	horizon_hours: int = 24,
	max_chars: int = USSD_MAX_CHARS,
) -> str:
	"""Render a forecast for a USSD screen, complete within ``max_chars``.

	Selects the largest prefix of ``rows`` (which the repository already orders
	by probability descending) whose full rendering -- including the count of
	omitted zones -- fits the screen. Falls back to progressively shorter
	renderings rather than cutting the string.
	"""
	assert max_chars > 0, "a screen has a positive width"
	assert isinstance(rows, list), "rows is a list of forecast rows"
	if not rows:
		return _fit(f"No outage risk data for {country or 'this area'}.", max_chars, country)

	header = f"{country or 'Outage'} risk {horizon_hours}h: "
	for count in range(min(len(rows), DEFAULT_ZONE_LIMIT * 4), 0, -1):
		parts = [
			f"{row.grid_zone} {round(row.probability.value * 100)}%" for row in rows[:count]
		]
		omitted = len(rows) - count
		tail = f" +{omitted} more" if omitted else ""
		message = f"{header}{', '.join(parts)}{tail}"
		if len(message) <= max_chars:
			return message

	# Even one named zone does not fit. Reduce the header, then the payload, but
	# never cut a zone name: an unnamed percentage is still a true statement.
	top = round(rows[0].probability.value * 100)
	for message in (
		f"{country or 'Area'} risk {horizon_hours}h: {top}%",
		f"{country or 'Area'} risk {top}%",
		f"{top}% outage risk",
	):
		if len(message) <= max_chars:
			return message

	# A screen narrower than a three-character percentage is not a USSD screen.
	raise ValueError(
		f"cannot render a forecast within {max_chars} characters; "
		f"the screen is too narrow for any complete message"
	)


def _fit(message: str, max_chars: int, country: str) -> str:
	assert message, "an empty message is not a message"
	if len(message) <= max_chars:
		return message
	shorter = f"No data for {country or 'area'}."
	if len(shorter) <= max_chars:
		return shorter
	raise ValueError(f"cannot render a message within {max_chars} characters")


def format_ussd_prices(rows: list, *, country: str = "", max_chars: int = USSD_MAX_CHARS) -> str:
	"""Render a price summary for a USSD screen."""
	assert isinstance(rows, list), "rows is a list of price rows"
	if not rows:
		return _fit(f"No price data for {country or 'this area'}.", max_chars, country)
	latest = rows[-1]
	message = f"{country or 'Price'} now {latest.price.value:.1f} {latest.price.unit}"
	if len(message) <= max_chars:
		return message
	return _fit(f"{country or 'Price'} {latest.price.value:.0f} {latest.price.unit}", max_chars, country)


def handle(text: str, *, country: str) -> tuple[str, bool]:
	"""The menu state machine. Returns ``(screen, end_session)``.

	``text`` is the aggregator's concatenated input: ``""`` on the first turn,
	``"1"`` after one choice, ``"1*2"`` after two. Only the last segment matters
	for a two-level menu, so the machine reads it and ignores the history.
	"""
	assert isinstance(text, str), "USSD input is text"
	segments = [segment for segment in text.split("*") if segment != ""]
	if not segments:
		return MENU, False
	choice = segments[-1]
	if choice == "0":
		return "Thank you for using ALEA.", True
	if choice == "1":
		return f"OUTAGE {country}", False
	if choice == "2":
		return f"PRICE {country}", False
	if choice == "3":
		return "STATUS", False
	return "Invalid choice. Reply 0 to exit.", False


@router.post("", response_model=UssdResponse, summary="One USSD turn")
async def ussd_turn(
	state: StateDep, principal: PublicDep, request: UssdRequest
) -> UssdResponse:
	"""Answer one USSD turn.

	A POST because the aggregator posts a form body, and a USSD turn is not a
	read -- it is an interaction. The response is bounded at 182 characters by
	the model, so an adapter bug cannot ship an over-long screen.
	"""
	assert state is not None, "ussd_turn needs application state"
	country = _country_for(state)
	screen, end = handle(request.text, country=country)
	if screen.startswith("OUTAGE "):
		rows = state.repository.outage_forecasts(country=country, horizon_hours=24)
		return UssdResponse(text=format_ussd_forecast(rows, country=country), end_session=True)
	if screen.startswith("PRICE "):
		rows = state.repository.prices(country=country)
		return UssdResponse(text=format_ussd_prices(rows, country=country), end_session=True)
	if screen == "STATUS":
		counts = await state.job_store.counts()
		text = f"ALEA up. {counts.get('running', 0)} jobs running."
		if len(text) > USSD_MAX_CHARS:  # pragma: no cover - defensive
			text = "ALEA up."
		return UssdResponse(text=text, end_session=True)
	return UssdResponse(text=screen, end_session=end)


def _country_for(state) -> str:
	"""The country a USSD session is about.

	A phone number does not carry a country, and the aggregator's service code
	does not either in this design, so the session country is the deployment's
	configured first country. A per-zone USSD deployment would map the service
	code instead; that mapping is a config change, not a code change.
	"""
	countries = list(state.config.scenario.countries)
	if not countries:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="the deployment configures no countries, so a USSD session has no subject",
		)
	return countries[0] or ""


__all__ = [
	"DEFAULT_ZONE_LIMIT",
	"MENU",
	"format_ussd_forecast",
	"format_ussd_prices",
	"handle",
	"router",
]
