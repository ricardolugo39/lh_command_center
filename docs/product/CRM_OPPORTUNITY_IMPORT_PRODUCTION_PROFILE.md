# Production CRM Opportunity Import Profile

## Workbook assessment

Source workbook: `export_150434.578.xlsx`

- Sheet: `Datos`
- Data rows: 879
- Fully blank rows: 0
- Columns: 20
- Unique CRM Opportunities: 451
- Opportunities with more than one row: 233
- Largest Opportunity group: 12 rows
- Exact duplicate rows: 1
- Unique source `ID` values: 469
- Unique `Documento` values: 425
- Unique `Oportunidad` values: 451

`Oportunidad` is the commercial pursuit identifier. Each `ID` and each
`Documento` observed belongs to only one Opportunity, but both repeat across
product rows. Therefore only normalized `Oportunidad` is used as
`external_id`.

### Column population

| Column | Populated | Blank | Unique |
|---|---:|---:|---:|
| ID | 879 | 0 | 469 |
| Fecha | 879 | 0 | 120 |
| Prioridad | 879 | 0 | 4 |
| Oportunidad | 879 | 0 | 451 |
| Nombre Empresa | 835 | 44 | 168 |
| Marca | 580 | 299 | 34 |
| Código producto | 452 | 427 | 342 |
| Descripción producto | 787 | 92 | 543 |
| Valor Potencial | 787 | 92 | 746 |
| Sucursal empresa | 835 | 44 | 2 |
| Documento | 835 | 44 | 425 |
| Probabilidad | 879 | 0 | 6 |
| Fecha Cierre | 879 | 0 | 152 |
| Vendedor | 877 | 2 | 20 |
| Creado por | 879 | 0 | 18 |
| Estado | 879 | 0 | 3 |
| Etapa | 825 | 54 | 4 |
| Teléfono | 824 | 55 | 164 |
| Móvil | 333 | 546 | 60 |
| Ciudad | 835 | 44 | 57 |

There are 167 distinct normalized company names. Twenty-eight Opportunity
groups have no company name. Two groups contain genuinely different company
names and are blocked. One exact duplicate source row is excluded from value
aggregation.

### Observed controlled values

- Status: `Abierto`, `Realizado`, `Cancelado`
- Stage: `Contacto`, `Propuesta o Cotizacion`, `Negociacion`,
  `Inicio Relacion Comercial`
- Priority: `1`, `2`, `3`, `4`
- Probability: `0`, `5`, `20`, `50`, `75`, `100`
- Sellers: 20 unique values
- Creators: 18 unique values

Six Opportunity groups contain more than one status, five contain more than
one stage, six contain more than one priority, five contain more than one
probability, and ten contain more than one close date. The most recent
`Fecha` is used when its rows agree. Same-date disagreements remain visible
as conflicts.

## Production mapping

The active versioned profile is:

`CRM Producción · export Oportunidades`, version 1.

| Source column | Treatment |
|---|---|
| Oportunidad | Immutable external Opportunity ID |
| Documento | Origin Reference; all references retained |
| ID | Source-row traceability |
| Fecha | CRM source update date |
| Nombre Empresa | Customer resolution |
| Sucursal empresa | Customer-site source fact |
| Teléfono, Móvil, Ciudad | Customer-resolution evidence and source facts |
| Vendedor | Commercial seller resolution |
| Creado por | Source metadata only |
| Estado, Etapa | CRM lifecycle source facts |
| Prioridad, Probabilidad, Fecha Cierre | CRM source facts |
| Marca, Código producto, Descripción producto | Repeating product-line facts |
| Valor Potencial | Repeating line value, aggregated per Opportunity |

## Customer resolution

Matching is deterministic and explainable:

1. Exact normalized company name.
2. Exact normalized company name plus city when the name is ambiguous.
3. Exact normalized company name plus phone or mobile.
4. Previously confirmed source-name alias.
5. Unique normalized legal-name variant after conservative legal-suffix
   normalization.

Customer names are never matched with broad fuzzy similarity. No customer is
created by this import.

Against the current customer data, the real workbook preview produces:

- 357 matched and eligible Opportunities
- 64 Opportunities requiring customer review
- 30 blocked Opportunities
  - 28 have no company name
  - 2 contain conflicting customer identities

The 357 matches consist of exact normalized names and nine unique legal-name
variants. User resolutions are stored as reusable aliases for later imports.

## Seller resolution

`Vendedor` is matched by normalized exact value against active users,
existing Opportunity sellers, and sellers in the customer dimension.
Confirmed aliases are reusable. All 451 Opportunity groups in the current
workbook resolve to a seller because the two blank seller rows belong to
groups with another populated seller row.

`Creado por` remains source metadata.

## Grouping and naming

Rows are grouped by normalized `Oportunidad`. Exact duplicate rows are
excluded from aggregation. The preview retains original row numbers, source
IDs, product lines, brands, codes, descriptions, and line values.

Opportunity names are generated deterministically:

1. Up to three brands plus the first product code.
2. Brands plus a concise product description.
3. Origin Reference.
4. `Oportunidad CRM <external_id>` as the final fallback.

The generated name is creation-only and remains editable locally.

## Lifecycle policy

The safe open-stage mapping is:

- `Contacto` → `prospect`
- `Propuesta o Cotizacion` → `quoted`
- `Negociacion` → `negotiation`
- `Inicio Relacion Comercial` → `prospect`

CRM `Realizado` and `Cancelado` are retained as source facts. They do not
create closure evidence or bypass the structured Won, Lost, or Cancelled
workflows. A reimport cannot reopen or rewrite a locally closed Opportunity;
the preview blocks that lifecycle conflict.

## Values and product lines

The workbook contains 786 meaningful unique product rows after excluding the
single exact duplicate. Their aggregate potential value is
29,105,509,135 COP.

Potential value, probability, priority, close date, status, and stage remain
structured CRM source facts. They do not overwrite governed commercial
amount, quote value, Request Discount probability, or closure timestamps.

Product rows remain structured import metadata. They are not converted into
Quotes, RFQ items, or a new permanent child-object type.

## Partial confirmation and deferred review

An import execution may complete successfully without resolving every
customer:

- matched and user-resolved groups are created or updated;
- unchanged eligible groups are synchronized without duplication;
- Needs Review and Blocked groups are retained as pending CRM candidates;
- no pending candidate appears in the Pipeline until it has a valid existing
  customer and is imported.

The pending queue preserves the original and latest source executions,
retained file, file hash, immutable profile version, mapped group snapshot,
match evidence, resolution history, and eventual Opportunity/import IDs.

A user may resolve one candidate or every pending candidate sharing the same
normalized CRM company identity. The decision creates a reusable customer
alias. Ready candidates can then be imported from the retained workbook
without uploading it again. File hash, profile version, customer existence,
and `origin=crm + external_id` identity are revalidated before writing.

When a newer export contains an already-pending external Opportunity, the
same pending record is refreshed rather than duplicated. User resolutions
and audit history are preserved. Absence from a later export does not delete,
close, or otherwise change either an Opportunity or a pending candidate.
