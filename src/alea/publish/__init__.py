# SPDX-License-Identifier: MIT
"""The serving projection: layer results as the tables the API reads.

The API's contract (11-layer8 §1) is that **no route computes**. Every route
reads an artefact. That contract has a second half nobody wrote down: something
must *produce* those artefacts, and for a year nothing did. The Layer 8 suite
passed because `tests/ci/test_api_layer8.py` writes all fourteen paths as
fixtures -- and a test that builds its own inputs cannot detect that no
production code builds them.

This package is the missing producer. It reads what the layers compute and
writes the tabular artefacts the repository reads, at the paths the repository
names.

**Why a projection and not a change to the layers.** A layer result is an
object shaped for the layer: `TlensRanking` is a ranked list with its parameters,
`ResilienceMetrics` is one wide record, `ClearingResult` is one clearing. The
serving table is a different shape -- one row per line, one row per metric, one
row per zone-hour. Making the layers emit the serving shape would put a
consumer's row layout inside the model, which is how a model acquires a field it
cannot explain. The seam stays where AD-4 puts it: the layer writes its result,
the projection reads it and writes the table.

**The schemas are the contract, and they are checked.** Each table has an
`ArtefactSchema` in :mod:`alea.publish.views`. A projection that drops a column
raises at write time; a repository that reads a column the schema does not
declare is a column the schema is missing. One list, read by both sides --
because two files that agree today are not one source of truth.
"""

from __future__ import annotations

from alea.publish.service import PublishError, project, table_path
from alea.publish.views import (
	PUBLISHED_TABLES,
	SERVING_SCHEMAS,
	UNPROJECTABLE,
	serving_schema,
)

__all__ = [
	"PUBLISHED_TABLES",
	"SERVING_SCHEMAS",
	"UNPROJECTABLE",
	"PublishError",
	"project",
	"serving_schema",
	"table_path",
]
