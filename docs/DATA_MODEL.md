# Commercial Command Center

## Data Model

---

# INVENTORY SNAPSHOTS

## inventario_snapshot

Historical ERP inventory by cutoff date, warehouse and product. Imports are
idempotent on `(fecha_snapshot, idbodega, idproducto)` and preserve the cost
average and transit breakdown reported by the source file.

Primary Key

`(fecha_snapshot, idbodega, idproducto)`

Important fields

| Column | Description |
|---------|-------------|
| fecha_snapshot | User-supplied date represented by the export |
| idbodega, nombre_bodega | ERP warehouse identity |
| idproducto, nombreproducto | ERP product identity |
| idfam1/idfam2/idfam3 | ERP product hierarchy |
| marca_codigo, marca_nombre | Product brand |
| grupo_fabricante_codigo/nombre | Manufacturer classification |
| unidades | Physical units |
| unidades_disponible/reservado/remisionado | Inventory status |
| transito_1/transito_2/transito_3 | ERP in-transit buckets |
| unidades_transito | Sum of the three transit buckets |
| costo_unitario | ERP average cost (`Promedio`) at the snapshot |
| valor_total | ERP inventory value (`Unidades × Promedio`) |
| archivo_origen, fecha_carga | Import audit trail |

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
