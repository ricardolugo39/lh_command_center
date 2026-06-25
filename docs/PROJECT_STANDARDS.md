# Commercial Command Center Standards

## Development Workflow

Data Source
    ↓
Loader
    ↓
RAW
    ↓
Pipeline
    ↓
DIM / FACT
    ↓
Repository
    ↓
Service
    ↓
Flask UI

---

## Rules

1. Never read Excel inside a Pipeline.

2. Every data source has a Loader.

3. Every Pipeline has a Test.

4. Every Sprint produces working software.

5. Every Ticket ends with a Git Commit.

6. Code before UI.

7. Data Warehouse before Dashboard.

8. One responsibility per module.

9. Always use:
   python -m pytest

10. Every new feature starts with the data model.