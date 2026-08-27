# Commercial Command Center — Conceptual Data Model

**Status:** Locked conceptual baseline  
**Purpose:** Define entity boundaries, relationships, ownership, and lifecycle rules before physical database design.

---

## 1. Model Overview

```text
ERP
├── Customers
└── Sales Transactions

Commercial Command Center
├── Users / Advisors
├── Customers (ERP-linked commercial profile)
│   ├── Contacts
│   ├── Activities
│   │   ├── Evidence
│   │   ├── Participants
│   │   ├── Products Discussed
│   │   ├── Business Lines
│   │   ├── Competitors
│   │   └── Commitments / Follow-ups
│   ├── RFQs
│   │   ├── RFQ Items
│   │   ├── Status History
│   │   └── Conclusion
│   ├── Opportunities
│   │   ├── Stage History
│   │   ├── RFQs
│   │   ├── Activities
│   │   ├── Contacts
│   │   └── Next Actions
│   ├── Agreements
│   │   ├── Milestones
│   │   ├── Risks
│   │   ├── Activities
│   │   └── Value Records
│   ├── Documents
│   └── Reports
│       ├── Narrative
│       ├── Blocks
│       ├── Sources
│       └── Versions
├── Attention Items
├── Ask Investigations
└── Import Executions
```

---

## 2. Source-of-Truth Boundaries

| Domain | Source of truth | Notes |
|---|---|---|
| ERP customer identity | ERP | Internal customer record preserves stable internal ID linked to ERP business key. |
| ERP sales | ERP | Imported append-only into analytical store. |
| Commercial contacts | Command Center | May be created and maintained by users. |
| Activities | Command Center | Principal source of commercial evidence. |
| RFQs | Command Center | Independent commercial entity. |
| Opportunities | Command Center | Represents meaningful pursuits or projects. |
| Agreements | Command Center / existing module | Extended incrementally. |
| Follow-ups | Command Center | Must have responsible user and due date. |
| Reports | Command Center | HTML-native compositions with source traceability. |
| Ask outputs | Command Center | Derived analysis, never authoritative source facts. |
| Calendar events | Google Calendar | Command Center stores links and synchronization metadata. |

---

## 3. Core Entities

## 3.1 User

Represents an authenticated platform user.

Primary responsibilities:

- Own customers, RFQs, opportunities, follow-ups, and report drafts.
- Participate in activities.
- Resolve attention items.

Key relationships:

- User 1:N Activity as advisor.
- User M:N Activity as internal participant.
- User 1:N RFQ as owner.
- User 1:N Opportunity as owner.
- User 1:N FollowUp as responsible user.
- User 1:N AttentionItem as assignee.

---

## 3.2 Customer

Represents the commercial workspace for an ERP customer.

Key rule:

The ERP controls authoritative identity and sales-related attributes. The Command Center adds commercial attributes without replacing the ERP record.

Relationships:

- Customer 1:N Contact.
- Customer 1:N Activity.
- Customer 1:N RFQ.
- Customer 1:N Opportunity.
- Customer 1:N Agreement.
- Customer 1:N Document.
- Customer 1:N Report.
- Customer 1:N SalesTransaction.

---

## 3.3 Contact

Represents a person at a customer.

Relationships:

- Contact N:1 Customer.
- Contact M:N Activity.
- Contact M:N Opportunity.
- Contact M:N RFQ where needed.

Derived values:

- Last activity date.
- Activity count.
- Related opportunity count.

---

## 3.4 Activity

Represents any commercial interaction, including visits, calls, meetings, training, technical support, inspections, emergency response, and follow-up actions.

Relationships:

- Activity N:1 Customer.
- Activity N:1 Advisor User.
- Activity M:N Participant User.
- Activity N:1 Contact, with optional additional contacts if later required.
- Activity M:N Product.
- Activity M:N BusinessLine.
- Activity M:N Competitor.
- Activity 1:N Evidence.
- Activity 1:N FollowUp or Commitment.
- Activity N:0..1 Opportunity.
- Activity N:0..1 RFQ.
- Activity N:0..1 Agreement.
- Activity M:N ReportBlockSource.

Key rule:

Activities are historical evidence. Important modifications must be audited.

---

## 3.5 Evidence

Represents a photo, PDF, or other approved attachment associated with an activity or another commercial entity.

Relationships:

- Evidence N:1 Activity in the initial model.
- Evidence may later support polymorphic entity attachment if needed.
- Evidence M:N ReportBlock through source links or evidence selection.

Key attributes:

- File metadata.
- Description.
- Uploaded by.
- Upload date.
- Source entity.
- Display order.

---

## 3.6 FollowUp

Represents a required next action or commitment.

Relationships:

- FollowUp N:1 Customer.
- FollowUp N:1 Responsible User.
- FollowUp N:0..1 Activity.
- FollowUp N:0..1 RFQ.
- FollowUp N:0..1 Opportunity.
- FollowUp N:0..1 Agreement.

Lifecycle:

- Pending.
- In progress.
- Completed.
- Rescheduled.
- Cancelled with reason.

Key rule:

Every active follow-up requires a due date and responsible user. Overdue follow-ups create AttentionItems.

---

## 3.7 RFQ

Represents a request for quotation.

Relationships:

- RFQ N:1 Customer.
- RFQ N:1 Owner User.
- RFQ N:0..1 Primary Contact.
- RFQ N:0..1 Opportunity.
- RFQ 1:N RFQItem.
- RFQ 1:N RFQStatusHistory.
- RFQ 1:N FollowUp.
- RFQ M:N Activity.
- RFQ 1:0..1 Conclusion.

Key rules:

- RFQ is independent from Opportunity.
- Multiple RFQs may relate to one Opportunity.
- Every open RFQ requires a next action.
- Every RFQ must eventually reach a conclusion.

---

## 3.8 RFQItem

Represents a requested product, service, or line item.

Relationships:

- RFQItem N:1 RFQ.
- RFQItem N:0..1 Product.

The design must allow free-text items when a requested item is not in the product catalog.

---

## 3.9 RFQConclusion

Represents the final outcome of an RFQ.

Possible outcomes:

- Won.
- Lost.
- Cancelled.
- Converted to or continued in Opportunity.

Key attributes:

- Outcome.
- Reason.
- Conclusion date.
- Final value when applicable.
- Related sale reference when available.
- Related opportunity when applicable.
- Concluded by.

---

## 3.10 Opportunity

Represents a meaningful commercial project or pursuit.

Relationships:

- Opportunity N:1 Customer.
- Opportunity N:1 Owner User.
- Opportunity M:N Contact.
- Opportunity M:N Activity.
- Opportunity 1:N RFQ.
- Opportunity 1:N FollowUp.
- Opportunity 1:N StageHistory.
- Opportunity 1:0..1 Conclusion.

Key rule:

Every active opportunity requires a current stage, owner, next action, and next-action date.

---

## 3.11 OpportunityConclusion

Represents the final outcome of an opportunity.

Possible outcomes:

- Won.
- Lost.
- Cancelled.
- On hold with explicit review date.

Loss and cancellation require reasons.

---

## 3.12 Agreement

Represents a commercial agreement or convenio.

Relationships:

- Agreement N:1 Customer.
- Agreement 1:N Milestone.
- Agreement 1:N Risk.
- Agreement M:N Activity.
- Agreement 1:N FollowUp.
- Agreement 1:N ValueRecord.
- Agreement 1:N Report.

Key rule:

The existing Agreements module remains. Enhancements must preserve current behavior and IDs.

---

## 3.13 AgreementMilestone

Represents a scheduled review, renewal, commitment, SLA milestone, or deliverable.

Overdue or upcoming milestones may create AttentionItems.

---

## 3.14 AgreementRisk

Represents a commercial, operational, financial, or relationship risk tied to an agreement.

Key attributes:

- Risk type.
- Severity.
- Description.
- Mitigation.
- Owner.
- Review date.
- Status.

---

## 3.15 ValueRecord

Represents value delivered or estimated for a customer or agreement.

Examples:

- Emergency response.
- Downtime avoided.
- Savings.
- Training delivered.
- Technical inspections.
- Inventory availability.
- Reliability improvement.

Key rule:

A value record must identify whether it is measured, calculated, estimated, or manually asserted.

---

## 3.16 SalesTransaction

Represents imported ERP sales data.

Relationships:

- SalesTransaction N:1 Customer.
- May relate to Product, BusinessLine, Advisor, branch, invoice, or other ERP dimensions depending on the available schema.

Key rules:

- Append-only.
- Idempotent import.
- Immutable source facts except through corrective import policy.

---

## 3.17 ImportExecution

Represents one import attempt.

Relationships:

- ImportExecution N:1 User.
- ImportExecution 1:N ImportIssue.

Key attributes:

- Import type.
- Original file.
- File hash.
- Schema version.
- Counts.
- Status.
- JSON log.

---

## 3.18 Report

Represents a live HTML report.

Relationships:

- Report N:1 Customer or another primary subject.
- Report N:1 Owner User.
- Report 1:N ReportVersion.
- Report 1:N ReportBlock.
- Report N:1 NarrativeDefinition or custom narrative configuration.

Possible subject types:

- Customer.
- Opportunity.
- Agreement.
- Project.
- Management period.

---

## 3.19 ReportVersion

Represents an approved or saved report state.

Key purposes:

- Preserve editorial review.
- Preserve source snapshot metadata.
- Support draft, review, publication, and archive states.

A report may have live blocks and locked blocks. Versioning must clearly identify which content is dynamic and which is frozen.

---

## 3.20 ReportBlock

Represents one composable report section.

Attributes:

- Block type.
- Title.
- Display order.
- Visibility.
- Content configuration.
- Manual content.
- Ask-generated content.
- Locked status.
- Refresh behavior.

Relationships:

- ReportBlock N:1 Report.
- ReportBlock 1:N ReportBlockSource.
- ReportBlock M:N Evidence where selected.

---

## 3.21 ReportBlockSource

Provides traceability from a report block to source records.

Source types may include:

- Activity.
- SalesTransaction aggregate.
- RFQ.
- Opportunity.
- Agreement.
- FollowUp.
- ValueRecord.
- Manual assertion.
- Ask analysis.

Key rule:

Factual statements generated by Ask should retain links to supporting sources when technically feasible.

---

## 3.22 NarrativeDefinition

Represents a strategic reporting narrative.

Examples:

- Commercial.
- Value.
- Agreement.
- Executive.
- Engineering.
- Reliability.
- Emergency.
- Training.
- Project.
- Follow-up.
- Custom.

A narrative defines:

- Preferred block order.
- Priority metrics.
- Tone.
- Suggested titles.
- Evidence emphasis.
- Ask instructions.
- Recommended calls to action.

---

## 3.23 AttentionItem

Represents an actionable issue shown on Home or in management views.

Relationships:

- AttentionItem N:1 Assigned User.
- AttentionItem N:1 TriggerRule.
- AttentionItem N:1 related commercial entity through a controlled polymorphic reference or dedicated nullable foreign keys.

Lifecycle:

- Open.
- In progress.
- Resolved.
- Dismissed with reason.

Examples:

- RFQ without update.
- RFQ due for conclusion.
- Opportunity stale.
- Follow-up overdue.
- Customer without visit.
- Agreement milestone approaching.

---

## 3.24 AskInvestigation

Represents a structured Ask request and its investigation trace.

Key attributes:

- User request.
- Context entity.
- Time range.
- Sources queried.
- Findings.
- Facts.
- Inferences.
- Recommendations.
- Generated date.

This entity supports reproducibility, report reuse, and audit of important commercial analyses.

---

## 4. Relationship Rules

### Customer and Activity

Every activity must belong to one customer. Cross-customer events require separate activity records or a later explicitly designed multi-customer event feature.

### Activity and Opportunity

An activity may relate to zero or one primary opportunity initially. If the business later needs one activity to update multiple opportunities, introduce a join table without changing activity identity.

### Activity and RFQ

An activity may relate to zero or one primary RFQ initially. Multiple relationships may be supported through a join table if required.

### RFQ and Opportunity

- RFQ may exist without opportunity.
- RFQ may link to one opportunity.
- Opportunity may contain many RFQs.

### Reports and Sources

Reports do not own or duplicate business facts. They reference source records and may store editorial content, configuration, and approved snapshots.

### Attention Items

Attention items are derived workflow objects, not replacements for the underlying business entities. Resolving an AttentionItem must update or document resolution of the underlying commercial object.

---

## 5. Lifecycle Integrity Rules

### Open commercial entity rule

Every active RFQ and Opportunity requires:

- Owner.
- Current status or stage.
- Next action.
- Next-action date.

### Conclusion rule

Closed RFQs and Opportunities require:

- Outcome.
- Conclusion date.
- Reason when lost or cancelled.
- Final value when applicable.

### Follow-up rule

Every pending follow-up requires:

- Responsible user.
- Due date.
- Description.
- Source or context.

### Activity evidence rule

Activity evidence must not be silently detached from the activity that created it. Deletion requires authorization and audit.

### Report source rule

Manual statements must be distinguishable from system-derived facts.

---

## 6. Recommended Physical Modeling Patterns

These are recommendations for the implementation specification, not final SQL definitions.

- Use stable UUID or existing project-standard IDs for internally owned entities.
- Preserve existing customer and agreement IDs.
- Use explicit history tables for lifecycle changes.
- Use join tables for multi-select and many-to-many relationships.
- Avoid comma-separated values in entity columns.
- Use soft-delete or archive timestamps for commercial records.
- Use JSON only for flexible configuration, execution logs, and report block settings—not as a substitute for core relational fields.
- Use timezone-aware timestamps.
- Store money with decimal/numeric types and currency code.
- Maintain created_by, updated_by, created_at, and updated_at where appropriate.

---

## 7. Conceptual Event Flow

```text
Activity registered
    ├── updates Customer timeline
    ├── may create FollowUp
    ├── may create or update RFQ
    ├── may create or update Opportunity
    ├── may update Agreement evidence
    ├── supplies Report evidence
    ├── supplies Ask context
    └── may resolve or create AttentionItems

RFQ updated
    ├── updates Home attention state
    ├── updates Customer workspace
    ├── updates Sales Management
    ├── may link to Opportunity
    └── supplies Ask and Reports

Opportunity updated
    ├── updates pipeline
    ├── updates Home attention state
    ├── updates Customer workspace
    ├── updates Sales Management
    └── supplies Ask and Reports
```

---

## 8. Locked Conceptual Decisions

- Customer is the principal commercial workspace.
- Activity is the principal evidence-generating entity.
- RFQ and Opportunity are distinct entities.
- Multiple RFQs may belong to one Opportunity.
- FollowUp is a first-class entity.
- AttentionItem is a derived actionable workflow entity.
- Report is a composition and narrative layer, not a duplicate fact store.
- Manual report content is allowed and source-labelled.
- Ask outputs are derived analysis and must not overwrite source facts.

