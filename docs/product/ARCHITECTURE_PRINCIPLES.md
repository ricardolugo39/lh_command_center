# Commercial Command Center
# Architecture Principles

Version: 1.0

---

# Purpose

This document defines the engineering principles that govern the Commercial Command Center.

These principles are mandatory.

Every implementation must follow them unless an Architecture Decision explicitly supersedes them.

The objective is long-term maintainability, consistency, and extensibility.

---

# Product Philosophy

Commercial Command Center is a Commercial Operating System.

It is NOT a CRM.

It helps commercial teams execute work rather than merely record information.

---

# Source of Truth

ERP is the source of truth for:

- Customers
- Sales
- Products
- Historical transactions

Commercial Command Center extends ERP.

It never replaces ERP.

---

# Google Workspace

Existing Google products are reused whenever possible.

Calendar remains Calendar.

Gmail remains Gmail.

Drive remains Drive.

Meet remains Meet.

The platform orchestrates them.

---

# Software Architecture

Prefer

Route
→ Service
→ Repository
→ Database

Business rules belong inside Services.

Repositories only access data.

Routes only coordinate requests.

---

# Transactions

Services own transactions.

Repositories never commit business transactions.

One business operation = one transaction.

---

# Business Logic

Business logic must never exist inside

- Routes
- Templates
- JavaScript

Business logic belongs in Services.

---

# Single Responsibility

One service.

One responsibility.

Avoid large "god classes."

---

# Repositories

Repositories

- query data

- persist data

They never make business decisions.

---

# UI

User interface language is Spanish.

Source code is English.

Database naming is English.

---

# Evidence First

Commercial work produces evidence.

Evidence includes

- Activities

- Visits

- RFQs

- Meetings

- Photos

- Files

- Emails

Evidence should be preserved.

---

# Audit

System audit is different from commercial evidence.

Never mix the two concepts.

---

# Activities

Activities are customer-centered.

Activities may relate to

- Opportunity

- RFQ

- Agreement

- Report

But they can exist independently.

---

# RFQ

RFQ is an independent business object.

It is not automatically an Opportunity.

---

# Opportunity

Opportunities represent commercial projects.

Everything inside an Opportunity should move the sale forward.

---

# Reports

Reports are HTML experiences.

Not PDF documents.

Reports are generated from reusable blocks.

---

# AI

Ask is a Commercial Analyst.

Ask never invents information.

Ask must distinguish

- Facts

- Inferences

- Recommendations

Every AI response must be explainable.

---

# Data Integrity

Do not duplicate business rules.

Do not duplicate business entities.

Prefer extending existing models.

---

# Extensibility

Prefer composition over duplication.

Avoid rewriting existing modules.

Integrate.

Extend.

Preserve compatibility whenever possible.

---

# Backwards Compatibility

Existing functionality should continue working unless an Architecture Decision explicitly changes behavior.

---

# Documentation

Every architectural change must update

- MASTER_SPEC

- ENTITY_DICTIONARY

- CONCEPTUAL_MODEL

- DECISIONS

when applicable.

Documentation is part of the implementation.

---

# Engineering Principle

Build software that can be understood one year from now.

Clarity is preferred over cleverness.

Consistency is preferred over novelty.

Long-term maintainability is preferred over short-term speed.