# Commercial Command Center — Product Architecture Summary

**Audience:** Product Managers onboarding to the project  
**Scope:** Product behavior present in the current repository as of July 30, 2026  
**Reading time:** Approximately 12–15 minutes

## Executive summary

Commercial Command Center is the commercial operating workspace for Lugo Hermanos. It brings together the work that happens around a customer—opportunities, activities, follow-ups, RFQs, quotes, agreements, visits, approvals, supporting files, purchase history, and analysis—without trying to replace the ERP or Google Workspace.

The product is organized around a simple operating model:

1. The **customer** is the root commercial context.
2. A meaningful sales pursuit becomes a **project**, which is the product’s current name for an opportunity.
3. **Activities, visits, RFQs, quotes, approvals, files, and follow-ups** provide the evidence and actions that move commercial work forward.
4. **Workspace** surfaces what needs attention now.
5. **Ask** analyzes available customer data and uploaded evidence to help a user make a decision, but its outputs do not replace source records.

The primary user is a salesperson managing a portfolio and active opportunities. Commercial managers also have meaningful review and approval use cases. Administrative users maintain data through imports and integration monitoring.

---

## 1. Product purpose

### What is Commercial Command Center?

Commercial Command Center is a commercial operating system: a place to execute and review commercial work, not merely a customer directory and not merely a dashboard.

It gives commercial users a shared view of:

- what requires attention;
- what should happen next;
- what has happened with a customer or opportunity;
- what evidence supports the current commercial position;
- what is at risk, blocked, overdue, or awaiting a decision.

### What business problem does it solve?

Commercial work is otherwise distributed across the ERP, spreadsheets, email, Google tools, uploaded documents, individual notes, and people’s memory. The product assembles that fragmented context around customers and active commercial pursuits.

It specifically reduces the risk that:

- follow-ups are forgotten;
- an opportunity has no clear next action;
- customer history is reviewed without its sales context;
- an RFQ remains open without an outcome;
- commercial decisions are made without evidence;
- account activity, agreements, and opportunity work are reviewed in isolation.

### Who is the primary user?

The primary user is a **sales representative** responsible for customers and commercial opportunities. The product also supports:

- **commercial managers**, who review portfolio health, opportunity progress, commercial approval requests, agreements, and account risk;
- **administrators**, who operate imports, integrations, access, and data-quality workflows.

### How should it be used during a normal workday?

A normal day begins in **Workspace**, where the user reviews overdue, due-today, and upcoming follow-ups. The user then opens the relevant opportunity or customer, completes or reschedules work, records activities, reviews quotes or RFQs, uploads evidence, and updates the current status or blocker.

During the day, the user may:

- inspect a customer before a call or visit;
- register a commercial activity;
- turn an imported visit into an opportunity candidate;
- create or advance an RFQ;
- work an opportunity and its next actions;
- request commercial approval for pricing or conditions;
- review an account agreement against purchase history;
- use Ask to analyze a decision, customer, or set of documents.

The intended rhythm is execution first: use the system to decide and record what happens next, then use its summaries and analysis to support judgment.

---

## 2. Modules

### 2.1 Workspace

**Purpose:** The daily execution center.

**Primary business object:** Follow-up, viewed in the context of an opportunity and customer.

**Current functionality:** Shows overdue follow-ups, items due today, and items due in the next seven days. Each item links back to its opportunity. It also provides a direct path to the project portfolio.

**Current limitations:** It is primarily a follow-up queue, not yet a complete cross-module attention center. RFQ deadlines, approvals, agreement risks, and imported-visit exceptions do not appear as one unified daily queue.

**Planned direction visible in the product:** The surrounding product principles position Workspace/Home as the central place for all incomplete, stale, overdue, or at-risk commercial work.

### 2.2 Customers

**Purpose:** Provide the root account context for commercial work.

**Primary business object:** Customer.

**Current functionality:** Searchable and filterable customer portfolio; customer detail; customer classification and assignment context; purchase and activity indicators; linked opportunities, activities, RFQs, contacts, and agreements. Strategic-account views add revenue, product-family mix, agreement performance, recent activity, and opportunity pipeline.

**Current limitations:** Customer experiences are split between a general customer profile and a richer strategic-account workspace. Several strategic-account tabs and cards are visibly marked as unavailable or future-phase features, including AI insights and parts of account planning.

**Planned direction visible in the product:** A progressively richer account workspace combining commercial profile, performance, agreement use, interaction history, opportunities, and intelligence.

### 2.3 Projects / Opportunities

**Purpose:** Manage a bounded commercial pursuit from identification to conclusion.

**Primary business object:** Opportunity, labeled “Proyecto” in the main navigation.

**Current functionality:** Create and edit an opportunity; connect it to a customer; assign owner, objective, proposed solution, brands, value, status, expected date, probability, site, source, and current blocker; manage quotes, activities, follow-ups, files, approvals, and a combined timeline; filter the portfolio by status, seller, health, and customer; show health and next-action guidance; close as won, lost, or cancelled with structured closure information.

**Current limitations:** Product terminology is inconsistent: lists and navigation say “Proyectos,” while many detailed views and rules say “Oportunidades.” Some value comes from quotes, while approved commercial values can supersede it, making the displayed value dependent on the opportunity’s current evidence. The opportunity does not yet absorb every related object automatically.

**Planned direction visible in the product:** A more complete opportunity operating workspace with stronger next-action guidance, timeline coverage, evidence, value controls, and portfolio management.

### 2.4 Activities

**Purpose:** Record commercial work and preserve customer-facing evidence.

**Primary business object:** Activity.

**Current functionality:** Register calls, visits, meetings, emails, and notes against a customer, optionally linking an opportunity, RFQ, or agreement. Activities capture participants, contact, purpose, summary, needs, risks, competition, products, business lines, results, evidence, and an optional follow-up. Contacts can be created during activity entry.

**Current limitations:** The main navigation opens the customer portfolio rather than a dedicated cross-customer activity feed. Current activity entry and imported AppSheet visits are related but remain distinct user experiences.

**Planned direction visible in the product:** Activities are intended to become the primary commercial evidence stream feeding customer history, opportunities, RFQs, follow-ups, management review, reporting, and Ask.

### 2.5 Commercial visits

**Purpose:** Bring field-visit records from the existing Google AppSheet/Sheets process into customer and opportunity work.

**Primary business object:** Commercial Visit.

**Current functionality:** Manual synchronization from the configured source; customer matching; duplicate and quality checks; visit detail; customer activity display; identification of visits that may represent opportunities; prefilled creation of an opportunity from a candidate visit; visibility of follow-up commitments and attachment status.

**Current limitations:** Synchronization depends on external configuration and credentials. Some visits may remain unmatched, ambiguously matched, duplicated, or have unresolved attachments. Imported visits are not the same record type as manually entered activities.

**Planned direction visible in the product:** Better reconciliation of visits with customers, activities, attachments, follow-ups, and opportunity creation while preserving the existing field-capture tool.

### 2.6 RFQs

**Purpose:** Manage customer requests for quotation as independent commercial processes.

**Primary business object:** RFQ.

**Current functionality:** Create an RFQ for a customer and contact; capture requested items, dates, value, owner, description, and next action; advance it through a defined workflow; conclude it as won, lost, cancelled, or continued as an opportunity; retain status history, documents, and conclusion details. It can be linked to an opportunity but does not create one automatically. Gmail-based sending and message synchronization are present when configured.

**Current limitations:** Email actions depend on Google authorization. RFQ and project quotes are separate concepts: an RFQ is a customer request, while a quote is the commercial proposal within an opportunity. The connection between the two is deliberate rather than automatic.

**Planned direction visible in the product:** Deeper email continuity, evidence preservation, and deliberate conversion from request to opportunity where warranted.

### 2.7 Quotes

**Purpose:** Represent commercial proposals and their revisions within an opportunity.

**Primary business object:** Quote.

**Current functionality:** Associate multiple quotes with an opportunity; track ERP quote number, revision, date, currency, exchange rate, amount, normalized COP value, status, brand, contact, validity, and notes; edit quote details and exchange-rate information; use current quote information in opportunity value displays.

**Current limitations:** Quotes are opportunity-level records rather than a standalone top-level module. Quote item detail, margin analysis, full revision automation, and ERP-driven quote ingestion are not complete user workflows.

**Planned direction visible in the product:** Richer revision history, item-level detail, ERP quote import, margin analysis, and stronger document linkage.

### 2.8 Follow-ups / Next actions

**Purpose:** Turn commercial intent into dated, owned future work.

**Primary business object:** Follow-up.

**Current functionality:** Create a follow-up within an opportunity; assign a responsible person and due date; display overdue, due-today, and upcoming work in Workspace; complete or reschedule it; preserve its history in the opportunity story.

**Current limitations:** Current opportunity follow-ups use a relatively simple pending/completed model. Broader follow-up behavior described elsewhere—such as recurring actions, notifications, and universal links to all commercial objects—is not fully surfaced.

**Planned direction visible in the product:** A cross-product next-action system with reminders, broader object coverage, and suggested actions.

### 2.9 Initiatives

**Purpose:** Group multiple opportunities under a strategic commercial program.

**Primary business object:** Initiative.

**Current functionality:** Create and edit an initiative with objective, owner, partner, status, dates, and financial context; link and remove opportunities; summarize opportunity count and pipeline; register initiative events, learnings, and decisions.

**Current limitations:** Initiatives are not yet deeply integrated into Workspace attention, customer views, or Ask. Their value is mainly as a portfolio grouping and structured learning record.

**Planned direction visible in the product:** A management layer above individual opportunities for partner programs, strategic themes, shared learning, and aggregated pipeline.

### 2.10 Agreements

**Purpose:** Manage long-term customer commercial agreements separately from opportunities.

**Primary business object:** Agreement.

**Current functionality:** Create, edit, list, and retire customer agreements; attach agreement documents; import agreement workbooks through preview and confirmation; preserve a replaced active agreement as expired; manage negotiated items; compare agreement products with sales history; show revenue coverage, never-purchased items, share of account, and product-matching quality.

**Current limitations:** Agreement functionality is concentrated in customer and strategic-account views rather than a top-level portfolio. Some fields anticipated by the product concept—such as milestones, renewal workflows, risks, savings, and support-value tracking—are not complete operating workflows.

**Planned direction visible in the product:** Ongoing agreement monitoring, renewal attention, richer risk and value tracking, and closer connection to account management.

### 2.11 Commercial approvals

**Purpose:** Control exceptions or special commercial conditions within an opportunity.

**Primary business object:** Commercial Approval Request.

**Current functionality:** Create and edit a draft request; capture product, competitor, opportunity value, probability, requested pricing or discount, margin, expected revenue, structured reason, justification, and risk context; submit for approval; approve or reject with approved commercial values; cancel; retain decisions and history; reflect approved values in opportunity displays and timelines.

**Current limitations:** Approval routing is a contained opportunity workflow rather than a configurable multi-level approval organization. It is not a top-level manager inbox.

**Planned direction visible in the product:** Stronger governance of opportunity value and commercial exceptions, with decisions remaining part of the opportunity evidence trail.

### 2.12 Ask

**Purpose:** Act as an evidence-based commercial analyst for a concrete decision.

**Primary business object:** Ask Analysis.

**Current functionality:** Start a conversational analysis with an objective and optional customer; attach spreadsheets, documents, PDFs, text, and images; inspect and summarize evidence; use customer and internal commercial context; continue the conversation; generate structured deliverables; review analysis history and versions; reanalyze; export tabular artifacts; mark work reviewed or exported.

**Current limitations:** Ask depends on configured AI access. Its quality is constrained by available source data, file readability, customer matching, and the user’s question. It does not write conclusions back as authoritative activities, opportunity changes, or ERP facts. Some future account “AI insights” surfaces are visibly placeholders rather than active Ask outputs.

**Planned direction visible in the product:** More analysis types, richer evidence use, reusable deliverables, and deeper grounding in the connected commercial record.

### 2.13 Integrations and imports

**Purpose:** Bring authoritative or externally captured information into the product and show its operational health.

**Primary business objects:** Import Execution and Visit Synchronization Run.

**Current functionality:** Integration Center shows ERP and Google visit-source status. ERP imports support separate customer and sales files, validation, preview, confirmation, warnings, errors, row results, retained source files, and execution history. Visit integration supports manual synchronization and data-quality review.

**Current limitations:** ERP synchronization is file-driven and manual, not continuous. Google visit synchronization requires configuration. The center currently covers ERP data and commercial visits; other Google capabilities are used in targeted flows rather than shown as full integration cards.

**Planned direction visible in the product:** Additional managed integrations while retaining visible status, history, and data-quality controls.

### 2.14 Purchase History / Analytics

**Purpose:** Show what a customer has actually purchased.

**Primary business object:** Sales Transaction, presented as aggregated purchase history.

**Current functionality:** Summarizes part number, brand, quantity, order count, sales value, and last purchase for a customer/product context. Imported sales also feed customer portfolio indicators, strategic-account revenue, product-family mix, agreement analysis, and Ask context.

**Current limitations:** The top-level Purchase History page is a narrow, hardcoded presentation for a specific customer/category/time window rather than a general interactive analytics module. “Analytics” itself appears as a disabled navigation heading, not a complete module.

**Planned direction visible in the product:** Broader customer, product, brand, agreement, growth, pipeline, and conversion analytics based on imported ERP history.

### 2.15 Authentication and access

**Purpose:** Identify the user and control access to commercial information.

**Primary business object:** User.

**Current functionality:** Google sign-in, user identity, active status, role, and development access support. User context is used for ownership, visibility, authorship, and approval actions.

**Current limitations:** The product surfaces limited user-administration and permission-management functionality in the main navigation.

**Planned direction visible in the product:** Role-aware execution and management experiences using the existing user and ownership model.

---

## 3. Business objects

The following objects exist in the current product. Supporting records are included where they carry distinct business meaning; purely presentational calculations are not treated as objects.

| Business object | Purpose and relationships | Lifecycle, creation, and use |
|---|---|---|
| **User / Advisor** | Person who owns or participates in commercial work. Related to customers, activities, opportunities, RFQs, follow-ups, Ask analyses, and approvals. | Enters through authenticated access; remains as historical ownership and authorship context. |
| **Customer** | Root account record. Connects ERP identity and sales history with contacts, activities, visits, opportunities, RFQs, agreements, and Ask. | Created or refreshed through customer imports; enriched and reviewed in Customers and account workspaces. |
| **Customer commercial profile** | Internal portfolio metadata such as assignment, classification, status, and notes layered on the ERP customer. | Maintained in the customer experience and used for portfolio filtering and prioritization without replacing ERP identity. |
| **Contact** | Person at a customer involved in commercial work. Can be linked to activities, RFQs, quotes, and opportunities. | Created during activity entry or customer work; reused as relationship context. |
| **Opportunity / Project** | A commercial pursuit with a beginning and a conclusion. Belongs to a customer and may connect to an initiative, RFQ, quotes, activities, visits, follow-ups, approvals, brands, and files. | Created manually or prefilled from an opportunity-candidate visit; progresses through active statuses; ends won, lost, or cancelled with a recorded reason and outcome. |
| **Activity** | A manually recorded commercial interaction and evidence source. Belongs to a customer and may relate to an opportunity, RFQ, agreement, contact, participants, results, evidence, and a follow-up. | Created from customer activity entry; used in histories, context, and future action. |
| **Commercial Visit** | Field interaction imported from AppSheet/Sheets. Related to a matched customer, advisor, contact details, follow-up commitment, attachment reference, and possible opportunity. | Imported through manual synchronization; matched and quality-checked; reviewed in the account; may seed a new opportunity. |
| **Follow-up** | Dated, owned next action, currently centered on an opportunity. | Created during opportunity work or activity capture; remains pending until completed or rescheduled; drives Workspace attention. |
| **RFQ** | Independent customer request for quotation. Related to customer, contact, owner, items, documents, email conversation, status history, conclusion, and optionally an opportunity. | Created manually; advanced through request-handling stages; concluded as won, lost, cancelled, or continued as an opportunity. |
| **RFQ item** | Requested product or free-text line within an RFQ. | Created with the RFQ; used to define the customer request. |
| **RFQ conclusion** | Explicit outcome of an RFQ, including reason and final value or continuation. | Created when the RFQ is closed; prevents the request from remaining indefinitely unresolved. |
| **Quote** | Commercial proposal or revision inside an opportunity. Related to value, currency, exchange rate, brand, contact, status, and opportunity. | Added and edited in the opportunity; may have multiple revisions; contributes to displayed opportunity value. |
| **Brand association** | Manufacturer/brand involved in an opportunity or quote. | Added during opportunity work; used to describe commercial scope and proposal context. |
| **Project file** | Evidence or documentation attached to an opportunity, such as quotes, proposals, drawings, photos, videos, catalogs, technical reports, or ROI material. | Uploaded to an opportunity; appears in its files and timeline; may be removed. |
| **Initiative** | Strategic program grouping multiple opportunities. Related to owner, partner, dates, events, learnings, decisions, and aggregate pipeline. | Created and updated separately; opportunities are attached or removed; initiative remains a management and learning container over time. |
| **Initiative event** | Dated occurrence in an initiative’s history. | Recorded from the initiative detail and used to preserve program chronology. |
| **Initiative learning** | Reusable insight learned through the initiative. | Added to the initiative and retained as structured learning. |
| **Initiative decision** | Explicit program-level decision. | Added to the initiative and retained as governance context. |
| **Agreement** | Long-term customer commercial arrangement, intentionally separate from an opportunity. Related to customer, negotiated items, source document, analytics, and status. | Created manually or imported from a workbook; becomes active; replacement preserves the former agreement as expired; can be updated or retired. |
| **Agreement item** | Negotiated product/reference and commercial condition within an agreement. | Created through agreement entry/import; reconciled with sales history for coverage and purchasing analysis. |
| **Agreement document** | Source file supporting an agreement. | Uploaded and retained with the agreement; used for traceability and re-review. |
| **Commercial Approval Request** | Request for approval of pricing, discount, or commercial conditions on an opportunity. Related to opportunity, request details, decisions, history, and attachments. | Created as draft; submitted; approved or rejected; may be revised and resubmitted or cancelled. |
| **Approval decision** | Manager’s outcome and approved values for a request. | Created during decision; becomes evidence and can determine the commercial value displayed on the opportunity. |
| **Ask Analysis** | Versioned commercial investigation centered on a decision, optionally tied to a customer. Related to messages, files, internal context, and artifacts. | Started conversationally; prepared and executed; continued or reanalyzed into a new version; reviewed and exported. |
| **Ask message** | User, analyst, or system turn within an Ask analysis. | Added throughout the conversation and preserved as analysis context. |
| **Ask file** | Evidence uploaded for an analysis, with its inspection and processing outcome. | Uploaded before or during analysis; processed, reviewed, downloaded, or removed while editable. |
| **Ask artifact** | Structured output such as a table or other deliverable generated by Ask. | Generated from an analysis; reviewed in the report and, where supported, exported. |
| **Import execution** | Auditable attempt to load ERP customers or sales. Related to source file, preview, counts, warnings, errors, and issues. | Created when a file is submitted; validated and previewed; confirmed or stopped; retained in import history. |
| **Import issue** | Row- or file-level warning/error arising from an import. | Created during validation or execution; reviewed from import results. |
| **Visit synchronization run** | Auditable attempt to import external commercial visits. | Created by manual sync; ends with counts and status; informs integration health. |
| **Visit/customer match** | Resolution between an external visit’s customer identity and a Command Center customer. | Generated during visit processing; can be matched, ambiguous, or unresolved and drives data-quality review. |
| **Sales transaction** | ERP-originated purchase fact used for historical and analytical views. | Imported from sales files; treated as source evidence and aggregated rather than manually edited. |
| **Inventory snapshot** | Imported point-in-time inventory fact available to analytical workflows. | Loaded from external data and used as supporting analysis context; it does not currently have a primary user-facing module. |

---

## 4. User workflows

### Start the workday

1. Open Workspace.
2. Review overdue, due-today, and next-seven-day follow-ups.
3. Open the related opportunity.
4. Complete, reschedule, or create the next action.
5. Update status, blocker, activity, quote, file, or approval evidence as needed.

### Import ERP data

1. Open Integrations and choose ERP imports.
2. Select either customer synchronization or sales update.
3. Upload the spreadsheet.
4. Review schema validation, preview, warnings, and expected changes.
5. Confirm the import.
6. Review inserted, updated, skipped, duplicate, warning, and error results.
7. Use the refreshed customer and sales information throughout the product.

### Review a customer

1. Search or filter the customer portfolio.
2. Open the customer profile or strategic-account overview.
3. Review commercial classification, ownership, purchase performance, product mix, recent activity, agreement status, and opportunity pipeline as available.
4. Open activities, RFQs, opportunities, or the agreement for detail.
5. Register new work or use Ask for a focused decision.

### Create and work an opportunity

1. Create a project manually, or start from an imported visit marked as an opportunity candidate.
2. Select the customer and record the objective, proposed solution, owner, value context, expected timing, brands, and current blocker.
3. Add activities, follow-ups, quotes, files, and commercial approval requests.
4. Use the timeline and health/next-action indicators to understand progress.
5. Change the opportunity stage as work advances.
6. Close as won, lost, or cancelled with the required conclusion details.

### Register an activity

1. Start from a customer.
2. Select or create the customer contact.
3. Record the interaction type, participants, purpose, summary, needs, risks, competition, products, and results.
4. Link the activity to an opportunity, RFQ, or agreement where relevant.
5. Add evidence and create a follow-up if future work is required.

### Synchronize and review visits

1. Open Integrations and run the visit synchronization.
2. Review totals and data-quality alerts.
3. Resolve operational understanding of unmatched, ambiguous, duplicate, or attachment-warning records.
4. Review visits in the related customer account.
5. For a visit marked as a candidate, open the prefilled opportunity creation flow and confirm the opportunity details.

### Manage an RFQ

1. Create the RFQ from the RFQ module or a customer’s RFQ view.
2. Capture the customer request, items, owner, timing, value, and next action.
3. Advance the RFQ through its working stages.
4. When Google authorization is available, send or synchronize its email conversation.
5. Conclude it as a sale, loss, cancellation, or continuation in an opportunity.

### Manage quotes and commercial value

1. Open an opportunity.
2. Add or update a quote and revision.
3. Record currency, exchange-rate basis, amount, date, brand, status, and supporting details.
4. Review its normalized value in the opportunity.
5. Where special conditions are required, create and submit a commercial approval request.
6. After a decision, use the approved commercial values as the governed opportunity value.

### Manage an agreement

1. Open the customer’s agreement view.
2. Create an agreement manually or upload the agreement workbook.
3. Review the import preview, validation, product reconciliation, and any existing active agreement.
4. Confirm the new agreement; if replacing one, explicitly confirm replacement while retaining the prior record as expired.
5. Review negotiated items against purchase history, including coverage, never-purchased products, sales participation, and matching quality.

### Run an Ask analysis

1. Describe the commercial decision in plain language.
2. Optionally select a customer.
3. Attach relevant files.
4. Review how the evidence was interpreted and any warnings.
5. Continue the conversation to investigate, compare, adjust, or request a deliverable.
6. Review generated artifacts and the analysis report.
7. Reanalyze as a new version or export supported tabular outputs.
8. Treat the result as analysis and recommendation, not as a replacement for source records.

### Manage a strategic initiative

1. Create the initiative and define its objective, owner, partner, dates, status, and financial context.
2. Attach relevant opportunities.
3. Review aggregate opportunity count and pipeline.
4. Record events, learnings, and decisions.
5. Update or close the initiative as the program evolves.

---

## 5. Data sources

| Source | Contribution to the product |
|---|---|
| **Manual user entry** | Opportunities, activities, contacts, follow-ups, RFQs, quotes, initiatives, agreements, approval requests, decisions, classifications, blockers, conclusions, and narrative context. |
| **ERP customer files** | Authoritative customer identity and ERP-controlled attributes. Customer imports refresh these records while preserving Command Center context. |
| **ERP sales files** | Historical transactions used in purchase history, customer performance, account revenue, product mix, agreement analytics, and Ask context. |
| **ERP-related quote references** | Quote numbers and commercial proposal context can be recorded, but a complete automated quote-import workflow is not currently exposed. |
| **Uploaded project and agreement files** | Commercial evidence such as proposals, quotes, drawings, photos, technical reports, and source agreements. |
| **Files uploaded to Ask** | Decision-specific evidence read and summarized within an Ask analysis; supported formats include spreadsheets, documents, PDFs, text, and images. |
| **Google AppSheet / Google Sheets** | External source of commercial visit records, including visit context, needs, risks, commitments, possible opportunities, and attachment references. |
| **Gmail / Google authorization** | Targeted RFQ email sending and synchronization, preserving conversation context with the RFQ when configured. |
| **Google identity** | User sign-in and identity for access, ownership, and authorship. |
| **Ask-generated analysis** | Derived summaries, inferences, recommendations, reports, and artifacts. These are analytical outputs, not authoritative customer, ERP, or opportunity facts. |
| **Inventory imports** | Point-in-time inventory information available to analysis and specialized operational work, without a general end-user inventory module today. |
| **Specialized uploaded workbooks and notebooks** | The repository contains customer-specific consignment and monthly-analysis workflows. Their outputs are analytical/supporting assets rather than a general application module. |

---

## 6. Relationships

The customer is the organizing root, but the product does not force every process into an opportunity.

```text
Customer
├── Contacts
├── Purchase history ← ERP sales imports
├── Activities
│   ├── Evidence
│   └── Follow-up
├── Commercial visits ← AppSheet / Google Sheets
│   └── Candidate opportunity
├── RFQs
│   ├── Items, documents, email, status history
│   └── Outcome: sale, loss, cancellation, or opportunity
├── Opportunities / Projects
│   ├── Activities and visits
│   ├── Follow-ups → Workspace daily queue
│   ├── Quotes and brands
│   ├── Commercial approvals
│   ├── Files
│   └── Timeline and conclusion
├── Agreements
│   ├── Negotiated items
│   └── Performance compared with purchase history
└── Ask analyses
    ├── Customer and internal context
    ├── Uploaded evidence
    └── Derived artifacts and reports

Initiative
└── Multiple opportunities across the commercial program
```

Important behavioral rules:

- A customer can exist without an opportunity.
- An activity can exist without an opportunity, though it always has customer context.
- An RFQ can exist and conclude without an opportunity.
- A commercial visit can remain only an account interaction or become an opportunity candidate.
- An agreement belongs to the customer and is not an opportunity.
- A quote belongs to an opportunity.
- A follow-up drives daily execution and currently belongs primarily to an opportunity.
- Ask may read across these sources, but its conclusions do not automatically change them.

---

## 7. Current product philosophy

### Centralized

- **Customer context:** customer identity anchors the commercial record.
- **Opportunity execution:** activities, follow-ups, quotes, files, approvals, and timeline are assembled in the opportunity workspace.
- **Daily attention:** Workspace centralizes near-term follow-up obligations.
- **Integration status:** ERP imports and visit synchronization are monitored from one center.
- **Evidence-based analysis:** Ask brings selected customer data and uploaded evidence into one investigation.

### Distributed

- Authoritative customer and sales facts remain in the ERP.
- Field visits remain captured in AppSheet/Sheets and are synchronized into the product.
- Gmail remains the email channel for RFQ correspondence.
- Source documents remain distinct evidence attached to the relevant commercial object.
- RFQs, opportunities, and agreements remain separate because they represent different commercial processes.

### What belongs inside Ask

- A decision or investigation objective.
- Customer and commercial context available to the analysis.
- Uploaded evidence.
- Conversation, interpretation warnings, derived findings, recommendations, and deliverables.

### What belongs outside Ask

- Authoritative ERP facts.
- Final customer or opportunity record changes.
- Activity registration.
- RFQ progression.
- Approval decisions.
- Agreement state.
- Owned and dated follow-ups.

### Intentionally manual

- ERP file selection, preview, and import confirmation.
- Visit synchronization.
- Opportunity creation and closure.
- Deciding whether an RFQ becomes an opportunity.
- Activity capture and follow-up ownership.
- Agreement replacement confirmation.
- Commercial approval submission and decision.
- Interpretation and adoption of Ask recommendations.

### Automated or derived

- Import validation, duplicate handling, counts, warnings, and history.
- Customer and sales aggregation.
- Opportunity health and next-action signals.
- Workspace grouping by due date.
- Timeline assembly from opportunity evidence.
- Currency-normalized quote value.
- Agreement/product reconciliation and performance calculations.
- Visit matching, duplicate signals, and quality warnings.
- Ask file inspection, evidence synthesis, and artifact generation.

The consistent philosophy is: preserve source authority, keep commercial conclusions explainable, and require an explicit outcome or next action.

---

## 8. Known gaps

These are observations of the current product, not recommendations.

- **Analytics is not a complete module.** It appears as a disabled navigation heading. Purchase History is a narrow, hardcoded customer/category/time-window page.
- **The activity navigation is indirect.** “Actividades” currently opens the customer portfolio rather than a global activity workspace.
- **Manual activities and imported visits are separate records and experiences.** They appear together in parts of the customer story but are not one unified activity object.
- **Workspace is not yet a universal attention queue.** It centers on opportunity follow-ups and does not consolidate all RFQ, agreement, approval, import-quality, and account risks.
- **Terminology is mixed.** “Proyecto” and “Oportunidad” refer to the same commercial pursuit in different surfaces.
- **Strategic-account views contain explicit placeholders.** AI insights and other account-planning capabilities are marked unavailable or assigned to later phases.
- **Purchase History is not generalized.** Its current top-level view names a specific customer, product family, and 18-month window.
- **ERP integration is manual.** Customers and sales arrive through uploaded files with explicit confirmation rather than continuous synchronization.
- **Google visit integration is configuration-dependent.** Unmatched customers, ambiguous matches, possible duplicates, and unresolved attachments are recognized operating states.
- **RFQ email is configuration-dependent.** Sending and synchronization require Google authorization.
- **Quote functionality is not a standalone end-to-end domain.** Item detail, automated ERP quote ingestion, comprehensive revision handling, and margin analysis remain incomplete.
- **Commercial approvals do not expose a central manager queue or configurable routing.** They are managed within each opportunity.
- **Agreement management is account-specific.** There is no top-level agreement portfolio or fully surfaced renewal/risk workflow.
- **Initiatives are lightly connected to the rest of daily work.** They group opportunities and preserve events, learning, and decisions but do not drive Workspace attention.
- **User and permission administration is not a visible product area.**
- **Some repository documentation is older than the current product.** Earlier backlog items describe as planned several capabilities that now exist, so the running product surfaces and current tests are more reliable indicators of present scope.
- **Specialized consignment and monthly-analysis work exists outside the general product experience.** It is represented by notebooks, scripts, and generated outputs rather than a reusable user-facing module.

---

## 9. Future extension points

The current product structure visibly leaves room for growth in these grounded areas:

- more integration cards and managed sources in Integration Center;
- broader Google Workspace orchestration beyond targeted identity, visits, and RFQ email;
- a unified attention system spanning follow-ups, RFQs, approvals, agreements, data quality, and stale opportunities;
- richer customer/account tabs and account-planning views already shown as unavailable;
- expanded opportunity timeline contributors and next-action types;
- quote items, revision history, ERP quote ingestion, and commercial analysis;
- agreement renewal, risk, milestone, savings, support-value, and consignment tracking;
- initiative-level management workflows and portfolio attention;
- more Ask capabilities, evidence types, analysis artifacts, and customer-grounded investigations;
- generalized purchase, product, brand, customer, agreement, and pipeline analytics;
- improved conversion paths among visits, RFQs, activities, and opportunities while retaining their separate business meanings;
- searchable and versioned commercial evidence across projects, agreements, activities, RFQs, and Ask.

These are extension points already implied by existing objects, placeholders, or documented boundaries; they are not redesign proposals.

---

## 10. One-page product map

### Modules and primary objects

| Product area | Primary objects | User value |
|---|---|---|
| Workspace | Follow-up, Opportunity | Know what must be done now. |
| Customers | Customer, Profile, Contact | Understand the account and navigate all related work. |
| Projects | Opportunity, Quote, Brand, File, Timeline | Move a commercial pursuit from identification to conclusion. |
| Activities | Activity, Evidence, Follow-up | Record work, learning, risk, and commitments. |
| Visits | Commercial Visit, Match, Sync Run | Bring field activity into the account and identify opportunities. |
| RFQs | RFQ, Item, Conclusion, Email Conversation | Manage a customer request without forcing it into an opportunity. |
| Initiatives | Initiative, Event, Learning, Decision | Manage a strategic program across opportunities. |
| Agreements | Agreement, Item, Document | Track negotiated account scope against actual purchasing. |
| Approvals | Approval Request, Decision | Govern commercial exceptions and approved value. |
| Ask | Analysis, Message, File, Artifact | Investigate a commercial decision using evidence. |
| Integrations | Import Execution, Import Issue, Sync Run | Refresh external data with visible control and quality status. |
| Purchase History | Sales Transaction | Understand actual customer purchasing behavior. |

### Core relationship map

```text
ERP customers and sales
          ↓
       Customer
     ↙    ↓     ↘
Activity  RFQ   Agreement
   ↓       ↓         ↘
Follow-up  └──→ Opportunity ←── Initiative
   ↓               ↓
Workspace     Quotes · Files · Approvals · Timeline
                   ↓
               Conclusion

AppSheet visit ──→ Customer activity
       └────────→ Candidate opportunity

Customer context + commercial records + uploaded files
                         ↓
                        Ask
                         ↓
              Analysis and deliverables
```

### Typical daily workflow

```text
1. Open Workspace
   ↓
2. Review overdue and upcoming actions
   ↓
3. Open the customer or opportunity
   ↓
4. Review evidence: activity, visit, RFQ, quote, agreement, files, history
   ↓
5. Execute: call, visit, prepare quote, request approval, follow up
   ↓
6. Record the result and update status/blocker
   ↓
7. Create or reschedule the next action
   ↓
8. Use Ask when a decision needs deeper analysis
   ↓
9. Conclude the RFQ or opportunity when the cycle ends
```

The shortest accurate mental model is: **Customer is the root, Opportunity is the pursuit, Activity is the evidence, Follow-up is the commitment, Workspace is the daily queue, and Ask is the analyst.**
