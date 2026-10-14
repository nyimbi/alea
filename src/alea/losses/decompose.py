# SPDX-License-Identifier: MIT
"""Loss decomposition into load-, generation- and topology-driven parts.

The specification's ``_topology_driven`` returns a hardcoded ``0``:

```python
def _topology_driven(self, snapshot, base):
    \"\"\"Difference from optimal topology.\"\"\"
    return 0  # Placeholder
```

A decomposition whose components do not sum to the total is worse than no
decomposition, because it looks like an analysis and invites a conclusion about
which driver dominates (07-layer4 §6.2). It is implemented here: the
topology-driven part is the loss difference between the current network and a
loss-optimal topology obtained by optimal line switching, computed with the DC
flow the kernel already provides.

The four measurements the kernel's ``decompose_losses`` consumes are defined
precisely, because the scheme's meaning lives in their definitions:

* ``actual_losses`` — loss on the actual network at the actual dispatch.
* ``reference_losses`` — loss on the reference (all-lines-in, loss-optimal
  topology) network at the reference dispatch.
* ``losses_with_actual_load_only`` — loss on the reference network at the
  actual load, i.e. the loss the load causes measured from the no-load case.
* ``losses_with_actual_topology_only`` — loss on the actual topology at the
  reference dispatch.

The kernel then sets ``load_driven = L``, ``topology_driven = T - R`` and
``generation_driven = A - L - (T - R)``, which sum to ``A`` by construction. An
earlier formulation measured ``load_driven`` from the reference instead of from
zero and left the reference loss unattributed, so the parts summed to
``A - R`` — a decomposition that looks like an analysis and under-reports every
driver.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from alea._core import decompose_losses
from alea.logging import get_logger
from alea.losses.flow import Network, solve_snapshot
from alea.losses.views import LossComponents, LossConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class DecompositionInputs:
	"""The four loss measurements the kernel decomposes."""

	actual_losses_mwh: float
	reference_losses_mwh: float
	losses_with_actual_load_only_mwh: float
	losses_with_actual_topology_only_mwh: float


def decompose(
	inputs: DecompositionInputs,
	config: LossConfig | None = None,
) -> LossComponents:
	"""Decompose four loss measurements into the three components.

	The sum invariant is guaranteed by the kernel and re-checked by
	:class:`LossComponents`'s validator, so a caller cannot receive parts that
	do not add up.
	"""
	cfg = config or LossConfig()
	components = decompose_losses(
		inputs.actual_losses_mwh,
		inputs.reference_losses_mwh,
		inputs.losses_with_actual_load_only_mwh,
		inputs.losses_with_actual_topology_only_mwh,
	)
	result = LossComponents(
		load_driven_mwh=components["load_driven"],
		generation_driven_mwh=components["generation_driven"],
		topology_driven_mwh=components["topology_driven"],
		total_mwh=components["total"],
		tolerance=cfg.decomposition_tolerance,
	)
	assert abs(result.sum_of_parts_mwh - result.total_mwh) <= (
		abs(result.total_mwh) * cfg.decomposition_tolerance + 1e-12
	)
	logger.info(
		"losses.decompose",
		total_mwh=result.total_mwh,
		load_share=result.shares["load_driven"],
		generation_share=result.shares["generation_driven"],
		topology_share=result.shares["topology_driven"],
	)
	return result


def _snapshot_loss(
	network: Network,
	injection_mw: NDArray[np.float64],
	config: LossConfig,
) -> float:
	return solve_snapshot(network, injection_mw, config).losses_mw


def reference_injection(dispatch_mw: NDArray[np.float64]) -> NDArray[np.float64]:
	"""The mean injection across snapshots: the network at its average loading.

	Spelled once because two callers need the same vector and they must not
	disagree about it: :func:`flat_reference_dispatch` repeats it for every
	snapshot, and :func:`alea.losses.switching.optimal_switching` chooses its
	topology *at* it. A switching search run at the peak while the decomposition
	attributes against the mean would pick a reference topology the reference
	case never sees -- and the topology-driven component would then carry a
	switching decision taken under a loading the report does not show.

	The mean is over snapshots and not over hours: a dispatch whose snapshots
	stand for unequal durations is a series this function cannot weight
	correctly, and nothing here reads ``LossConfig.snapshot_hours``. Callers with
	such a series pass an explicit ``reference_dispatch_mw``.
	"""
	matrix = np.asarray(dispatch_mw, dtype=np.float64)
	if matrix.ndim != 2:
		raise ValueError(f"dispatch must be [n_snapshots, n_buses], got {matrix.shape}")
	mean = matrix.mean(axis=0)
	assert mean.shape == (matrix.shape[1],), f"{mean.shape} != ({matrix.shape[1]},)"
	return mean


def flat_reference_dispatch(dispatch_mw: NDArray[np.float64]) -> NDArray[np.float64]:
	"""The mean injection repeated for every snapshot: the reference *series*.

	The matrix form of :func:`reference_injection`. A caller that wants the
	reference case's loss over the whole series wants this; one that wants the
	loading to choose a topology at wants the vector, and handing the vector's
	caller a matrix is a shape error the solver reports rather than a subtly
	different answer -- which is what makes the two functions worth separating
	rather than one returning whichever form its caller expected.
	"""
	matrix = np.asarray(dispatch_mw, dtype=np.float64)
	mean = reference_injection(matrix)
	reference = np.tile(mean, (matrix.shape[0], 1))
	assert reference.shape == matrix.shape, f"{reference.shape} != {matrix.shape}"
	return reference


def measure(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	config: LossConfig | None = None,
	*,
	reference_dispatch_mw: NDArray[np.float64] | None = None,
	reference_network: Network | None = None,
	topology_network: Network | None = None,
) -> DecompositionInputs:
	"""Measure the four losses the decomposition consumes.

	``dispatch_mw`` is ``[n_snapshots, n_buses]``. ``reference_dispatch_mw``
	defaults to a flat dispatch carrying the same total energy — the network at
	its average loading, which is what a "reference" case means when no
	historical baseline is supplied. ``reference_network`` defaults to the
	network itself (all lines in). ``topology_network`` defaults to ``network``
	— the actual topology — because the component it feeds is defined as *what
	the actual topology adds over the reference*, so the actual network is the
	only network that can measure it.

	**That default is the repair, and its old value was the defect.** It used to
	default to the reference network, which made ``T - R`` zero for every caller
	who supplied a reference and no topology — so the first stage to resolve a
	loss-optimal reference network would have published ``topology_driven ==
	0.0`` and looked correct while measuring nothing. The specification's
	``_topology_driven = 0 # Placeholder`` was reproduced by the signature that
	was supposed to fix it. ``test_a_reference_network_alone_attributes_the_
	topology`` pins the repaired direction.
	"""
	cfg = config or LossConfig()
	dispatch = np.asarray(dispatch_mw, dtype=np.float64)
	if dispatch.ndim != 2 or dispatch.shape[1] != network.n_buses:
		raise ValueError(
			f"dispatch must be [n_snapshots, {network.n_buses}], got {dispatch.shape}"
		)
	reference = (
		flat_reference_dispatch(dispatch)
		if reference_dispatch_mw is None
		else np.asarray(reference_dispatch_mw, dtype=np.float64)
	)
	if reference.shape != dispatch.shape:
		raise ValueError(
			f"reference dispatch {reference.shape} must match dispatch {dispatch.shape}"
		)
	reference_net = reference_network or network
	topology_net = topology_network or network

	# Each snapshot's loss is in MW; the hours it stands for turn the four sums
	# into the energies the decomposition's field names claim.
	hours = cfg.snapshot_hours
	actual = float(sum(_snapshot_loss(network, dispatch[i], cfg) for i in range(dispatch.shape[0]))) * hours
	reference_loss = (
		float(sum(_snapshot_loss(reference_net, reference[i], cfg) for i in range(reference.shape[0])))
		* hours
	)
	# Actual load on the reference network: the loss the load causes, measured
	# from the no-load case. This is what makes the parts sum.
	load_only = (
		float(sum(_snapshot_loss(reference_net, dispatch[i], cfg) for i in range(dispatch.shape[0])))
		* hours
	)
	# Actual topology at the reference dispatch.
	topology_only = (
		float(sum(_snapshot_loss(topology_net, reference[i], cfg) for i in range(reference.shape[0])))
		* hours
	)
	return DecompositionInputs(
		actual_losses_mwh=actual,
		reference_losses_mwh=reference_loss,
		losses_with_actual_load_only_mwh=load_only,
		losses_with_actual_topology_only_mwh=topology_only,
	)


def decompose_series(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	config: LossConfig | None = None,
	*,
	reference_dispatch_mw: NDArray[np.float64] | None = None,
	reference_network: Network | None = None,
	topology_network: Network | None = None,
) -> LossComponents:
	"""Measure and decompose in one call, for the common case."""
	inputs = measure(
		network,
		dispatch_mw,
		config,
		reference_dispatch_mw=reference_dispatch_mw,
		reference_network=reference_network,
		topology_network=topology_network,
	)
	return decompose(inputs, config)


def losses_by_component(
	network: Network,
	dispatch_mw: NDArray[np.float64],
	config: LossConfig | None = None,
	**kwargs: object,
) -> dict[str, float]:
	"""The decomposition as a flat mapping, for an artefact payload."""
	components = decompose_series(network, dispatch_mw, config, **kwargs)  # type: ignore[arg-type]
	return {
		"load_driven_mwh": components.load_driven_mwh,
		"generation_driven_mwh": components.generation_driven_mwh,
		"topology_driven_mwh": components.topology_driven_mwh,
		"total_mwh": components.total_mwh,
		**{f"share_{key}": value for key, value in components.shares.items()},
	}


__all__ = [
	"DecompositionInputs",
	"decompose",
	"decompose_series",
	"flat_reference_dispatch",
	"losses_by_component",
	"measure",
	"reference_injection",
]
