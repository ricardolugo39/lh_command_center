# Architecture Decision Records

## ADR-001 — Access only for initial migration

Access will only be used as a temporary source for the initial migration.

After migration, the Commercial Command Center will use SQLite as the source database.

## ADR-002 — Raw tables are immutable

Raw tables store source data exactly as received.

Raw tables must not be cleaned, enriched, deleted, or manually modified.

## ADR-003 — Business logic uses facts and dimensions

Dashboards and services should use clean fact and dimension tables, not raw tables directly.

## ADR-004 — UI does not access the database directly

Flask routes and templates must not query the database directly.

Data access should go through repositories and services.

## ADR-005 — Flask is the interface, not the core product

The core product is the commercial data engine.

Flask is the user interface layer on top of the data model, services, and pipelines.

## ADR-006 — Product Dimension

Status: Accepted

### Decision

Product families and product groups will be stored in a single dimension table (`dim_product`).

### Rationale

Commercial reports always analyze products by hierarchy.

A single dimension simplifies joins, reporting, and future extensions while matching the business mental model.