# 06 — Layer 3: Market Simulation

**Track A.** Agent-based clearing, capture prices, PPA benchmarks, bankability,
risk. Budget: **seven weeks**, after Layer 2.

Layer 3 answers the questions an optimiser cannot: *what price* results from a
given system, and *what is that price worth* to a specific asset or contract.

---

## 1. What Layer 3 owns

| Concern | Module | Depends on |
|---|---|---|
| Agent-based market clearing | `market.agents` | Layer 1/2 network |
| Strategic bidding | `market.strategy` | — |
| Capture prices | `market.capture` | Network + prices |
| PPA benchmark curves | `market.ppa` | Capture prices |
| Bankability (DSCR, IRR) | `market.bankability` | Prices + costs |
| Portfolio risk (VaR, CVaR) | `market.risk` → `alea_risk` | Monte Carlo |

---

## 2. The specification's example, and what is wrong with it

`spec4-base.md` §10 gives a `mesa`-based market model. Four defects must be
corrected before it is implementable:

### 2.1 The `mesa` API in the example is obsolete

```python
super().__init__(uid, model)          # mesa < 2.0 signature
self.schedule = mesa.time.RandomActivation(self)
```

`mesa` 2.x removed `mesa.time.RandomActivation` and changed `Agent.__init__` to
take no positional uid. The example will not run against any current `mesa`.
**Decision: do not use `mesa`.** See §3.

### 2.2 An RL agent per generator is not a design

```python
def _init_strategy(self):
    return PPO("MlpPolicy", BiddingEnv(self), verbose=0)
```

This constructs a *separate PPO policy per generator agent*. There is no
training loop, no shared learning, no episode structure — and at continental
scale it would mean thousands of independent neural networks. It also makes the
result non-deterministic (AD-8) and unreproducible.

**Decision.** Strategic bidding is a **parametric strategy with an explicit
markup function**, not learned RL. See §4. If learned bidding is added later it
is a single shared policy trained offline, versioned as an artefact, and loaded
deterministically.

### 2.3 `clear_market` does not clear a market

```python
for price, cap, agent in bids:
    cum_capacity += cap
    dispatched.append((price, min(cap, demand)))
    if cum_capacity >= demand:
        break
clearing_price = dispatched[-1][0]
```

Three problems:

1. The marginal unit is dispatched at `min(cap, demand)` — the *last* unit's
   quantity is truncated to total demand, not to its own residual. Demand can
   exceed what is dispatched.
2. `min(cap, demand)` uses total demand, not the residual demand remaining. Every
   dispatched unit is capped at the *same* number.
3. The clearing price is the marginal unit's bid, which is correct for a
   uniform-price auction — but only if the stack is built correctly and
   demand is actually met.

**Decision.** Clearing is a proper merit-order stack with residual demand and an
explicit handling of the case where supply is short (unserved energy priced at
VoLL). See §3.

### 2.4 The reward logic is a placeholder

```python
for price, qty in dispatched:
    # ... reward logic
```

A comment where the payoff function should be. **Decision.** §4 defines the
payoff explicitly.

---

## 3. Market clearing

### 3.1 Model choice: merit order first, agents second

**The clearing engine is a merit-order stack with explicit strategic markups.**
It is deterministic, fast, auditable, and produces the same clearing price as a
uniform-price auction among the same bids. Agents *choose the bids*; the stack
*clears* them. This separates the strategic question (what markup?) from the
mechanical one (what price results?), which is what makes the result
interpretable.

```python
# src/alea/market/clearing.py
from __future__ import annotations
import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass

@dataclass(frozen=True)
class Bid:
	unit_id: str
	quantity_mw: float
	price_usd_per_mwh: float
	available: bool = True

@dataclass(frozen=True)
class ClearingResult:
	clearing_price_usd_per_mwh: float
	dispatched: dict[str, float]         # unit_id -> MW
	unserved_mwh: float
	shortage_price_usd_per_mwh: float

def clear_market(
	bids: list[Bid],
	demand_mw: float,
	*,
	value_of_lost_load_usd_per_mwh: float,
) -> ClearingResult:
	"""Uniform-price auction over a merit-order stack.

	Deterministic: ties in price break on ``unit_id`` lexicographically, never
	on list order (AD-8). A tie broken by list order is a tie broken by dict
	iteration, which is a result that changes between runs.

	If the stack cannot meet demand, the shortfall is priced at VoLL and
	``unserved_mwh`` is non-zero. Reporting a clearing price from a stack that
	did not meet demand, without saying so, is how a market model reports a
	price for a system that was in blackout.
	"""
	stack = sorted(
		(b for b in bids if b.available),
		key=lambda b: (b.price_usd_per_mwh, b.unit_id),
	)
	remaining = demand_mw
	dispatched: dict[str, float] = {}
	clearing_price = value_of_lost_load_usd_per_mwh

	for bid in stack:
		if remaining <= 0:
			break
		taken = min(bid.quantity_mw, remaining)
		dispatched[bid.unit_id] = taken
		remaining -= taken
		clearing_price = bid.price_usd_per_mwh

	unserved = max(remaining, 0.0)
	return ClearingResult(
		clearing_price_usd_per_mwh=clearing_price,
		dispatched=dispatched,
		unserved_mwh=unserved,
		shortage_price_usd_per_mwh=(
			value_of_lost_load_usd_per_mwh if unserved > 0 else 0.0
		),
	)
```

**The tie-break rule is not decoration.** `sorted` on price alone leaves equal
prices in input order, and input order comes from a dict or a dataframe index —
both of which are non-deterministic across runs in the ways AD-8 forbids.

### 3.2 Multi-zone clearing

A single national market clears once; a power-pool market clears with
transmission constraints between zones. The zonal case reuses
`alea_losses::dc_power_flow` (Layer 4's crate, built earlier in the schedule) to
compute flows, then iterates: clear, check flows against limits, split the market
at the congested interface, repeat until no interface is violated.

**Congestion is the interesting output.** A single-price national model cannot
produce it, and congestion is what makes a zonal price forecast useful.

---

## 4. Strategic bidding

### 4.1 The markup function

```python
# src/alea/market/strategy.py
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class StrategyKind(StrEnum):
	COMPETITIVE = "competitive"      # bid at marginal cost
	MARKUP = "markup"                # cost × (1 + m)
	SUPPLY_FUNCTION = "supply_function"   # SFE: bid above cost, slope from residual demand
	HEDGE = "hedge"                  # bid to protect a contracted position

@dataclass(frozen=True)
class Strategy:
	kind: StrategyKind
	markup: float = 0.0
	"""Fractional markup over marginal cost. Only for MARKUP."""
	supply_function_alpha: float = 0.0
	"""Conduct parameter. 0 = competitive, 1 = monopoly. Only for SUPPLY_FUNCTION."""
	contract_cover_fraction: float = 0.0
	"""Fraction of capacity sold forward. Only for HEDGE."""

	def bid_price(self, marginal_cost_usd_per_mwh: float) -> float:
		"""Bid price for a unit with this marginal cost.

		The competitive benchmark is the marginal cost, and every result is
		reported *against* it. A market result without a competitive benchmark
		beside it cannot be read: nobody knows whether the markup is the
		modelling or the finding.
		"""
		match self.kind:
			case StrategyKind.COMPETITIVE:
				return marginal_cost_usd_per_mwh
			case StrategyKind.MARKUP:
				return marginal_cost_usd_per_mwh * (1.0 + self.markup)
			case StrategyKind.SUPPLY_FUNCTION:
				# The supply-function-equilibrium conduct parameter: a fraction
				# alpha of the way from competitive to the monopoly price.
				# The monopoly price is not known analytically here, so alpha is
				# applied as a markup on cost and calibrated against a
				# Cournot benchmark in a test.
				return marginal_cost_usd_per_mwh * (1.0 + self.supply_function_alpha)
			case StrategyKind.HEDGE:
				# A hedged unit bids low on its contracted volume: the contract
				# fixes its revenue, so it wants to be dispatched.
				cover = self.contract_cover_fraction
				return marginal_cost_usd_per_mwh * (1.0 - cover)
		raise ValueError(f"unhandled strategy kind: {self.kind}")
```

**`supply_function` needs a calibration test.** The conduct parameter α is only
meaningful if α=1 reproduces a known monopoly price on a synthetic network and
α=0 reproduces the competitive price. That test is required, because otherwise
α is a knob with units of nothing.

### 4.2 Where the marginal cost comes from

```
marginal_cost = fuel_cost + carbon_price × co2_intensity + vom
```

Carbon price and fuel prices are scenario parameters (Layer 5). VOM comes from
the cost dataset (`02-data-pipeline.md`). **Every component is recorded in the
bid artefact**, so a clearing price can be decomposed into what produced it.

### 4.3 Rejected: reinforcement learning

The specification's `PPO` per agent is rejected (§2.2). If learned bidding is
wanted, the honest version is: one shared policy, trained offline against a
fixed network, versioned, loaded with fixed weights, and evaluated against the
supply-function benchmark. It is a Layer 3 *extension*, not the default path.

---

## 5. Capture prices

### 5.1 The specification's example, corrected

```python
capture = revenue / generation if generation > 0 else 0
capture_rate = capture / price.mean() if price.mean() > 0 else 0
```

Two issues. First, `capture = 0` when generation is zero is **wrong** — the
correct value is undefined (NaN), and setting it to zero drags a portfolio
average down and makes a technology with no generation look like a technology
with a terrible capture rate. Second, a negative price is possible (curtailment
pricing) and `price.mean() > 0` silently zeroes the capture rate there.

```python
# src/alea/market/capture.py
def capture_price(
	generation_mw: NDArray[np.float64],
	price_usd_per_mwh: NDArray[np.float64],
) -> float:
	"""Revenue-weighted capture price. NaN when there is no generation.

	NaN, not zero. A technology that generated nothing has an undefined capture
	price; reporting zero is a specific claim (it sold its output at zero) that
	is not true and that propagates into every portfolio average.
	"""
	assert generation_mw.shape == price_usd_per_mwh.shape
	assert np.all(generation_mw >= 0.0)
	total = generation_mw.sum()
	if total <= 0.0:
		return float("nan")
	return float((generation_mw * price_usd_per_mwh).sum() / total)
```

**Capture rate** is `capture_price / time_weighted_price`, computed only where
the time-weighted price is non-zero, and NaN otherwise. The `[UNVERIFIED]`
benchmark here is COMPASS's South African capture curves; M8 compares ALEA's
South African output against them.

### 5.2 Cannibalisation

The reason capture prices matter: as VRE share rises, a technology's own output
depresses the price it receives. The Layer 3 deliverable is the **capture-rate
curve** — capture rate against VRE penetration — which is what a developer needs
to size a project and what a lender needs to stress a PPA.

---

## 6. PPA benchmarks

A PPA curve gives a price for a given tenor, technology, and country. Three
adjustments, each recorded:

| Adjustment | Basis | Recorded as |
|---|---|---|
| Tenor | Capture price over the contract term, not year one | `tenor_years` |
| Currency risk | Local-currency vs. USD spread | `fx_basis_pct`, `fx_source` |
| Counterparty risk | Sovereign/utility credit spread | `credit_spread_pct`, `credit_source` |

**Currency is the trap** (`02-data-pipeline.md` §2.3). Every PPA price in local
currency records the FX rate and its date. The project's own history includes a
document that stated a target in KES at one implied rate and converted USD at
another, producing a 10% self-contradiction no lint could see.

---

## 7. Bankability and risk

### 7.1 Bankability

DSCR, project IRR, equity IRR per scenario. The **inputs** are Layer 3's price
forecast and Layer 1's cost data; the calculation is arithmetic and must be
checked against a hand-computed fixture.

### 7.2 Portfolio risk — `alea_risk`

VaR and CVaR over revenue distributions from `alea_risk::var_cvar`
(`03-rust-core.md` §7). Correlated inputs (fuel price, demand, carbon price)
enter through a Cholesky factor that is **checked for positive-definiteness** —
a correlation matrix from expert elicitation frequently is not, and an
unchecked Cholesky produces NaNs that propagate silently into a VaR.

**Sign convention:** VaR and CVaR are reported as **positive loss magnitudes**.
A test asserts `CVaR >= VaR >= 0`.

### 7.3 Efficient frontiers

The Layer 5 engine produces cost–risk frontiers by sweeping scenario parameters
and calling Layer 3. Layer 3 provides the per-scenario risk metrics; it does not
own the sweep.

---

## 8. Module layout

```
src/alea/market/
├── __init__.py
├── clearing.py       # merit-order stack, zonal clearing
├── strategy.py       # markup functions, conduct parameter
├── agents.py         # the agent wrapper over Strategy + Bid
├── capture.py        # capture prices, cannibalisation curves
├── ppa.py            # benchmark curves, FX and credit adjustments
├── bankability.py    # DSCR, IRR
├── risk.py           # VaR/CVaR via alea_risk
└── service.py
```

---

## 9. Gates

| Gate | Assertion | Canary |
|---|---|---|
| `test_clearing_deterministic` | Ties break on unit_id, not list order | Shuffle input; same output |
| `test_clearing_meets_demand` | Dispatched + unserved == demand | Inject a short stack; must report unserved |
| `test_shortage_priced_at_voll` | Unserved energy priced at VoLL | Remove capacity; price must rise to VoLL |
| `test_competitive_matches_merit_order` | Competitive strategy == pure merit order | Inject markup; must differ |
| `test_alpha_calibration` | α=0 competitive, α=1 monopoly on synthetic network | Perturb; must fail |
| `test_capture_nan_on_no_generation` | Zero generation → NaN, not 0 | Change to 0; must fail |
| `test_var_sign_convention` | `CVaR >= VaR >= 0` | Flip sign; must fail |
| `test_cholesky_checked` | Non-PSD correlation raises | Inject non-PSD; must fail |
| `test_fx_rate_recorded` | Every PPA price records rate and date | Remove rate; must fail |

---

## 10. Exit criteria for Layer 3

| # | Criterion | Gate |
|---|---|---|
| 1 | Kenya merit-order clearing matches a hand-computed stack | Fixture test |
| 2 | Zonal clearing produces congestion on a congested fixture | Integration test |
| 3 | Competitive strategy reproduces Layer 1 marginal prices | Cross-check |
| 4 | Capture prices for Kenya solar/wind computed | Integration test |
| 5 | Capture-rate curve rises monotonically with VRE share | Property test |
| 6 | South Africa capture curves compared to COMPASS | M8 |
| 7 | VaR/CVaR on a normal sample matches 1.645σ at 95% | Analytic test |
| 8 | Bankability matches a hand-computed fixture | Fixture test |
| 9 | Two identical runs byte-identical | Determinism job |
| 10 | Every gate canaried | `tests/ci/canaries` |

**Criterion 3 is the integration gate.** A competitive market model must
reproduce Layer 1's marginal prices at the same snapshots. If it does not, the
market layer and the planning layer disagree about the same system, and any
price forecast built on it is measuring the discrepancy rather than the market.
