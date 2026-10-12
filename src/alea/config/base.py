# SPDX-License-Identifier: MIT
"""The base every config model inherits.

Its own module rather than a class in :mod:`alea.config.models` because the
root :class:`~alea.config.models.Config` composes the layer models, and a layer
model that inherits from a name *in* that module closes a cycle: ``models``
imports ``alea.outages.views`` for the ``predictive`` section, and
``outages.views`` imports this class back. Python resolves that only when the
import order happens to define the name first, which is a package that imports
cleanly from one entry point and raises ``ImportError: cannot import name`` from
another. A leaf module has no order to get wrong.

Nothing here imports anything but pydantic and the country registry, so it stays
a leaf.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AleaConfig(BaseModel):
	"""Base for every config model.

	``extra='forbid'`` is not stylistic. An unknown key is a typo, and a typo that
	reaches a solve costs hours; failing at load costs a second and names the key.
	``frozen=True`` means a config is a value: nothing downstream can mutate the
	configuration it was handed, so a stage cannot change the parameters another
	stage will read.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		frozen=True,
	)


__all__ = ["AleaConfig"]
