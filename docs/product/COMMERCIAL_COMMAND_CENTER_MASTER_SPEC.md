# Commercial Command Center — Master Specification

**Status:** Locked baseline  
**Product type:** Commercial Operating System  
**Primary language:** Spanish UI  
**Internal code language:** English  

---

## 1. Product Vision

Commercial Command Center is not a traditional CRM and not a dashboard collection. It is a Commercial Operating System designed to organize execution, preserve evidence, close commercial cycles, support management, and generate evidence-based commercial intelligence.

The ERP remains the source of truth for customers and sales. Google Workspace is leveraged rather than replaced. The platform connects commercial activity, opportunities, RFQs, agreements, follow-ups, reporting, and management into a single operating model.

### Core promise

The system must answer, for every commercial user:

> What requires attention, what must be done today, what is at risk, and what commercial action should happen next?

### Global operating rule

> Every commercial object must end in a conclusion or a next action.

No RFQ, opportunity, activity commitment, follow-up, agreement risk, or commercial process may remain indefinitely open without an explicit outcome or an active next step.

---

## 2. Product Principles

### 2.1 Execution before dashboards

The Home page is not a KPI dashboard. Its first responsibility is to surface incomplete, overdue, stale, or at-risk commercial work.

### 2.2 Evidence before opinion

Commercial conclusions must be grounded in ERP data, registered activities, RFQs, opportunities, agreements, documents, and user-entered context.

### 2.3 One commercial reality

Customers, activities, RFQs, opportunities, agreements, and reports are interconnected entities. Information must not be duplicated across disconnected modules.

### 2.4 Incremental extension

The platform is already functional. Existing working modules must not be removed or redesigned unless explicitly required. New capabilities extend the current system.

### 2.5 Drillability

Every KPI, alert, count, comparison, and recommendation must lead to the underlying records.

### 2.6 Spanish interface, English internals

- UI labels, messages, actions, navigation, reports, and user-facing content: Spanish.
- Classes, functions, endpoints, tables, migrations, logs, tests, and technical documentation: English.

### 2.7 HTML-native reporting

The system generates live HTML experiences, not static documents. PDF is not a native format and may only be produced through browser printing when needed.

---

## 3. Product Roles

### Sales Representative

- Registers and updates commercial activities.
- Maintains contacts, RFQs, opportunities, and follow-ups.
- Concludes open commercial processes.
- Uses Home as the daily execution queue.
- Uses Ask for customer and territory analysis.

### Commercial Manager

- Reviews team execution, coverage, pipeline, RFQs, agreements, and risk.
- Maintains manual watchlists.
- Conducts one-on-one reviews.
- Uses Ask as a commercial analyst.
- Generates executive reports.

### Administrator

- Manages configuration, imports, catalogs, permissions, and system integrity.
- Reviews import histories and execution logs.

---

## 4. System Architecture

### 4.1 Source systems

- ERP: authoritative source for customers and sales.
- Commercial Command Center: authoritative source for activities, contacts created internally, RFQs, opportunities, follow-ups, report narratives, evidence, and management workflows.
- Google Workspace: calendar and productivity integration.

### 4.2 Core architectural boundaries

- Imports are manual and auditable.
- No automatic ERP synchronization in the initial scope.
- Sales imports are append-only and idempotent.
- Customer imports use UPSERT while preserving internal IDs.
- Uploaded source files, hashes, warnings, and execution results are retained.

### 4.3 Cross-cutting services

- Authentication and authorization.
- Audit trail.
- Evidence storage.
- Notification and attention engine.
- Ask investigation engine.
- Report composition engine.
- Search and entity linking.

---

## 5. Module Map

### Foundation

1. ERP Import Center
2. Commercial Activities
3. Customer Workspace
4. Home

### Execution

5. RFQs
6. Opportunities
7. Follow-ups
8. Google Calendar integration

### Intelligence

9. Ask
10. Reports / Executive Report Engine
11. Executive Briefing

### Management

12. Sales Management
13. One-on-One Reviews
14. Watchlists and Agreement Monitoring

---

## 6. ERP Import Center

### 6.1 User experience

The module contains two primary cards:

- **Actualizar Ventas**
- **Sincronizar Clientes**

Each import follows this flow:

1. Select file.
2. Validate schema before processing.
3. Show preview.
4. Show warnings for extra columns.
5. Stop on missing required columns.
6. Execute only after confirmation.
7. Save original Excel file.
8. Save file hash.
9. Save structured execution log.
10. Display results and history.

### 6.2 Sales rules

- Append only.
- Never insert duplicates.
- Reprocessing the same file must be idempotent.
- A file containing only duplicates completes with a warning that no records changed.

### 6.3 Customer rules

- UPSERT by the approved ERP business key.
- Preserve internal customer IDs.
- Update ERP-controlled fields.
- Preserve internal-only attributes unless explicitly mapped.

### 6.4 Audit requirements

Every execution records:

- User.
- Timestamp.
- Source filename.
- Stored file path.
- File hash.
- Import type.
- Schema version.
- Rows read.
- Rows inserted.
- Rows updated.
- Rows skipped.
- Duplicate count.
- Warnings.
- Errors.
- JSON execution log.

---

## 7. Commercial Activities

### 7.1 Concept

The module is named **Actividades**, not Visitas. A visit is one activity type. Activities are transversal and feed customers, opportunities, RFQs, management, reports, and Ask.

### 7.2 Required field groups

#### General

- Fecha actividad
- Tipo actividad
- Asesor
- Participantes Lugo Hermanos
- Cliente
- Contacto
- Cargo

The customer must be selected from the database. Contacts may be selected or created inline.

#### Business context

- Motivo
- Resumen
- Necesidad detectada
- Riesgo detectado

#### Competition

- Competidores involucrados

#### Products

- Productos discutidos

#### Business lines

- Líneas de negocio

#### Supplier participation

- Participó proveedor
- Proveedor
- Persona
- Cargo
- Objetivo

#### Opportunity relationship

- Ninguna
- Oportunidad existente
- Crear oportunidad
- Valor potencial

#### Follow-up

- Crear seguimiento
- Acción
- Responsable
- Fecha

#### Evidence

- Multiple photos
- PDFs
- Description per evidence item

#### Location

- Ciudad
- Planta / Sede
- Área visitada

#### Result

Multi-select examples:

- Oportunidad identificada
- RFQ recibida
- Cotización solicitada
- Capacitación realizada
- Soporte realizado
- Seguimiento requerido
- Cliente sin necesidad
- Pendiente información
- Otro

### 7.3 Rules

- Activities appear in the customer timeline.
- Activities may relate to an opportunity, RFQ, agreement, follow-up, or report.
- Activity evidence is available to the report engine.
- Commitments generated by an activity must have a responsible person and due date.
- Overdue commitments appear on Home.
- An activity must not be edited in a way that destroys its historical evidence; important changes require audit history.

---

## 8. Customer Workspace

### 8.1 Tabs

- Resumen
- Ventas
- Oportunidades
- Actividades
- Contactos
- RFQs
- Convenios
- Documentos

### 8.2 Customer summary

The summary must combine:

- Current commercial status.
- Recent sales trend.
- Open opportunities.
- Open RFQs.
- Last activity.
- Next action.
- Agreement status.
- Attention items.
- Ask opinion.

### 8.3 Contacts

Fields:

- Nombre
- Cargo
- Email
- Celular
- Área
- Influencia
- Activo / Inactivo
- Notas

Derived fields:

- Última actividad
- Número de actividades
- Oportunidades relacionadas

WhatsApp is not a dedicated field.

### 8.4 Agreements

The existing Convenios module remains and is improved incrementally. It may be enriched with derived information, monitoring rules, risk indicators, activities, value delivered, and Ask analysis.

---

## 9. Home — Daily Commercial Execution

### 9.1 Purpose

Home answers:

> ¿Qué debes hacer hoy?

It does not begin with business KPIs. It begins with objects that require action.

### 9.2 Shared layout by role

- Requiere atención
- Hoy
- Actividad reciente
- Ask

The layout is shared by managers and sales representatives, while content changes according to role and permissions.

### 9.3 Attention engine

Home surfaces, at minimum:

- RFQs requiring conclusion.
- RFQs without update beyond the configured threshold.
- Opportunities without recent activity.
- Opportunities with expired expected close dates.
- Overdue follow-ups.
- Activity commitments overdue.
- Priority customers without visits in 30, 60, or 90 days.
- Agreements with risks, missing actions, or upcoming milestones.
- Records missing required commercial conclusions.

### 9.4 Object completion rule

Every surfaced item must offer a direct action, such as:

- Update.
- Conclude.
- Reschedule.
- Assign.
- Create next action.
- Link activity.
- Mark as not applicable with reason.

Dismissal without a reason is not allowed for material commercial items.

---

## 10. RFQs

### 10.1 Entity decision

An RFQ is an independent commercial entity. It does not automatically create an opportunity.

An RFQ may:

- Exist without an opportunity.
- Be linked to an existing opportunity.
- Lead to creation of an opportunity.
- End in a sale.
- End without sale.

Multiple RFQs may belong to one opportunity.

### 10.2 Lifecycle

Suggested states:

- Recibida
- En análisis
- Cotización en preparación
- Cotización enviada
- En seguimiento
- Ganada
- Perdida
- Cancelada

### 10.3 Required conclusion

An RFQ cannot remain open indefinitely. It must end with:

- Ganada.
- Perdida with reason.
- Cancelada with reason.
- Converted or linked to an active opportunity with a next action.

### 10.4 Attention conditions

- No update within threshold.
- Quotation due date approaching or overdue.
- Customer response pending beyond threshold.
- Missing assigned owner.
- Missing next action.
- Open after expected decision date.

These conditions feed Home and Sales Management.

---

## 11. Opportunities

### 11.1 Purpose

Opportunities represent true commercial projects or meaningful pursuits, not every quotation.

### 11.2 Core attributes

- Customer.
- Name.
- Owner.
- Business line.
- Stage.
- Potential value.
- Probability.
- Expected close date.
- Need / problem.
- Proposed solution.
- Competitors.
- Risks.
- Next action.
- Related activities.
- Related RFQs.
- Related contacts.
- Outcome and loss reason.

### 11.3 Lifecycle discipline

An opportunity must always have:

- A current stage.
- A next action.
- A responsible owner.
- A next-action date.

Stale opportunities appear on Home and in management reviews.

---

## 12. Ask — Commercial Analyst

### 12.1 Identity

Ask acts as a Commercial Analyst and behaves like a demanding Commercial Director. It is not a chatbot and not an SQL assistant.

### 12.2 Response standards

Ask must:

- Be evidence-based.
- Be direct and objective.
- Challenge assumptions.
- Separate facts, inferences, and recommendations.
- Explain causes, not only display KPIs.
- Investigate beyond the literal user question.
- State when evidence is insufficient.
- Redirect attention to a more important commercial issue when justified.

### 12.3 Investigation behavior

Ask may perform multi-stage investigation across:

- Sales.
- Customers.
- Activities.
- Contacts.
- RFQs.
- Opportunities.
- Agreements.
- Follow-ups.
- Reports.
- Management data.

Expected internal behavior:

1. Interpret request and context.
2. Identify relevant entities and time period.
3. Query multiple sources.
4. Form hypotheses.
5. Validate or reject hypotheses.
6. Build an evidence-backed answer.
7. Recommend actions.

### 12.4 Placement

Ask is persistent and context-aware throughout the platform. It can use the current customer, opportunity, RFQ, agreement, report, or management view as context.

---

## 13. Executive Report Engine

### 13.1 Format

All reports are HTML-native and URL-addressable.

Examples:

- `/reportes/clientes/{customer_slug}`
- `/reportes/oportunidades/{opportunity_id}`
- `/reportes/convenios/{agreement_id}`
- `/reportes/gerencia/{period}`

### 13.2 Reporting philosophy

Reports are live web experiences with an industrial, professional, consulting-grade visual standard inspired by leading industrial distributors and manufacturers.

The reference example is the executive HTML report already provided by the user, using an Applied Industrial-style visual direction.

### 13.3 Content sources

The principal evidence source is Commercial Activities, including:

- Visit summaries.
- Needs.
- Risks.
- Products discussed.
- Supplier participation.
- Results.
- Commitments.
- Photos.
- Documents.
- Related RFQs and opportunities.

Additional sources include:

- ERP sales.
- Customer data.
- Contacts.
- Agreements.
- Opportunities.
- RFQs.
- Follow-ups.
- Calculations.
- Manual content.

### 13.4 Manual content

Users may add information that does not yet exist in structured data, without creating fictitious activities.

Examples:

- Customer context.
- Background.
- Program objectives.
- Technical explanation.
- Expected benefits.
- Estimated savings.
- Conclusions.
- Recommendations.
- External images.
- Special sections.

Each block retains its source internally:

- Activity.
- ERP.
- System calculation.
- Ask-generated.
- Manual.

### 13.5 Block-based composition

Reports are assembled from reusable blocks, including:

- Hero / Cover
- Executive Summary
- KPIs
- Sales
- Timeline
- Activities
- Evidence Gallery
- RFQs
- Opportunities
- Agreements
- Products Sold
- Products Recommended
- Success Cases
- Value Generated
- Emergency Response
- Training
- Engineering Findings
- Risks
- Recommendations
- Next Steps
- Annexes

Users can:

- Add blocks.
- Remove or hide blocks.
- Reorder blocks.
- Edit titles.
- Edit narrative.
- Add manual content.
- Select evidence.
- Regenerate an Ask-authored block.
- Lock blocks against regeneration.

### 13.6 Strategic narratives

The same data may support different stories. The selected narrative changes prioritization, ordering, emphasis, tone, metrics, and recommendations without altering source facts.

Supported narrative types include:

- Comercial
- Gestión de Valor
- Convenio
- Ejecutivo
- Ingeniería
- Confiabilidad
- Emergencias
- Capacitación
- Proyecto
- Seguimiento
- Personalizada

A custom narrative accepts a user instruction such as:

- “Resaltar el valor generado durante el convenio.”
- “Demostrar nuestra capacidad de atención de emergencias.”
- “Orientar el reporte a una nueva venta.”

### 13.7 Publication states

Suggested report states:

- Draft.
- In review.
- Published.
- Archived.

Published reports must preserve an approved narrative version while allowing the underlying live data to be refreshed according to explicit refresh rules. The system must distinguish between locked editorial content and live data blocks.

---

## 14. Sales Management and One-on-One Reviews

### 14.1 Tabs

- Resumen
- Pipeline
- Actividades
- Clientes
- RFQs
- Impacto
- Ask

### 14.2 Summary

- Meta mensual COP
- Ventas
- Cumplimiento
- Proyección

### 14.3 Comparisons

- Versus target.
- Versus previous month.
- Versus previous year.
- Versus team.
- Versus top seller.

### 14.4 Coverage

- Assigned customers.
- Visited customers.
- No visit in 30, 60, or 90 days.
- Abandoned A customers.
- Territory coverage.

### 14.5 Core KPIs

- Target.
- Sales.
- Coverage.
- Activities.
- Conversion.
- Portfolio.
- Commercial health.

Every KPI must be drillable.

### 14.6 Management controls

- Manual watchlist.
- Automatic agreement monitoring.
- Advisor attention queue.
- Stale opportunities.
- RFQs requiring conclusion.
- Follow-ups overdue.
- Customers at risk.

---

## 15. Notifications and Attention Rules

The system should use configurable thresholds rather than hard-coded business assumptions.

Examples:

- RFQ stale after X days.
- Opportunity stale after X days by stage.
- Priority customer without activity after X days.
- Agreement review due X days before milestone.
- Follow-up reminder X days before due date.

Each attention item records:

- Rule that triggered it.
- Trigger date.
- Severity.
- Assigned user.
- Related entity.
- Resolution action.
- Resolution date.
- Resolution reason.

---

## 16. Audit, Integrity, and Traceability

### 16.1 Audit history

Material changes must be auditable, including:

- Ownership.
- Status.
- Stage.
- Value.
- Expected close date.
- Conclusions.
- Loss reasons.
- Report approvals.
- Manual report content.

### 16.2 Source traceability

Ask and reports must be able to identify the source records supporting factual claims.

### 16.3 Soft deletion

Commercial entities should normally use archival or inactive states rather than destructive deletion.

---

## 17. UI Standards

### 17.1 General

- Spanish UI.
- Clear hierarchy.
- Minimal unnecessary navigation.
- Responsive layout.
- Direct actions from alerts.
- Consistent status badges.
- Accessible forms.

### 17.2 Home

- Attention-first.
- No decorative KPI overload.
- Clear due dates and responsible users.
- Direct resolution actions.

### 17.3 Reports

- Industrial premium visual language.
- Applied Industrial-style direction.
- Strong hero sections.
- Cards, timelines, galleries, charts, and evidence.
- Professional enough for customer and executive presentation.
- Browser print stylesheet for optional PDF output.

---

## 18. Implementation Governance

### 18.1 Documentation workflow

- One module = one Markdown specification.
- One Markdown specification = complete implementation scope.
- One Codex prompt = complete implementation, including backend, frontend, migrations, tests, and documentation updates.
- Do not fragment one module into multiple artificial sprints.

### 18.2 Definition of done for a module

A module is complete when it includes:

- Database migrations.
- Backend domain logic.
- API or server routes.
- Frontend UI in Spanish.
- Authorization.
- Validation.
- Audit behavior.
- Attention-engine integration where applicable.
- Ask/report integration where applicable.
- Automated tests.
- Seed or fixture support where needed.
- Updated technical documentation.

### 18.3 Change control

Locked product decisions are not revisited unless the Product Owner explicitly changes them.

---

## 19. Initial Implementation Sequence

1. Confirm current repository architecture and existing features.
2. Implement or complete ERP Import Center.
3. Implement Commercial Activities.
4. Expand Customer Workspace.
5. Implement Home attention engine.
6. Implement RFQ lifecycle and conclusion discipline.
7. Complete Opportunities and follow-up discipline.
8. Integrate Google Calendar.
9. Implement Ask investigation foundation.
10. Implement Executive Report Engine.
11. Implement Sales Management.
12. Add Executive Briefing.

---

## 20. Locked Decisions Summary

- Product is a Commercial Operating System.
- ERP is source of truth for customers and sales.
- Google Workspace is leveraged, not replaced.
- Ask is a Commercial Analyst, not a chatbot.
- Home answers “¿Qué debes hacer hoy?”.
- Every commercial object requires a conclusion or next action.
- RFQ is an independent entity and does not automatically create an opportunity.
- Activities are the principal source of report evidence.
- Reports are HTML-native, live, URL-addressable experiences.
- Manual report content is allowed and source-tracked.
- Reports use strategic narratives adapted to each customer and objective.
- Existing functionality is extended incrementally, not removed without explicit instruction.

