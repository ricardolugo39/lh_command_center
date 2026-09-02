RAW_TABLES = [
    "raw_sales",
    "raw_customers",
    "inventario_snapshot",
    "raw_product_classification",
    "raw_customer_activity",
    "raw_crm",
    "raw_quotes",
]

DIM_TABLES = [
    "dim_product_category",
    "dim_customer_activity",
    "dim_customer",
]

FACT_TABLES = [
    "fact_sales",
    "fact_crm",
    "fact_quotes",
]

OPERATIONAL_TABLES = [
    "ws_customers",
    "ws_projects",
    "ws_activities",
    "ws_followups",
    "ws_project_quotes",
    "ws_project_brands",
    "ws_project_files",
    "ws_initiatives",
    "ws_initiative_events",
    "ws_initiative_learnings",
    "ws_initiative_decisions",
    "ws_agreements",
    "ws_agreement_items",
    "ws_agreement_documents",
    "ws_customer_portfolio_metadata",
    "ws_approval_types",
    "ws_commercial_approvals",
    "ws_commercial_approval_decisions",
    "ws_commercial_approval_history",
    "ws_commercial_approval_attachments",
    "ws_commercial_visits",
    "ws_visit_sync_runs",
    "ws_visit_customer_matches",
    "ws_visit_followups",
    "erp_import_executions",
    "erp_import_issues",
    "erp_fob_price_history",
    "ws_users",
    "contacts",
    "activity_participants",
    "activity_results",
    "activity_evidence",
    "activity_history",
    "rfqs",
    "rfq_items",
    "rfq_status_history",
    "rfq_conclusions",
    "rfq_documents",
    "rfq_email_threads",
    "rfq_email_messages",
    "ask_analyses",
    "ask_messages",
    "ask_files",
    "ask_artifacts",
    "stock_planning_vendor_profiles",
    "stock_planning_product_catalog",
    "stock_planning_branches",
    "stock_planning_families",
    "stock_planning_family_members",
    "stock_planning_transformations",
    "stock_planning_transformation_inputs",
    "stock_planning_transit_supplies",
    "stock_planning_snapshots",
    "stock_planning_snapshot_products",
    "stock_planning_snapshot_inventory",
    "stock_planning_snapshot_transit",
    "stock_planning_snapshot_issues",
    "stock_planning_snapshot_fob_prices",
    "stock_planning_snapshot_sales_movements",
    "stock_planning_replenishment_runs",
    "stock_planning_import_requests",
    "stock_planning_notifications",
    "stock_planning_analysis_inputs",
]

# Backward-compatible name for callers that still use the old registry label.
PROJECT_WORKSPACE_TABLES = OPERATIONAL_TABLES

ALL_TABLES = (
    RAW_TABLES
    + DIM_TABLES
    + FACT_TABLES
    + OPERATIONAL_TABLES
)
