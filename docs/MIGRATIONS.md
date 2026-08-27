# Database migrations

`app.database.migrations` is the single migration authority for operational
`ws_*` tables. Raw, dimensional, and fact tables remain pipeline-owned.

## Running migrations

Run:

```bash
python scripts/workspace/init_workspace.py
```

The runner enables and verifies SQLite foreign-key enforcement, opens one
transaction, and applies the explicit `MIGRATION_MANIFEST` in ascending order.
Applied versions are recorded in `schema_migrations`. Re-running the command is
safe. Existing databases without a ledger are inspected and upgraded in place;
idempotent migrations then establish their version history.

Integrity violations are reported as warnings after migration. Migrations must
never silently delete, merge, or rewrite conflicting production records.

## Current order

1. Core workspace
2. Opportunity MVP
3. Customer-site association
4. Quote currency and exchange-rate domain
5. Project files
6. Initiatives
7. Opportunity closure
8. Agreements and agreement items

## Rules for future migrations

- Add one immutable entry to `MIGRATION_MANIFEST` with the next integer version.
- Use a descriptive, unique name.
- Make the operation safe for both fresh and previously upgraded databases.
- Use schema introspection before SQLite `ALTER TABLE` operations.
- Execute statements through the supplied connection; never commit in a
  migration function.
- Preserve data and repository compatibility.
- Add fresh-installation, upgrade, repeatability, and preservation tests.
- Never use implicit filesystem discovery or edit an applied migration.

## Legacy files

Historical scripts under `database/` and `scripts/workspace/` are retained
temporarily for auditability. They are superseded and must not be executed.
They can be removed only after the canonical chain has been validated in the
deployment environments.

Destructive downgrade is intentionally unsupported. Restore a verified backup
when rollback is required.
