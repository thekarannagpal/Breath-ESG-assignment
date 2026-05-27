# Breathe ESG Relational Emissions Data Model

This document outlines the database schema and architectural choices for the Breathe ESG ingestion, normalization, and audit review platform.

---

## 1. Schema Diagram & Relationships

Our database uses a relational schema designed in Django to model multi-tenant separation, data lineage, unit conversion multipliers, and data corrections:

```
[Organization] (Tenant)
  │
  ├───[UserProfile] (Role: Analyst, Auditor, Admin)
  │
  ├───[Facility] (Lookup Code mapping for Plants & Meters)
  │
  ├───[IngestionJob] (Runs ledger)
  │     └───[RawRecord] (Original payload, status, validations)
  │           └───[NormalizedRecord] (Calculated carbon footprint, Scope, lock state)
  │
  └───[AuditLog] (Ledger of corrections and review state modifications)
```

---

## 2. Model Schema Specification

### Organization (Tenant Base)
Represents the client enterprise. It is the root of the multi-tenancy model.
- `id` (UUID, Primary Key): Globally unique tenant identifier.
- `name` (String): Display name of the client.
- `domain` (String): Domain used for automatic resolution or user allocation.
- `created_at` (DateTime): Organization registration timestamp.

### UserProfile
Links Django's built-in auth `User` to their `Organization` and assigns permission authorization roles.
- `user` (OneToOne -> User): Reference to the authentication account.
- `organization` (ForeignKey -> Organization): Active tenant boundary.
- `role` (String, Choices: `analyst`, `auditor`, `admin`): Enforces permissions. E.g., only `admin` can unlock approved rows.

### Facility
Acts as a mapping registry translating cryptic source identifiers (SAP Plant codes, Utility account numbers, Meter IDs) into physical sites with geographic coordinates or grid emission regions.
- `organization` (ForeignKey -> Organization): Enforces multi-tenancy.
- `name` (String): Human-readable site name (e.g., "Heidelberg Logistics Center").
- `facility_code` (String): The original lookup key (e.g. `1000`, `E-MTR-8899`).
- `region` (String): Used to resolve location-specific Scope 2 grid factors (e.g., `US-CA`, `DE`, `UK`).
- *Unique Constraint*: `('organization', 'facility_code')` ensures that plant codes are unique per tenant, allowing different clients to use identical default plant codes (e.g. `1000`) without collision.

### IngestionJob
Maintains metadata regarding import runs (both CSV uploads and API syncs).
- `organization` (ForeignKey -> Organization)
- `source_type` (String, Choices: `SAP`, `UTILITY`, `CONCUR`)
- `status` (String, Choices: `RUNNING`, `COMPLETED`, `FAILED`)
- `filename` (String): Source file name or sync reference ID.
- `summary` (JSONField): Caches statistics of the run: `{total, success, failed, suspicious}`.
- `created_at` (DateTime): Run start timestamp.
- `created_by` (ForeignKey -> User): User who triggered the import.

### RawRecord
Stores the raw input data exactly as it was ingested. This acts as the immutable "Source of Truth".
- `organization` (ForeignKey -> Organization)
- `job` (ForeignKey -> IngestionJob): Link to import job.
- `row_index` (Integer): Original spreadsheet line number or API array index.
- `raw_data` (JSONField): Complete key-value structure of the ingested data (German fields, string numbers, unmapped units).
- `status` (String, Choices: `PENDING`, `APPROVED`, `REJECTED`, `SUSPICIOUS`)
- `validation_errors` (JSONField): Array of warnings/errors flagged during ingestion (e.g., "Unknown Plant Code", "Usage exceeds historical threshold").

### NormalizedRecord
Contains the standardized physical quantities and calculated CO2e emissions. Linked 1-to-1 to the raw record.
- `organization` (ForeignKey -> Organization)
- `raw_record` (OneToOne -> RawRecord): Immutable link to the source of truth.
- `facility` (ForeignKey -> Facility, Nullable): Mapped facility (null for corporate travel).
- `scope` (Integer, Choices: 1, 2, 3): Scope boundary.
- `category` (String): Classification category (e.g., "Stationary Combustion (Diesel)", "Purchased Electricity", "Business Travel (Flights)").
- `activity_date` (Date): Normalised transaction date.
- `start_date` / `end_date` (Date, Nullable): Billing or activity duration.
- `raw_quantity` (Decimal): Original input quantity.
- `raw_unit` (String): Original input unit.
- `normalized_quantity` (Decimal): Quantity in base unit.
- `normalized_unit` (String): Standardized unit (e.g. `L`, `kWh`, `pkm`).
- `co2e_kg` (Decimal): Computed greenhouse gas footprint.
- `calculation_metadata` (JSONField): Full formula audit trail: conversion rates, emission factors, and daily pro-rating split details.
- `is_locked` (Boolean): Locks record from adjustments. True once approved.
- `approved_at` / `approved_by` (DateTime / ForeignKey -> User): Audit trail tracking sign off.

### AuditLog
An immutable ledger tracking all user adjustments, review state changes, and locking actions.
- `organization` (ForeignKey -> Organization)
- `user` (ForeignKey -> User): Person making the change.
- `timestamp` (DateTime): Timestamp of action.
- `action` (String, Choices: `CREATE`, `UPDATE`, `APPROVE`, `REJECT`, `UNLOCK`)
- `record_type` (String): "RAW_RECORD" or "NORMALIZED_RECORD"
- `record_id` (Integer): ID of target record.
- `field_name` (String, Nullable): Target field modified (e.g., "Quantity").
- `old_value` / `new_value` (Text, Nullable): States before and after the modification.
- `reason` (Text): The analyst's required justification for the override.

### EmissionFactor
The master lookup table containing conversion rates and emissions factors.
- `category` (String): Fuel or activity type (e.g., `diesel`, `electricity`, `flight_long`).
- `raw_unit` (String): Unit name expected from input (e.g. `Ltr`, `MWh`, `mi`).
- `normalized_unit` (String): Target base unit (e.g. `L`, `kWh`, `km`).
- `conversion_multiplier` (Decimal): Multiplied by raw quantity to yield normalized quantity.
- `factor_kg_co2e` (Decimal): Multiplied by normalized quantity to yield kg CO2e.
- `region` (String): Grid location for electricity factor differentiation, or `GLOBAL`.
- `scope` (Integer): Target scope boundary.

---

## 3. Key Data Model Design Decisions

### Shared Database Multi-Tenancy (Row-Level Security)
We selected the shared-database, tenant-column approach using `organization` FK relations on every model. This isolates data efficiently without the resource overhead of schema-per-tenant or DB-per-tenant designs (which are hard to deploy and scale in SQLite/Postgres for prototype environments). 
- Every database query in our API views is explicitly filtered by the active tenant: `RawRecord.objects.filter(organization=org)`.
- Enforces hard boundaries. Sending request headers for Org B when authenticated as Org A will resolve only Org A's query sets, preventing data leakage.

### The Immutable Raw JSON Payload (Source-of-Truth Tracking)
By preserving the original data structure in a JSON field (`RawRecord.raw_data`), we prevent information loss when parsing. If we update our mapping tables (e.g., adding a plant mapping), we can re-evaluate the raw payload at any time without asking the user to upload the spreadsheet again.

### One-to-One Record Linkage & Calculation Metadata
We bind the `NormalizedRecord` to `RawRecord` via a `OneToOneField`. This guarantees that a single transaction source generates exactly one calculated footprint, preventing duplicate counting. Detailed pro-rating data (calendar splits) is cached within the `calculation_metadata` JSON field, maintaining database simplicity while allowing frontend charts to query granular monthly information.

### Locking and Audit Integrity
- When an analyst clicks "Approve", the record transitions to `APPROVED` and the normalized counterpart sets `is_locked = True`.
- Write requests (`edit`) on locked records automatically fail.
- To make a correction, the record must be explicitly unlocked. Unlocking requires the `admin` role and logs an `UNLOCK` event specifying the user's justification.
- Every edit creates an `UPDATE` `AuditLog` entry detailing the previous quantity/unit and the new quantity/unit, satisfying auditor compliance.
