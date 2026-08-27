# Opportunity / Project Experience — Current Product and UX Assessment

**Assessment date:** July 30, 2026  
**Scope:** Existing Commercial Command Center behavior only  
**Product direction assumed:** Preserve the current Opportunity detail experience; merge manual Projects and CRM-imported Opportunities into the same object and portfolio.

## Product terminology

“Project” and “Opportunity” currently describe the same core commercial object.

- Main navigation and portfolio title: **Proyectos**
- Detail-page language and business rules: predominantly **Oportunidad**
- Customer and initiative views: predominantly **Oportunidades**

This assessment uses **Opportunity** for the business object and **Project** when quoting the current interface.

---

## 1. Opportunity list / portfolio page

### Current layout

The page is a single portfolio table titled **Proyectos**.

The page contains, in order:

1. Page title and **Nuevo proyecto** action.
2. One filter card.
3. One results table.
4. An empty state when no records match.

There are **no portfolio summary cards or KPIs** on this page today.

### Filters

The filter card supports:

- **Estado:** all lifecycle states, including cancelled.
- **Vendedor:** values already present on opportunities.
- **Salud:** Activa, En riesgo, Esperando cliente, Requiere seguimiento, Ganada, Perdida, or Cancelada.
- **Cliente:** free-text, case-insensitive customer-name search.

Status, seller, and health selectors submit immediately when changed. Customer search is submitted through the form. Active filters remain selected in the page URL and a **Limpiar filtros** action appears when any filter is active.

Filters can be combined.

### Sorting

There is no user-controlled sorting.

The fixed ordering is:

1. Most recently updated opportunity.
2. Most recently created opportunity when update timestamps are equal.

### Columns shown

| Column | Current presentation |
|---|---|
| **Cliente** | Customer name in bold. |
| **Proyecto** | Linked opportunity name. |
| **Valor comercial** | Approved commercial amount when present; otherwise the primary quote amount; otherwise “Sin cotización.” |
| **Valor en COP** | Primary quote’s normalized COP value. For USD quotes, the exchange-rate type is also shown. |
| **Estado** | Spanish lifecycle label in a blue badge. |
| **Salud** | Derived health label in a colored badge. |
| **Bloqueo actual** | Current blocker text or “Sin bloqueo actual.” |
| **Actualizado** | Last update timestamp. |

### Information not shown in the table

- Seller/owner is filterable but is **not a visible column**.
- Created date, close date, expected-close date, and next follow-up date are not shown.
- Next-action recommendations are not shown.
- Objective, proposed solution, probability, source, initiative, site, brands, RFQ count, file count, and approval count are not shown.
- There is no card-view alternative.

### Available actions

- **Nuevo proyecto**
- Open an opportunity by selecting its project name.
- Apply or clear filters.

There are no inline edit, close, delete, approval, or follow-up actions in the portfolio.

### Health on the portfolio

Portfolio health is calculated in this order:

1. Closed state wins: won, lost, or cancelled.
2. Any overdue pending follow-up produces **Seguimiento vencido / En riesgo**.
3. `waiting_customer` produces **Esperando cliente**.
4. Activity within seven days produces **Activo**.
5. No activity for 21 days or more produces **Sin actividad reciente / En riesgo**.
6. Everything else produces **Requiere seguimiento**.

No activity at all falls into **Requiere seguimiento**, unless another earlier rule applies.

### Value on the portfolio

The first priority is the opportunity’s canonical approved commercial amount. If it exists, it is labeled **Monto comercial aprobado**.

If no approved commercial amount exists, the page uses the opportunity’s primary quote: the earliest quote by revision and then by record order. If no quote exists, the value is **Sin cotización**.

The separate **Valor en COP** column is quote-based even when an approved commercial amount is displayed in **Valor comercial**.

---

## 2. Opportunity detail page

### Overall page structure

The current detail page is a vertical opportunity workspace:

1. Closed/read-only notice when applicable.
2. Identity header and primary actions.
3. Commercial summary metric cards.
4. Commercial-value workflow.
5. Stage tracker.
6. Objective card.
7. Collapsible quotes table.
8. Two workspace tabs: **Timeline** and **Archivos**.
9. Within Timeline: commercial history on the left and execution tools on the right.
10. Commercial-decision closure modal.

### Header

The header shows:

- breadcrumb-style text: `Proyectos / [project name]`;
- customer initials avatar;
- customer name as the largest title;
- project/opportunity name as subtitle;
- customer site city and address when available;
- seller when available;
- raw status badge;
- brand badges;
- **Editar proyecto** for open opportunities;
- **Decisión comercial** for open opportunities.

Closed opportunities replace editing actions with a read-only message.

### Commercial summary

The **Resumen comercial** section shows six cards, plus probability when available:

- **Estado actual**
- **Salud**
- **Bloqueo actual**
- **Responsable**
- **Valor comercial**
- **Última actividad**
- **Probabilidad**, only when the latest commercial approval contains one

The blocker can be edited inline through **Actualizar bloqueo** while the opportunity is open.

### Commercial-value workflow

The **Gestión del valor comercial** strip groups:

- **Ver cotizaciones**, when quotes exist;
- **Ver solicitudes**;
- **Solicitar descuento**, while the opportunity is open.

If the latest approval has an approved total, the strip shows the latest approved amount. Otherwise it explains that the area covers quotes, discount requests, and approvals.

### Stage tracker

The visible ordered stages are:

1. Prospecto
2. Cotización
3. Esperando cliente
4. Negociación
5. Ganada
6. Perdida

Only the four open stages are directly selectable in the tracker. Won, lost, and cancelled are reached through the commercial-decision closure workflow, not by clicking the stage track.

The user can move directly among any of the open stages; the experience does not enforce strictly forward-only progression. Status changes create system history.

Cancelled is a valid status but is not a stage displayed in the track.

### Objective

A full-width card presents the opportunity objective under:

> ¿Qué problema estamos resolviendo?

The proposed solution is editable in the project edit workflow but is not shown as a separate detail-page card.

### Tabs

There are exactly two workspace tabs:

- **Timeline**
- **Archivos**

Timeline is selected by default.

Quotes are not a tab. They are revealed or hidden by **Ver cotizaciones**.

### Timeline

The timeline combines five sources:

- manually entered and system activities;
- imported commercial visits linked to the opportunity;
- quotes;
- commercial approval events;
- uploaded files.

Events are newest first. Each entry shows an icon, title, description, source badge, date, and user and links to its underlying record or action.

Timeline filters are:

- **Comercial** — default;
- **Sistema**;
- **Todo**.

Approval and visit events are deduplicated when both a general activity record and a specialized event represent the same action.

### Activities

The right-side **Ejecución** card allows quick activity entry for:

- Llamada
- Visita
- Reunión
- Correo
- Nota

The user enters a required short description called **Gestión realizada**.

This quick-entry activity is opportunity-centered and simpler than the full customer Activity form. It creates timeline evidence.

The same form can optionally schedule a follow-up with a required date and description.

### Follow-ups

Pending follow-ups appear below activity entry with:

- description;
- due date;
- pending badge;
- **Completar**;
- **Reprogramar** with a replacement date.

Completing or rescheduling a follow-up creates opportunity history. Closed opportunities preserve follow-ups but remove all completion and rescheduling actions.

### Derived next actions

The **Próximas acciones** card appears below execution. Recommendations are deterministic and link directly to the relevant part of the existing experience.

For open opportunities, it can recommend:

- **Programar seguimiento** when status is Esperando cliente and no pending follow-up exists.
- **Revisar aprobaciones pendientes** when a decision is pending.
- **Resolver bloqueo comercial** whenever a blocker is present.
- **Contactar al cliente** when the most recent commercial timeline event is more than 15 days old. In the current timeline, a manual activity, visit, or quote can be that event.
- **Crear cotización** when the stage is Cotización or later and there are no quotes.
- **Completar proceso de valor comercial** when no approved commercial amount exists.

Actions are deduplicated and ordered Critical, High, Medium, then Low. Closed opportunities have no recommended next actions.

### Quotes

When quotes exist, **Ver cotizaciones** reveals a table showing:

- quote number and revision;
- original currency amount;
- normalized COP amount;
- exchange rate;
- estimated/final exchange-rate type;
- quote date;
- quote status;
- edit action while the opportunity is open.

COP values normalize directly. USD values require a positive exchange rate and an estimated or final rate type.

The general project edit workflow manages the primary quote’s prefix, number, amount, and date. The quote-specific edit flow also manages currency, exchange rate, rate type, and quote status.

### RFQs

RFQs can reference an opportunity, and the RFQ detail page links back to it.

The current Opportunity detail page has:

- no RFQ card;
- no RFQ tab;
- no RFQ list;
- no create-RFQ action.

RFQs are therefore related data in the product but not presently surfaced in this detail experience.

### Files

The **Archivos** tab contains:

- category selector;
- file upload;
- file table;
- original name;
- category;
- upload date;
- download action;
- delete action while open.

Available upload categories are Cotización, Presentación, Técnico, Reunión, Visita, and Otro.

File uploads also appear as timeline events.

### Commercial approvals

The opportunity links to:

- an approval list for this opportunity;
- creation of a discount request;
- individual approval detail and decision history.

The approval list can be filtered by status and displays request number, status, type, requested discount, approved discount, approved amount, approver, decision date, and detail action. It also has approval summary metrics and pagination.

### Editing workflows

**Editar proyecto** allows changes to:

- project name;
- seller;
- objective;
- proposed solution;
- current blocker;
- primary quote prefix, number, value, and date;
- brands.

Customer and site are explicitly not editable from this screen.

The blocker can also be changed inline from the summary. Stage is changed from the stage tracker. Quote financial details can be edited from the quote table.

Open opportunities can currently also be deleted through the project-management behavior, although deletion is not exposed as a primary action on the detail header.

### Closure workflow

**Decisión comercial** opens a modal with three outcomes:

#### Won

Required:

- final sale amount greater than zero.

Optional:

- customer purchase order;
- order number;
- comments.

The opportunity becomes Won, receives a close timestamp, stores the final sale evidence, clears loss/competitor fields, creates a closure activity, and becomes read-only.

#### Lost

Required:

- primary reason: price, delivery time, inventory, technical specification, customer cancellation, no budget, commercial relationship, or other.

Optional:

- what would have changed the result;
- competitor company;
- competitor type;
- competitor brand;
- comments.

The opportunity becomes Lost, receives a close timestamp, clears won-order fields, creates a detailed closure activity, and becomes read-only.

#### Cancelled

Required:

- free-text cancellation reason.

Optional:

- comments.

The opportunity becomes Cancelled, receives a close timestamp, clears won and competitor fields, creates a closure activity, and becomes read-only.

### Ask integration

Ask can use opportunity data as internal commercial context when conducting customer analysis.

There is currently **no Ask button, Ask card, Ask tab, or opportunity-specific Ask launch action on the Opportunity detail page**. Ask analyses are not displayed in the opportunity timeline.

### Other present functionality

- Opportunities can belong to an Initiative.
- Imported AppSheet visits can be linked to an opportunity and appear in its timeline.
- A visit marked as an opportunity candidate can prefill new-opportunity creation.
- The detail page derives last activity, last visit, last quote, latest movement, next follow-up, open quote count, follow-up count, approval count, and file count. Not every derived value is visibly presented.

---

## 3. Existing business rules

### Opportunity value precedence

The canonical display rule is:

1. **Approved commercial amount on the opportunity**
2. **Primary quote amount**
3. **Sin cotización**

An approved amount is independent from quote value and takes precedence everywhere the canonical commercial value is used.

### Quote effects

- Quotes provide the fallback opportunity value when no approved amount exists.
- The primary quote is the earliest revision, not the most recent revision.
- Quote currency can be COP or USD.
- USD requires an exchange rate and rate type.
- Quote normalization supplies the COP comparison value.
- Changing a quote does not overwrite an already approved commercial amount.

### Approval and discount effects

- Approval calculations use list unit price × quantity after the approved discount.
- The result is rounded to two monetary decimals.
- The discount allows up to four decimals and must be between 0% and 100%.
- Approval requires a valid positive list price and positive quantity.
- On approval, the calculated total and currency overwrite any existing canonical commercial amount.
- A later approved request overwrites that amount again while preserving earlier request decisions and history.
- Rejected, returned, cancelled, or failed approval attempts do not change opportunity value.
- The approval process does not depend on the opportunity quote.

### Health

Two current health presentations use different thresholds.

**Portfolio health:**

- closed state first;
- overdue follow-up;
- waiting customer;
- active within 7 days;
- at risk at 21 or more days;
- otherwise requires follow-up.

Portfolio recency uses opportunity activity records. It does not use quote, file,
approval, or separately imported visit dates for this calculation.

**Detail summary health:**

- no recorded activity or 30+ days: **En riesgo**;
- 15–29 days: **Atención**;
- overdue follow-up: **Atención**;
- otherwise: **Saludable**.

Detail recency uses the most recent manual activity or linked commercial visit.
On the detail page, inactivity is evaluated before overdue follow-ups. Closed
status does not replace the detail health calculation; status and health remain
separate summary cards.

### Next actions

Next actions are derived, read-only recommendations. They do not create work until the user follows the link and performs the action. The rules are the six conditions documented in the detail section above.

### Status and stage behavior

Open states:

- Prospecto
- Cotización
- Esperando cliente
- Negociación

Closed states:

- Ganada
- Perdida
- Cancelada

Users may move among open states from the stage tracker. Closed outcomes require the structured closure workflow. Once closed, the entire opportunity is read-only.

### Ownership and visibility

- `sales_rep` is the opportunity’s commercial owner.
- It is required in the current create and edit forms.
- It is displayed in the detail header and summary and can filter the portfolio.
- The current portfolio is not scoped to only the signed-in seller; all opportunities returned by the portfolio are visible.
- General opportunity editing is not restricted by seller ownership.
- Authenticated actor identity is used in history.
- Commercial approval decisions require the approver role and currently require the named approver **Ricardo Lugo**.

### Existing source fields

The opportunity itself has no general source-system, source label, external CRM ID, or import timestamp.

Source-related behavior that does exist:

- a commercial visit can be linked to the opportunity;
- new-opportunity creation can receive a source visit;
- quotes can retain ERP user/number context;
- customers retain ERP identity;
- approval requests can retain an ERP price snapshot and its retrieval time;
- timeline entries show their source type: Activity, Visit, Quote, Approval, or File.

---

## 4. Existing data model from a product perspective

### Fields on the opportunity today

| Field group | Existing fields |
|---|---|
| Identity | Internal ID, customer, customer site, initiative, name |
| Ownership | Seller |
| Lifecycle | Status, created date, updated date, closed date |
| Commercial definition | Objective, proposed solution, current blocker |
| Governed value | Commercial amount, commercial currency |
| Won outcome | Final won amount, customer PO, order number, comments |
| Lost outcome | Loss reason, what would have changed the result, competitor company/type/brand, comments |
| Cancelled outcome | Cancellation reason and comments, stored in the closure fields |

### Fields that can already receive CRM opportunity data

Subject to mapping and field-ownership rules, the existing object can hold:

- customer relationship, if the CRM customer can resolve to an existing customer;
- opportunity name;
- seller;
- current stage/status;
- objective or description;
- proposed solution;
- current blocker;
- created, updated, and closed timestamps;
- customer site;
- amount and currency;
- closure reason and comments;
- competitor information;
- final won amount;
- customer PO and order number;
- initiative relationship, if separately resolved.

### Fields currently manual or Command Center-owned

- objective and proposed solution entered by the user;
- current blocker;
- local stage changes;
- brands;
- primary and revised quotes;
- commercial activities;
- follow-ups;
- files;
- initiative assignment;
- approval requests, decisions, and approved canonical value;
- structured closure evidence;
- visit links.

### Likely conflict fields during future CRM updates

The current object does not distinguish imported ownership from local ownership. The following fields can be changed locally and could also plausibly arrive from CRM:

- name;
- customer;
- seller;
- stage/status;
- value and currency;
- probability;
- objective/description;
- proposed solution;
- blocker;
- expected or close dates;
- won/lost result and reason;
- competitor;
- created/updated timestamps.

Probability currently lives on the latest commercial approval rather than on the opportunity itself. Expected close date is not currently an opportunity field. A CRM import of either would therefore need a defined product mapping.

The most sensitive conflict is **commercial amount**: Request Discount treats the opportunity amount as a governed, locally approved value. A CRM import must not silently replace it.

### Child records preserved around the opportunity

- activities, including system history and approval events;
- follow-ups;
- quotes and revisions;
- brands;
- files;
- commercial approval requests;
- approval decisions, status history, and attachment records;
- linked commercial visits;
- initiative membership;
- RFQ references from the RFQ side;
- structured closure fields;
- the combined timeline derived from those records.

---

## 5. Request Discount

### Entry point

The workflow starts on an open Opportunity detail page in **Gestión del valor comercial** through **Solicitar descuento**.

The user can also review all prior requests through **Ver solicitudes**.

Closed opportunities cannot start, edit, submit, cancel, decide, or expire requests.

### Request form

Customer, opportunity, office, and seller are displayed as context.

The editable information is:

**Commercial information**

- manufacturer;
- product family;
- product reference;
- quantity;
- competitor;
- opportunity value;
- probability of winning;
- commercial impact.

**Pricing**

- ERP list price;
- requested price;
- requested discount;
- estimated margin;
- expected revenue;
- currency: COP or USD.

**Structured justification**

- reason;
- justification.

Reason choices:

- Competencia
- Cuenta estratégica
- Desarrollo de cuenta
- Oportunidad de volumen
- Acuerdo existente
- Retención de cliente
- Requerimiento técnico
- Excepción comercial
- Otro

**Competition and risk**

- competitor price;
- competition notes;
- business notes.

### Required information and validation

Always required to save:

- valid reason;
- justification;
- currency;
- requested discount, either entered directly or derived from list price and requested price.

Rules:

- requested discount must be 0%–100%;
- maximum four decimal places;
- quantity, when supplied, must be positive;
- list price, when supplied, must be positive.

To approve and calculate a final amount, valid list price and positive quantity are required.

Manufacturer defaults from the first opportunity brand when present. Office defaults from the customer assignment. Opportunity value defaults from the current canonical commercial amount. Competitor can default from closure-related opportunity context. The request snapshots customer and opportunity names, stage, seller, and commercial information.

### Statuses and transitions

Statuses:

- Borrador
- Enviada
- Pendiente de aprobación
- Devuelta
- Aprobada
- Rechazada
- Cancelada
- Vencida

Lifecycle:

```text
Borrador → Enviada → Pendiente de aprobación
    ↓                        ├── Aprobada → Vencida
 Cancelada                  ├── Rechazada
                            ├── Devuelta → Enviada
                            ├── Cancelada
                            └── Vencida
```

Only draft and returned requests can be edited. Submission moves immediately through Enviada to Pendiente de aprobación.

### Decision behavior

The pending-request screen contains a dedicated **Decisión de Ricardo Lugo** panel.

Required:

- decision comments.

For approval:

- approved discount, defaulted to the requested discount;
- optional expiration date.

Available decisions:

- **Aprobar**
- **Devolver**
- **Rechazar**

The decision-maker must have the approver role and must match the named approver Ricardo Lugo.

### Effect on the opportunity

Approval calculates:

1. approved unit price from list price and approved discount;
2. approved total from unit price × quantity;
3. currency from the request.

That total becomes the opportunity’s canonical commercial amount and supersedes both:

- any prior canonical amount;
- quote value for canonical display purposes.

The prior amount is retained in decision/history evidence. Non-approval outcomes do not change the opportunity amount.

The entire decision and amount update behave as one operation: if the opportunity amount cannot be updated, the approval does not partially complete.

### Timeline and evidence

The workflow preserves:

- request number in `AP-000000` format;
- request snapshot;
- every status transition;
- actor;
- comments;
- before/after request edits;
- decision;
- requested and approved discounts;
- list and approved unit prices;
- quantity;
- approved total and currency;
- previous and replacement opportunity amounts;
- optional expiration;
- decision date.

The opportunity timeline receives distinct events for:

- request created;
- submitted;
- approved;
- returned;
- rejected;
- cancelled.

The approval event links to the approval detail. Specialized approval events take precedence over duplicate generic activity events in the combined timeline.

---

## 6. Screens and screenshots

### Rendered views requested

- Opportunity portfolio
- Opportunity detail
- Request Discount flow

No controllable browser was available in this assessment session, so screenshots could not be captured responsibly. No synthetic or reconstructed screenshots have been substituted.

The current rendered-view landmarks are:

| Screen | Primary visible landmarks |
|---|---|
| Portfolio | Proyectos title, Nuevo proyecto, four filters, eight-column table |
| Detail | Customer/project header, summary cards, value workflow, stage track, objective, Timeline/Archivos tabs, execution and next-action cards |
| Request Discount | General context followed by Commercial Information, Pricing, Structured Justification, and Competition/Risk cards |

---

## 7. Do Not Regress

If manual Projects and imported CRM Opportunities are merged, preserve all of the following:

- One shared Opportunity detail experience regardless of source.
- Existing customer-root relationship and customer/site context.
- Existing opportunity URL continuity and internal identity.
- Project/opportunity name, seller, objective, proposed solution, blocker, brands, and initiative membership.
- Current open and closed lifecycle states.
- Direct movement among open stages.
- Structured Won, Lost, and Cancelled closure flows.
- Closure timestamps, reasons, competitor evidence, final value, PO, order number, comments, and closure activity.
- Full read-only behavior after closure.
- Portfolio filters for status, seller, health, and customer.
- Fixed default recency ordering until intentionally changed in a later product decision.
- Portfolio value precedence: approved amount, then primary quote, then no quote.
- Quote amount and normalized-COP display.
- Current portfolio health behavior.
- Current detail health behavior, including its separate thresholds.
- Commercial summary cards and optional probability card.
- Inline blocker update.
- Commercial-value workflow and latest-approval display.
- **Solicitar descuento** entry point.
- Approval list, filtering, metrics, pagination, and detail views.
- Full Request Discount form and structured reason choices.
- Draft, submitted, pending, returned, approved, rejected, cancelled, and expired states.
- Draft/returned editing and resubmission.
- Named/role-based approval protection.
- Server-calculated approved price and total.
- Approved amount overwriting canonical opportunity value.
- Rejection, return, and cancellation leaving opportunity value unchanged.
- Preservation of earlier approval decisions when a later approval changes value.
- Approval history, comments, price snapshot, amount-before/after evidence, and timeline events.
- Timeline sources for activities, visits, quotes, approvals, and files.
- Timeline ordering, source badges, links, deduplication, and Commercial/System/All filters.
- Quick activity entry for calls, visits, meetings, emails, and notes.
- Activity plus optional follow-up creation in one interaction.
- Pending follow-up display, completion, and rescheduling.
- Follow-up history and Workspace attention behavior.
- Deterministic next-action recommendations and deep links.
- Quote list, revisions, currencies, exchange rates, normalized value, statuses, and editing.
- File categories, upload, download, delete, and timeline evidence.
- Linked AppSheet visit history and visit-to-opportunity creation/linkage.
- RFQ-to-opportunity relationship, even though RFQs are not currently displayed on the detail page.
- Ask’s ability to read opportunity context without making Ask a separate opportunity experience.
- Existing child records remaining attached through imports and updates.
- All open opportunities remaining writable and all closed opportunities remaining read-only.

---

## 8. Integration implications

These are the smallest compatibility changes implied by the intended merge. They do not require a different Opportunity detail page.

### Import CRM opportunities from Excel

The existing Opportunity object needs import metadata sufficient to identify the external record:

- source system;
- stable external CRM opportunity ID;
- last imported timestamp or import reference.

The import must resolve the CRM customer to the existing Command Center customer before creating the opportunity. It then maps compatible CRM values into the existing opportunity fields and creates the same object used by manual Projects.

### Update existing opportunities on future imports

Future files must match on the stable pair of source system and external opportunity ID, not on name, customer, or seller.

The import operation must update the existing opportunity in place. It must not replace the opportunity record, because replacement would orphan or discard its activities, follow-ups, quotes, files, visits, approvals, initiative membership, RFQ references, timeline, and closure evidence.

### Distinguish manual and imported opportunities

Source should be stored as metadata on the same object:

- manual records have a manual/local source;
- imported records have CRM source plus external ID.

Source does not imply a different detail page, lifecycle, or child-record model.

### Show both in the same portfolio

The current portfolio already reads one opportunity collection. Once imported records are created in that same collection and have valid customer, status, and seller mappings, both sources can use:

- the same table;
- the same filters;
- the same health calculation;
- the same value presentation;
- the same detail link.

No separate imported-opportunity portfolio is required to satisfy the stated direction.

### Preserve the current detail experience unchanged

Imported opportunities must be loaded through the existing Opportunity workspace contract. The detail experience expects:

- one valid customer;
- a recognized lifecycle status;
- opportunity name and objective;
- seller/site when available;
- all existing child collections, even when empty;
- existing derived dashboard, health, timeline, and next-action behavior.

CRM-only data that has no current visible destination can remain import metadata; it does not need a new detail-page surface for the initial merge.

### Keep Request Discount operational

The import must treat the canonical approved commercial amount as Command Center-governed data.

Minimum preservation rule:

- CRM amount may populate an imported/source amount or an initially empty opportunity amount according to the agreed mapping;
- once Request Discount has produced an approved canonical amount, later CRM imports must not silently overwrite it;
- approval records must continue to reference the same stable internal opportunity;
- customer, opportunity name, stage, and seller snapshots must remain valid at request creation;
- imported closed status must respect the existing read-only rule and must not strand an in-flight approval without an explicit import policy.

The core integration boundary is therefore:

> CRM controls imported source facts; Command Center preserves local execution records and the approved commercial amount.

This allows manual and imported opportunities to share one pipeline and the existing detail page without turning source into a separate product experience.
