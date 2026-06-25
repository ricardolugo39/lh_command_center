RAW_TABLES = [
    "raw_sales",
    "raw_customers",
    "raw_product_classification",
    "raw_customer_activity",
    "raw_crm",
    "raw_quotes",
]

DIM_TABLES = [
    "dim_product_classification",
    "dim_customer_activity",
    "dim_customer",
]

FACT_TABLES = [
    "fact_sales",
    "fact_crm",
    "fact_quotes",
]


ALL_TABLES = RAW_TABLES + DIM_TABLES + FACT_TABLES