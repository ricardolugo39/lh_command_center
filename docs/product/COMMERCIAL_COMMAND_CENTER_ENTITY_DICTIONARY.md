# Commercial Command Center — Entity Dictionary

**Status:** Baseline dictionary for implementation specifications  
**Convention:** User-facing labels are Spanish; internal entity and field names are English.

---

## 1. User

**Spanish label:** Usuario / Asesor  
**Internal name:** `User`

Purpose: authenticated person who performs or manages commercial work.

Minimum fields:

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Nombre | `full_name` | string | Yes | Display name. |
| Email | `email` | string | Yes | Unique login identity. |
| Rol | `role` | enum | Yes | Sales rep, manager, admin. |
| Activo | `is_active` | boolean | Yes | Inactive users retained historically. |
| Zona horaria | `timezone` | string | Yes | Default organization or user timezone. |

---

## 2. Customer

**Spanish label:** Cliente  
**Internal name:** `Customer`

Purpose: commercial workspace linked to the ERP customer.

Minimum fields:

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| ID interno | `id` | identifier | Yes | Stable internal ID. |
| Código ERP | `erp_customer_code` | string | Yes | Authoritative business key. |
| Razón social | `legal_name` | string | Yes | ERP-controlled. |
| Nombre comercial | `trade_name` | string | No | ERP or internal enrichment. |
| NIT / Identificación | `tax_id` | string | No | ERP-controlled. |
| Ciudad | `city` | string | No | ERP-controlled or normalized. |
| Dirección | `address` | string | No | ERP-controlled. |
| Asesor asignado | `assigned_user_id` | FK | No | Internal assignment. |
| Prioridad | `priority_tier` | enum | No | A/B/C or configured model. |
| Estado comercial | `commercial_status` | enum | No | Internal enrichment. |
| Activo | `is_active` | boolean | Yes | Preserve history when inactive. |
| Última actividad | derived | datetime | No | Computed. |
| Próxima acción | derived | datetime | No | Computed from open follow-ups and entities. |

---

## 3. Contact

**Spanish label:** Contacto  
**Internal name:** `Contact`

Purpose: person associated with a customer.

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Cliente | `customer_id` | FK | Yes | Parent customer. |
| Nombre | `full_name` | string | Yes | |
| Cargo | `job_title` | string | No | |
| Email | `email` | string | No | |
| Celular | `mobile_phone` | string | No | |
| Área | `department` | string | No | |
| Influencia | `influence_level` | enum | No | Decision maker, influencer, user, etc. |
| Activo | `is_active` | boolean | Yes | |
| Notas | `notes` | text | No | |
| Última actividad | derived | datetime | No | |
| Número de actividades | derived | integer | No | |
| Oportunidades relacionadas | derived | integer | No | |

---

## 4. Activity

**Spanish label:** Actividad  
**Internal name:** `Activity`

Purpose: evidence-bearing commercial interaction.

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Fecha actividad | `activity_at` | datetime | Yes | |
| Tipo actividad | `activity_type_id` | FK / enum | Yes | Configurable catalog. |
| Asesor | `advisor_user_id` | FK | Yes | Primary owner. |
| Cliente | `customer_id` | FK | Yes | Database selection only. |
| Contacto | `contact_id` | FK | No | May be created inline. |
| Cargo | derived | string | No | Autofilled from contact. |
| Motivo | `purpose` | text | Yes | |
| Resumen | `summary` | text | Yes | |
| Necesidad detectada | `identified_need` | text | No | |
| Riesgo detectado | `identified_risk` | text | No | |
| Participó proveedor | `supplier_participated` | boolean | Yes | |
| Proveedor | `supplier_id` | FK | Conditional | Required when supplier participated. |
| Persona proveedor | `supplier_person_name` | string | No | |
| Cargo proveedor | `supplier_person_role` | string | No | |
| Objetivo proveedor | `supplier_objective` | text | No | |
| Relación oportunidad | `opportunity_id` | FK | No | Existing or newly created. |
| Relación RFQ | `rfq_id` | FK | No | Optional. |
| Relación convenio | `agreement_id` | FK | No | Optional. |
| Valor potencial | `potential_value` | decimal | No | Currency required when set. |
| Ciudad | `city` | string | No | |
| Planta / Sede | `site_name` | string | No | |
| Área visitada | `visited_area` | string | No | |
| Creado por | `created_by` | FK | Yes | Audit. |
| Creado en | `created_at` | datetime | Yes | Audit. |
| Actualizado por | `updated_by` | FK | Yes | Audit. |
| Actualizado en | `updated_at` | datetime | Yes | Audit. |

Related collections:

- `participants`
- `competitors`
- `products`
- `business_lines`
- `results`
- `evidence_items`
- `follow_ups`

---

## 5. ActivityParticipant

**Spanish label:** Participante Lugo Hermanos  
**Internal name:** `ActivityParticipant`

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `activity_id` | FK | Yes | |
| `user_id` | FK | Yes | |

Unique pair: activity and user.

---

## 6. Evidence

**Spanish label:** Evidencia  
**Internal name:** `Evidence`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Archivo | `file_path` / storage key | file | Yes | Never expose raw private path. |
| Nombre archivo | `original_filename` | string | Yes | |
| Tipo MIME | `mime_type` | string | Yes | |
| Tamaño | `size_bytes` | integer | Yes | |
| Descripción | `description` | text | No | Per evidence item. |
| Actividad | `activity_id` | FK | Yes initially | Principal source entity. |
| Subido por | `uploaded_by` | FK | Yes | |
| Fecha carga | `uploaded_at` | datetime | Yes | |
| Orden | `display_order` | integer | Yes | Gallery ordering. |
| Activo | `is_active` | boolean | Yes | Soft removal. |

---

## 7. FollowUp

**Spanish label:** Seguimiento / Próxima acción  
**Internal name:** `FollowUp`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Cliente | `customer_id` | FK | Yes | |
| Acción | `action_text` | text | Yes | |
| Responsable | `responsible_user_id` | FK | Yes | |
| Fecha | `due_at` | datetime | Yes | |
| Estado | `status` | enum | Yes | Pending, in progress, completed, rescheduled, cancelled. |
| Prioridad | `priority` | enum | No | |
| Actividad origen | `activity_id` | FK | No | |
| RFQ | `rfq_id` | FK | No | |
| Oportunidad | `opportunity_id` | FK | No | |
| Convenio | `agreement_id` | FK | No | |
| Fecha completado | `completed_at` | datetime | No | |
| Motivo cancelación | `cancellation_reason` | text | Conditional | |
| Reprogramado desde | `rescheduled_from_id` | FK | No | Traceability. |

Validation:

- Pending or in-progress requires due date and responsible user.
- Cancelled requires reason.
- Completed requires completion timestamp.

---

## 8. RFQ

**Spanish label:** RFQ / Solicitud de cotización  
**Internal name:** `RFQ`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Número | `rfq_number` | string | Yes | Unique human-readable identifier. |
| Cliente | `customer_id` | FK | Yes | |
| Contacto | `contact_id` | FK | No | |
| Asesor | `owner_user_id` | FK | Yes | |
| Fecha recibida | `received_at` | datetime | Yes | |
| Fecha requerida | `required_by` | datetime | No | Customer requirement. |
| Estado | `status` | enum | Yes | Received, analysis, preparing, sent, follow-up, won, lost, cancelled. |
| Descripción | `description` | text | Yes | |
| Valor estimado | `estimated_value` | decimal | No | |
| Moneda | `currency_code` | string | Conditional | Required with monetary values. |
| Oportunidad | `opportunity_id` | FK | No | Never auto-created. |
| Próxima acción | `next_action` | text | Conditional | Required while open. |
| Fecha próxima acción | `next_action_at` | datetime | Conditional | Required while open. |
| Fecha esperada decisión | `expected_decision_at` | datetime | No | Attention threshold reference. |
| Última actualización | `last_activity_at` | datetime | Derived / stored | Used by attention engine. |
| Cerrada en | `closed_at` | datetime | No | |

---

## 9. RFQItem

**Spanish label:** Ítem RFQ  
**Internal name:** `RFQItem`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| RFQ | `rfq_id` | FK | Yes | |
| Producto | `product_id` | FK | No | Allow free text. |
| Descripción | `description` | text | Yes | |
| Cantidad | `quantity` | decimal | No | |
| Unidad | `unit_of_measure` | string | No | |
| Precio cotizado | `quoted_unit_price` | decimal | No | |
| Moneda | `currency_code` | string | Conditional | |

---

## 10. RFQStatusHistory

**Spanish label:** Historial RFQ  
**Internal name:** `RFQStatusHistory`

| Field | Type | Required |
|---|---:|---:|
| `rfq_id` | FK | Yes |
| `from_status` | enum | No |
| `to_status` | enum | Yes |
| `changed_by` | FK | Yes |
| `changed_at` | datetime | Yes |
| `comment` | text | No |

---

## 11. RFQConclusion

**Spanish label:** Conclusión RFQ  
**Internal name:** `RFQConclusion`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Resultado | `outcome` | enum | Yes | Won, lost, cancelled, continued in opportunity. |
| Motivo | `reason` | text | Conditional | Required for lost/cancelled. |
| Fecha conclusión | `concluded_at` | datetime | Yes | |
| Valor final | `final_value` | decimal | No | |
| Venta ERP | `erp_sale_reference` | string | No | |
| Oportunidad | `opportunity_id` | FK | Conditional | For continued-in-opportunity. |
| Concluido por | `concluded_by` | FK | Yes | |

---

## 12. Opportunity

**Spanish label:** Oportunidad  
**Internal name:** `Opportunity`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Nombre | `name` | string | Yes | |
| Cliente | `customer_id` | FK | Yes | |
| Asesor | `owner_user_id` | FK | Yes | |
| Línea de negocio | `business_line_id` | FK | No | |
| Etapa | `stage` | enum / FK | Yes | Configurable pipeline. |
| Valor potencial | `potential_value` | decimal | No | |
| Moneda | `currency_code` | string | Conditional | |
| Probabilidad | `probability_percent` | integer | No | 0–100. |
| Fecha esperada cierre | `expected_close_date` | date | No | |
| Necesidad | `customer_need` | text | Yes | |
| Solución propuesta | `proposed_solution` | text | No | |
| Riesgos | `risks` | text | No | Structured risks may follow later. |
| Próxima acción | `next_action` | text | Conditional | Required while active. |
| Fecha próxima acción | `next_action_at` | datetime | Conditional | Required while active. |
| Estado | `status` | enum | Yes | Active, won, lost, cancelled, on hold. |
| Fecha cierre | `closed_at` | datetime | No | |
| Motivo pérdida | `loss_reason` | text | Conditional | |
| Fecha revisión | `review_at` | datetime | Conditional | Required when on hold. |

---

## 13. OpportunityStageHistory

**Spanish label:** Historial de etapa  
**Internal name:** `OpportunityStageHistory`

| Field | Type | Required |
|---|---:|---:|
| `opportunity_id` | FK | Yes |
| `from_stage` | string / FK | No |
| `to_stage` | string / FK | Yes |
| `changed_by` | FK | Yes |
| `changed_at` | datetime | Yes |
| `comment` | text | No |

---

## 14. Agreement

**Spanish label:** Convenio  
**Internal name:** `Agreement`

The physical field set must be reconciled with the existing module before implementation. Minimum conceptual additions:

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Cliente | `customer_id` | FK | Yes | Preserve current relationship. |
| Nombre | `name` | string | Yes | |
| Estado | `status` | enum | Yes | |
| Fecha inicio | `start_date` | date | No | |
| Fecha fin | `end_date` | date | No | |
| Responsable | `owner_user_id` | FK | No | |
| Objetivo | `objective` | text | No | |
| Próxima revisión | `next_review_at` | datetime | No | |

---

## 15. AgreementMilestone

**Spanish label:** Hito del convenio  
**Internal name:** `AgreementMilestone`

| UI label | Internal field | Type | Required |
|---|---|---:|---:|
| Convenio | `agreement_id` | FK | Yes |
| Nombre | `name` | string | Yes |
| Fecha | `due_at` | datetime | Yes |
| Estado | `status` | enum | Yes |
| Responsable | `owner_user_id` | FK | No |
| Descripción | `description` | text | No |

---

## 16. AgreementRisk

**Spanish label:** Riesgo del convenio  
**Internal name:** `AgreementRisk`

| UI label | Internal field | Type | Required |
|---|---|---:|---:|
| Convenio | `agreement_id` | FK | Yes |
| Tipo | `risk_type` | enum / FK | Yes |
| Severidad | `severity` | enum | Yes |
| Descripción | `description` | text | Yes |
| Mitigación | `mitigation` | text | No |
| Responsable | `owner_user_id` | FK | No |
| Fecha revisión | `review_at` | datetime | No |
| Estado | `status` | enum | Yes |

---

## 17. ValueRecord

**Spanish label:** Registro de valor  
**Internal name:** `ValueRecord`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Cliente | `customer_id` | FK | Yes | |
| Convenio | `agreement_id` | FK | No | |
| Actividad | `activity_id` | FK | No | Evidence source. |
| Tipo de valor | `value_type` | enum / FK | Yes | Savings, downtime avoided, emergency, training, etc. |
| Descripción | `description` | text | Yes | |
| Valor | `amount` | decimal | No | |
| Moneda | `currency_code` | string | Conditional | |
| Método | `measurement_method` | enum | Yes | Measured, calculated, estimated, manual. |
| Supuestos | `assumptions` | text | Conditional | Important for estimates. |
| Fecha | `recorded_at` | datetime | Yes | |
| Registrado por | `created_by` | FK | Yes | |

---

## 18. SalesTransaction

**Spanish label:** Venta ERP  
**Internal name:** `SalesTransaction`

The exact field set depends on the ERP workbook schema. Required conceptual fields:

| Internal field | Type | Required | Notes |
|---|---:|---:|---|
| `source_key` | string | Yes | Unique idempotency key. |
| `customer_id` | FK | Yes | Resolved by ERP customer code. |
| `transaction_date` | date | Yes | |
| `document_number` | string | No | |
| `product_code` | string | No | |
| `description` | string | No | |
| `quantity` | decimal | No | |
| `net_sales` | decimal | Yes | |
| `cost` | decimal | No | |
| `gross_margin` | decimal | No | Derived or imported. |
| `currency_code` | string | Yes | |
| `source_import_execution_id` | FK | Yes | Audit. |

---

## 19. ImportExecution

**Spanish label:** Ejecución de importación  
**Internal name:** `ImportExecution`

| UI label | Internal field | Type | Required |
|---|---|---:|---:|
| Tipo importación | `import_type` | enum | Yes |
| Archivo original | `original_filename` | string | Yes |
| Archivo almacenado | `stored_file_path` | string | Yes |
| Hash | `file_hash` | string | Yes |
| Versión esquema | `schema_version` | string | Yes |
| Estado | `status` | enum | Yes |
| Filas leídas | `rows_read` | integer | Yes |
| Insertadas | `rows_inserted` | integer | Yes |
| Actualizadas | `rows_updated` | integer | Yes |
| Omitidas | `rows_skipped` | integer | Yes |
| Duplicadas | `duplicates_count` | integer | Yes |
| Advertencias | `warnings_json` | JSON | No |
| Errores | `errors_json` | JSON | No |
| Log ejecución | `execution_log_json` | JSON | Yes |
| Ejecutado por | `executed_by` | FK | Yes |
| Inicio | `started_at` | datetime | Yes |
| Fin | `finished_at` | datetime | No |

---

## 20. AttentionItem

**Spanish label:** Requiere atención  
**Internal name:** `AttentionItem`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Tipo | `attention_type` | enum | Yes | RFQ stale, follow-up overdue, etc. |
| Título | `title` | string | Yes | Spanish user-facing summary. |
| Descripción | `description` | text | Yes | |
| Severidad | `severity` | enum | Yes | Info, warning, critical. |
| Responsable | `assigned_user_id` | FK | Yes | |
| Fecha activación | `triggered_at` | datetime | Yes | |
| Fecha límite | `due_at` | datetime | No | |
| Estado | `status` | enum | Yes | Open, in progress, resolved, dismissed. |
| Regla | `trigger_rule_code` | string | Yes | Traceable configuration. |
| Tipo entidad | `entity_type` | enum | Yes | Controlled polymorphic reference. |
| ID entidad | `entity_id` | identifier | Yes | |
| Resuelto en | `resolved_at` | datetime | No | |
| Acción resolución | `resolution_action` | text | No | |
| Motivo descarte | `dismissal_reason` | text | Conditional | Required when dismissed. |

---

## 21. Report

**Spanish label:** Reporte  
**Internal name:** `Report`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Título | `title` | string | Yes | |
| Slug | `slug` | string | Yes | Unique URL key. |
| Tipo sujeto | `subject_type` | enum | Yes | Customer, agreement, opportunity, project, management period. |
| ID sujeto | `subject_id` | identifier | Yes | |
| Narrativa | `narrative_definition_id` | FK | No | Custom narrative allowed. |
| Instrucción narrativa | `custom_narrative_prompt` | text | No | |
| Estado | `status` | enum | Yes | Draft, review, published, archived. |
| Propietario | `owner_user_id` | FK | Yes | |
| Publicado en | `published_at` | datetime | No | |
| URL pública interna | derived | URL | No | Authorization applies. |

---

## 22. ReportBlock

**Spanish label:** Bloque de reporte  
**Internal name:** `ReportBlock`

| UI label | Internal field | Type | Required | Notes |
|---|---|---:|---:|---|
| Reporte | `report_id` | FK | Yes | |
| Tipo bloque | `block_type` | enum / FK | Yes | Hero, executive summary, activities, etc. |
| Título | `title` | string | No | |
| Orden | `display_order` | integer | Yes | |
| Visible | `is_visible` | boolean | Yes | |
| Bloqueado | `is_locked` | boolean | Yes | Prevent Ask regeneration. |
| Comportamiento actualización | `refresh_mode` | enum | Yes | Live, manual, frozen. |
| Contenido manual | `manual_content` | text / JSON | No | Block-specific. |
| Contenido Ask | `generated_content` | text / JSON | No | |
| Configuración | `configuration_json` | JSON | No | Charts, filters, period, layout. |
| Última generación | `generated_at` | datetime | No | |
| Generado por | `generated_by_user_id` | FK | No | User who requested generation. |

---

## 23. ReportBlockSource

**Spanish label:** Fuente del bloque  
**Internal name:** `ReportBlockSource`

| Internal field | Type | Required | Notes |
|---|---:|---:|---|
| `report_block_id` | FK | Yes | |
| `source_type` | enum | Yes | Activity, ERP, RFQ, opportunity, agreement, manual, Ask. |
| `source_entity_id` | identifier | No | Null for aggregate or manual source. |
| `source_description` | string | No | Human-readable trace. |
| `is_primary` | boolean | Yes | |
| `added_at` | datetime | Yes | |

---

## 24. NarrativeDefinition

**Spanish label:** Narrativa  
**Internal name:** `NarrativeDefinition`

| UI label | Internal field | Type | Required |
|---|---|---:|---:|
| Nombre | `name` | string | Yes |
| Código | `code` | string | Yes |
| Descripción | `description` | text | Yes |
| Orden de bloques | `default_block_order_json` | JSON | Yes |
| Métricas prioritarias | `priority_metrics_json` | JSON | No |
| Instrucción Ask | `ask_instruction` | text | Yes |
| Tono | `tone` | string / enum | No |
| Activa | `is_active` | boolean | Yes |

Initial codes:

- `commercial`
- `value`
- `agreement`
- `executive`
- `engineering`
- `reliability`
- `emergency`
- `training`
- `project`
- `follow_up`
- `custom`

---

## 25. AskInvestigation

**Spanish label:** Investigación Ask  
**Internal name:** `AskInvestigation`

| UI label | Internal field | Type | Required |
|---|---|---:|---:|
| Solicitud | `user_query` | text | Yes |
| Contexto | `context_type` + `context_id` | controlled reference | No |
| Periodo inicio | `period_start` | date | No |
| Periodo fin | `period_end` | date | No |
| Fuentes consultadas | `sources_json` | JSON | Yes |
| Hechos | `facts_json` | JSON | Yes |
| Inferencias | `inferences_json` | JSON | Yes |
| Recomendaciones | `recommendations_json` | JSON | Yes |
| Respuesta | `response_text` | text | Yes |
| Solicitado por | `requested_by` | FK | Yes |
| Generado en | `generated_at` | datetime | Yes |

---

## 26. Shared Catalog Entities

The following should normally be normalized catalogs instead of free-form lists:

- `ActivityType`
- `ActivityResult`
- `BusinessLine`
- `Product`
- `Competitor`
- `Supplier`
- `OpportunityStage`
- `RFQLossReason`
- `OpportunityLossReason`
- `RiskType`
- `ValueType`

Catalogs should support active/inactive status and display order.

---

## 27. Shared Audit Fields

Internally owned entities should use the project-standard equivalent of:

- `created_at`
- `created_by`
- `updated_at`
- `updated_by`
- `archived_at`
- `archived_by`
- `version` or optimistic concurrency field where justified

Important lifecycle changes also require dedicated history records.

---

## 28. Required Validation Rules

1. An open RFQ must have owner, next action, and next-action date.
2. A closed RFQ must have a conclusion.
3. Lost or cancelled RFQs require a reason.
4. An active Opportunity must have owner, stage, next action, and next-action date.
5. Lost or cancelled Opportunities require a reason.
6. An on-hold Opportunity requires a review date.
7. A pending FollowUp requires responsible user and due date.
8. Supplier details become conditionally required when supplier participation is true.
9. Monetary values require a currency code.
10. Estimated ValueRecords require assumptions.
11. Manual report content must retain manual-source labeling.
12. Dismissing material AttentionItems requires a reason.
13. Customer selection for activities, RFQs, and opportunities must use an existing Customer record.

---

## 29. Naming Conventions

- Entity classes: singular PascalCase, e.g. `Opportunity`.
- Database tables: follow existing project convention; do not introduce a new convention without repository review.
- API routes: English internal paths unless the current application standard differs.
- UI labels and navigation: Spanish.
- Enums: English internal values with Spanish display mapping.
- Currency: ISO 4217 code.
- Time: timezone-aware UTC storage with localized display.

