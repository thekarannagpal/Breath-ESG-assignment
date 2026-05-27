# Breathe ESG Data Source Research & Realities

This document details the real-world research behind our three data sources, the structure of our sample templates, and what would fail in a production environment.

---

## 1. SAP ERP: Fuel & Procurement

### Real-World Format Researched
We researched standard SAP ALV Grid report exports, specifically from transactions **MB51** (Material Movements) and **ME2N** (Purchase Order History). 

### Key Research Findings
* SAP database structures rely on German technical abbreviations: `MBLNR` (Material Document Number), `BUDAT` (Posting Date), `MATNR` (Material Number), `WERKS` (Plant), `MENGE` (Quantity), `MEINS` (Base Unit of Measure), and `EBELN` (Purchase Order Number).
* Reports exported from European SAP clients frequently use European localization: German column headers (e.g. `Buchungsdatum` instead of Posting Date, `Werk` instead of Plant) and European number formatting (e.g., `12.500,50` where `.` is the thousands separator and `,` is the decimal separator).

### Sample Data Design
Our SAP sample template contains the following structure:
```csv
Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg
50001001,12.04.2026,DIESEL_01,Industrial Diesel,"12.500,50",LTR,1000,45000921
50001002,18.04.2026,NAT_GAS_02,Natural Gas Pipeline,4500,M3,1100,45000922
50001003,24.04.2026,DIESEL_01,Industrial Diesel,90000,LTR,1000,45000923
```
* **Row 1**: Standard purchase, testing German decimal replacement (`12.500,50` -> `12500.50`).
* **Row 2**: Natural Gas purchase, testing volume-to-carbon calculation.
* **Row 3**: Anomaly row, testing the extreme value trigger (>100,000 limits).
* **Row 4 & 5**: Validation checks, testing missing facility plant mappings (e.g. Plant `1300` which isn't registered) and unmapped materials.

### What Would Break in Production
* **Custom Z-Fields**: If the client's SAP implementation uses custom fields (e.g., `ZBUDAT` or custom column headers) or shifts column orders, standard CSV headers will fail to map.
* **Plant Code Drift**: If the procurement team creates a new manufacturing plant in SAP (e.g. Plant `3000`) but fails to register it in Breathe ESG first, imports will stall with "Unmapped Plant" warnings.

---

## 2. Utility Data: Purchased Electricity

### Real-World Format Researched
We researched Green Button XML data exports and standard commercial billing ledgers from utility portals (specifically PG&E and ConEd).

### Key Research Findings
* Utility portal ledgers output billing cycles based on reading schedules (e.g. April 12 to May 11). These billing periods span across calendar months, preventing simple monthly reporting without splitting.
* Industrial facilities sometimes report electricity in Megawatt-hours (MWh) instead of Kilowatt-hours (kWh). Our engine must detect and convert these automatically.

### Sample Data Design
Our Utility sample template contains the following structure:
```csv
Account Number,Meter Number,Bill Period Start,Bill Period End,Usage,Unit,Tariff,Total Cost
98765432,E-MTR-8899,2026-04-12,2026-05-11,12450.00,kWh,E-19,2450.75
98765432,E-MTR-1234,2026-04-15,2026-05-14,22.40,MWh,E-19,4500.20
```
* **Row 1**: Standard monthly cycle, testing linear calendar pro-rating (split across April and May).
* **Row 2**: Megawatt-hour billing, testing unit conversion logic (`22.4 MWh * 1000 = 22400 kWh`).
* **Row 3**: Anomaly row, testing billing period duration gaps (period > 45 days).
* **Row 4**: Orphan check, testing unregistered meter IDs.

### What Would Break in Production
* **Billing Period Gaps/Overlaps**: If billing files are uploaded out of sequence, overlaps can cause double counting. 
* **Seasonal Pro-Rating Errors**: Simple linear daily splitting assumes energy consumption is uniform. In reality, electricity usage is highly dependent on temperature. Assuming a linear split might misrepresent seasonal carbon peaks (cooling peaks in July vs. heating peaks in December).

---

## 3. Corporate Travel: Business Flights & Hotels

### Real-World Format Researched
We researched the **Navan Booking API** (REST JSON schema) and **SAP Concur Standard Accounting Extracts (SAE)**.

### Key Research Findings
* Modern travel API payloads return detailed flight booking structures containing origin and destination IATA codes (e.g. `JFK`, `LHR`), cabin classes, hotel nights, and room counts.
* Cabin classes are critical for carbon calculation: business and first-class seats occupy larger cabin areas, leading to standard DEFRA multipliers (e.g. business class flights carry 2.9x higher carbon emissions per kilometer than economy).

### Sample Data Design
Our Concur sync simulator payload contains the following structure:
```json
[
  {
    "booking_id": "BK-88091",
    "type": "flight",
    "start_date": "2026-05-10",
    "origin": "JFK",
    "destination": "LHR",
    "cabin_class": "Business",
    "passengers": 1,
    "amount": 2450.00
  },
  {
    "booking_id": "BK-88092",
    "type": "hotel",
    "start_date": "2026-05-10",
    "end_date": "2026-05-15",
    "hotel_city": "London, UK",
    "hotel_nights": 5,
    "hotel_rooms": 1,
    "amount": 1250.00
  }
]
```
* **Row 1**: Business flight from JFK to LHR. Tests Haversine distance (~5567 km) and business class multiplier (2.9x).
* **Row 2**: Hotel stay in London. Tests room-night calculations (`5 nights * 1 room = 5 room-nights`) and UK-specific hotel emission factors.
* **Row 3**: Unknown airport codes, testing distance failure flags.
* **Row 4**: Booking amount exceedance, testing financial safety flags (booking > $10,000).

### What Would Break in Production
* **Multi-Leg Flight Routes**: If an employee books a flight with layovers (e.g., SFO -> ORD -> JFK -> LHR), and the API only exposes the origin SFO and destination LHR, a direct great-circle calculation under-represents actual flight distances.
* **Orphan Airport Codes**: If a travel booking contains a remote municipal airport code (e.g., `LBE` or a new regional airport) that is not indexed in our internal coordinates table, the distance calculation will fail, requiring analyst manual override.
