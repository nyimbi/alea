# SPDX-License-Identifier: MIT
"""Delivery adapters.

Eighteen channels, one API (AD-7). Each adapter is a formatter and, where the
channel is push, a webhook -- never a second codebase with its own data path.
The insight the architecture rests on is that a USSD menu and a web dashboard
read the same endpoints; this package is where that is either true or not.

The two adapters with a hard external constraint are USSD (182 characters) and
SMS (160). Both enforce their limit in code, against the constants in
``alea.api.views``, and neither truncates: a truncated forecast is a wrong
forecast, and the adapter selects the top-N rows and states how many it omitted
so the message is complete at its own resolution.
"""

from __future__ import annotations

from alea.api.adapters import dashboard, sms, ussd, whatsapp

__all__ = ["dashboard", "sms", "ussd", "whatsapp"]
