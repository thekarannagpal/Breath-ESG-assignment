# Breathe ESG Key Product Tradeoffs

To deliver a high-integrity prototype in 4 days, we focused on building a solid relational data engine and an intuitive analyst UI rather than adding high-maintenance features that degrade reliability. Here are three features we deliberately skipped:

---

## 1. Automated PDF OCR Parsing for Utility Bills
* **What we did instead**: Implemented a CSV ledger upload portal.
* **Why**: Large enterprises receive electric bills from dozens of municipal utility companies, each using customized layouts. Building automated OCR (Optical Character Recognition) templates to extract bill amounts and dates is extremely brittle; a slight change in invoice structure from a utility company breaks the pipeline. Advanced AI OCR (like LLM document extraction) is slow and expensive for bulk historical audits. CSV exports from utility portals are structured, standardized, and clean.

## 2. Live Third-Party IATA Airport Coordinates API Integration
* **What we did instead**: Embedded a coordinates dictionary for the top 20 global corporate aviation hubs (JFK, LHR, CDG, SIN, DXB, SFO, LAX, ORD, FRA, etc.) inside the ingestion module.
* **Why**: Relying on external geo-location or airport API queries (like IATA APIs or Google Geocoding) introduces runtime network dependencies, latency, external rate limits, and credential security overhead. For a prototype, local coordinate lookups allow the system to instantly calculate great-circle travel distances (Haversine formula) in memory with zero dependencies, keeping the application fast and self-contained.

## 3. Utility Portal Web Scrapers (Automated Crawlers)
* **What we did instead**: Relied on facilities teams exporting and dragging-and-dropping portal CSV files.
* **Why**: Building scrapers (e.g. using Selenium or Puppeteer) to bypass utility portal authentication, handle two-factor codes, and extract billing data is a massive maintenance burden. Utility portals continuously update security parameters, blocking automated script access. Manual CSV upload is secure, reliable, and represents the realistic enterprise data collection standard.
