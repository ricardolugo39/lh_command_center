# Unified Opportunity Pipeline — Architecture Proposal

**Sprint:** Merge Projects and CRM Opportunities  
**Status:** Proposed for review; no implementation authorized  
**Date:** July 30, 2026

## Decision summary

Commercial Command Center will have one commercial pursuit object:
**Opportunity**.

The existing Project object becomes the Opportunity object. Existing records are
not recreated, and the existing Opportunity detail workspace is not redesigned.
Origin becomes immutable metadata on the same object. It records how the
Opportunity entered Commercial Command Center and never changes afterward.

Supported Origin values:

- Manual
- CRM
- Quote
- Visit
- RFQ

The existing Projects portfolio becomes **Pipeline**, the shared portfolio of all
Opportunities.

This proposal deliberately does not define CRM spreadsheet columns, mappings, or
stage conversions. Those require the real CRM export.

---

## Opportunity Origin Principle

Every commercial pursuit is represented by exactly one Opportunity.

That Opportunity has exactly one immutable Origin:

- Manual
- CRM
- Quote
- Visit
- RFQ

Origin identifies the entry point that created the Opportunity. It does not
define a different Opportunity type, page, lifecycle, or workflow.

Everything else enriches the same Opportunity:

- Activities
- Quotes
- RFQs
- Visits
- Commercial Approvals
- Ask Analyses
- Files
- Follow-ups
- Timeline events

These records are evidence attached to the commercial pursuit. They do not turn
it into a different kind of Opportunity and they do not change its Origin.

When a Quote, Visit, or RFQ is itself the entry point that causes an Opportunity
to be created, that creation event determines Origin. Any later Quotes, Visits,
or RFQs are evidence only.

This principle prevents future duplication into “CRM Opportunities,” “Visit
Opportunities,” or other parallel Opportunity types.

---

## 1. Proposed database changes

### Preserve the current opportunity record

The existing opportunity record remains the parent of all current commercial
execution history. It should not be replaced or split by Origin.

No physical rename of the existing opportunity storage is required in this
sprint. Product terminology can move from Project to Opportunity without risking
existing record IDs and relationships.

### Add opportunity identity and Origin metadata

Proposed additions to the existing opportunity record:

| Attribute | Purpose | Rule |
|---|---|---|
| `origin` | Immutable entry point of the Opportunity | Required; Manual, CRM, Quote, Visit, or RFQ. Existing records default to Manual. |
| `external_id` | Stable identifier assigned by the originating system or record | Optional; required for repeatable CRM synchronization. |
| `origin_reference` | Immutable traceability reference to the record that caused creation | Optional for Manual; retained for CRM, Quote, Visit, and RFQ origins when available. Never used as a replacement for internal Opportunity ID. |
| `imported_at` | First successful import time | Null for locally created records. Set once. |
| `last_synchronized_at` | Most recent successful origin-system update | Null until imported or synchronized. |
| `created_import_execution_id` | Import execution that first created the opportunity | Optional, immutable audit reference. |
| `last_import_execution_id` | Most recent import execution that updated it | Optional, updated after successful synchronization. |
| `import_metadata` | Non-business audit metadata | Optional structured metadata such as mapping-profile version, file reference, and source row references. |

### Identity constraint

Add a conditional uniqueness rule for:

```text
origin + external_id
```

The rule applies only when `external_id` is present and nonblank.

Consequences:

- CRM imports can update the same Opportunity reliably.
- Quote, Visit, and RFQ origins can later use their own stable external
  identifiers.
- Manual Opportunities can continue without an external ID.
- Customer name and opportunity name never participate in import identity.

### External ID versus Origin Reference

These fields serve different purposes:

- `external_id` is the stable machine identity used to match future imports by
  Origin + External ID.
- `origin_reference` is the immutable traceability reference for the record that
  caused the Opportunity to be created.

Examples of an Origin Reference may eventually include a CRM record reference,
Quote number, Visit reference, or RFQ number. The exact formatting and CRM
mapping remain configurable and are not assumed in this proposal.

The two values may be identical for a particular origin, but they remain
separate architectural concepts. Neither changes after Opportunity creation.

### Existing-record migration

All existing opportunities receive:

```text
origin = Manual
external_id = empty
origin_reference = empty
import timestamps = empty
```

Existing IDs and every child relationship remain unchanged.

Visit-created Opportunities should receive `origin = Visit` after the Origin
field exists. The migration approach must identify them only through the current
explicit visit-to-opportunity relationship; names or descriptions must not be
used to infer origin.

If an existing Opportunity cannot be proven to have originated from a visit, it
remains Manual.

### Import configuration records

Prepare a versioned **Opportunity Import Mapping Profile** concept with:

| Attribute | Purpose |
|---|---|
| Profile ID and name | Identifies one reusable CRM-export configuration. |
| Import origin | CRM for this workflow; extensible to other originating systems. |
| Version | Makes every import reproducible. |
| Active status | Determines which configuration can be selected. |
| Column mapping | Maps source headers to canonical opportunity concepts. |
| Transformation rules | References approved, named transformations without embedding spreadsheet-specific behavior in the importer. |
| Grouping configuration | Identifies the mapped field that groups multiple rows into one Opportunity. |
| Validation configuration | Defines required mapped concepts and field-level rules. |
| Stage/value ownership configuration | Holds mappings approved after reviewing the real export. |
| Created/updated audit | Preserves configuration history. |

An import execution should retain a snapshot or immutable version reference to
the mapping profile used. A later profile edit must not change the meaning of a
completed import.

### Future company configuration

The architecture should allow company-level commercial settings independently
from import mappings. Reserve the configuration key:

```text
minimum_quote_value_for_opportunity_creation_cop
```

Its proposed default is `5,000,000 COP`. No configuration record, setting UI, or
automatic Quote behavior is implemented in this sprint.

### Reuse existing import audit

The current import execution and issue history can remain the shared audit
mechanism. CRM Opportunity executions need to record, at minimum:

- source filename and retained file;
- file hash;
- mapping-profile ID and version;
- rows read;
- Opportunity groups identified;
- groups to create;
- groups to update;
- unchanged groups;
- blocked groups;
- warnings and errors;
- rows represented by each Opportunity group;
- confirmation user and timestamps.

No CRM Opportunity records are written until confirmation.

---

## 2. Opportunity model changes

### Canonical product object

The conceptual model becomes:

```text
Opportunity
├── Identity: internal ID
├── Origin: immutable Origin + optional external ID
├── Import audit
├── Customer and owner
├── Lifecycle and commercial context
├── Governed commercial value
└── Existing child records
```

“Project” ceases to be a separate product concept. It remains only as legacy
internal terminology where changing it would create unnecessary migration risk.

### Origin behavior

Origin is immutable creation metadata. It is assigned once when the Opportunity
is created and cannot be edited or changed by later imports, activities, quotes,
visits, RFQs, Ask analyses, files, follow-ups, or approvals.

Origin Reference is also assigned only at creation and remains immutable.

It does not change:

- the detail page;
- lifecycle stages;
- health rules;
- next-action rules;
- closure rules;
- available child records;
- Request Discount;
- commercial-value precedence;
- read-only behavior after closure.

### Creation rules by Origin

| Entry point | Opportunity Origin |
|---|---|
| Current new-project flow | Manual |
| CRM Opportunity import | CRM |
| Existing visit-to-opportunity flow | Visit |
| Future qualifying quote automation | Quote |
| Future RFQ conversion | RFQ |

The future Quote and RFQ rules are not implemented in this sprint. After
creation, any additional Quote, Visit, or RFQ is evidence and does not change
Origin.

### Future Quote-origin threshold

The future rule that may create an Opportunity from a qualifying Quote must use
company configuration rather than a hardcoded amount.

Proposed configuration concept:

| Setting | Default |
|---|---:|
| Minimum Quote Value Required to Automatically Create an Opportunity | COP 5,000,000 |

The threshold is evaluated in COP against the Quote's normalized value. When the
future behavior is implemented:

- a qualifying Quote with no existing Opportunity may create one with
  Origin = Quote;
- a Quote associated with an existing Opportunity is attached as evidence and
  does not create another Opportunity;
- changing the company setting affects future evaluations only and does not
  change existing Opportunity Origins.

This sprint only reserves the configuration concept. It does not implement the
setting, Quote import, threshold evaluation, or automatic Opportunity creation.

### Update ownership

The model needs explicit ownership boundaries rather than a universal
“last writer wins” rule.

**CRM-owned imported facts**

The exact list remains unconfigured until the real export is reviewed. The
mapping profile will declare which supported Opportunity fields may be refreshed
from CRM. CRM origin never makes the full Opportunity record CRM-owned.

**Command Center-owned execution**

Future imports never replace or delete:

- activities;
- timeline history;
- follow-ups;
- quotes and revisions;
- files;
- approvals and decisions;
- Request Discount records;
- linked visits;
- initiative relationship;
- RFQ relationship;
- closure history.

**Command Center-governed commercial amount**

When an approved Request Discount has established the canonical commercial
amount, a CRM import cannot overwrite it.

The existing value precedence remains:

```text
Approved commercial amount
    ↓ otherwise
Primary quote amount
    ↓ otherwise
No commercial value
```

An imported CRM potential value is an imported fact. It must not be treated as an
approved commercial amount. Its exact storage mapping is deferred until the CRM
export is reviewed.

### Closed opportunities

The current product makes Won, Lost, and Cancelled Opportunities read-only.

The future CRM synchronization policy for a locally closed record must be
explicitly approved before importer implementation. The importer architecture
must be able to flag an imported/local lifecycle conflict in preview rather than
silently reopening or rewriting a closed Opportunity.

---

## 3. Pipeline page mockup

### Minimal UI change

Rename:

```text
Navigation: Proyectos         → Pipeline
Page title: Proyectos         → Pipeline de oportunidades
Primary action: Nuevo proyecto → Nueva oportunidad
Table column: Proyecto        → Oportunidad
```

Add only:

- **Creada desde** filter, backed by Origin
- **Creada desde** column, backed by Origin

All existing filtering, ordering, value, health, blocker, and navigation behavior
remains unchanged.

### Proposed desktop layout

```text
Pipeline de oportunidades                         [Nueva oportunidad]

┌─────────────────────────────────────────────────────────────────────┐
│ Estado       Vendedor      Salud        Creada desde               │
│ [Todos ▾]    [Todos ▾]     [Todas ▾]    [Todas ▾]                  │
│                                                                     │
│ Cliente                                                            │
│ [Buscar cliente.................................................]  │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Cliente │ Oportunidad │ Creada desde │ Valor comercial │ Valor COP │ Estado │ ... │
├──────────────────────────────────────────────────────────────────────────────┤
│ Acme    │ Reductores  │ CRM    │ COP 8.5M        │ COP 9.0M  │ Negoc. │ ... │
│ Beta    │ Taller SKF  │ Manual │ Sin cotización  │ —         │ Prosp. │ ... │
│ Gamma   │ TKST        │ Visita │ COP 6.2M        │ COP 6.2M  │ Esper. │ ... │
└──────────────────────────────────────────────────────────────────────────────┘
```

The remaining columns stay exactly as today:

- Salud
- Bloqueo actual
- Actualizado

### Origin presentation

The internal architectural field remains `origin`. The Spanish UI presents it
with the natural label **Creada desde** (“Created From”), avoiding internal
architecture terminology in the commercial experience.

It appears as one compact, read-only text badge:

- Manual
- CRM
- Cotización
- Visita
- RFQ

The badge is informational and immutable. It does not link to another detail
experience.

Origin Reference is retained for traceability and import audit. No new
Opportunity-detail field or section is proposed for it in this sprint.

### Sorting and actions

Preserve:

- fixed most-recently-updated ordering;
- opportunity-name link to the existing detail page;
- combined filters and clear-filter behavior;
- no inline row actions.

No new summary cards, sorting controls, views, or pipeline stages are proposed.

---

## Workspace versus Pipeline

Workspace and Pipeline are complementary product surfaces.

**Workspace** answers:

> What requires my attention today?

It is task-oriented and organizes overdue, current, and upcoming execution.

**Pipeline** answers:

> What commercial opportunities am I trying to win?

It is Opportunity-oriented and provides the shared commercial portfolio.

This distinction is conceptual only. No Workspace UI change is proposed.

---

## 4. CRM Opportunity import architecture

### Placement

Add **Oportunidades CRM** as an import type in the existing ERP Import Center.
It uses the established controlled-import pattern but adds mapping and grouping
steps.

### Target workflow

```text
Upload Excel
    ↓
Inspect columns and select mapping profile
    ↓
Validate mapped concepts and row values
    ↓
Group rows into Opportunities
    ↓
Resolve every group to an existing customer
    ↓
Preview create/update/unchanged/conflict results
    ↓
Show summary and issues
    ↓
Explicit confirmation
    ↓
Create or update Opportunities in place
```

The importer is not implemented in this sprint.

### Responsibilities

1. **File intake**
   - Reuse accepted spreadsheet handling, retained source file, hash, and
     execution audit.

2. **Column inspection**
   - Read headers exactly as supplied.
   - Do not require hardcoded CRM column names.
   - Select an existing mapping profile or stop until a valid profile exists.

3. **Mapping**
   - Convert source columns into canonical Opportunity concepts through the
     selected profile.
   - Keep source-header knowledge outside the core import workflow.

4. **Validation**
   - Validate that required concepts are mapped.
   - Validate source identity, customer resolution, types, controlled values,
     and group consistency.
   - Report issues before confirmation.

5. **Grouping**
   - Group source rows using the column mapped to External Opportunity ID.
   - One group represents one Opportunity.
   - Retain every source row number belonging to the group.
   - Multiple product rows do not create duplicate Opportunities.

6. **Resolution**
   - Match existing records only by `CRM + external_id`.
   - Resolve customers through stable customer identity configured in the
     mapping; never by customer name.
   - When customer resolution is confident and unique, attach the existing
     Command Center customer.
   - When no confident, unique match exists, classify the group as
     **Needs Review**.
   - Show Needs Review groups in preview and allow the user to select the
     correct existing customer.
   - Record the user-confirmed resolution in the import execution.
   - Do not create a new customer as a side effect of Opportunity import.
   - Do not create or update an Opportunity until customer resolution succeeds.
   - Classify resolved groups as Create, Update, Unchanged, or Blocked.

7. **Preview**
   - Show Opportunity-level results, not only spreadsheet rows.
   - Show changed fields for updates.
   - Show protected local fields and conflicts.
   - Show Needs Review groups and the customer-resolution control.
   - Keep confirmation blocked while any included group lacks a resolved
     existing customer.
   - Show group row counts and validation issues.

8. **Confirmation**
   - Re-read the retained file using the same immutable mapping-profile version.
   - Revalidate before writing.
   - Create or update the Opportunity as one operation per confirmed import.
   - Revalidate every user-selected customer before writing.
   - Reject any unresolved group; orphan Opportunities are never permitted.
   - Preserve all existing child records.

9. **Audit**
   - Save counts, warnings, mapping version, source rows, created IDs, updated
     IDs, and protected-field decisions.

### Opportunity grouping rules

The grouping engine requires a canonical **External Opportunity ID** mapping.
The source column name is unknown until configuration.

Within a group:

- Opportunity-level fields must resolve consistently or raise a preview issue.
- The group must resolve to exactly one existing Command Center customer before
  it becomes eligible for creation or update.
- Repeated product rows contribute to the group summary.
- Product-row behavior beyond grouping is deferred; the sprint does not invent
  product mappings or create quote items.
- Blank or inconsistent identity blocks confirmation for that group.

### Customer resolution states

```text
Matched
└── One confident existing-customer match; eligible for preview action.

Needs Review
└── No confident unique match; user must choose an existing customer.

Resolved by User
└── Existing customer selected and recorded; eligible for preview action.

Blocked
└── Customer remains unresolved or selected customer is no longer valid.
```

The Opportunity importer never creates an orphan Opportunity and never creates a
customer implicitly.

### Idempotency

Reimporting the same file or a later file containing the same CRM Opportunity:

- does not create another Opportunity;
- updates the same internal record;
- preserves its children and history;
- records the new synchronization execution;
- reports unchanged groups when no owned source fact changed.

---

## 5. Configurable mapping architecture

### Canonical field registry

The importer works with canonical concepts, not CRM column names.

Potential concepts include:

- External Opportunity ID
- Origin Reference
- Customer identity
- Seller
- Stage
- Probability
- Potential value
- Currency
- Close date

These are examples only. They do not establish the real schema or final mapping.

Each canonical concept declares:

- data type;
- whether it is required for this profile;
- whether it is Opportunity-level or repeating-row data;
- allowed transformation identifiers;
- validation behavior;
- imported/local ownership behavior.

### Mapping profile

A profile maps:

```text
Source header → Canonical concept
```

It may also reference named transformations, for example:

- trim text;
- normalize a controlled value;
- parse a number;
- parse a date;
- map a source stage to a current Opportunity status;
- resolve a stable customer key;
- resolve a seller identity.

The architecture allows these transformations, but none are configured until the
real CRM file is reviewed.

### Business-rule configuration

Rules that depend on the source export belong to the versioned profile or an
approved source policy, including:

- required concepts;
- source-stage mapping;
- customer-key mapping;
- seller mapping;
- blank-value behavior;
- whether a source value may update an existing local field;
- group consistency rules;
- product-row interpretation.

Universal product rules remain outside the profile:

- match only by Origin + External ID;
- never recreate an existing Opportunity;
- never change an Opportunity's Origin;
- never create an Opportunity without a resolved existing customer;
- preserve all child records;
- never overwrite a Request Discount-approved commercial amount;
- never infer identity from customer or opportunity name.

### Preview contract

The mapping layer must produce a source-neutral preview model:

```text
Opportunity group
├── external identity
├── resolved customer
├── customer-resolution status
├── mapped Opportunity facts
├── source row numbers
├── proposed action
├── field-level changes
├── protected-field conflicts
└── warnings/errors
```

The UI and confirmation workflow consume this contract. Changing the CRM mapping
does not require redesigning either.

---

## 6. Existing screens affected

| Screen | Proposed sprint effect |
|---|---|
| Main navigation | Rename Proyectos to Pipeline. Destination remains the shared portfolio. |
| Projects portfolio | Rename to Pipeline de oportunidades; rename Proyecto column; add the UI filter and column **Creada desde**, backed by immutable Origin. |
| New Project | Rename user-facing Project terminology to Opportunity; records created here receive Origin = Manual. No field expansion proposed. |
| Edit Project | Rename user-facing terminology only. Existing editing behavior remains. Origin is not an editable business field. |
| Opportunity detail | **No layout, tab, card, action, or field change.** |
| Customer opportunity links | Continue opening the same Opportunity detail; user-facing Project terminology may be normalized to Opportunity. |
| Initiative opportunity links | Continue referencing the same internal Opportunity records. |
| Visit-to-opportunity flow | Preserve current flow; created Opportunity receives Origin = Visit. |
| ERP Import Center | Add the proposed CRM Opportunities import entry and workflow when implementation is approved. |
| Import preview | Add mapping-profile, Opportunity-grouping, customer-resolution, change, and conflict views for this import type. Existing import types remain unchanged. |
| Import history/detail | Recognize CRM Opportunity executions and their Opportunity-level counts. |
| RFQ experience | No current workflow change. Future conversion can create Origin = RFQ. |
| Quote experience | No current workflow change. Future qualifying quote behavior can create Origin = Quote. |
| Ask | No screen change. It continues reading the unified Opportunity context. |

Existing URLs and internal IDs should remain stable unless a separate migration is
explicitly approved.

---

## 7. Compatibility analysis

### Opportunity Origin preserved

Confirmed. Every Opportunity has one immutable Origin assigned at creation.
Later evidence and synchronization cannot change it or create a parallel
Opportunity type.

### Customer integrity preserved

Confirmed. CRM preview uses Needs Review for unresolved customers, allows
explicit resolution to an existing customer, and blocks Opportunity writes until
resolution succeeds. Orphan Opportunities are not permitted.

### Opportunity detail page preserved

Confirmed. Immutable Origin metadata is added to the existing Opportunity record and does
not require a different detail view. No detail-page redesign, reorganization, or
new section is proposed.

### Request Discount preserved

Confirmed. Approval requests continue to reference the same internal Opportunity
ID. Approved commercial amount remains Command Center-authoritative and protected
from CRM updates.

### Timeline preserved

Confirmed. Activities, visits, quotes, approvals, and files remain attached to
the same Opportunity. Import updates do not replace the parent record.

### Quotes preserved

Confirmed. Existing quotes and revisions remain child records. Imported CRM
potential value is not substituted for quote value or approved value without a
future explicit mapping decision.

### Activities preserved

Confirmed. Manual and system activities remain untouched during imported updates.
The current quick-entry workflow and history remain unchanged.

### Follow-ups preserved

Confirmed. Pending, completed, and rescheduled follow-ups remain attached and
continue driving Workspace, health, and next-action behavior.

### Files preserved

Confirmed. Uploads retain their parent Opportunity ID and timeline presence.

### Commercial approvals preserved

Confirmed. Requests, decisions, history, attachments, named-approver rule,
calculation, and amount update remain unchanged.

### Visits preserved

Confirmed. Existing visit links remain intact. Visit-origin Opportunities use the
same workspace with Origin = Visit.

### Initiative relationship preserved

Confirmed. Import synchronization does not clear or replace current initiative
membership unless a future, explicitly approved mapping owns that field.

### Closure history preserved

Confirmed. Won, Lost, and Cancelled fields, closure activity, close timestamp, and
read-only behavior remain. Lifecycle conflicts from CRM are previewed rather than
silently applied until a specific policy is approved.

### Existing business rules preserved

Confirmed:

- value precedence remains approved amount, then primary quote;
- portfolio and detail health calculations remain unchanged;
- next-action rules remain unchanged;
- open-stage behavior remains unchanged;
- structured closure remains unchanged;
- closed opportunities remain read-only;
- visibility and seller behavior remain unchanged.

---

## 8. Deferred decisions requiring the real CRM export

The following are intentionally not decided in this proposal:

- CRM sheet name;
- header names;
- required source columns;
- customer identifier supplied by CRM;
- seller identifier supplied by CRM;
- stage values and their mapping;
- probability format;
- value and currency format;
- close-date format;
- product-row columns;
- treatment of missing or blank values;
- exact fields owned by CRM after local edits;
- closed-status synchronization policy;
- storage/use of imported potential value;
- whether imported source rows later create additional product associations.

None of these should be hardcoded before the real file is reviewed.

---

## 9. Review gate

No implementation should begin until this proposal is reviewed and the following
are approved:

1. Add immutable Origin, external identity, and immutable Origin Reference to the
   existing Opportunity record.
2. Preserve current physical IDs and child relationships.
3. Use immutable Origin + External ID as the only import match key.
4. Rename the portfolio to Pipeline with only immutable Origin added, presented
   in the UI as **Creada desde**.
5. Keep the Opportunity detail page unchanged.
6. Protect the Request Discount-approved commercial amount.
7. Use versioned configurable mapping profiles.
8. Require resolution to an existing customer before Opportunity creation or
   update.
9. Support a future company-configurable Quote-origin threshold with a default
   of COP 5,000,000.
10. Defer all CRM-specific mappings until the real export is available.

After approval, implementation can be divided into:

- Opportunity Origin/data-model preparation;
- minimal Pipeline terminology, filter, and column changes;
- visit-Origin backfill;
- CRM import entry and mapping/grouping framework;
- tests confirming every preservation constraint.

The CRM importer itself remains outside this sprint.
