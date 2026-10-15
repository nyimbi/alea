## 🏆 ALEA vs. The World: A Comparative Analysis

When fully implemented, ALEA will not just be "better than COMPASS"; it is designed to be the most comprehensive and integrated energy intelligence platform for Africa, surpassing even the world's leading academic and commercial tools in several key dimensions.

Here is a comparison of ALEA against the best-in-class tools.

| Capability / Dimension | ALEA (Proposed) | PyPSA-Earth / PyPSA Meets Africa | OSeMOSYS / TEMBA | Calliope Africa | PLEXOS |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Geographic Scope** | **All 55 AU member states**, 5 power pools, AfSEM alignment. | Global/Continental Africa. Validated for the entire continent. | All African countries, but with simplified time slices. | Country-resolution for Africa. | Global. |
| **Spatial Resolution** | Flexible: Continental, power-pool, national, and sub-national (down to settlement). | High, adaptable spatial resolution (e.g., 80 clusters for Africa). | Nation as a node. | Country-resolution. | Zonal or nodal. |
| **Temporal Resolution** | **Full hourly chronology (8,760 hours)** with optional sub-hourly (15-min) for operations. | **Hourly**. | Simplified time slices (e.g., seasonal, day/night). This can mask short-term fluctuations crucial for storage and intermittent renewables. | Hourly. | Sub-hourly (1-second) to decades. |
| **Sector Coupling** | **Full**: Electricity, hydrogen, heat, transport, industry, water. | Sector-coupled variant exists (PyPSA-Earth-Sec). | Limited. | Power sector only. | Electricity, gas, hydrogen, water markets. |
| **Market Simulation** | **Yes**: Agent-based market clearing (AMIRIS/ASSUME) for price formation. | No. Focus is on least-cost optimisation. | No. | No. | Yes. Advanced market simulation is a core feature. |
| **Outage Prediction** | **Yes**: VIIRS/Black Marble, ML forecasting, predictive maintenance. | No. | No. | No. | No. |
| **What-If Engine** | **Yes**: Interactive, parameter-driven, with a PRG for consistency. | No. Requires re-running the model. | No. Requires re-running the model. | No. Requires re-running the model. | Yes. Scenario management is a key feature. |
| **Parameter Consistency** | **Yes**: The PRG enforces physical, economic, and policy consistency across 784 parameters. | No. | No. | No. | No. |
| **Delivery & Accessibility** | **Open-source, with REST API, interactive dashboard, SDKs, and multi-channel delivery (WhatsApp, USSD).** | Open-source, but requires significant technical expertise to run. | Open-source. | Open-source, but limited to Python API. | **Proprietary, expensive, and closed-source.** |
| **Cost** | **Free / Freemium.** | Free. | Free. | Free. | **Very High (Commercial Licence).** |
| **Key Weakness** | Data scarcity in some regions. Complexity of integrating so many modules. | Limited market simulation; no predictive analytics. | Simplified temporal resolution; no network constraints (in the base version). | Power sector only; no market simulation or predictive analytics. | **Proprietary, expensive, and inaccessible to most African stakeholders.** |

### The Decisive Advantages of ALEA

1.  **Unmatched Integration**: No other platform integrates long-term planning, market simulation, outage prediction, and a what-if engine into a single, coherent system. A user can ask "What is the least-cost generation mix for 2050?" and then immediately ask "What happens to prices if a key transmission line fails next week?" in the same interface.
2.  **The Parameter Relationship Graph (PRG)**: This is ALEA's "secret sauce." It is the only platform that ensures every scenario is physically and economically consistent. This prevents the "garbage in, garbage out" problem that plagues other models when users input contradictory parameters.
3.  **True Accessibility**: While other tools are designed for a small group of expert modellers, ALEA is designed for **everyone**. A journalist can use the dashboard, a developer can use the API, and a citizen can use USSD. This democratises energy intelligence in a way no other tool does.
4.  **Predictive Capability**: By integrating satellite-based outage detection, weather-driven forecasting, and predictive maintenance, ALEA moves beyond planning into **operational intelligence**. No other open-source model does this.
5.  **Comprehensive Data Handling**: The multi-store persistence architecture, combined with the automated data collection and intelligence scanning module, makes ALEA a **living system** that continuously updates its knowledge base.

In essence, **PyPSA-Earth is the engine, but ALEA is the entire vehicle** — a complete, road-ready, and accessible platform for Africa's energy transition, while other tools are powerful but require a team of mechanics to operate.
