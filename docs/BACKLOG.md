# Commercial Command Center
# Product Backlog

Last Updated: 2026-07-11

---

# Product Vision

Commercial Command Center is the operating system for Lugo Hermanos' commercial organization.

The objective is to allow a salesperson to spend an entire workday inside the application without relying on notebooks, spreadsheets, or disconnected tools.

Every new feature should answer one of these questions:

- Does it help execute work?
- Does it improve customer knowledge?
- Does it improve commercial intelligence?
- Does it reduce administrative work?

If not, it probably belongs in the backlog until later.

---

# Current Version

## v0.1 — Execution Engine ✅

Completed

- Customer Lookup
- Project Management
- Timeline
- Activities
- Follow-ups
- Complete Follow-up
- Reschedule Follow-up
- Pipeline
- Brands
- Quote Association

---

# Sprint 3 — Commercial Intelligence 🚧

## Epic 3.1 — Quote Domain

Priority: ⭐⭐⭐⭐⭐

Status: In Progress

### Stories

- [ ] Quote Repository
- [ ] Quote Service
- [ ] Currency Support (COP / USD)
- [ ] Exchange Rate
- [ ] Normalized COP Amount
- [ ] Quote Detail Card
- [ ] Quote Detail Page
- [ ] Quote Status
- [ ] Quote Revisions
- [ ] ERP Quote Import

---

## Epic 3.2 — Attachments

Priority: ⭐⭐⭐⭐⭐

Status: Planned

### Stories

- [ ] Upload Files
- [ ] Quote PDF
- [ ] Photos
- [ ] Videos
- [ ] Technical Documents
- [ ] Timeline Integration
- [ ] Attachment Categories
- [ ] Attachment Preview

---

## Epic 3.3 — Activity History

Priority: ⭐⭐⭐⭐☆

Status: Planned

### Stories

- [ ] Activity History Page
- [ ] Hide System Events
- [ ] Filter by Type
- [ ] Filter by Date
- [ ] Filter by Sales Rep
- [ ] Export Activity Report

---

## Epic 3.4 — Project Portfolio

Priority: ⭐⭐⭐⭐⭐

Status: Planned

### Stories

- [ ] Rich Project Cards
- [ ] Quote Value Preview
- [ ] Brands Preview
- [ ] Next Follow-up Preview
- [ ] Current Blocker Preview
- [ ] Last Activity Preview

---

## Epic 3.5 — Dashboard

Priority: ⭐⭐⭐⭐⭐

Status: Planned

### Stories

- [ ] Overdue Follow-ups
- [ ] Due Today
- [ ] Projects without Follow-up
- [ ] Pipeline Value
- [ ] Recent Activity
- [ ] Projects by Status

---

# Future — Customer Intelligence

## Epic 4.1 — Customer Page

Priority: ⭐⭐⭐⭐⭐

- [ ] Customer Dashboard
- [ ] Projects
- [ ] Purchase History
- [ ] Contacts
- [ ] Files
- [ ] Activity Summary
- [ ] Sales Trends

---

## Epic 4.2 — Agreements

Priority: ⭐⭐⭐⭐⭐

Purpose

Annual commercial agreements.

These are customer-level entities.

They are NOT projects.

Stories

- [ ] Agreement Entity
- [ ] Agreement Dashboard
- [ ] Agreement Status
- [ ] Commercial Conditions
- [ ] Annual Target
- [ ] Renewal Tracking

---

## Epic 4.3 — Support Value

Stories

- [ ] Technical Visits
- [ ] Training Sessions
- [ ] Engineering Support
- [ ] Failure Analysis
- [ ] Support Reports
- [ ] Estimated Value Delivered

---

## Epic 4.4 — Consignment Warehouse

Stories

- [ ] Warehouse Indicator
- [ ] Inventory Summary
- [ ] Consumption
- [ ] Replenishment
- [ ] Inventory Value

---

# Future — Commercial Analytics

- [ ] Customer Ranking
- [ ] Pipeline Forecast
- [ ] Win Rate
- [ ] Lost Opportunity Analysis
- [ ] Sales by Brand
- [ ] Sales by Industry
- [ ] Customer Growth
- [ ] Quote Conversion Rate

---

# Future — AI

## AI Assistant

- [ ] Opportunity Summary
- [ ] Suggested Next Action
- [ ] Meeting Summary
- [ ] Email Summary
- [ ] Customer Insights
- [ ] Quote Recommendations
- [ ] Executive Reports

---

# UX Backlog

These items intentionally do NOT block functionality.

## Workspace

- [ ] Reorganize Workspace layout
- [ ] Better use of whitespace
- [ ] Improve project summary card

## Project List

- [ ] Redesign list
- [ ] Better visual hierarchy
- [ ] Card view
- [ ] Compact view

## Timeline

- [ ] Better icons
- [ ] Better spacing
- [ ] Relative timestamps

---

# Technical Debt

- [ ] Split WorkspaceService into domain services
- [ ] QuoteService
- [ ] ActivityService
- [ ] FollowupService
- [ ] AttachmentService
- [ ] Unit Tests
- [ ] Repository Tests
- [ ] API Tests

---

# Parking Lot

Ideas that are intentionally NOT scheduled yet.

- Email Integration
- Outlook Integration
- Teams Integration
- Google Calendar
- Mobile App
- Push Notifications
- OCR
- AI Document Extraction
- Voice Notes
- Offline Mode
- Route Planning
- Digital Visit Reports

---

# Product Decisions

## Customer is the root entity.

Projects belong to customers.

---

## ERP is the source of truth.

Commercial Command Center complements the ERP.

---

## Execution first.

Every screen should help the salesperson execute work.

---

## Intelligence second.

Dashboards and analytics are built on top of execution data.

---

## Documentation first.

Architecture decisions are documented before implementation whenever practical.

### Deferred (Post-MVP)

- [ ] Quote Revisions
- [ ] Primary Quote
- [ ] Quote Attachments
- [ ] Exchange Rate History
- [ ] Quote Timeline
- [ ] ERP Quote Synchronization

### Quote Improvements (Post-MVP)

- [ ] Replace free-text quote status with a controlled dropdown.
- [ ] Standardize internal status values while displaying user-friendly labels.
- [ ] Add quote conversion reports based on status.