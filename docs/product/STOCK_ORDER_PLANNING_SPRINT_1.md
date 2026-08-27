# Stock Order Planning — Sprint 1 Data Foundation

Sprint 1 implements the vendor-independent data foundation only. It does not
forecast demand or recommend purchase quantities.

## Delivered foundation

- Configurable vendor profiles and source aliases
- Configurable branches
- Vendor product catalogue, including zero-inventory products
- Product families and role-based family membership
- Versioned purchase-to-sale transformations
- Dated transit supplies kept separate from undated ERP transit columns
- Complete product universe built from catalogue, sales, inventory, transit,
  families, and transformations
- Separate frozen inventory positions per branch and product
- Data-quality issues for missing catalogue records, missing inventory,
  negative usable stock, and undated transit
- Database-enforced immutable planning snapshots

## Snapshot contract

A snapshot records the source cutoff dates, source fingerprint, complete product
universe, every configured branch position, dated transit evidence, and quality
issues. Later source imports or master-data changes cannot alter it.

The snapshot is the input boundary for Sprint 2. Forecasts must read a frozen
snapshot rather than query changing operational tables directly.

## Configuration rule

THK is configured through a vendor profile, inventory brand aliases, sales
suffixes, catalogue records, families, and transformation records. No THK name,
branch allocation, rail family, or SKU conversion is embedded in the engine.

## Activation boundary

Migration 35 must be applied through the canonical migration runner. Production
vendor profiles, branches, catalogue records, family relationships, and
transformations should be loaded only after review. Sprint 1 intentionally does
not modify the production database during automated tests.

