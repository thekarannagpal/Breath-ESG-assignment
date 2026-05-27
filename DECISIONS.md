# Breathe ESG Resolved Ambiguities & Scope Decisions

This document details every design ambiguity resolved during development, what subsets of source data we handled or ignored, and questions we would raise to the Product Manager for future iterations.

---

## 1. Source Subsets: Handled vs. Ignored

### SAP ERP (Fuel & Procurement)
* **What we handled**: Flat-file CSV extracts modeled after standard SAP transaction outputs (like `MB51` or `ME2N`). We parsed standard technical headers in German/English (`MBLNR` Document, `BUDAT` Date, `MATNR` Material, `MAKTX` Description, `MENGE` Quantity, `MEINS` Unit, `WERKS` Plant). We implemented parser sanitization for German date structures (`DD.MM.YYYY`) and comma-decimal formats (e.g., `1.250,50` to `1250.50`). We resolved plant codes (`WERKS`) to physical facility locations to apply grid factors.
* **What we ignored**: Nested XML IDocs, BAPI RFC interface connections, and OData Gateway service integration. These require enterprise firewall configurations and middleware that are not practical for a prototype. We also ignored warehouse transfer documents (movement codes that simply shift fuel stock rather than consume it) by focusing on procurement receipts.

### Utility Data (Electricity)
* **What we handled**: Standard billing ledgers exported from utility portals (like PG&E, National Grid). We mapped account/meter numbers to facilities. Because billing periods do not align with calendar months, we implemented a linear daily calendarization engine (`split_utility_period`) that splits consumption proportionally and records monthly chunks (e.g. splitting a bill from April 15 to May 14 into April and May components).
* **What we ignored**: PDF invoice OCR processing (prone to reading errors) and utility API pulls (since utility companies rarely expose standard public APIs). We also ignored demand charge tariffs, power factor penalties, and electricity billing tiers, focus-modeling purely on total active energy consumed (kWh/MWh).

### Corporate Travel (Concur/Navan)
* **What we handled**: API integration JSON sync payload. 
  - *Flights*: We parsed origin and destination IATA codes, resolved their coordinates, and calculated the Great Circle distance (Haversine formula). We classified flights as short-haul (<480 km) or long-haul (>=480 km), applying distinct base emission factors. We applied cabin class multipliers: Economy (1.0), Premium Economy (1.6), Business (2.9), and First Class (4.0).
  - *Hotels*: We calculated room-nights (`nights * rooms`) and applied country-specific emissions factors (e.g., US, UK, DE, and GLOBAL fallbacks).
  - *Ground Transport*: We supported mile-to-km conversions and fuel-type emissions factors (Petrol, Diesel, Electric).
* **What we ignored**: Multi-leg flight layovers (calculated as a single direct great-circle leg), baggage weight parameters, hotel meal footprints, taxi receipts, and corporate travel reward point calculations.

---

## 2. Post-Submission Review: Defending Key Decisions

### Q: Why build a simulated API Sync for Travel but CSV Uploads for SAP/Utility?
* **A**: Corporate travel platforms (Navan, TravelPerk, Concur) are modern SaaS applications that expose excellent, clean JSON REST APIs. Simulating an API pull fits the real-world operational path for travel. 
* Conversely, SAP ERP data in enterprise environments sits behind strict network firewalls, and obtaining direct API access often takes IT departments several months. A CSV flat-file ALV report export is the pragmatic onboarding mechanism.
* Similarly, utility companies do not offer uniform APIs. Facilities teams pull CSV ledgers from utility portals once a month. Implementing a CSV uploader matches the real workflow.

### Q: How does the calendarization algorithm handle leap years and boundary dates?
* **A**: The daily rate is calculated as `total_usage / total_days` where `total_days` is calculated inclusively as `(end_date - start_date).days + 1`. The algorithm increments the loop day-by-day and groups them into their respective calendar months. This natively accommodates leap years (as the Python `datetime` module handles February 29 automatically) and safely splits bills spanning year-end boundaries (e.g., Dec 15 to Jan 14 is split into December and January proportions).

### Q: How do we determine if a transaction is "Suspicious"?
* **A**: We implemented multi-stage anomaly detection:
  1. *Limits*: Flagged if fuel quantity >100,000 units, flight distance >15,000 km, hotel stay >30 nights, daily utility consumption >10,000 kWh, or booking cost >$10,000.
  2. *Orphans*: Flagged if a plant code `WERKS` or meter number is not mapped in the facilities directory (represented as pending mapping review).
  3. *Unclassified*: Flagged if the fuel description in SAP cannot be matched to diesel or natural gas.

---

## 3. What We Would Ask the PM

1. **Emission Factor Selection**: Do client companies need to override standard factors with custom registries (e.g., using their specific market-based utility contract factors instead of location-based grid averages)?
2. **Pro-Rating Accuracy**: Should calendarization splits account for temperature/degree-day variations (using historical weather data) rather than assuming flat linear consumption across billing days?
3. **Approval Workflows**: Should we implement a dual-approval scheme where one analyst submits changes and a separate auditor signs off (maker-checker pattern) to prevent single-point-of-failure errors?
