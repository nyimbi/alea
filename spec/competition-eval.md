To assess how our proposed Alea capabilities compare to the global best, we can benchmark against established models and frameworks across key dimensions.

Here is how the capabilities stack up against the world's leading energy system models.

### 🎯 Benchmarking Criteria

We compare Alea against the best-in-class models on six core capabilities: **Geographic Scope**, **Data Granularity**, **Sector Coupling**, **Market Simulation**, **Stochastic Optimisation**, and **Delivery & Accessibility**.

---

### 🌍 Geographic Scope & Continental Ambition

**Our Capability:** 55 AU member states, five power pools, AfSEM alignment.

**Global Best:** The **AETOS** model (Africa–Europe Transcontinental OSeMOSYS) is a direct competitor, covering 48 African and 30 European countries. The **Calliope Africa** model is also country-resolution and pan-African. The **Continental Power System Master Plan (CMP)** for Africa represents the official planning framework. Crucially, **PyPSA-Earth** is already the data backbone for the OASES continental case study, and its data pipeline has been validated for the entire African continent.

**Assessment:** **Strong**. Our scope is highly competitive. The key advantage is our deep integration with PyPSA-Earth, which is already the de facto standard for open-source African data. The challenge is not ambition but execution against the data realities discussed later.

---

### 📊 Data Granularity: Spatial & Temporal Resolution

**Our Capability:** Flexible spatial resolution (continental to provincial) and full hourly temporal resolution (8,760 hours/year).

**Global Best:** **PyPSA-Earth** itself sets the standard for open models, offering a spatial resolution of **30 km × 30 km** and hourly time resolution. In contrast, many established models like **OSeMOSYS** and **TIMES** typically use a lower temporal resolution (e.g., 288 representative timeslices) to manage computational complexity. **PLEXOS** is capable of very high-resolution simulations but is a commercial, closed-source tool.

**Assessment:** **World-Class (for an open model)**. By leveraging PyPSA-Earth, we inherit best-in-class open-source data resolution. This is a significant advantage over OSeMOSYS/TIMES for capturing renewable variability, but it also means we inherit the computational challenges that come with it.

---

### 🔗 Sector Coupling: Beyond Electricity

**Our Capability:** Full integration of electricity, heat, hydrogen, transport, industry, and water.

**Global Best:** **TIMES** is a benchmark for comprehensive sector coupling, endogenizing buildings, industry, and transport with explicit balances for electricity, heat, H₂, and CH₄. **PyPSA-Eur-Sec** is the leading open-source sector-coupled model for Europe. The **PyPSA-Earth sector-coupled** extension has already demonstrated hydrogen applications in Africa, specifically for Egypt and Brazil, validating the technical approach.

**Assessment:** **Strong**. Our capability is aligned with the global frontier. The PyPSA ecosystem is explicitly designed for this kind of integration, and its application to African hydrogen scenarios de-risks the technical implementation.

---

### ⚡ Market Simulation: From Optimisation to Agent-Based Modelling

**Our Capability:** Agent-based bidding, multi-market clearing, and regulatory simulation.

**Global Best:** This is where we move **beyond** the capabilities of most traditional optimisation models. The leading open-source frameworks for this are **AMIRIS** and **ASSUME**. ASSUME is particularly advanced, incorporating **multi-agent deep reinforcement learning** for adaptive market participants. A direct comparison of AMIRIS and ASSUME showed both achieve a Mean Absolute Error (MAE) of **5.6–6.4 €/MWh** against a benchmark dataset, demonstrating their practical accuracy.

**Assessment:** **Cutting-Edge**. By integrating these frameworks (or similar approaches), Alea would be at the global forefront of open-source market simulation. This is a key differentiator from purely optimisation-based tools like OSeMOSYS or TIMES.

---

### 🎲 Stochastic Optimisation & Risk Management

**Our Capability:** Multi-stage stochastic programming with CVaR.

**Global Best:** This is a recent but crucial advancement. **PyPSA v1.0** now natively supports **two-stage stochastic programming** with scenario trees and **CVaR-based risk-averse optimisation** via a simple API (`n.set_risk_preference(alpha=..., omega=...)`). **PLEXOS** has long offered stochastic optimisation, allowing users to generate an "efficient frontier" of solutions ranging from low-risk/high-cost to high-risk/low-cost.

**Assessment:** **State-of-the-Art**. Because we are building on PyPSA v1.0+, we inherit these powerful, newly available capabilities directly. This puts us on par with commercial tools like PLEXOS for risk-aware planning, but within an open-source framework.

---

### 📦 Delivery & Accessibility: Beyond a Black Box

**Our Capability:** REST API, interactive dashboards, automated reporting, and an open-source scenario database.

**Global Best:** Most leading models, particularly commercial ones like **PLEXOS**, are black boxes. Open models like **OSeMOSYS** and **PyPSA-Earth** are highly capable but require significant technical expertise to run, and their outputs are not typically delivered via polished, user-friendly interfaces. The open-source community has recognized this gap, leading to initiatives like the **Open Energy Modelling Tool Tracker** to help navigate the landscape.

**Assessment:** **Pioneering**. A modern, accessible delivery layer is a **major competitive advantage**. It directly addresses the "steep learning curve" and "lack of polished GUIs" that are common criticisms of open-source modelling tools. This capability is essential for the stated goal of empowering a wide range of African stakeholders.

---

### 💎 Overall Assessment: How We Compare

| Capability | Status vs. Global Best | Key Benchmark |
| :--- | :--- | :--- |
| **Geographic Scope** | **Strong** | AETOS, Calliope Africa, PyPSA-Earth (OASES) |
| **Data Granularity** | **World-Class (Open)** | PyPSA-Earth (30 km, hourly), PLEXOS (commercial) |
| **Sector Coupling** | **Strong** | TIMES, PyPSA-Eur-Sec, PyPSA-Earth-Sec |
| **Market Simulation** | **Cutting-Edge** | AMIRIS, ASSUME (reinforcement learning) |
| **Stochastic Optimisation** | **State-of-the-Art** | PyPSA v1.0+ (CVaR), PLEXOS |
| **Delivery & Accessibility** | **Pioneering** | Commercial tools (closed), Open tools (steep curve) |

**Conclusion:** The proposed Alea is not merely "better than COMPASS"; it is designed to be **competitive with the global state-of-the-art** across every major dimension. Its unique strength is the **combination** of these world-class capabilities—open-source granular data, advanced market and risk modelling, and a modern delivery interface—into a single, unified platform focused on Africa.

The primary challenge is not a lack of ambition or technical sophistication, but the **execution against severe data constraints**, as documented in our per-country completeness assessment. The platform's success will hinge on how effectively it can bridge these data gaps using advanced methods like satellite-based asset detection and proxy estimation.

If you would like to dive deeper into the benchmarking for any specific capability, such as the market simulation frameworks or the data validation methodologies, please let me know.