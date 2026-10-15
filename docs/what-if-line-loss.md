# Alea What-If Analysis: Modelling Transmission Line Loss

## Yes — and It Goes Far Beyond Simply Removing a Line

The Alea What-If engine can model the loss of any transmission line — single or multiple, planned or unplanned, permanent or temporary — and trace the full cascade of consequences through the network, generation fleet, market prices, and system reliability. This is not a simple "remove the line and re-solve" feature. It is a **contingency-aware, cascading, probabilistic resilience analysis** integrated with every other layer of the platform.

---

## 1. How the User Triggers a Line Loss

### 1.1 Direct Parameter Override

The user can modify any transmission line's parameters through the What-If API or dashboard:

| Parameter | Description | Unit | Example |
|---|---|---|---|
| `line_active` | Line in service or out | Boolean | `False` |
| `line_capacity_override` | Override nominal capacity | MVA | `0` |
| `line_capacity_factor` | Reduce capacity to % of nominal | % | `50` |
| `line_impedance_multiplier` | Change impedance (e.g., degraded conductor) | Multiplier | `2.0` |
| `line_loss_factor_override` | Override loss factor | % | `15` |
| `line_outage_start` | When the outage begins | Timestamp | `2030-06-01T00:00:00Z` |
| `line_outage_end` | When the outage ends | Timestamp | `2030-06-15T00:00:00Z` |
| `line_outage_probability` | Probability of outage | Ratio | `0.3` |
| `line_outage_duration` | Expected duration | Hours | `168` |

### 1.2 Named Contingency Scenarios

The user can select from pre-built contingency scenarios:

| Scenario | Description | Lines Affected |
|---|---|---|
| `n_1_single_line` | Loss of any single line | 1 (user-selected or all) |
| `n_2_double_line` | Loss of any two lines | 2 |
| `n_1_1_generator` | Loss of line + generator | 1 line + 1 generator |
| `common_mode_tower` | Loss of all lines on a shared tower | Multiple |
| `corridor_outage` | Loss of an entire transmission corridor | Multiple |
| `cascading_failure` | Sequential loss of lines | Simulated cascade |
| `extreme_weather` | Loss of lines due to weather | Weather-dependent |
| `cyber_physical` | Coordinated loss of lines | Multiple |

### 1.3 Interactive Dashboard Interaction

In the dashboard, the user can:

1. Navigate to the continental or country map
2. Click on any transmission line
3. Select "Simulate Outage" from the context menu
4. Choose the type of outage (permanent, temporary, partial)
5. See the results update in real-time

---

## 2. What the System Models When a Line Is Lost

### 2.1 Immediate Power Flow Redistribution

When a line is lost, the power that was flowing through it must find alternative paths. Alea solves the **linear power flow (LPF)** with the line removed and computes:

- **New flows on all remaining lines**: Using the network's impedance matrix and Kirchhoff's laws.
- **Overload detection**: Any line whose flow exceeds its rating is flagged.
- **Congestion pricing**: Lines that become congested receive congestion rents.
- **Loop flows**: Power may flow through parallel paths, including through neighbouring countries.

**Mathematical formulation**: The power flow equations are re-solved with the line's susceptance set to zero:

$$P_{ij} = \frac{\theta_i - \theta_j}{x_{ij}} \quad \text{for all lines } (i,j) \neq \text{outaged line}$$

Where $\theta_i$ is the voltage angle at bus $i$ and $x_{ij}$ is the line reactance. The outaged line is excluded from the sum.

### 2.2 Generation Re-Dispatch

The loss of a line changes the optimal dispatch of the entire generation fleet. Alea re-solves the **economic dispatch** (or unit commitment, if enabled) with the new network topology:

- **Cheaper generation may be curtailed** if it can no longer reach load centres.
- **More expensive generation may be dispatched** to serve load that was previously served by cheaper, remote generation.
- **Reserve requirements may increase** to cover the additional uncertainty.

The change in dispatch is computed as:

$$\Delta G_{n,s,t} = G_{n,s,t}^{\text{post-outage}} - G_{n,s,t}^{\text{pre-outage}}$$

### 2.3 Load Shedding / Energy Not Served (ENS)

If the network cannot serve all load after the line loss, Alea computes **Energy Not Served (ENS)** as:

$$\text{ENS} = \sum_{t} \sum_{n} \left( d_{n,t} - \sum_{s} G_{n,s,t}^{\text{served}} \right)$$

Where $d_{n,t}$ is demand and $G_{n,s,t}^{\text{served}}$ is the generation actually dispatched to serve load at node $n$.

**Load shedding is modelled as a generator** with a very high marginal cost (the Value of Lost Load, VoLL), so the optimisation naturally minimises unserved energy.

### 2.4 Price Impacts (LMP Changes)

The **Locational Marginal Prices (LMPs)** change dramatically after a line loss:

- **Upstream of the outage**: If generation is trapped, prices may **drop** (or even go negative).
- **Downstream of the outage**: If load is stranded, prices may **spike** to the cost of the most expensive generation or to VoLL.
- **Congestion rents**: The price difference between nodes reflects the cost of the constraint.

Alea computes the **price change** for every node and time step:

$$\Delta \pi_{n,t} = \pi_{n,t}^{\text{post-outage}} - \pi_{n,t}^{\text{pre-outage}}$$

### 2.5 Loss Changes

The loss of a line changes total system losses:

- **If the lost line was heavily loaded**: Losses may decrease (less power flowing).
- **If the lost line forces power through longer paths**: Losses may increase.
- **The TLENS metric** (Transmission Lines' Contribution to Energy Not Supplied) is computed for the lost line, quantifying its contribution to system resilience.

### 2.6 Cascading Failures

Alea can simulate **cascading failures** through an iterative process:

1. Solve the base case with all lines active.
2. Remove the initial line(s) and re-solve.
3. Check for overloaded lines.
4. If any line exceeds its rating, remove the most overloaded line and re-solve.
5. Repeat until no lines are overloaded or the system collapses.

This produces a **cascade sequence**: a list of lines that fail in order, with the time step at which each failure occurs.

**Cascade metrics**:

| Metric | Description |
|---|---|
| `cascade_depth` | Number of lines lost in the cascade |
| `cascade_duration` | Time from initial outage to stabilisation |
| `total_ens` | Total energy not served during the cascade |
| `critical_lines` | Lines whose loss triggers the largest cascades |
| `cascade_probability` | Probability of cascade given initial outage |

### 2.7 Probabilistic Outage Modelling

When the line loss is uncertain (e.g., weather-dependent), Alea runs a **Monte Carlo simulation** with multiple outage scenarios:

- Each line has a **probability of outage** based on weather, age, and loading.
- The model samples outage scenarios from this probability distribution.
- For each scenario, it solves the power flow and computes ENS, price changes, and losses.
- The results are aggregated into **expected values** and **confidence intervals**.

---

## 3. What the User Sees

### 3.1 Dashboard Visualisation

| Visualisation | Description |
|---|---|
| **Network map** | The outaged line is shown in red with a "X" marker |
| **Flow arrows** | Arrows on remaining lines show the new flow direction and magnitude; overloaded lines are highlighted |
| **Price heatmap** | Nodes are coloured by LMP change (blue = price drop, red = price spike) |
| **ENS map** | Affected areas are shaded by unserved energy |
| **Cascade animation** | Sequential line failures are animated over time |
| **Comparison table** | Side-by-side comparison of pre- and post-outage metrics |

### 3.2 Metrics Panel

| Metric | Pre-Outage | Post-Outage | Change |
|---|---|---|---|
| **Total system cost** | $12.3B | $12.8B | +$0.5B |
| **Energy not served** | 0 MWh | 45,000 MWh | +45,000 MWh |
| **Average price** | $65/MWh | $78/MWh | +$13/MWh |
| **Max price** | $120/MWh | $450/MWh | +$330/MWh |
| **Total losses** | 2,100 MW | 2,450 MW | +350 MW |
| **Overloaded lines** | 0 | 3 | +3 |
| **Cascade depth** | 0 | 4 | +4 |

### 3.3 Query Results

The user can query specific results:

```json
GET /v1/whatif/result?scenario_id=line_outage_abc123&metric=price_change&country=NG

{
  "scenario_id": "line_outage_abc123",
  "line": "Lagos-Ibadan 330kV",
  "outage_start": "2030-06-01T00:00:00Z",
  "outage_end": "2030-06-15T00:00:00Z",
  "price_changes": [
    {"node": "Lagos", "pre_price": 65, "post_price": 450, "change": 385},
    {"node": "Ibadan", "pre_price": 62, "post_price": 380, "change": 318},
    {"node": "Abuja", "pre_price": 58, "post_price": 72, "change": 14}
  ],
  "ens_mwh": 45000,
  "overloaded_lines": ["Ibadan-Oshogbo 330kV", "Oshogbo-Abuja 330kV"],
  "cascade_depth": 4
}
```

---

## 4. Parameters the User Can Modify

### 4.1 Line-Specific Parameters

| Parameter | Description | Unit | Range |
|---|---|---|---|
| `line_id` | Line identifier | String | — |
| `outage_type` | Type of outage | Categorical | Permanent, Temporary, Partial |
| `outage_start` | Start time | Timestamp | Any |
| `outage_duration` | Duration | Hours | 1–8760 |
| `outage_probability` | Probability of outage | Ratio | 0–1 |
| `repair_time` | Expected repair time | Hours | 1–720 |
| `repair_crew_availability` | Crew availability | % | 0–100 |
| `spare_equipment_availability` | Spare equipment availability | % | 0–100 |
| `restoration_priority` | Restoration priority | Categorical | High, Medium, Low |

### 4.2 Network-Level Parameters

| Parameter | Description | Unit | Range |
|---|---|---|---|
| `n_1_criterion` | Enforce N-1 security | Boolean | True/False |
| `n_2_criterion` | Enforce N-2 security | Boolean | True/False |
| `cascade_simulation` | Enable cascade simulation | Boolean | True/False |
| `max_cascade_depth` | Maximum cascade depth | Lines | 1–20 |
| `overload_threshold` | Overload threshold | % | 80–150 |
| `load_shedding_allowed` | Allow load shedding | Boolean | True/False |
| `voll` | Value of lost load | $/MWh | 1000–50000 |

### 4.3 Response Parameters

| Parameter | Description | Unit | Range |
|---|---|---|---|
| `demand_response_available` | Demand response available | MW | 0–10000 |
| `storage_discharge_available` | Storage discharge available | MW | 0–5000 |
| `generator_ramp_available` | Generator ramp available | MW/min | 0–1000 |
| `black_start_available` | Black start available | Boolean | True/False |
| `islanding_allowed` | Islanding allowed | Boolean | True/False |
| `microgrid_support` | Microgrid support | Boolean | True/False |

---

## 5. Pre-Built Line Outage Scenarios

| Scenario | Description | Lines Affected |
|---|---|---|
| **Single Line N-1** | Loss of the most critical line | 1 |
| **Double Line N-2** | Loss of two most critical lines | 2 |
| **Corridor Loss** | Loss of an entire transmission corridor | 3–10 |
| **Tower Failure** | Loss of all lines on a shared tower | 2–6 |
| **Substation Failure** | Loss of all lines into a substation | 3–8 |
| **Weather Event** | Loss of lines due to storm/flood | 5–20 |
| **Cascading Failure** | Sequential loss of lines | Dynamic |
| **Blackout** | Total system collapse | All |
| **Restoration** | Sequential restoration of lines | Dynamic |

---

## 6. Integration with Other Alea Layers

### 6.1 Integration with Outage Prediction

The line outage What-If is **informed by** the Outage Prediction module:

- **VIIRS-detected outages** provide historical line outage patterns.
- **Weather forecasts** provide probabilistic outage risk by line.
- **Predictive maintenance** provides failure probability by line.
- **The What-If engine** uses these probabilities to weight scenarios.

### 6.2 Integration with Market Simulation

The line outage What-If is **integrated with** the Market Simulation layer:

- **Agent-based bidding** responds to the new network topology.
- **Prices** reflect the new supply-demand balance.
- **Capture prices** change for affected generators.
- **PPA benchmarks** shift for affected countries.

### 6.3 Integration with Loss Mitigation

The line outage What-If is **connected to** the Loss Mitigation module:

- **TLENS** is computed for the outaged line.
- **Loss decomposition** shows how losses change.
- **Mitigation options** are ranked for the post-outage state.
- **Resilience metrics** (ENS, EENS, SAIDI, SAIFI) are updated.

### 6.4 Integration with Periodic Reporting

Line outage scenarios feed into **periodic reports**:

- **Daily reports** include outage forecasts and alerts.
- **Weekly reports** include resilience updates.
- **Monthly reports** include outage statistics.
- **Quarterly reports** include resilience scorecards.

---

## 7. Advanced Capabilities

### 7.1 Probabilistic Contingency Analysis

For each line, Alea computes the **probability-weighted impact** of its loss:

$$\text{Expected Impact}_l = \sum_{s \in S} p_s \cdot \text{Impact}(l, s)$$

Where $p_s$ is the probability of scenario $s$ (weather, loading, etc.) and $\text{Impact}(l, s)$ is the impact of line $l$'s loss in scenario $s$.

### 7.2 Critical Line Ranking

Lines are ranked by **criticality** using multiple metrics:

| Metric | Description |
|---|---|
| **TLENS** | Contribution to energy not served |
| **ENS increase** | Absolute increase in ENS |
| **Price impact** | Maximum price change |
| **Cascade potential** | Likelihood of triggering a cascade |
| **Load affected** | Number of customers affected |
| **Economic cost** | Total economic impact |

### 7.3 Restoration Optimisation

Alea can optimise the **restoration sequence** after a line outage:

1. Identify the optimal order to restore lines.
2. Minimise total ENS during restoration.
3. Prioritise critical loads (hospitals, water treatment, etc.).
4. Coordinate with generation restart.
5. Account for crew and equipment availability.

### 7.4 Preventive vs. Corrective Actions

The What-If engine can compare:

| Action Type | Description | Example |
|---|---|---|
| **Preventive** | Actions taken before outage | Line upgrade, vegetation management, spare equipment |
| **Corrective** | Actions taken after outage | Re-dispatch, demand response, load shedding |
| **Adaptive** | Actions that change with conditions | Dynamic line rating, topology switching |

### 7.5 Multi-Line Simultaneous Outages

For **N-k contingencies** (loss of k lines simultaneously), Alea can:

- Enumerate all combinations of k lines.
- Compute the impact of each combination.
- Identify the **worst-case combination**.
- Rank combinations by probability-weighted impact.
- Compute the **N-k security margin**.

### 7.6 Spatial and Temporal Correlation

Alea models **spatial correlation** (e.g., lines in the same corridor fail together) and **temporal correlation** (e.g., outages cluster during storms) using:

- **Copula models** for spatial dependence.
- **Markov chains** for temporal dependence.
- **Weather-driven** outage models.

---

## 8. Example Workflow

**User question**: "What happens if the Inga–Kolwezi 220 kV line in DRC fails for 2 weeks during the dry season?"

**Alea workflow**:

1. **Load base network**: DRC + SAPP network with 2030 demand and generation.
2. **Apply outage**: Set `line_active = False` for Inga–Kolwezi, `outage_start = 2030-06-01`, `outage_end = 2030-06-15`.
3. **Re-solve power flow**: Compute new flows on all remaining lines.
4. **Detect overloads**: Identify lines exceeding rating.
5. **Re-dispatch generation**: Solve economic dispatch with new topology.
6. **Compute ENS**: Calculate unserved energy in affected areas.
7. **Compute price changes**: Calculate new LMPs.
8. **Simulate cascade**: Check if overloaded lines fail sequentially.
9. **Compute TLENS**: Rank the line's criticality.
10. **Generate report**: Produce a summary with visualisations and metrics.
11. **Compare scenarios**: Compare to base case and alternative outage scenarios.

**Output**:

```json
{
  "scenario": "Inga-Kolwezi outage 2030-06-01 to 2030-06-15",
  "total_ens_mwh": 125000,
  "max_price_usd_mwh": 620,
  "avg_price_increase": 45,
  "overloaded_lines": ["Kolwezi-Lubumbashi", "Lubumbashi-Kasumbalesa"],
  "cascade_depth": 3,
  "cascade_lines": ["Kolwezi-Lubumbashi", "Lubumbashi-Kasumbalesa", "Kasumbalesa-Solwezi"],
  "total_cost_increase_usd": 85000000,
  "affected_population": 2500000,
  "critical_loads_affected": ["Kolwezi Hospital", "Lubumbashi Water Treatment"],
  "restoration_time_hours": 336,
  "tlens_rank": 3,
  "recommendations": [
    "Upgrade Kolwezi-Lubumbashi line to 400 kV",
    "Install 200 MW battery storage at Kolwezi",
    "Add N-1 redundancy on Inga-Kolwezi corridor"
  ]
}
```

---

## 9. Summary

| Capability | Description |
|---|---|
| **Single line outage** | Model loss of any single line |
| **Multi-line outage** | Model loss of k lines simultaneously |
| **Cascading failure** | Simulate sequential line failures |
| **Probabilistic outage** | Model weather-dependent outage probability |
| **Price impact** | Compute LMP changes at every node |
| **ENS computation** | Calculate energy not served |
| **Cascade metrics** | Depth, duration, probability |
| **Critical line ranking** | TLENS and multi-metric ranking |
| **Restoration optimisation** | Optimise restoration sequence |
| **Preventive vs. corrective** | Compare intervention strategies |
| **Spatial correlation** | Model correlated outages |
| **Temporal correlation** | Model clustered outages |
| **Integration** | With outage prediction, market simulation, loss mitigation, reporting |
| **Visualisation** | Maps, flows, heatmaps, cascade animations |
| **API access** | Query results programmatically |
| **Pre-built scenarios** | N-1, N-2, corridor, tower, substation, weather, cascade, blackout, restoration |

Alea's What-If engine does not merely answer "what happens if a line is lost?" It answers:

- **Which lines are most critical?**
- **What is the cascade risk?**
- **How much energy will be unserved?**
- **How do prices change?**
- **Who is affected?**
- **What is the economic cost?**
- **How long will restoration take?**
- **What preventive actions should be taken?**
- **What is the probability-weighted impact?**
- **How does this compare to alternative scenarios?**

This makes Alea the most comprehensive transmission resilience analysis platform for African power systems.