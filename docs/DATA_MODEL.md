# Commercial Command Center

## Data Model

---

# DIMENSIONS

## dim_product

Business Purpose

Stores the commercial product hierarchy used across sales,
CRM, quotations and inventory.

Primary Key

(family_id, group_id)

Columns

| Column | Type | Description |
|---------|------|-------------|
| family_id | TEXT | ERP Family ID |
| group_id | TEXT | ERP Group ID |
| family_name | TEXT | Product Family |
| group_name | TEXT | Product Group |

Source

raw_product_classification

Pipeline

ProductDimensionPipeline