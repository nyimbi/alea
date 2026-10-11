# SPDX-License-Identifier: MIT
"""Layer 8: the REST API and its delivery adapters.

One API, many adapters (AD-7). The web dashboard, the USSD menu, the SMS
gateway, the WhatsApp bot and every other channel the specification lists read
the same endpoints and the same data path; an adapter formats, it does not
compute.

The four decisions that shape this package, each of which corrects a defect the
plan records in the specification's own API sketch (11-layer8 §2):

1. **No GET takes a body.** A GET takes scalar query parameters; anything with a
   complex body is a POST. A GET with a body is not cacheable, not linkable, and
   is dropped silently by many clients.
2. **No route blocks on a solve.** Every long-running operation is a durable
   job with a pollable status, stored in SQLite so it survives a restart. A job
   whose worker died reports ``interrupted`` rather than reading as still
   running.
3. **API keys are stored hashed**, never in plaintext, and the plaintext is
   shown exactly once at creation.
4. **Every value carries its basis.** The API does not serve bare numbers, so a
   consumer cannot render a proxy estimate as though it were a measurement.

``create_app(config)`` is the entry point the CLI calls.
"""

from __future__ import annotations

from alea.api.app import create_app

__all__ = ["create_app"]
