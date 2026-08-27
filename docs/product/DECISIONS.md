# Commercial Command Center
## Architecture Decisions Log

---

# Purpose

This document records every architectural and product decision that has been approved.

These decisions are considered **LOCKED**.

Future implementations must respect these decisions unless they are explicitly superseded by a new decision.

This document is the single source of truth for architectural decisions.

---

# Decision Format

Each decision includes:

- ID
- Date
- Status
- Category
- Decision
- Rationale
- Impact

---

# DEC-001

Status

LOCKED

Category

Product

Decision

Commercial Command Center is a Commercial Operating System, not a CRM.

Rationale

The objective is to help commercial teams execute work, not simply record customer information.

Impact

All future modules must support commercial execution.

---

# DEC-002

Status

LOCKED

Category

Architecture

Decision

ERP remains the System of Record.

Commercial Command Center extends ERP capabilities.

It never replaces ERP.

---

# DEC-003

Status

LOCKED

Category

Architecture

Decision

Google Workspace is leveraged whenever possible instead of recreating existing functionality.

Examples

Calendar

Drive

Gmail

Meet

---

# DEC-004

Status

LOCKED

Category

Activities

Decision

Activities are the primary source of commercial intelligence.

Activities feed

- Ask

- Reports

- Customer Timeline

- Follow-ups

- Opportunity History

- RFQs

---

# DEC-005

Status

LOCKED

Category

Home

Decision

Home is not a KPI dashboard.

Home exists to surface incomplete commercial work.

---

# DEC-006

Status

LOCKED

Category

RFQ

Decision

RFQ is an independent business object.

It does NOT automatically create an Opportunity.

Possible outcomes

- Sale

- Lost

- Opportunity

---

# DEC-007

Status

LOCKED

Category

Reports

Decision

Reports are native HTML.

PDF is only an optional browser export.

---

# DEC-008

Status

LOCKED

Category

Reports

Decision

Reports are generated using reusable content blocks.

Examples

Hero

Timeline

KPIs

Activities

Photos

Recommendations

Executive Summary

---

# DEC-009

Status

LOCKED

Category

Reports

Decision

Reports support multiple Narratives.

The data remains the same.

The story changes according to the report objective.

Examples

Commercial

Executive

Engineering

Emergency Response

Value

Agreement

Reliability

Project

---

# DEC-010

Status

LOCKED

Category

AI

Decision

Ask acts as a Commercial Analyst.

Ask never invents information.

Ask distinguishes

Facts

Inference

Recommendations

---

# DEC-011

Status

LOCKED

Category

Data

Decision

Every commercial object must end in either

a conclusion

or

a next action.

Nothing remains forgotten.

---

# Future Decisions

Append new decisions below.

Never edit previous decisions.

Only supersede them by creating a new decision referencing the old one.