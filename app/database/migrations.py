from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from sqlite3 import Connection

from app.database.connection import get_connection


MigrationFunction = Callable[[Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFunction


@dataclass(frozen=True)
class MigrationReport:
    applied_versions: tuple[int, ...]
    current_version: int
    warnings: tuple[str, ...]


def _column_exists(
    connection: Connection,
    table_name: str,
    column_name: str,
) -> bool:
    return any(
        row["name"] == column_name
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    return connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone() is not None


def _add_column(
    connection: Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if not _column_exists(connection, table_name, column_name):
        connection.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )


def _execute_statements(
    connection: Connection,
    statements: tuple[str, ...],
) -> None:
    for statement in statements:
        connection.execute(statement)


def _migration_0001_core_workspace(connection: Connection) -> None:
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS ws_customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                erp_customer_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'prospect',
                objective TEXT NOT NULL,
                proposed_solution TEXT,
                current_blocker TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                FOREIGN KEY (customer_id) REFERENCES ws_customers(id)
                    ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT,
                created_by TEXT NOT NULL DEFAULT 'system',
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ws_projects(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                completed_at TEXT,
                created_by TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ws_projects(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_ws_followups_unique_pending
            ON ws_followups(project_id, due_date, description)
            WHERE status = 'pending'
            """,
        ),
    )


def _migration_0002_opportunity_mvp(connection: Connection) -> None:
    _add_column(connection, "ws_projects", "sales_rep", "TEXT")
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS ws_project_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                quote_number TEXT NOT NULL,
                branch TEXT,
                prefix TEXT NOT NULL,
                quote_date TEXT,
                amount REAL,
                quote_status TEXT,
                erp_user TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ws_projects(id)
                    ON DELETE CASCADE,
                UNIQUE(project_id, prefix, quote_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_project_brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                brand TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ws_projects(id)
                    ON DELETE CASCADE,
                UNIQUE(project_id, brand)
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_ws_customers_unique_erp_customer
            ON ws_customers(erp_customer_id)
            WHERE erp_customer_id IS NOT NULL
                AND TRIM(erp_customer_id) <> ''
            """,
        ),
    )


def _migration_0003_customer_site(connection: Connection) -> None:
    _add_column(connection, "ws_projects", "customer_site_id", "TEXT")


def _migration_0004_quote_domain(connection: Connection) -> None:
    _add_column(
        connection,
        "ws_project_quotes",
        "currency_code",
        "TEXT DEFAULT 'COP'",
    )
    _add_column(connection, "ws_project_quotes", "exchange_rate", "REAL")
    _add_column(
        connection,
        "ws_project_quotes",
        "normalized_amount",
        "REAL",
    )
    _add_column(
        connection,
        "ws_project_quotes",
        "revision",
        "INTEGER DEFAULT 0",
    )
    _add_column(
        connection,
        "ws_project_quotes",
        "exchange_rate_type",
        "TEXT CHECK (exchange_rate_type IS NULL OR "
        "exchange_rate_type IN ('estimated', 'final'))",
    )
    _execute_statements(
        connection,
        (
            """
            UPDATE ws_project_quotes
            SET currency_code = 'COP'
            WHERE currency_code IS NULL OR TRIM(currency_code) = ''
            """,
            """
            UPDATE ws_project_quotes
            SET normalized_amount = amount
            WHERE currency_code = 'COP' AND normalized_amount IS NULL
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ws_project_quotes_project_id
            ON ws_project_quotes(project_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ws_project_quotes_currency
            ON ws_project_quotes(currency_code)
            """,
        ),
    )


def _migration_0005_project_files(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ws_project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER,
            uploaded_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES ws_projects(id)
                ON DELETE CASCADE
        )
        """
    )


def _migration_0006_initiatives(connection: Connection) -> None:
    _add_column(connection, "ws_projects", "initiative_id", "INTEGER")
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS ws_initiatives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning','active','paused','completed')),
                objective TEXT NOT NULL,
                description TEXT,
                strategy TEXT,
                partner TEXT,
                owner TEXT NOT NULL,
                start_date TEXT,
                expected_end_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_initiative_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initiative_id INTEGER NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'update',
                title TEXT NOT NULL,
                details TEXT,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL DEFAULT 'system',
                FOREIGN KEY (initiative_id) REFERENCES ws_initiatives(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_initiative_learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initiative_id INTEGER NOT NULL,
                category TEXT NOT NULL CHECK (
                    category IN (
                        'worked','did_not_work','insight',
                        'objection','recommendation'
                    )
                ),
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL DEFAULT 'system',
                FOREIGN KEY (initiative_id) REFERENCES ws_initiatives(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_initiative_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initiative_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                decided_by TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (initiative_id) REFERENCES ws_initiatives(id)
                    ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_ws_initiatives_status "
            "ON ws_initiatives(status)",
            "CREATE INDEX IF NOT EXISTS idx_ws_initiatives_owner "
            "ON ws_initiatives(owner)",
            "CREATE INDEX IF NOT EXISTS idx_ws_initiative_events_initiative "
            "ON ws_initiative_events(initiative_id, occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_ws_initiative_learnings_initiative "
            "ON ws_initiative_learnings(initiative_id, category)",
            "CREATE INDEX IF NOT EXISTS idx_ws_initiative_decisions_initiative "
            "ON ws_initiative_decisions(initiative_id, decision_date)",
            "CREATE INDEX IF NOT EXISTS idx_ws_projects_initiative_id "
            "ON ws_projects(initiative_id)",
        ),
    )


def _migration_0007_opportunity_closure(connection: Connection) -> None:
    for name, definition in (
        ("close_reason", "TEXT"),
        ("close_comments", "TEXT"),
        ("competitor_company", "TEXT"),
        ("competitor_type", "TEXT"),
        ("competitor_brand", "TEXT"),
        ("won_amount", "REAL"),
        ("order_number", "TEXT"),
        ("customer_po", "TEXT"),
        ("result_changer", "TEXT"),
    ):
        _add_column(connection, "ws_projects", name, definition)


def _migration_0008_agreements(connection: Connection) -> None:
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS ws_agreements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                agreement_number TEXT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (
                    status IN ('draft','active','renewal','expired','closed')
                ),
                agreement_type TEXT,
                supplier TEXT,
                annual_target REAL,
                currency TEXT NOT NULL DEFAULT 'COP',
                start_date TEXT,
                end_date TEXT,
                renewal_date TEXT,
                has_consignment INTEGER NOT NULL DEFAULT 0
                    CHECK (has_consignment IN (0, 1)),
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES ws_customers(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ws_agreement_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agreement_id INTEGER NOT NULL,
                part_number TEXT NOT NULL,
                skf_reference TEXT NOT NULL,
                list_price_usd REAL,
                agreement_price_usd REAL,
                suggested_price_usd REAL,
                product_line TEXT,
                spc TEXT,
                source_file_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agreement_id) REFERENCES ws_agreements(id)
                    ON DELETE CASCADE,
                UNIQUE(agreement_id, part_number, skf_reference)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_ws_agreements_customer_id "
            "ON ws_agreements(customer_id)",
            "CREATE INDEX IF NOT EXISTS idx_ws_agreements_status "
            "ON ws_agreements(status)",
            "CREATE INDEX IF NOT EXISTS idx_ws_agreement_items_agreement_id "
            "ON ws_agreement_items(agreement_id)",
            "CREATE INDEX IF NOT EXISTS idx_ws_agreement_items_part_number "
            "ON ws_agreement_items(part_number)",
            "CREATE INDEX IF NOT EXISTS idx_ws_agreement_items_reference "
            "ON ws_agreement_items(skf_reference)",
        ),
    )


def _migration_0009_agreement_import(connection: Connection) -> None:
    for name, definition in (
        ("source_row_number", "INTEGER"),
        ("internal_sku", "TEXT"),
        ("manufacturer_part_number", "TEXT"),
        ("description", "TEXT"),
        ("negotiated_price", "REAL"),
        ("price_currency", "TEXT"),
        ("unit_of_measure", "TEXT"),
        ("product_start_date", "TEXT"),
        ("product_end_date", "TEXT"),
        ("item_notes", "TEXT"),
        ("normalized_reference", "TEXT"),
    ):
        _add_column(connection, "ws_agreement_items", name, definition)

    _execute_statements(connection, (
        """
        CREATE TABLE IF NOT EXISTS ws_agreement_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            mime_type TEXT,
            file_size INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agreement_id) REFERENCES ws_agreements(id)
                ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ws_agreement_documents_agreement "
        "ON ws_agreement_documents(agreement_id)",
        "CREATE INDEX IF NOT EXISTS idx_ws_agreement_items_normalized_reference "
        "ON ws_agreement_items(normalized_reference)",
    ))


def _migration_0010_agreement_xls_metadata(connection: Connection) -> None:
    _add_column(
        connection,
        "ws_agreement_documents",
        "file_extension",
        "TEXT",
    )


def _migration_0011_agreement_decimal_prices(connection: Connection) -> None:
    for name in (
        "list_price_decimal",
        "negotiated_price_decimal",
        "suggested_price_decimal",
    ):
        _add_column(connection, "ws_agreement_items", name, "TEXT")


def _migration_0012_customer_portfolio_metadata(connection: Connection) -> None:
    _execute_statements(connection, (
        """
        CREATE TABLE IF NOT EXISTS ws_customer_portfolio_metadata (
            erp_customer_id TEXT PRIMARY KEY,
            is_strategic INTEGER NOT NULL DEFAULT 0 CHECK(is_strategic IN (0, 1)),
            branch TEXT,
            advisor TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ws_customer_portfolio_branch ON ws_customer_portfolio_metadata(branch)",
        "CREATE INDEX IF NOT EXISTS idx_ws_customer_portfolio_advisor ON ws_customer_portfolio_metadata(advisor)",
        """
        INSERT OR IGNORE INTO ws_customer_portfolio_metadata (
            erp_customer_id, is_strategic
        )
        SELECT DISTINCT TRIM(erp_customer_id), 1 FROM ws_customers
        WHERE TRIM(COALESCE(erp_customer_id, '')) <> ''
        """,
    ))
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_customer'"
    ).fetchone():
        connection.execute("""
            INSERT INTO ws_customer_portfolio_metadata (
                erp_customer_id, is_strategic, branch, advisor
            )
            SELECT TRIM(customer_id), 0,
                CASE WHEN UPPER(MAX(COALESCE(seller,''))) LIKE '%CALI%'
                     THEN 'Cali' ELSE 'Bogotá' END,
                COALESCE(NULLIF(MAX(seller),''), 'Sin asignar')
            FROM dim_customer
            WHERE TRIM(COALESCE(customer_id,'')) <> ''
            GROUP BY TRIM(customer_id)
            ON CONFLICT(erp_customer_id) DO UPDATE SET
                branch = excluded.branch,
                advisor = excluded.advisor,
                updated_at = CURRENT_TIMESTAMP
        """)


def _migration_0013_customer_responsible_office(connection: Connection) -> None:
    _add_column(connection, "ws_customer_portfolio_metadata", "office", "TEXT")
    connection.execute("""
        UPDATE ws_customer_portfolio_metadata
        SET office = branch
        WHERE office IS NULL AND branch IS NOT NULL
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ws_customer_portfolio_office "
        "ON ws_customer_portfolio_metadata(office)"
    )


def _migration_0014_commercial_approvals(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ws_approval_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS ws_commercial_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            approval_type_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            opportunity_name TEXT NOT NULL,
            manufacturer TEXT,
            branch TEXT,
            sales_representative TEXT,
            product_family TEXT,
            product TEXT,
            quantity REAL,
            competitor TEXT,
            opportunity_value REAL,
            probability REAL,
            current_stage TEXT,
            list_price REAL,
            requested_price REAL,
            requested_discount REAL NOT NULL,
            estimated_margin REAL,
            expected_revenue REAL,
            currency TEXT NOT NULL DEFAULT 'COP',
            reason_code TEXT NOT NULL,
            justification TEXT NOT NULL,
            competitor_price REAL,
            competition_notes TEXT,
            commercial_impact TEXT,
            business_notes TEXT,
            created_by TEXT NOT NULL,
            submitted_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            soft_deleted_at TEXT,
            FOREIGN KEY(project_id) REFERENCES ws_projects(id) ON DELETE RESTRICT,
            FOREIGN KEY(approval_type_id) REFERENCES ws_approval_types(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS ws_commercial_approval_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id INTEGER NOT NULL,
            decision TEXT NOT NULL,
            approver TEXT NOT NULL,
            comments TEXT NOT NULL,
            approved_discount REAL,
            expiration_date TEXT,
            decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(approval_id) REFERENCES ws_commercial_approvals(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS ws_commercial_approval_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            actor TEXT NOT NULL,
            comments TEXT,
            event_data TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(approval_id) REFERENCES ws_commercial_approvals(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS ws_commercial_approval_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            mime_type TEXT,
            file_size INTEGER,
            uploaded_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(approval_id) REFERENCES ws_commercial_approvals(id) ON DELETE RESTRICT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_approvals_project_status ON ws_commercial_approvals(project_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_approval_history_approval ON ws_commercial_approval_history(approval_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_approval_decisions_approval ON ws_commercial_approval_decisions(approval_id,decided_at)",
        "INSERT OR IGNORE INTO ws_approval_types(code,name) VALUES ('commercial_discount','Descuento comercial')",
    ))


def _migration_0015_approval_monetary_decision(connection: Connection) -> None:
    for name, definition in (
        ("requested_discount_percent", "TEXT"),
        ("approved_discount_percent", "TEXT"),
        ("list_unit_price", "TEXT"),
        ("approved_unit_price", "TEXT"),
        ("quantity_decimal", "TEXT"),
        ("approved_total_amount", "TEXT"),
        ("decision_currency", "TEXT"),
        ("decision_comments", "TEXT"),
        ("decided_by", "TEXT"),
    ):
        _add_column(connection, "ws_commercial_approval_decisions", name, definition)


def _migration_0016_approval_erp_price_snapshot(connection: Connection) -> None:
    for name, definition in (
        ("commercial_amount", "TEXT"),
        ("commercial_currency", "TEXT"),
    ):
        _add_column(connection, "ws_projects", name, definition)
    for name, definition in (
        ("product_reference", "TEXT"),
        ("erp_price_source", "TEXT"),
        ("erp_price_retrieved_at", "TEXT"),
    ):
        _add_column(connection, "ws_commercial_approvals", name, definition)


def _migration_0017_commercial_visits(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ws_commercial_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            source_visit_id TEXT NOT NULL,
            source_row_hash TEXT NOT NULL,
            source_created_at TEXT,
            visit_date TEXT,
            advisor_name TEXT,
            advisor_id INTEGER,
            customer_id INTEGER,
            customer_erp_id TEXT,
            source_customer_name TEXT,
            customer_match_status TEXT NOT NULL DEFAULT 'unmatched'
                CHECK(customer_match_status IN ('matched','unmatched','ambiguous')),
            visited_contact_name TEXT,
            visited_contact_role TEXT,
            visit_type TEXT NOT NULL,
            source_visit_type TEXT,
            visit_reason TEXT,
            executive_summary TEXT,
            detected_need TEXT,
            detected_risk TEXT,
            competitor TEXT,
            key_comments TEXT,
            requires_action INTEGER NOT NULL DEFAULT 0 CHECK(requires_action IN (0,1)),
            required_action TEXT,
            follow_up_owner_name TEXT,
            follow_up_owner_id INTEGER,
            commitment_date TEXT,
            generate_opportunity_requested INTEGER NOT NULL DEFAULT 0 CHECK(generate_opportunity_requested IN (0,1)),
            visit_status TEXT NOT NULL,
            source_visit_status TEXT,
            attachment_reference TEXT,
            project_id INTEGER,
            possible_duplicate INTEGER NOT NULL DEFAULT 0 CHECK(possible_duplicate IN (0,1)),
            quality_warnings TEXT,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_payload_json TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id) ON DELETE SET NULL,
            FOREIGN KEY(project_id) REFERENCES ws_projects(id) ON DELETE SET NULL,
            UNIQUE(source_system,source_visit_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_visits_customer_date ON ws_commercial_visits(customer_id,visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_visits_match_status ON ws_commercial_visits(customer_match_status)",
        "CREATE INDEX IF NOT EXISTS idx_visits_project ON ws_commercial_visits(project_id)",
        """CREATE TABLE IF NOT EXISTS ws_visit_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            status TEXT NOT NULL,
            rows_read INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            unchanged_count INTEGER NOT NULL DEFAULT 0,
            unmatched_count INTEGER NOT NULL DEFAULT 0,
            possible_duplicate_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            error_summary TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS ws_visit_customer_matches (
            source_customer_key TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS ws_visit_followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id INTEGER NOT NULL,
            external_key TEXT NOT NULL UNIQUE,
            description TEXT,
            owner_name TEXT,
            due_date TEXT,
            status TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(visit_id) REFERENCES ws_commercial_visits(id) ON DELETE CASCADE
        )""",
    ))


def _migration_0018_erp_import_center(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS erp_import_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_type TEXT NOT NULL CHECK(
                import_type IN ('sales','customers','inventory')
            ),
            original_filename TEXT NOT NULL,
            stored_file_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN ('previewed','processing','completed','failed')
            ),
            rows_read INTEGER NOT NULL DEFAULT 0,
            rows_inserted INTEGER NOT NULL DEFAULT 0,
            rows_updated INTEGER NOT NULL DEFAULT 0,
            rows_skipped INTEGER NOT NULL DEFAULT 0,
            duplicates_count INTEGER NOT NULL DEFAULT 0,
            warnings_json TEXT,
            errors_json TEXT,
            execution_log_json TEXT NOT NULL DEFAULT '{}',
            executed_by TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_type_started
        ON erp_import_executions(import_type, started_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_hash
        ON erp_import_executions(file_hash, import_type)""",
        """CREATE TABLE IF NOT EXISTS erp_import_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_execution_id INTEGER NOT NULL,
            row_number INTEGER,
            severity TEXT NOT NULL CHECK(severity IN ('warning','error')),
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE CASCADE
        )""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_issues_execution
        ON erp_import_issues(import_execution_id, severity)""",
    ))
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "raw_sales" in tables and _column_exists(
        connection, "raw_sales", "sales_line_key"
    ):
        connection.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_sales_line_key
            ON raw_sales(sales_line_key)
            WHERE sales_line_key IS NOT NULL
                AND TRIM(sales_line_key) <> ''"""
        )
    if "raw_customers" in tables:
        customer_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(raw_customers)"
            ).fetchall()
        }
        source_key = "ID" if "ID" in customer_columns else (
            "id" if "id" in customer_columns else None
        )
        if source_key:
            connection.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS
                idx_raw_customers_erp_source_id
                ON raw_customers("{source_key}")
                WHERE "{source_key}" IS NOT NULL
                    AND TRIM("{source_key}") <> ''"""
            )


def _migration_0019_commercial_activities(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ws_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            email TEXT UNIQUE,
            role TEXT NOT NULL DEFAULT 'advisor',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """INSERT OR IGNORE INTO ws_users (id, display_name, role)
        VALUES (1, 'Sistema', 'system')""",
        """CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            job_title TEXT,
            role TEXT,
            influence TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE CASCADE,
            FOREIGN KEY(created_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL
        )""",
        """CREATE INDEX IF NOT EXISTS idx_contacts_customer
        ON contacts(customer_id, is_active, full_name)""",
    ))

    # Rebuild the legacy opportunity-only activity table so an activity can
    # exist for a customer independently while all historical IDs survive.
    connection.execute("ALTER TABLE ws_activities RENAME TO ws_activities_legacy")
    connection.execute(
        """CREATE TABLE ws_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            activity_type TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT,
            created_by TEXT NOT NULL DEFAULT 'system',
            occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            customer_id INTEGER,
            contact_id INTEGER,
            advisor_user_id INTEGER,
            purpose TEXT,
            summary TEXT,
            identified_need TEXT,
            identified_risk TEXT,
            supplier_participated INTEGER NOT NULL DEFAULT 0
                CHECK(supplier_participated IN (0,1)),
            supplier_name TEXT,
            supplier_person_name TEXT,
            supplier_person_role TEXT,
            supplier_objective TEXT,
            agreement_id INTEGER,
            potential_value REAL,
            currency_code TEXT,
            city TEXT,
            site_name TEXT,
            visited_area TEXT,
            created_by_user_id INTEGER,
            updated_by_user_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(project_id) REFERENCES ws_projects(id)
                ON DELETE SET NULL,
            FOREIGN KEY(contact_id) REFERENCES contacts(id)
                ON DELETE SET NULL,
            FOREIGN KEY(advisor_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL,
            FOREIGN KEY(created_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL,
            FOREIGN KEY(updated_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL,
            FOREIGN KEY(agreement_id) REFERENCES ws_agreements(id)
                ON DELETE SET NULL,
            CHECK(potential_value IS NULL OR
                (currency_code IS NOT NULL AND TRIM(currency_code) <> '')),
            CHECK(supplier_participated = 0 OR
                (supplier_name IS NOT NULL AND TRIM(supplier_name) <> '')),
            CHECK(customer_id IS NOT NULL OR project_id IS NOT NULL)
        )"""
    )
    connection.execute(
        """INSERT INTO ws_activities (
            id, customer_id, project_id, activity_type, title, details,
            summary, created_by, occurred_at, created_at
        )
        SELECT a.id, p.customer_id, a.project_id, a.activity_type, a.title,
            a.details, a.details, a.created_by, a.occurred_at, a.created_at
        FROM ws_activities_legacy a
        JOIN ws_projects p ON p.id = a.project_id"""
    )
    connection.execute("DROP TABLE ws_activities_legacy")
    _execute_statements(connection, (
        """CREATE INDEX idx_ws_activities_customer_date
        ON ws_activities(customer_id, occurred_at DESC)""",
        """CREATE INDEX idx_ws_activities_project_date
        ON ws_activities(project_id, occurred_at DESC)""",
        """CREATE TRIGGER trg_ws_activities_legacy_customer
        AFTER INSERT ON ws_activities
        WHEN NEW.customer_id IS NULL AND NEW.project_id IS NOT NULL
        BEGIN
            UPDATE ws_activities
            SET customer_id = (
                SELECT customer_id FROM ws_projects WHERE id = NEW.project_id
            )
            WHERE id = NEW.id;
        END""",
        """CREATE TABLE activity_participants (
            activity_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(activity_id, user_id),
            FOREIGN KEY(activity_id) REFERENCES ws_activities(id)
                ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES ws_users(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE activity_results (
            activity_id INTEGER NOT NULL,
            result_type TEXT NOT NULL,
            PRIMARY KEY(activity_id, result_type),
            FOREIGN KEY(activity_id) REFERENCES ws_activities(id)
                ON DELETE CASCADE
        )""",
        """CREATE TABLE activity_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            description TEXT,
            uploaded_by_user_id INTEGER,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(activity_id) REFERENCES ws_activities(id)
                ON DELETE CASCADE,
            FOREIGN KEY(uploaded_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL
        )""",
        """CREATE INDEX idx_activity_evidence_activity
        ON activity_evidence(activity_id, is_active, display_order)""",
        """CREATE TABLE activity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            changed_by_user_id INTEGER,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(activity_id) REFERENCES ws_activities(id)
                ON DELETE CASCADE,
            FOREIGN KEY(changed_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL
        )""",
    ))


def _migration_0020_rfq_lifecycle(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE rfqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_number TEXT NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            contact_id INTEGER,
            owner_user_id INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            required_by TEXT,
            status TEXT NOT NULL CHECK(status IN (
                'received','analysis','preparing','sent','follow_up',
                'won','lost','cancelled','opportunity'
            )),
            description TEXT NOT NULL,
            estimated_value REAL,
            currency_code TEXT,
            opportunity_id INTEGER,
            next_action TEXT,
            next_action_at TEXT,
            expected_decision_at TEXT,
            last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
            FOREIGN KEY(owner_user_id) REFERENCES ws_users(id) ON DELETE RESTRICT,
            FOREIGN KEY(opportunity_id) REFERENCES ws_projects(id)
                ON DELETE SET NULL,
            CHECK(estimated_value IS NULL OR
                (currency_code IS NOT NULL AND TRIM(currency_code) <> '')),
            CHECK(status IN ('won','lost','cancelled','opportunity') OR
                (next_action IS NOT NULL AND TRIM(next_action) <> ''
                 AND next_action_at IS NOT NULL))
        )""",
        """CREATE INDEX idx_rfqs_customer_status
        ON rfqs(customer_id, status, updated_at DESC)""",
        """CREATE INDEX idx_rfqs_owner_next_action
        ON rfqs(owner_user_id, next_action_at)""",
        """CREATE TABLE rfq_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            product_id TEXT,
            description TEXT NOT NULL,
            quantity REAL,
            unit_of_measure TEXT,
            quoted_unit_price REAL,
            currency_code TEXT,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            CHECK(quoted_unit_price IS NULL OR
                (currency_code IS NOT NULL AND TRIM(currency_code) <> ''))
        )""",
        """CREATE TABLE rfq_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            changed_by_user_id INTEGER NOT NULL,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            comment TEXT,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            FOREIGN KEY(changed_by_user_id) REFERENCES ws_users(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE rfq_conclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL UNIQUE,
            outcome TEXT NOT NULL CHECK(outcome IN (
                'won','lost','cancelled','opportunity'
            )),
            reason TEXT,
            concluded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            final_value REAL,
            currency_code TEXT,
            erp_sale_reference TEXT,
            opportunity_id INTEGER,
            concluded_by_user_id INTEGER NOT NULL,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            FOREIGN KEY(opportunity_id) REFERENCES ws_projects(id)
                ON DELETE SET NULL,
            FOREIGN KEY(concluded_by_user_id) REFERENCES ws_users(id)
                ON DELETE RESTRICT,
            CHECK(outcome NOT IN ('lost','cancelled') OR
                (reason IS NOT NULL AND TRIM(reason) <> '')),
            CHECK(outcome <> 'opportunity' OR opportunity_id IS NOT NULL),
            CHECK(final_value IS NULL OR
                (currency_code IS NOT NULL AND TRIM(currency_code) <> ''))
        )""",
        """CREATE TABLE rfq_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER,
            uploaded_by_user_id INTEGER,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            FOREIGN KEY(uploaded_by_user_id) REFERENCES ws_users(id)
                ON DELETE SET NULL
        )""",
    ))


def _migration_0021_normalize_user_table(connection: Connection) -> None:
    """Repair the short-lived pre-release `users` table name safely.

    Fresh databases already receive `ws_users` from migration 19. Databases
    that ran the original migration 19 are upgraded in place; SQLite updates
    dependent foreign-key definitions during the rename.
    """
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "users" in tables and "ws_users" not in tables:
        connection.execute("ALTER TABLE users RENAME TO ws_users")


def _migration_0022_targeted_rfq_and_oauth(connection: Connection) -> None:
    tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # Recover safely from early MVP databases whose registry said migration 20
    # was applied even though its RFQ tables were absent.
    if "rfqs" not in tables:
        _migration_0020_rfq_lifecycle(connection)
    for column_name, definition in (
        ("google_subject", "TEXT"),
        ("email_normalized", "TEXT"),
        ("branch", "TEXT"),
        ("portfolio_scope", "TEXT"),
        ("last_login_at", "TEXT"),
    ):
        _add_column(connection, "ws_users", column_name, definition)
    connection.execute(
        """UPDATE ws_users SET email_normalized = LOWER(TRIM(email))
        WHERE email IS NOT NULL AND TRIM(email) <> ''"""
    )
    _execute_statements(connection, (
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_users_google_subject
        ON ws_users(google_subject)
        WHERE google_subject IS NOT NULL AND TRIM(google_subject) <> ''""",
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_users_email_normalized
        ON ws_users(email_normalized)
        WHERE email_normalized IS NOT NULL AND TRIM(email_normalized) <> ''""",
        """INSERT INTO ws_users (
            display_name, email, email_normalized, role, is_active
        )
        SELECT 'Ricardo Lugo', 'ricardo.lugo@lugohermanos.com',
            'ricardo.lugo@lugohermanos.com', 'administrator', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM ws_users
            WHERE LOWER(TRIM(email)) = 'ricardo.lugo@lugohermanos.com'
        )""",
        """INSERT INTO ws_users (
            display_name, email, email_normalized, role, is_active
        )
        SELECT 'Jean Pierre Flórez', 'jeanp.florez@lugohermanos.com',
            'jeanp.florez@lugohermanos.com', 'advisor', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM ws_users
            WHERE LOWER(TRIM(email)) = 'jeanp.florez@lugohermanos.com'
        )""",
    ))

    for column_name, definition in (
        ("prequotation_number", "TEXT"),
        ("prequotation_number_normalized", "TEXT"),
        (
            "workflow_status",
            """TEXT CHECK(workflow_status IS NULL OR workflow_status IN (
                'draft','sent','in_progress','answered','closed','cancelled'
            ))""",
        ),
        ("cancellation_reason", "TEXT"),
        ("sent_at", "TEXT"),
    ):
        _add_column(connection, "rfqs", column_name, definition)
    connection.execute(
        """UPDATE rfqs SET workflow_status = CASE status
            WHEN 'sent' THEN 'sent'
            WHEN 'analysis' THEN 'in_progress'
            WHEN 'preparing' THEN 'in_progress'
            WHEN 'follow_up' THEN 'in_progress'
            WHEN 'won' THEN 'closed'
            WHEN 'lost' THEN 'closed'
            WHEN 'cancelled' THEN 'cancelled'
            WHEN 'opportunity' THEN 'closed'
            ELSE 'draft'
        END
        WHERE workflow_status IS NULL"""
    )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS
        idx_rfqs_prequotation_number_normalized
        ON rfqs(prequotation_number_normalized)
        WHERE prequotation_number_normalized IS NOT NULL
            AND TRIM(prequotation_number_normalized) <> ''"""
    )

    for column_name, definition in (
        ("reference", "TEXT"),
        ("brand", "TEXT"),
        ("notes", "TEXT"),
        ("display_order", "INTEGER NOT NULL DEFAULT 0"),
    ):
        _add_column(connection, "rfq_items", column_name, definition)
    connection.execute(
        """UPDATE rfq_items SET reference = COALESCE(reference, description)
        WHERE reference IS NULL"""
    )

    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS rfq_email_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL UNIQUE,
            provider TEXT NOT NULL DEFAULT 'gmail',
            provider_thread_id TEXT UNIQUE,
            subject TEXT NOT NULL,
            sender_email TEXT NOT NULL,
            recipient_emails_json TEXT NOT NULL,
            cc_emails_json TEXT NOT NULL DEFAULT '[]',
            sent_message_id TEXT,
            sent_at TEXT,
            sync_status TEXT NOT NULL DEFAULT 'pending',
            last_synced_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS rfq_email_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            provider_message_id TEXT NOT NULL UNIQUE,
            direction TEXT NOT NULL CHECK(direction IN ('outgoing','incoming')),
            sender_email TEXT,
            recipient_emails_json TEXT NOT NULL DEFAULT '[]',
            cc_emails_json TEXT NOT NULL DEFAULT '[]',
            subject TEXT,
            body_text TEXT,
            body_html_sanitized TEXT,
            message_at TEXT,
            synchronized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(thread_id) REFERENCES rfq_email_threads(id)
                ON DELETE CASCADE
        )""",
        """CREATE INDEX IF NOT EXISTS idx_rfq_email_messages_thread_date
        ON rfq_email_messages(thread_id, message_at, id)""",
    ))


def _migration_0023_customer_import_site_metrics(connection: Connection) -> None:
    if not connection.execute(
        """SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='erp_import_executions'"""
    ).fetchone():
        _migration_0018_erp_import_center(connection)
    for column_name in (
        "customers_inserted", "customers_updated", "customers_unchanged",
        "customer_sites_inserted", "customer_sites_updated",
        "customer_sites_unchanged",
    ):
        _add_column(
            connection, "erp_import_executions", column_name,
            "INTEGER NOT NULL DEFAULT 0",
        )
    # The former ID index encoded an incorrect ERP contract. Keep the legacy
    # column/data readable, but stop treating it as the customer or site key.
    connection.execute(
        "DROP INDEX IF EXISTS idx_raw_customers_erp_source_id"
    )


def _migration_0024_ask_mvp(connection: Connection) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ask_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root_analysis_id INTEGER,
            parent_analysis_id INTEGER,
            version INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            focus TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN (
                'draft','ready','running','completed','failed'
            )),
            customer_id INTEGER,
            customer_site_id TEXT,
            context_json TEXT NOT NULL DEFAULT '{}',
            mappings_json TEXT NOT NULL DEFAULT '{}',
            assumptions_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '[]',
            blocking_reasons_json TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT,
            ai_response_json TEXT,
            report_html TEXT,
            error_message TEXT,
            created_by_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            executed_at TEXT,
            FOREIGN KEY(root_analysis_id) REFERENCES ask_analyses(id)
                ON DELETE SET NULL,
            FOREIGN KEY(parent_analysis_id) REFERENCES ask_analyses(id)
                ON DELETE SET NULL,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE SET NULL,
            FOREIGN KEY(created_by_user_id) REFERENCES ws_users(id)
                ON DELETE RESTRICT,
            UNIQUE(root_analysis_id, version)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_ask_analyses_user_updated
        ON ask_analyses(created_by_user_id, updated_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_ask_analyses_customer
        ON ask_analyses(customer_id, updated_at DESC)""",
        """CREATE TABLE IF NOT EXISTS ask_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','analyst','system')),
            content TEXT NOT NULL,
            clarification_type TEXT,
            related_entity_type TEXT,
            related_entity_id TEXT,
            resolved_action TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(analysis_id) REFERENCES ask_analyses(id)
                ON DELETE CASCADE
        )""",
        """CREATE INDEX IF NOT EXISTS idx_ask_messages_analysis
        ON ask_messages(analysis_id, created_at, id)""",
        """CREATE TABLE IF NOT EXISTS ask_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_extension TEXT NOT NULL,
            mime_type TEXT,
            file_size_bytes INTEGER NOT NULL,
            file_hash TEXT NOT NULL,
            processing_status TEXT NOT NULL CHECK(processing_status IN (
                'pending','processed','failed'
            )),
            inspection_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(analysis_id) REFERENCES ask_analyses(id)
                ON DELETE CASCADE
        )""",
        """CREATE INDEX IF NOT EXISTS idx_ask_files_analysis
        ON ask_files(analysis_id, uploaded_at, id)""",
    ))


def _migration_0025_ask_analysis_workspace(connection: Connection) -> None:
    _add_column(
        connection, "ask_analyses", "lifecycle_status",
        """TEXT NOT NULL DEFAULT 'draft' CHECK(lifecycle_status IN (
            'draft','waiting_clarification','running','ready_review',
            'reviewed','exported','failed'
        ))""",
    )
    connection.execute(
        """UPDATE ask_analyses SET lifecycle_status=CASE status
            WHEN 'running' THEN 'running'
            WHEN 'completed' THEN 'ready_review'
            WHEN 'failed' THEN 'failed'
            WHEN 'ready' THEN 'draft'
            ELSE 'draft' END"""
    )
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ask_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            artifact_key TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            title TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            artifact_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(analysis_id) REFERENCES ask_analyses(id)
                ON DELETE CASCADE,
            UNIQUE(analysis_id, artifact_key)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_ask_artifacts_analysis
        ON ask_artifacts(analysis_id, position, id)""",
    ))


def _migration_0026_inventory_import(connection: Connection) -> None:
    execution_sql_row = connection.execute(
        """SELECT sql FROM sqlite_master
        WHERE type='table' AND name='erp_import_executions'"""
    ).fetchone()
    execution_sql = str(execution_sql_row["sql"] or "") if execution_sql_row else ""
    if "'inventory'" not in execution_sql:
        connection.execute(
            "ALTER TABLE erp_import_issues RENAME TO erp_import_issues_pre_inventory"
        )
        connection.execute(
            """ALTER TABLE erp_import_executions
            RENAME TO erp_import_executions_pre_inventory"""
        )
        _execute_statements(connection, (
            """CREATE TABLE erp_import_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_type TEXT NOT NULL CHECK(
                    import_type IN ('sales','customers','inventory')
                ),
                original_filename TEXT NOT NULL,
                stored_file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('previewed','processing','completed','failed')
                ),
                rows_read INTEGER NOT NULL DEFAULT 0,
                rows_inserted INTEGER NOT NULL DEFAULT 0,
                rows_updated INTEGER NOT NULL DEFAULT 0,
                rows_skipped INTEGER NOT NULL DEFAULT 0,
                duplicates_count INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT,
                errors_json TEXT,
                execution_log_json TEXT NOT NULL DEFAULT '{}',
                executed_by TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                customers_inserted INTEGER NOT NULL DEFAULT 0,
                customers_updated INTEGER NOT NULL DEFAULT 0,
                customers_unchanged INTEGER NOT NULL DEFAULT 0,
                customer_sites_inserted INTEGER NOT NULL DEFAULT 0,
                customer_sites_updated INTEGER NOT NULL DEFAULT 0,
                customer_sites_unchanged INTEGER NOT NULL DEFAULT 0,
                snapshot_date TEXT
            )""",
            """INSERT INTO erp_import_executions (
                id, import_type, original_filename, stored_file_path,
                file_hash, schema_version, status, rows_read, rows_inserted,
                rows_updated, rows_skipped, duplicates_count, warnings_json,
                errors_json, execution_log_json, executed_by, started_at,
                completed_at, customers_inserted, customers_updated,
                customers_unchanged, customer_sites_inserted,
                customer_sites_updated, customer_sites_unchanged
            )
            SELECT id, import_type, original_filename, stored_file_path,
                file_hash, schema_version, status, rows_read, rows_inserted,
                rows_updated, rows_skipped, duplicates_count, warnings_json,
                errors_json, execution_log_json, executed_by, started_at,
                completed_at, customers_inserted, customers_updated,
                customers_unchanged, customer_sites_inserted,
                customer_sites_updated, customer_sites_unchanged
            FROM erp_import_executions_pre_inventory""",
            """CREATE TABLE erp_import_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_execution_id INTEGER NOT NULL,
                row_number INTEGER,
                severity TEXT NOT NULL CHECK(severity IN ('warning','error')),
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(import_execution_id)
                    REFERENCES erp_import_executions(id) ON DELETE CASCADE
            )""",
            """INSERT INTO erp_import_issues (
                id, import_execution_id, row_number, severity, code,
                message, details_json, created_at
            )
            SELECT id, import_execution_id, row_number, severity, code,
                message, details_json, created_at
            FROM erp_import_issues_pre_inventory""",
            "DROP TABLE erp_import_issues_pre_inventory",
            "DROP TABLE erp_import_executions_pre_inventory",
        ))
    else:
        _add_column(
            connection, "erp_import_executions", "snapshot_date", "TEXT"
        )

    _execute_statements(connection, (
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_type_started
        ON erp_import_executions(import_type, started_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_hash
        ON erp_import_executions(file_hash, import_type)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_issues_execution
        ON erp_import_issues(import_execution_id, severity)""",
        """CREATE TABLE IF NOT EXISTS inventario_snapshot (
            fecha_snapshot TEXT NOT NULL,
            idbodega TEXT NOT NULL,
            nombre_bodega TEXT NOT NULL,
            idproducto TEXT NOT NULL,
            nombreproducto TEXT NOT NULL,
            unidad_medida TEXT,
            unidades REAL NOT NULL DEFAULT 0,
            idfam1 TEXT,
            nombre_fam1 TEXT,
            idfam2 TEXT,
            nombre_fam2 TEXT,
            idfam3 TEXT,
            nombre_fam3 TEXT,
            marca_codigo TEXT,
            marca_nombre TEXT,
            grupo_fabricante_codigo TEXT,
            grupo_fabricante_nombre TEXT,
            unidades_disponible REAL NOT NULL DEFAULT 0,
            unidades_reservado REAL NOT NULL DEFAULT 0,
            unidades_remisionado REAL NOT NULL DEFAULT 0,
            transito_1 REAL NOT NULL DEFAULT 0,
            transito_2 REAL NOT NULL DEFAULT 0,
            transito_3 REAL NOT NULL DEFAULT 0,
            unidades_transito REAL NOT NULL DEFAULT 0,
            costo_unitario REAL,
            valor_total REAL,
            ultima_entrada TEXT,
            ubicacion TEXT,
            codigo_barras TEXT,
            archivo_origen TEXT NOT NULL,
            fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(fecha_snapshot, idbodega, idproducto)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_inventario_snapshot_bodega_fecha
        ON inventario_snapshot(idbodega, fecha_snapshot)""",
        """CREATE INDEX IF NOT EXISTS idx_inventario_snapshot_producto_fecha
        ON inventario_snapshot(idproducto, fecha_snapshot)""",
    ))


def _migration_0027_opportunity_origin(connection: Connection) -> None:
    if not _table_exists(connection, "ws_projects"):
        return

    for name, definition in (
        (
            "origin",
            "TEXT NOT NULL DEFAULT 'manual' CHECK "
            "(origin IN ('manual','crm','quote','visit','rfq'))",
        ),
        ("external_id", "TEXT"),
        ("origin_reference", "TEXT"),
        ("imported_at", "TEXT"),
        ("last_synchronized_at", "TEXT"),
        (
            "created_import_execution_id",
            "INTEGER REFERENCES erp_import_executions(id) ON DELETE RESTRICT",
        ),
        (
            "last_import_execution_id",
            "INTEGER REFERENCES erp_import_executions(id) ON DELETE RESTRICT",
        ),
        ("import_metadata", "TEXT"),
    ):
        _add_column(connection, "ws_projects", name, definition)

    connection.execute(
        """
        UPDATE ws_projects
        SET origin = 'manual'
        WHERE origin IS NULL OR TRIM(origin) = ''
        """
    )
    connection.execute(
        """
        UPDATE ws_projects
        SET
            origin = 'visit',
            origin_reference = (
                SELECT source_visit_id
                FROM ws_commercial_visits
                WHERE ws_commercial_visits.project_id = ws_projects.id
                ORDER BY id ASC
                LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1
            FROM ws_commercial_visits
            WHERE ws_commercial_visits.project_id = ws_projects.id
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_ws_projects_origin_external_id
        ON ws_projects(origin, external_id)
        WHERE external_id IS NOT NULL AND TRIM(external_id) <> ''
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
            trg_ws_projects_immutable_origin
        BEFORE UPDATE OF origin ON ws_projects
        WHEN NEW.origin <> OLD.origin
        BEGIN
            SELECT RAISE(ABORT, 'Opportunity origin is immutable');
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS
            trg_ws_projects_immutable_external_identity
        BEFORE UPDATE OF external_id, origin_reference, imported_at,
            created_import_execution_id ON ws_projects
        WHEN
            NEW.external_id IS NOT OLD.external_id
            OR NEW.origin_reference IS NOT OLD.origin_reference
            OR NEW.imported_at IS NOT OLD.imported_at
            OR NEW.created_import_execution_id
                IS NOT OLD.created_import_execution_id
        BEGIN
            SELECT RAISE(
                ABORT,
                'Opportunity origin identity is immutable'
            );
        END
        """
    )


def _migration_0028_opportunity_import_framework(
    connection: Connection,
) -> None:
    execution_sql_row = connection.execute(
        """SELECT sql FROM sqlite_master
        WHERE type='table' AND name='erp_import_executions'"""
    ).fetchone()
    execution_sql = (
        str(execution_sql_row["sql"] or "") if execution_sql_row else ""
    )
    if "'crm_opportunities'" not in execution_sql:
        _execute_statements(connection, (
            """CREATE TABLE erp_import_executions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_type TEXT NOT NULL CHECK(
                    import_type IN (
                        'sales','customers','inventory','crm_opportunities'
                    )
                ),
                original_filename TEXT NOT NULL,
                stored_file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN (
                        'previewed','processing','completed','failed'
                    )
                ),
                rows_read INTEGER NOT NULL DEFAULT 0,
                rows_inserted INTEGER NOT NULL DEFAULT 0,
                rows_updated INTEGER NOT NULL DEFAULT 0,
                rows_skipped INTEGER NOT NULL DEFAULT 0,
                duplicates_count INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT,
                errors_json TEXT,
                execution_log_json TEXT NOT NULL DEFAULT '{}',
                executed_by TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                customers_inserted INTEGER NOT NULL DEFAULT 0,
                customers_updated INTEGER NOT NULL DEFAULT 0,
                customers_unchanged INTEGER NOT NULL DEFAULT 0,
                customer_sites_inserted INTEGER NOT NULL DEFAULT 0,
                customer_sites_updated INTEGER NOT NULL DEFAULT 0,
                customer_sites_unchanged INTEGER NOT NULL DEFAULT 0,
                snapshot_date TEXT
            )""",
            """INSERT INTO erp_import_executions_new (
                id, import_type, original_filename, stored_file_path,
                file_hash, schema_version, status, rows_read, rows_inserted,
                rows_updated, rows_skipped, duplicates_count, warnings_json,
                errors_json, execution_log_json, executed_by, started_at,
                completed_at, customers_inserted, customers_updated,
                customers_unchanged, customer_sites_inserted,
                customer_sites_updated, customer_sites_unchanged,
                snapshot_date
            )
            SELECT id, import_type, original_filename, stored_file_path,
                file_hash, schema_version, status, rows_read, rows_inserted,
                rows_updated, rows_skipped, duplicates_count, warnings_json,
                errors_json, execution_log_json, executed_by, started_at,
                completed_at, customers_inserted, customers_updated,
                customers_unchanged, customer_sites_inserted,
                customer_sites_updated, customer_sites_unchanged,
                snapshot_date
            FROM erp_import_executions""",
            """CREATE TABLE erp_import_issues_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_execution_id INTEGER NOT NULL,
                row_number INTEGER,
                severity TEXT NOT NULL CHECK(
                    severity IN ('warning','error')
                ),
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(import_execution_id)
                    REFERENCES erp_import_executions_new(id)
                    ON DELETE CASCADE
            )""",
            """INSERT INTO erp_import_issues_new (
                id, import_execution_id, row_number, severity, code,
                message, details_json, created_at
            )
            SELECT id, import_execution_id, row_number, severity, code,
                message, details_json, created_at
            FROM erp_import_issues""",
            "DROP TABLE erp_import_issues",
            "DROP TABLE erp_import_executions",
            """ALTER TABLE erp_import_executions_new
            RENAME TO erp_import_executions""",
            """ALTER TABLE erp_import_issues_new
            RENAME TO erp_import_issues""",
        ))

    for name, definition in (
        (
            "mapping_profile_version_id",
            "INTEGER REFERENCES opportunity_import_profile_versions(id) "
            "ON DELETE RESTRICT",
        ),
        ("groups_identified", "INTEGER NOT NULL DEFAULT 0"),
        ("groups_to_create", "INTEGER NOT NULL DEFAULT 0"),
        ("groups_to_update", "INTEGER NOT NULL DEFAULT 0"),
        ("groups_unchanged", "INTEGER NOT NULL DEFAULT 0"),
        ("groups_needs_review", "INTEGER NOT NULL DEFAULT 0"),
        ("groups_blocked", "INTEGER NOT NULL DEFAULT 0"),
        ("customer_resolutions_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        _add_column(
            connection, "erp_import_executions", name, definition
        )

    _execute_statements(connection, (
        """CREATE INDEX IF NOT EXISTS
        idx_erp_import_executions_type_started
        ON erp_import_executions(import_type, started_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_hash
        ON erp_import_executions(file_hash, import_type)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_issues_execution
        ON erp_import_issues(import_execution_id, severity)""",
        """CREATE TABLE IF NOT EXISTS opportunity_import_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            import_origin TEXT NOT NULL DEFAULT 'crm'
                CHECK(import_origin IN ('crm')),
            is_active INTEGER NOT NULL DEFAULT 0
                CHECK(is_active IN (0,1)),
            current_version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_name, import_origin)
        )""",
        """CREATE TABLE IF NOT EXISTS opportunity_import_profile_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            column_mapping_json TEXT NOT NULL DEFAULT '{}',
            transformation_rules_json TEXT NOT NULL DEFAULT '{}',
            grouping_configuration_json TEXT NOT NULL DEFAULT '{}',
            validation_configuration_json TEXT NOT NULL DEFAULT '{}',
            ownership_configuration_json TEXT NOT NULL DEFAULT '{}',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(profile_id)
                REFERENCES opportunity_import_profiles(id)
                ON DELETE RESTRICT,
            UNIQUE(profile_id, version)
        )""",
        """CREATE TRIGGER IF NOT EXISTS
        trg_opportunity_import_profile_versions_immutable_update
        BEFORE UPDATE ON opportunity_import_profile_versions
        BEGIN
            SELECT RAISE(
                ABORT,
                'Opportunity import profile versions are immutable'
            );
        END""",
        """CREATE TRIGGER IF NOT EXISTS
        trg_opportunity_import_profile_versions_immutable_delete
        BEFORE DELETE ON opportunity_import_profile_versions
        BEGIN
            SELECT RAISE(
                ABORT,
                'Opportunity import profile versions are immutable'
            );
        END""",
        """CREATE TABLE IF NOT EXISTS
        opportunity_import_customer_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_execution_id INTEGER NOT NULL,
            external_opportunity_id TEXT NOT NULL,
            source_customer_key TEXT,
            customer_id INTEGER,
            resolution_status TEXT NOT NULL CHECK(
                resolution_status IN (
                    'matched','needs_review','resolved_by_user','blocked'
                )
            ),
            resolved_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id)
                REFERENCES ws_customers(id) ON DELETE RESTRICT,
            UNIQUE(import_execution_id, external_opportunity_id)
        )""",
        """CREATE INDEX IF NOT EXISTS
        idx_opportunity_import_resolutions_execution
        ON opportunity_import_customer_resolutions(
            import_execution_id, resolution_status
        )""",
    ))


def _migration_0029_production_crm_opportunity_import(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS opportunity_import_customer_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalized_source_identity TEXT NOT NULL UNIQUE,
            source_display_name TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            match_reason TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS opportunity_import_seller_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalized_source_seller TEXT NOT NULL UNIQUE,
            source_display_name TEXT NOT NULL,
            resolved_sales_rep TEXT NOT NULL,
            match_reason TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS opportunity_import_seller_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_execution_id INTEGER NOT NULL,
            external_opportunity_id TEXT NOT NULL,
            source_seller TEXT,
            resolved_sales_rep TEXT,
            resolution_status TEXT NOT NULL CHECK(
                resolution_status IN (
                    'matched','needs_review','resolved_by_user','blocked'
                )
            ),
            match_reason TEXT,
            resolved_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE CASCADE,
            UNIQUE(import_execution_id, external_opportunity_id)
        )""",
    ))

    mapping = {
        "source_row_id": "ID",
        "source_updated_at": "Fecha",
        "external_opportunity_id": "Oportunidad",
        "origin_reference": "Documento",
        "customer_identity": "Nombre Empresa",
        "customer_site": "Sucursal empresa",
        "customer_phone": "Teléfono",
        "customer_mobile": "Móvil",
        "customer_city": "Ciudad",
        "seller": "Vendedor",
        "creator": "Creado por",
        "crm_status": "Estado",
        "crm_stage": "Etapa",
        "priority": "Prioridad",
        "probability": "Probabilidad",
        "close_date": "Fecha Cierre",
        "brand": "Marca",
        "product_code": "Código producto",
        "product_description": "Descripción producto",
        "line_potential_value": "Valor Potencial",
    }
    transformations = {
        key: "trim_text"
        for key in mapping
        if key not in {
            "source_updated_at", "close_date", "probability",
            "line_potential_value",
        }
    }
    transformations.update({
        "source_updated_at": "parse_date",
        "close_date": "parse_date",
        "probability": "parse_decimal",
        "line_potential_value": "parse_decimal",
    })
    grouping = {
        "strategy": "production_crm_product_lines_v1",
        "sheet_name": "Datos",
        "consistent_concepts": ["customer_identity", "seller"],
        "latest_row_concepts": [
            "crm_status", "crm_stage", "priority", "probability",
            "close_date", "source_updated_at",
        ],
        "name_strategy": "brand_product_or_document_v1",
    }
    validation = {
        "customer_resolution": "production_company_identity_v1",
        "seller_resolution": "production_seller_identity_v1",
        "seller_required": False,
        "ambiguous_lifecycle_as_source_fact": True,
    }
    ownership = {
        "import_owned_fields": ["sales_rep"],
        "creation_only_fields": ["name"],
        "protected_fields": [
            "objective", "proposed_solution", "current_blocker",
            "commercial_amount", "commercial_currency", "closed_at",
        ],
    }
    cursor = connection.execute(
        """INSERT OR IGNORE INTO opportunity_import_profiles(
            profile_name, import_origin, is_active, current_version,
            created_by, updated_by
        ) VALUES (
            'CRM Producción · export Oportunidades', 'crm', 1, 1,
            'migration-29', 'migration-29'
        )"""
    )
    profile = connection.execute(
        """SELECT id FROM opportunity_import_profiles
        WHERE profile_name='CRM Producción · export Oportunidades'
          AND import_origin='crm'"""
    ).fetchone()
    profile_id = int(profile["id"])
    connection.execute(
        "UPDATE opportunity_import_profiles SET is_active=0 "
        "WHERE import_origin='crm' AND id<>?",
        (profile_id,),
    )
    connection.execute(
        "UPDATE opportunity_import_profiles SET is_active=1 WHERE id=?",
        (profile_id,),
    )
    connection.execute(
        """INSERT OR IGNORE INTO opportunity_import_profile_versions(
            profile_id, version, column_mapping_json,
            transformation_rules_json, grouping_configuration_json,
            validation_configuration_json, ownership_configuration_json,
            created_by
        ) VALUES (?,1,?,?,?,?,?,'migration-29')""",
        (
            profile_id,
            json.dumps(mapping, ensure_ascii=False),
            json.dumps(transformations, ensure_ascii=False),
            json.dumps(grouping, ensure_ascii=False),
            json.dumps(validation, ensure_ascii=False),
            json.dumps(ownership, ensure_ascii=False),
        ),
    )


def _migration_0030_deferred_crm_opportunity_import(
    connection: Connection,
) -> None:
    for name in (
        "groups_eligible", "groups_imported", "groups_deferred",
    ):
        _add_column(
            connection, "erp_import_executions", name,
            "INTEGER NOT NULL DEFAULT 0",
        )
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS crm_opportunity_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_opportunity_id TEXT NOT NULL UNIQUE,
            origin_reference TEXT,
            source_company_name TEXT,
            normalized_customer_identity TEXT,
            customer_id INTEGER,
            resolution_status TEXT NOT NULL CHECK(
                resolution_status IN (
                    'needs_review','blocked','ready','imported'
                )
            ),
            match_reason TEXT,
            group_snapshot_json TEXT NOT NULL,
            original_import_execution_id INTEGER NOT NULL,
            latest_import_execution_id INTEGER NOT NULL,
            mapping_profile_version_id INTEGER NOT NULL,
            resolved_by TEXT,
            resolved_at TEXT,
            alias_created INTEGER NOT NULL DEFAULT 0
                CHECK(alias_created IN (0,1)),
            imported_opportunity_id INTEGER,
            imported_import_execution_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(original_import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT,
            FOREIGN KEY(latest_import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT,
            FOREIGN KEY(mapping_profile_version_id)
                REFERENCES opportunity_import_profile_versions(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(imported_opportunity_id)
                REFERENCES ws_projects(id) ON DELETE RESTRICT,
            FOREIGN KEY(imported_import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_crm_pending_status_company
        ON crm_opportunity_pending(
            resolution_status, normalized_customer_identity
        )""",
        """CREATE TABLE IF NOT EXISTS crm_opportunity_pending_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pending_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            import_execution_id INTEGER,
            actor TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(pending_id) REFERENCES crm_opportunity_pending(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_crm_pending_history_pending
        ON crm_opportunity_pending_history(pending_id, created_at, id)""",
    ))


def _migration_0031_crm_commercial_line_quote_bridge(
    connection: Connection,
) -> None:
    if _table_exists(connection, "ws_project_quotes"):
        for name, definition in (
            (
                "generated_from_crm_lines",
                "INTEGER NOT NULL DEFAULT 0 CHECK("
                "generated_from_crm_lines IN (0,1))",
            ),
            ("source_lines_signature", "TEXT"),
            ("generated_at", "TEXT"),
        ):
            _add_column(connection, "ws_project_quotes", name, definition)
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS imported_commercial_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            source_line_key TEXT NOT NULL,
            origin_opportunity_id TEXT NOT NULL,
            origin_reference TEXT,
            brand TEXT,
            part_number TEXT,
            description TEXT,
            potential_value REAL,
            currency_code TEXT NOT NULL DEFAULT 'COP',
            crm_row_ids_json TEXT NOT NULL DEFAULT '[]',
            crm_row_numbers_json TEXT NOT NULL DEFAULT '[]',
            import_execution_id INTEGER NOT NULL,
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(opportunity_id) REFERENCES ws_projects(id)
                ON DELETE CASCADE,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT,
            UNIQUE(opportunity_id,source_line_key)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_imported_commercial_lines_active
        ON imported_commercial_lines(opportunity_id,is_active,created_at)""",
        """CREATE TABLE IF NOT EXISTS ws_quote_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL,
            imported_commercial_line_id INTEGER,
            brand TEXT,
            part_number TEXT,
            description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1 CHECK(quantity >= 0),
            unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
            line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0),
            currency_code TEXT NOT NULL DEFAULT 'COP',
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id)
                ON DELETE CASCADE,
            FOREIGN KEY(imported_commercial_line_id)
                REFERENCES imported_commercial_lines(id) ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_ws_quote_lines_quote
        ON ws_quote_lines(quote_id,display_order,id)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS
        idx_ws_quote_lines_imported_source
        ON ws_quote_lines(quote_id,imported_commercial_line_id)
        WHERE imported_commercial_line_id IS NOT NULL""",
    ))


def _migration_0032_quote_management_system(connection: Connection) -> None:
    """Add the RFQ-first USD quote domain without replacing legacy quotes."""
    # Quotes historically required an Opportunity. Rebuild the parent while
    # foreign keys are suspended by upgrade(), retaining every existing id.
    had_quotes = _table_exists(connection, "ws_project_quotes")
    connection.execute("PRAGMA legacy_alter_table = ON")
    if had_quotes:
        connection.execute(
            "ALTER TABLE ws_project_quotes RENAME TO ws_project_quotes_legacy"
        )
    connection.execute("""
        CREATE TABLE ws_project_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            customer_id INTEGER,
            originating_rfq_id INTEGER,
            quote_series_key TEXT,
            revised_from_quote_id INTEGER,
            split_key TEXT NOT NULL DEFAULT 'default',
            quote_number TEXT NOT NULL,
            branch TEXT,
            prefix TEXT NOT NULL,
            quote_date TEXT,
            amount REAL,
            quote_status TEXT,
            erp_user TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            currency_code TEXT NOT NULL DEFAULT 'COP',
            exchange_rate REAL,
            normalized_amount REAL,
            revision INTEGER NOT NULL DEFAULT 0,
            exchange_rate_type TEXT,
            generated_from_crm_lines INTEGER NOT NULL DEFAULT 0,
            source_lines_signature TEXT,
            generated_at TEXT,
            sales_rep_user_id INTEGER,
            sales_rep_name TEXT,
            sales_rep_email TEXT,
            customer_email TEXT,
            rfq_number_snapshot TEXT,
            request_comments_snapshot TEXT,
            origin_country_code TEXT,
            origin_service_area_code TEXT,
            calculated_dhl_zone INTEGER,
            final_dhl_zone INTEGER,
            zone_override_reason TEXT,
            zone_overridden_by_user_id INTEGER,
            zone_overridden_at TEXT,
            estimated_trm TEXT,
            validity_days INTEGER NOT NULL DEFAULT 10,
            commercial_comments TEXT,
            internal_notes TEXT,
            premium_service TEXT,
            actual_weight_kg TEXT,
            chargeable_weight_kg TEXT,
            calculated_shipping_usd TEXT,
            final_shipping_usd TEXT,
            shipping_override_reason TEXT,
            shipping_overridden_by_user_id INTEGER,
            shipping_overridden_at TEXT,
            customs_applied INTEGER NOT NULL DEFAULT 0,
            customs_base_cop TEXT,
            customs_usd TEXT,
            bank_fee_usd TEXT,
            landed_cost_usd TEXT,
            profit_usd TEXT,
            margin_percent TEXT,
            roi_percent TEXT,
            dhl_rate_profile_id INTEGER,
            ready_at TEXT,
            issued_at TEXT,
            sent_at TEXT,
            created_by_user_id INTEGER,
            FOREIGN KEY(project_id) REFERENCES ws_projects(id) ON DELETE SET NULL,
            FOREIGN KEY(customer_id) REFERENCES ws_customers(id) ON DELETE RESTRICT,
            FOREIGN KEY(originating_rfq_id) REFERENCES rfqs(id) ON DELETE RESTRICT,
            FOREIGN KEY(revised_from_quote_id) REFERENCES ws_project_quotes(id) ON DELETE RESTRICT,
            FOREIGN KEY(sales_rep_user_id) REFERENCES ws_users(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by_user_id) REFERENCES ws_users(id) ON DELETE SET NULL,
            CHECK(currency_code IN ('COP','USD')),
            CHECK(premium_service IS NULL OR premium_service IN ('0900','1200')),
            CHECK(calculated_dhl_zone IS NULL OR calculated_dhl_zone BETWEEN 1 AND 7),
            CHECK(final_dhl_zone IS NULL OR final_dhl_zone BETWEEN 1 AND 7)
        )
    """)
    if had_quotes:
        connection.execute("""
            INSERT INTO ws_project_quotes (
            id,project_id,customer_id,quote_number,branch,prefix,quote_date,
            amount,quote_status,erp_user,created_at,currency_code,exchange_rate,
            normalized_amount,revision,exchange_rate_type,
            generated_from_crm_lines,source_lines_signature,generated_at,
            quote_series_key
        )
        SELECT q.id,q.project_id,p.customer_id,q.quote_number,q.branch,q.prefix,
            q.quote_date,q.amount,q.quote_status,q.erp_user,q.created_at,
            COALESCE(q.currency_code,'COP'),q.exchange_rate,q.normalized_amount,
            COALESCE(q.revision,0),q.exchange_rate_type,
            COALESCE(q.generated_from_crm_lines,0),q.source_lines_signature,
            q.generated_at,q.prefix || ':' || q.quote_number
            FROM ws_project_quotes_legacy q
            LEFT JOIN ws_projects p ON p.id=q.project_id
        """)
        connection.execute("DROP TABLE ws_project_quotes_legacy")
    connection.execute("PRAGMA legacy_alter_table = OFF")

    for name, definition in (
        ("vendor_fob_unit_usd", "TEXT"), ("unit_weight_kg", "TEXT"),
        ("lead_time", "TEXT"), ("vendor_comments", "TEXT"),
        ("pricing_rule_id", "INTEGER"), ("pricing_rule_snapshot", "TEXT"),
        ("pricing_default_value", "TEXT"), ("pricing_override_value", "TEXT"),
        ("pricing_override_reason", "TEXT"), ("pricing_overridden_by_user_id", "INTEGER"),
        ("pricing_overridden_at", "TEXT"), ("internal_notes", "TEXT"),
        ("source_rfq_item_id", "INTEGER"), ("allocated_shipping_usd", "TEXT"),
        ("allocated_customs_usd", "TEXT"), ("allocated_bank_fee_usd", "TEXT"),
        ("landed_cost_usd", "TEXT"), ("selling_unit_usd", "TEXT"),
        ("profit_usd", "TEXT"), ("margin_percent", "TEXT"),
        ("roi_percent", "TEXT"),
    ):
        _add_column(connection, "ws_quote_lines", name, definition)

    for name, definition in (
        ("vendor_response_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("fob_unit_usd", "TEXT"), ("unit_weight_kg", "TEXT"),
        ("lead_time", "TEXT"), ("availability", "TEXT"),
        ("vendor_comments", "TEXT"), ("vendor_valid_until", "TEXT"),
        ("vendor_responded_at", "TEXT"),
    ):
        _add_column(connection, "rfq_items", name, definition)

    _execute_statements(connection, (
        """CREATE TABLE quote_settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, value_type TEXT NOT NULL,
            notes TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE quote_vendor_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL,
            vendor_name TEXT NOT NULL, vendor_email TEXT NOT NULL,
            default_cc_json TEXT NOT NULL DEFAULT '[]', active INTEGER NOT NULL DEFAULT 1,
            email_template TEXT, default_language TEXT NOT NULL DEFAULT 'en', notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(brand COLLATE NOCASE)
        )""",
        """CREATE TABLE quote_pricing_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, rule_name TEXT NOT NULL,
            rule_type TEXT NOT NULL CHECK(rule_type IN ('cost_multiplier','markup','gross_margin')),
            default_value TEXT NOT NULL, brand TEXT, product_family TEXT, product_type TEXT,
            minimum_margin TEXT, maximum_override TEXT, active INTEGER NOT NULL DEFAULT 1,
            effective_date TEXT, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE rfq_vendor_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, rfq_id INTEGER NOT NULL,
            brand TEXT NOT NULL, vendor_config_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'prepared', recipient_email TEXT NOT NULL,
            cc_json TEXT NOT NULL DEFAULT '[]', subject TEXT NOT NULL,
            body_text TEXT NOT NULL, body_html TEXT NOT NULL,
            attachment_ids_json TEXT NOT NULL DEFAULT '[]',
            provider_message_id TEXT, provider_thread_id TEXT, last_error TEXT,
            sent_by_user_id INTEGER, sent_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            FOREIGN KEY(vendor_config_id) REFERENCES quote_vendor_configs(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE dhl_rate_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_name TEXT NOT NULL,
            carrier TEXT NOT NULL DEFAULT 'DHL', service TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'import_to_colombia', effective_date TEXT NOT NULL,
            expiration_date TEXT, currency TEXT NOT NULL DEFAULT 'USD', active INTEGER NOT NULL DEFAULT 1,
            source_attachment TEXT, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE dhl_country_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
            country_code TEXT NOT NULL, country_name TEXT NOT NULL,
            service_area_code TEXT NOT NULL DEFAULT 'default', service_area_name TEXT,
            zone INTEGER NOT NULL CHECK(zone BETWEEN 1 AND 7), active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(profile_id) REFERENCES dhl_rate_profiles(id) ON DELETE CASCADE,
            UNIQUE(profile_id,country_code,service_area_code)
        )""",
        """CREATE TABLE dhl_weight_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
            shipment_kind TEXT NOT NULL DEFAULT 'package', weight_kg TEXT NOT NULL,
            zone INTEGER NOT NULL, rate_usd TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES dhl_rate_profiles(id) ON DELETE CASCADE,
            UNIQUE(profile_id,shipment_kind,weight_kg,zone)
        )""",
        """CREATE TABLE dhl_increment_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
            from_weight_kg TEXT NOT NULL, to_weight_kg TEXT NOT NULL,
            increment_kg TEXT NOT NULL, zone INTEGER NOT NULL, rate_usd TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES dhl_rate_profiles(id) ON DELETE CASCADE,
            UNIQUE(profile_id,from_weight_kg,to_weight_kg,zone)
        )""",
        """CREATE TABLE quote_attachment_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL,
            rfq_document_id INTEGER, original_filename TEXT NOT NULL, stored_filename TEXT,
            mime_type TEXT, size_bytes INTEGER, category TEXT NOT NULL DEFAULT 'other',
            uploaded_by_user_id INTEGER, included_in_delivery INTEGER NOT NULL DEFAULT 0,
            vendor_confidential INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id) ON DELETE CASCADE,
            FOREIGN KEY(rfq_document_id) REFERENCES rfq_documents(id) ON DELETE RESTRICT
        )""",
        """CREATE TABLE quote_pdfs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL,
            stored_filename TEXT NOT NULL, template_version TEXT NOT NULL,
            generated_by_user_id INTEGER, generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE quote_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'prepared', recipient_email TEXT NOT NULL,
            cc_json TEXT NOT NULL DEFAULT '[]', subject TEXT NOT NULL,
            body_text TEXT NOT NULL, body_html TEXT NOT NULL,
            advisor_note TEXT, note_internal_only INTEGER NOT NULL DEFAULT 1,
            note_included INTEGER NOT NULL DEFAULT 1, attachment_ids_json TEXT NOT NULL DEFAULT '[]',
            provider_message_id TEXT, provider_thread_id TEXT, last_error TEXT,
            prepared_by_user_id INTEGER, prepared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_by_user_id INTEGER, sent_at TEXT,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE quote_followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL,
            assigned_user_id INTEGER, due_date TEXT NOT NULL, description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', completed_at TEXT, response_note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE quote_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL UNIQUE,
            outcome TEXT NOT NULL CHECK(outcome IN ('won','lost','cancelled')),
            final_order_amount_usd TEXT, customer_po TEXT, order_number TEXT,
            loss_reason TEXT, competitor TEXT, comments TEXT, outcome_date TEXT NOT NULL,
            recorded_by_user_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quote_id) REFERENCES ws_project_quotes(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX idx_quotes_rfq ON ws_project_quotes(originating_rfq_id,quote_series_key,revision)",
        "CREATE INDEX idx_quotes_portfolio ON ws_project_quotes(quote_status,quote_date,customer_id)",
    ))
    settings = (
        ('customs_base_cop','300000','decimal','Base aduanera configurable'),
        ('bank_fee_usd','30','decimal','Una comisión por cotización'),
        ('followup_business_days','3','integer','Seguimiento tras envío'),
        ('minimum_quote_value_for_opportunity_creation_cop','5000000','decimal','Umbral informativo'),
        ('quote_validity_days','10','integer','Vigencia predeterminada'),
        ('premium_0900_usd','29','decimal','DHL Premium 9:00'),
        ('premium_1200_usd','10','decimal','DHL Premium 12:00'),
    )
    connection.executemany(
        "INSERT INTO quote_settings(key,value,value_type,notes) VALUES (?,?,?,?)", settings
    )
    vendor_cc = '["nicolas.lugo@lugohermanos.com","ricardo.lugo@lugohermanos.com","gerencia@lugohermanos.com","compras@lugohermanos.com","importaciones@lugohermanos.com"]'
    connection.executemany("""INSERT INTO quote_vendor_configs(
        brand,vendor_name,vendor_email,default_cc_json,email_template,default_language,notes
    ) VALUES (?,?,?,?,?,?,?)""", (
        ('THK','THK Brasil','vendas@thk.com.br',vendor_cc,None,'en','Configuración inicial'),
        ('Thomson','Thomson / Regal Rexnord','tiago.freitas@regalrexnord.com',vendor_cc,None,'en','Configuración inicial'),
    ))
    connection.execute("""INSERT INTO dhl_rate_profiles(
        profile_name,service,effective_date,currency,source_attachment,notes
    ) VALUES ('Lugo Hermanos DHL Import 2026','Express Worldwide Import',
        '2026-01-01','USD','Tarifas Lugo Hermanos 2026.pdf',
        'Valores publicados ya incluyen descuento negociado; no aplicar descuento adicional')""")
    profile_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.executemany("""INSERT INTO dhl_country_zones(
        profile_id,country_code,country_name,service_area_code,service_area_name,zone
    ) VALUES (?,?,?,?,?,?)""", (
        (profile_id,'BR','Brasil','default',None,4),
        (profile_id,'US','Estados Unidos','miami','Boca Raton / Miami Gateway / Miami',2),
        (profile_id,'US','Estados Unidos','rest','Resto de Estados Unidos',3),
    ))
    # Published package rows used by the primary RFQ origins. More countries
    # use the same seven-zone profile and can be configured without code changes.
    published = {
        '0.5': ('30.61','31.92','37.02','38.06','53.26','59.71','70.02'),
        '1.0': ('34.08','34.17','40.20','42.82','58.18','68.03','80.09'),
        '1.5': ('37.54','36.43','43.37','47.59','63.10','76.35','90.16'),
        '2.0': ('41.00','38.68','46.55','52.35','68.03','84.67','100.23'),
        '2.5': ('44.47','40.94','49.73','57.14','72.97','92.99','110.30'),
        '3.0': ('48.04','43.29','53.05','61.12','78.09','101.29','119.78'),
        '3.5': ('51.61','45.65','56.36','65.11','83.22','109.59','129.26'),
        '4.0': ('55.19','48.00','59.68','69.09','88.35','117.89','138.75'),
        '4.5': ('58.76','50.36','62.99','73.08','93.48','126.18','148.23'),
        '5.0': ('62.33','52.71','66.31','77.06','98.61','134.48','157.71'),
        '5.5': ('65.90','55.07','69.65','81.12','103.74','142.78','167.19'),
        '6.0': ('69.48','57.42','73.00','85.17','108.87','151.08','176.67'),
        '6.5': ('73.05','59.78','76.34','89.22','114.00','159.38','186.15'),
        '7.0': ('76.62','62.13','79.69','93.28','119.13','167.68','195.63'),
        '7.5': ('80.19','64.49','83.04','97.33','124.26','175.98','205.11'),
        '8.0': ('83.77','66.84','86.38','101.39','129.39','184.28','214.59'),
        '8.5': ('87.34','69.20','89.73','105.44','134.52','192.58','224.07'),
        '9.0': ('90.91','71.55','93.07','109.50','139.65','200.88','233.55'),
        '9.5': ('94.49','73.91','96.42','113.55','144.78','209.18','243.03'),
        '10.0': ('98.06','76.26','99.77','117.61','149.91','217.48','252.52'),
        '11.0': ('104.50','80.10','105.78','124.72','159.80','232.15','270.30'),
        '12.0': ('110.94','83.94','111.80','131.83','169.70','246.83','288.09'),
        '13.0': ('117.38','87.79','117.81','138.94','179.59','261.51','305.87'),
        '14.0': ('123.82','91.63','123.82','146.05','189.49','276.19','323.66'),
        '15.0': ('130.26','95.47','129.84','153.17','199.39','290.86','341.44'),
        '16.0': ('136.70','99.31','135.85','160.28','209.28','305.54','359.23'),
        '17.0': ('143.14','103.15','141.87','167.39','219.18','320.22','377.01'),
        '18.0': ('149.58','106.99','147.88','174.50','229.07','334.90','394.80'),
        '19.0': ('156.02','110.84','153.90','181.61','238.97','349.57','412.59'),
        '20.0': ('162.46','114.68','159.91','188.73','248.86','364.25','430.37'),
        '21.0': ('166.69','119.20','164.53','192.61','255.04','374.61','441.45'),
        '22.0': ('170.93','123.72','169.15','196.50','261.23','384.97','452.54'),
        '23.0': ('175.16','128.23','173.77','200.38','267.41','395.33','463.62'),
        '24.0': ('179.39','132.75','178.39','204.27','273.59','405.69','474.70'),
        '25.0': ('183.63','137.27','183.01','208.16','279.77','416.05','485.78'),
        '26.0': ('187.86','141.79','187.63','212.04','285.96','426.41','496.87'),
        '27.0': ('192.09','146.31','192.25','215.93','292.14','436.77','507.95'),
        '28.0': ('196.33','150.83','196.87','219.82','298.32','447.13','519.03'),
        '29.0': ('200.56','155.35','201.49','223.70','304.50','457.49','530.11'),
        '30.0': ('204.79','159.87','206.11','227.59','310.69','467.85','541.20'),
        '40.0': ('249.93','193.41','252.90','271.83','379.68','578.82','659.64'),
        '50.0': ('295.07','226.96','299.69','316.07','448.67','689.78','778.08'),
        '60.0': ('340.20','260.50','346.47','360.31','517.66','800.74','896.52'),
        '70.0': ('385.34','294.04','393.26','404.55','586.65','911.71','1014.96'),
    }
    rate_rows = [
        (profile_id,'package',weight,zone,value)
        for weight, values in published.items()
        for zone, value in enumerate(values, start=1)
    ]
    connection.executemany("""INSERT INTO dhl_weight_rates(
        profile_id,shipment_kind,weight_kg,zone,rate_usd
    ) VALUES (?,?,?,?,?)""", rate_rows)
    increments = (
        ('10.1','20','0.5',('3.22','1.92','3.01','3.56','4.95','7.34','8.89')),
        ('20.1','30','0.5',('2.12','2.26','2.31','1.94','3.09','5.18','5.54')),
        ('30.1','70','1',('4.51','3.35','4.68','4.42','6.90','11.10','11.84')),
        ('70.1','300','1',('5.19','3.81','5.09','5.28','7.48','12.13','13.24')),
        ('300.1','9999','1',('5.73','4.20','5.56','5.73','8.16','13.36','14.75')),
    )
    connection.executemany("""INSERT INTO dhl_increment_rates(
        profile_id,from_weight_kg,to_weight_kg,increment_kg,zone,rate_usd
    ) VALUES (?,?,?,?,?,?)""", [
        (profile_id,start,end,increment,zone,value)
        for start,end,increment,values in increments
        for zone,value in enumerate(values,start=1)
    ])


def _migration_0033_commercial_assignment_fields(connection: Connection) -> None:
    _add_column(connection, "rfqs", "sales_rep_name", "TEXT")
    connection.execute(
        "UPDATE rfqs SET sales_rep_name=(SELECT display_name FROM ws_users "
        "WHERE ws_users.id=rfqs.owner_user_id) WHERE sales_rep_name IS NULL"
    )


def _migration_0034_account_visit_analysis(connection: Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS account_visit_analyses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        input_signature TEXT NOT NULL,
        source_visit_count INTEGER NOT NULL,
        source_through_date TEXT,
        prompt_version TEXT NOT NULL,
        model TEXT,
        status TEXT NOT NULL,
        analysis_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_by TEXT NOT NULL DEFAULT 'system',
        FOREIGN KEY(customer_id) REFERENCES ws_customers(id) ON DELETE CASCADE,
        UNIQUE(customer_id,input_signature,prompt_version)
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_account_visit_analysis_customer ON account_visit_analyses(customer_id,created_at DESC)")


def _migration_0035_stock_order_planning_foundation(
    connection: Connection,
) -> None:
    """Vendor-neutral master data and immutable planning snapshots."""
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_vendor_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            profile_code TEXT NOT NULL UNIQUE,
            inventory_brand_codes_json TEXT NOT NULL DEFAULT '[]',
            sales_suffixes_json TEXT NOT NULL DEFAULT '[]',
            default_manufacturing_days INTEGER,
            default_shipping_days INTEGER,
            default_receiving_days INTEGER,
            default_cali_transfer_days INTEGER,
            lead_time_day_basis TEXT NOT NULL DEFAULT 'calendar'
                CHECK(lead_time_day_basis IN ('calendar','business')),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_product_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            internal_sku TEXT NOT NULL,
            vendor_sku TEXT,
            product_name TEXT,
            purchase_uom TEXT,
            units_per_pack REAL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vendor_profile_id)
                REFERENCES stock_planning_vendor_profiles(id)
                ON DELETE RESTRICT,
            UNIQUE(vendor_profile_id, internal_sku)
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_branches (
            branch_code TEXT PRIMARY KEY,
            branch_name TEXT NOT NULL,
            is_primary_receipt INTEGER NOT NULL DEFAULT 0
                CHECK(is_primary_receipt IN (0,1)),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_catalog_vendor_sku
        ON stock_planning_product_catalog(vendor_profile_id, vendor_sku)""",
        """CREATE TABLE IF NOT EXISTS stock_planning_families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            family_code TEXT NOT NULL,
            family_name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'derived',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vendor_profile_id)
                REFERENCES stock_planning_vendor_profiles(id)
                ON DELETE RESTRICT,
            UNIQUE(vendor_profile_id, family_code)
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_family_members (
            family_id INTEGER NOT NULL,
            internal_sku TEXT NOT NULL,
            relationship_role TEXT NOT NULL DEFAULT 'member',
            confidence REAL,
            source TEXT NOT NULL DEFAULT 'derived',
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(family_id, internal_sku, relationship_role),
            FOREIGN KEY(family_id) REFERENCES stock_planning_families(id)
                ON DELETE CASCADE
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_family_members_sku
        ON stock_planning_family_members(internal_sku)""",
        """CREATE TABLE IF NOT EXISTS stock_planning_transformations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            transformation_code TEXT NOT NULL,
            transformation_type TEXT NOT NULL CHECK(
                transformation_type IN (
                    'unit_conversion','length_cut','pack','substitute','assembly'
                )
            ),
            purchase_sku TEXT NOT NULL,
            purchase_quantity REAL NOT NULL DEFAULT 1 CHECK(purchase_quantity > 0),
            waste_rate REAL NOT NULL DEFAULT 0 CHECK(waste_rate >= 0),
            rounding_mode TEXT NOT NULL DEFAULT 'ceil'
                CHECK(rounding_mode IN ('ceil','nearest','none')),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','approved','retired')),
            effective_from TEXT,
            effective_to TEXT,
            notes TEXT,
            created_by TEXT NOT NULL DEFAULT 'system',
            approved_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            FOREIGN KEY(vendor_profile_id)
                REFERENCES stock_planning_vendor_profiles(id)
                ON DELETE RESTRICT,
            UNIQUE(vendor_profile_id, transformation_code, version)
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_transformation_inputs (
            transformation_id INTEGER NOT NULL,
            sales_sku TEXT NOT NULL,
            sales_quantity REAL NOT NULL DEFAULT 1 CHECK(sales_quantity > 0),
            normalized_consumption REAL NOT NULL CHECK(normalized_consumption > 0),
            PRIMARY KEY(transformation_id, sales_sku),
            FOREIGN KEY(transformation_id)
                REFERENCES stock_planning_transformations(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_transit_supplies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            branch_code TEXT NOT NULL,
            internal_sku TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity >= 0),
            expected_date TEXT,
            purchase_order_reference TEXT,
            transit_status TEXT NOT NULL DEFAULT 'confirmed'
                CHECK(transit_status IN ('planned','confirmed','shipped','received','cancelled')),
            source TEXT NOT NULL DEFAULT 'manual',
            created_by TEXT NOT NULL DEFAULT 'system',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vendor_profile_id)
                REFERENCES stock_planning_vendor_profiles(id)
                ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_transit_vendor_branch_sku
        ON stock_planning_transit_supplies(
            vendor_profile_id, branch_code, internal_sku, expected_date
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            snapshot_key TEXT NOT NULL UNIQUE,
            as_of_date TEXT NOT NULL,
            inventory_snapshot_date TEXT,
            sales_through_date TEXT,
            source_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'frozen' CHECK(status = 'frozen'),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vendor_profile_id)
                REFERENCES stock_planning_vendor_profiles(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_products (
            snapshot_id INTEGER NOT NULL,
            internal_sku TEXT NOT NULL,
            vendor_sku TEXT,
            product_name TEXT,
            product_sources_json TEXT NOT NULL,
            is_catalog_product INTEGER NOT NULL DEFAULT 0 CHECK(is_catalog_product IN (0,1)),
            has_sales_history INTEGER NOT NULL DEFAULT 0 CHECK(has_sales_history IN (0,1)),
            has_inventory_history INTEGER NOT NULL DEFAULT 0 CHECK(has_inventory_history IN (0,1)),
            has_transit INTEGER NOT NULL DEFAULT 0 CHECK(has_transit IN (0,1)),
            PRIMARY KEY(snapshot_id, internal_sku),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_inventory (
            snapshot_id INTEGER NOT NULL,
            branch_code TEXT NOT NULL,
            branch_name TEXT,
            internal_sku TEXT NOT NULL,
            on_hand REAL NOT NULL DEFAULT 0,
            reserved REAL NOT NULL DEFAULT 0,
            remitted REAL NOT NULL DEFAULT 0,
            usable REAL NOT NULL DEFAULT 0,
            undated_transit REAL NOT NULL DEFAULT 0,
            dated_transit REAL NOT NULL DEFAULT 0,
            average_cost REAL,
            PRIMARY KEY(snapshot_id, branch_code, internal_sku),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_transit (
            snapshot_id INTEGER NOT NULL,
            transit_supply_id INTEGER NOT NULL,
            branch_code TEXT NOT NULL,
            internal_sku TEXT NOT NULL,
            quantity REAL NOT NULL,
            expected_date TEXT,
            purchase_order_reference TEXT,
            PRIMARY KEY(snapshot_id, transit_supply_id),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(transit_supply_id)
                REFERENCES stock_planning_transit_supplies(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            severity TEXT NOT NULL CHECK(severity IN ('info','warning','error')),
            issue_code TEXT NOT NULL,
            branch_code TEXT,
            internal_sku TEXT,
            message TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_snapshot_issues
        ON stock_planning_snapshot_issues(snapshot_id, severity, issue_code)""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_no_update
        BEFORE UPDATE ON stock_planning_snapshots BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_no_delete
        BEFORE DELETE ON stock_planning_snapshots BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_products_no_update
        BEFORE UPDATE ON stock_planning_snapshot_products BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_products_no_delete
        BEFORE DELETE ON stock_planning_snapshot_products BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_inventory_no_update
        BEFORE UPDATE ON stock_planning_snapshot_inventory BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_inventory_no_delete
        BEFORE DELETE ON stock_planning_snapshot_inventory BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_transit_no_update
        BEFORE UPDATE ON stock_planning_snapshot_transit BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_transit_no_delete
        BEFORE DELETE ON stock_planning_snapshot_transit BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_issues_no_update
        BEFORE UPDATE ON stock_planning_snapshot_issues BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_snapshot_issues_no_delete
        BEFORE DELETE ON stock_planning_snapshot_issues BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
    ))


def _migration_0036_stock_planning_operational_inputs(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_analysis_inputs (
            snapshot_id INTEGER PRIMARY KEY,
            manufacturing_days INTEGER NOT NULL CHECK(manufacturing_days >= 0),
            international_shipping_days INTEGER NOT NULL
                CHECK(international_shipping_days >= 0),
            receiving_days INTEGER NOT NULL CHECK(receiving_days >= 0),
            cali_transfer_days INTEGER NOT NULL CHECK(cali_transfer_days >= 0),
            coverage_months REAL NOT NULL CHECK(coverage_months > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_inputs_no_update
        BEFORE UPDATE ON stock_planning_analysis_inputs BEGIN
            SELECT RAISE(ABORT, 'stock planning analysis inputs are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_inputs_no_delete
        BEFORE DELETE ON stock_planning_analysis_inputs BEGIN
            SELECT RAISE(ABORT, 'stock planning analysis inputs are immutable');
        END""",
    ))


def _migration_0037_stock_planning_forecast_evidence(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_forecast_evidence (
            snapshot_id INTEGER PRIMARY KEY,
            engine_version TEXT NOT NULL,
            result_json TEXT NOT NULL,
            calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_forecast_evidence_no_update
        BEFORE UPDATE ON stock_planning_forecast_evidence BEGIN
            SELECT RAISE(ABORT, 'stock planning forecast evidence is immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_forecast_evidence_no_delete
        BEFORE DELETE ON stock_planning_forecast_evidence BEGIN
            SELECT RAISE(ABORT, 'stock planning forecast evidence is immutable');
        END""",
    ))


def _migration_0038_stock_planning_versioned_forecasts(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_forecast_versions (
            snapshot_id INTEGER NOT NULL,
            engine_version TEXT NOT NULL,
            result_json TEXT NOT NULL,
            calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(snapshot_id,engine_version),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """INSERT OR IGNORE INTO stock_planning_forecast_versions
        (snapshot_id,engine_version,result_json,calculated_at)
        SELECT snapshot_id,engine_version,result_json,calculated_at
        FROM stock_planning_forecast_evidence""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_forecast_versions_no_update
        BEFORE UPDATE ON stock_planning_forecast_versions BEGIN
            SELECT RAISE(ABORT, 'stock planning forecast versions are immutable');
        END""",
        """CREATE TRIGGER IF NOT EXISTS trg_stock_forecast_versions_no_delete
        BEFORE DELETE ON stock_planning_forecast_versions BEGIN
            SELECT RAISE(ABORT, 'stock planning forecast versions are immutable');
        END""",
    ))


def _migration_0039_stock_planning_decisions(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            item_type TEXT NOT NULL CHECK(item_type IN ('purchase','transfer')),
            item_key TEXT NOT NULL,
            internal_sku TEXT NOT NULL,
            branch_code TEXT,
            from_branch_code TEXT,
            to_branch_code TEXT,
            suggested_quantity REAL NOT NULL CHECK(suggested_quantity >= 0),
            approved_quantity REAL NOT NULL CHECK(approved_quantity >= 0),
            decision_status TEXT NOT NULL CHECK(
                decision_status IN ('approved','changed','rejected')
            ),
            decision_note TEXT,
            decided_by TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT,
            UNIQUE(snapshot_id,item_type,item_key)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_decisions_snapshot
        ON stock_planning_decisions(snapshot_id,item_type)""",
        """CREATE TABLE IF NOT EXISTS stock_planning_decision_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER NOT NULL,
            snapshot_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            suggested_quantity REAL NOT NULL,
            approved_quantity REAL NOT NULL,
            decision_status TEXT NOT NULL,
            decision_note TEXT,
            decided_by TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(decision_id) REFERENCES stock_planning_decisions(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
    ))


def _migration_0040_stock_planning_decision_history(
    connection: Connection,
) -> None:
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_decision_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER NOT NULL,
            snapshot_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            suggested_quantity REAL NOT NULL,
            approved_quantity REAL NOT NULL,
            decision_status TEXT NOT NULL,
            decision_note TEXT,
            decided_by TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(decision_id) REFERENCES stock_planning_decisions(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_decision_history_item
        ON stock_planning_decision_history(snapshot_id,item_type,item_key,decided_at)""",
    ))


def _migration_0041_repair_crm_opportunity_lifecycle(
    connection: Connection,
) -> None:
    """Repair lifecycle fields imported before CRM stage normalization."""
    if not _table_exists(connection, "ws_projects"):
        return
    required = {"origin", "import_metadata", "status"}
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(ws_projects)").fetchall()
    }
    if not required.issubset(columns):
        return
    rows = connection.execute(
        """SELECT id,status,import_metadata FROM ws_projects
        WHERE origin='crm' AND import_metadata IS NOT NULL"""
    ).fetchall()
    for row in rows:
        if row["status"] in {"won", "lost", "cancelled"}:
            continue
        try:
            facts = json.loads(row["import_metadata"]).get("source_facts", {})
        except (TypeError, json.JSONDecodeError):
            continue
        status = str(facts.get("crm_status") or "").strip().casefold()
        stage = str(facts.get("crm_stage") or "").strip().casefold()
        normalized = (
            "cancelled" if status in {"cancelado", "cancelada", "cancelled"}
            else "won" if status in {"realizado", "realizada", "ganado", "ganada", "won"}
            else "lost" if status in {"perdido", "perdida", "lost"}
            else "negotiation" if "negoci" in stage
            else "waiting_customer" if "esper" in stage and "cliente" in stage
            else "quoting" if "propuesta" in stage or "cotiz" in stage
            else "prospect"
        )
        source_date = facts.get("source_updated_at")
        connection.execute(
            """UPDATE ws_projects
            SET status=?,
                closed_at=CASE
                    WHEN ? IN ('won','lost','cancelled')
                    THEN COALESCE(closed_at, ?)
                    ELSE closed_at
                END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (normalized, normalized, source_date, row["id"]),
        )


def _migration_0042_advisor_management(connection: Connection) -> None:
    """Unify visit commitments and persist lightweight advisor reviews."""
    if _table_exists(connection, "ws_visit_followups"):
        _add_column(connection, "ws_visit_followups", "completed_at", "TEXT")
        _add_column(
            connection, "ws_visit_followups", "reschedule_count",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _add_column(connection, "ws_visit_followups", "reschedule_reason", "TEXT")
        connection.execute(
            """UPDATE ws_visit_followups
            SET status=CASE
                WHEN LOWER(COALESCE(status,'')) IN
                    ('cerrado','closed','completado','completed') THEN 'completed'
                ELSE 'pending'
            END"""
        )
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ws_advisor_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            advisor_name TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled'
                CHECK(status IN ('scheduled','completed','cancelled')),
            notes TEXT,
            created_by TEXT NOT NULL DEFAULT 'system',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_advisor_reviews_name_date
        ON ws_advisor_reviews(advisor_name, scheduled_at)""",
    ))


def _migration_0043_canonical_visit_advisors(connection: Connection) -> None:
    """Map AppSheet display names to the canonical commercial identity."""
    aliases = (
        ("Andrea Jimenez", "NUBIA ANDREA JIMENEZ"),
        ("Fabio Valencia", "FABIO NELSON VALENCIA"),
        ("Jairo Vera", "JAIRO DAVID VERA"),
        ("Jeisman Holguin", "JEISMAN HOLGUIN"),
        ("Jose Beltran", "JOSE TRINIDAD BELTRAN CARVAJAL"),
        ("Yeisson Renteria", "YEISSON ANDRES RENTERIA MOSQUERA"),
    )
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS ws_advisor_aliases (
            alias TEXT PRIMARY KEY COLLATE NOCASE,
            canonical_name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'appsheet',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
    ))
    for alias, canonical in aliases:
        connection.execute(
            """INSERT INTO ws_advisor_aliases(alias,canonical_name,source)
            VALUES (?,?,'appsheet') ON CONFLICT(alias) DO UPDATE SET
            canonical_name=excluded.canonical_name,is_active=1""",
            (alias, canonical),
        )
        if _table_exists(connection, "ws_commercial_visits"):
            connection.execute(
                """UPDATE ws_commercial_visits SET advisor_name=?
                WHERE LOWER(TRIM(advisor_name))=LOWER(TRIM(?))""",
                (canonical, alias),
            )
        if _table_exists(connection, "ws_visit_followups"):
            connection.execute(
                """UPDATE ws_visit_followups SET owner_name=?
                WHERE LOWER(TRIM(owner_name))=LOWER(TRIM(?))""",
                (canonical, alias),
            )


def _migration_0044_customer_branch_mapping(connection: Connection) -> None:
    """Map ERP sales branches to customer sites and commercial owners."""
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS erp_customer_branch_mappings (
            customer_id TEXT NOT NULL,
            branch_code TEXT NOT NULL,
            customer_site_id TEXT,
            site_label TEXT,
            city TEXT,
            sales_rep TEXT NOT NULL,
            office TEXT NOT NULL CHECK(office IN ('Bogotá','Cali')),
            mapping_status TEXT NOT NULL DEFAULT 'confirmed'
                CHECK(mapping_status IN ('confirmed','owner_only','pending')),
            evidence TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(customer_id,branch_code)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_erp_branch_mapping_owner
        ON erp_customer_branch_mappings(sales_rep,office)""",
    ))
    mappings = (
        ("860002302", "0", None, "Sede Eternit no diferenciada", None,
         "JHON ALEXANDER PINZON", "Bogotá", "owner_only",
         "Eternit tiene dos sedes no Cali, ambas asignadas a Jhon; falta distinguir Barranquilla/Sibaté."),
        ("860002302", "1", None, "Sede Eternit no diferenciada", None,
         "JHON ALEXANDER PINZON", "Bogotá", "owner_only",
         "Eternit tiene dos sedes no Cali, ambas asignadas a Jhon; falta distinguir Barranquilla/Sibaté."),
        ("860002302", "2", "860002302_YUMBO_PUERTO ISAACS, YUMBO KM 15",
         "ETERNIT COLOMBIANA S.A. - CALI", "YUMBO",
         "YEISSON ANDRES RENTERIA MOSQUERA", "Cali", "confirmed",
         "Confirmado en ERP: Dirección 3/3, Cód 2, Puerto Isaacs Yumbo Km 15, vendedor Yeisson."),
    )
    for mapping in mappings:
        connection.execute(
            """INSERT INTO erp_customer_branch_mappings(
                customer_id,branch_code,customer_site_id,site_label,city,
                sales_rep,office,mapping_status,evidence
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(customer_id,branch_code) DO UPDATE SET
                customer_site_id=excluded.customer_site_id,
                site_label=excluded.site_label,city=excluded.city,
                sales_rep=excluded.sales_rep,office=excluded.office,
                mapping_status=excluded.mapping_status,evidence=excluded.evidence,
                updated_at=CURRENT_TIMESTAMP""",
            mapping,
        )


def _migration_0045_priority_branch_mappings(connection: Connection) -> None:
    """Infer ERP branch codes from each customer's ID-ordered address list."""
    if not all(
        _table_exists(connection, table)
        for table in ("raw_customers", "raw_sales", "dim_customer")
    ):
        return
    target_customers = (
        "860002523",  # Cemex
        "890300406",  # Cartón de Colombia
        "890900161",  # Productos Familia
        "830050346",  # Nestlé Purina
    )
    cali_sellers = {
        "ALMACEN CALI -UNO-", "DIANA MARIA VELASQUEZ C",
        "FABIO NELSON VALENCIA", "JAIRO DAVID VERA", "JEISMAN HOLGUIN",
        "JOSE TRINIDAD BELTRAN CARVAJAL", "NUBIA ANDREA JIMENEZ",
        "RICARDO LUGO", "WHATSAPP CALI",
        "YEISSON ANDRES RENTERIA MOSQUERA",
    }
    for customer_id in target_customers:
        source_rows = connection.execute(
            """SELECT rowid AS source_rowid,ID,nit,razonsocial,ciudad,
                direccion1,vendedor,
                ROW_NUMBER() OVER (
                    PARTITION BY REPLACE(nit,',','')
                    ORDER BY CAST(ID AS INTEGER),ID,rowid
                ) - 1 AS inferred_code
            FROM raw_customers
            WHERE REPLACE(nit,',','')=?
            ORDER BY inferred_code""",
            (customer_id,),
        ).fetchall()
        sales_codes = {
            str(row["sucursal"]).strip()
            for row in connection.execute(
                """SELECT DISTINCT sucursal FROM raw_sales
                WHERE REPLACE(nit,',','')=?""",
                (customer_id,),
            ).fetchall()
        }
        for row in source_rows:
            branch_code = str(row["inferred_code"])
            if branch_code not in sales_codes:
                continue
            existing = connection.execute(
                """SELECT 1 FROM erp_customer_branch_mappings
                WHERE customer_id=? AND branch_code=?""",
                (customer_id, branch_code),
            ).fetchone()
            if existing:
                continue
            site = connection.execute(
                """SELECT customer_site_id FROM dim_customer
                WHERE customer_id=?
                  AND UPPER(TRIM(COALESCE(city,'')))=UPPER(TRIM(COALESCE(?,'')))
                  AND UPPER(TRIM(COALESCE(address,'')))=UPPER(TRIM(COALESCE(?,'')))
                ORDER BY customer_site_id LIMIT 1""",
                (customer_id, row["ciudad"], row["direccion1"]),
            ).fetchone()
            seller = str(row["vendedor"] or "").strip().upper()
            connection.execute(
                """INSERT INTO erp_customer_branch_mappings(
                    customer_id,branch_code,customer_site_id,site_label,city,
                    sales_rep,office,mapping_status,evidence
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    customer_id, branch_code,
                    site["customer_site_id"] if site else None,
                    f"{row['razonsocial']} · {row['ciudad']}", row["ciudad"],
                    seller, "Cali" if seller in cali_sellers else "Bogotá",
                    "confirmed" if site else "owner_only",
                    "Inferido por posición de la dirección ordenada por ID ERP; "
                    "regla validada contra Cód de sucursal de Eternit.",
                ),
            )


def _migration_0046_industrial_branch_mappings(connection: Connection) -> None:
    """Infer remaining multisite branches, excluding retail channels."""
    if not all(
        _table_exists(connection, table)
        for table in ("raw_customers", "raw_sales", "dim_customer")
    ):
        return
    cali_sellers = {
        "DIANA MARIA VELASQUEZ C", "FABIO NELSON VALENCIA",
        "JAIRO DAVID VERA", "JEISMAN HOLGUIN",
        "JOSE TRINIDAD BELTRAN CARVAJAL", "NUBIA ANDREA JIMENEZ",
        "RICARDO LUGO", "YEISSON ANDRES RENTERIA MOSQUERA",
    }
    commerce_sellers = {"ALMACEN", "ALMACEN CALI -UNO-", "WHATSAPP CALI", "WHATSAPP MARÍA"}
    multi_customer_ids = [
        row["customer_id"]
        for row in connection.execute(
            """SELECT customer_id FROM dim_customer GROUP BY customer_id
            HAVING COUNT(DISTINCT seller)>1"""
        ).fetchall()
    ]
    for customer_id in multi_customer_ids:
        rows = connection.execute(
            """SELECT rowid AS source_rowid,ID,razonsocial,ciudad,direccion1,
                vendedor,ROW_NUMBER() OVER (
                    PARTITION BY REPLACE(nit,',','')
                    ORDER BY CAST(ID AS INTEGER),ID,rowid
                ) - 1 AS inferred_code
            FROM raw_customers WHERE REPLACE(nit,',','')=?
            ORDER BY inferred_code""",
            (customer_id,),
        ).fetchall()
        sales_codes = {
            str(row["sucursal"]).strip()
            for row in connection.execute(
                """SELECT DISTINCT sucursal FROM raw_sales
                WHERE REPLACE(nit,',','')=?""",
                (customer_id,),
            ).fetchall()
        }
        for row in rows:
            branch_code = str(row["inferred_code"])
            seller = str(row["vendedor"] or "").strip().upper()
            if branch_code not in sales_codes or seller in commerce_sellers or not seller:
                continue
            if connection.execute(
                """SELECT 1 FROM erp_customer_branch_mappings
                WHERE customer_id=? AND branch_code=?""",
                (customer_id, branch_code),
            ).fetchone():
                continue
            site = connection.execute(
                """SELECT customer_site_id FROM dim_customer
                WHERE customer_id=?
                  AND UPPER(TRIM(COALESCE(city,'')))=UPPER(TRIM(COALESCE(?,'')))
                  AND UPPER(TRIM(COALESCE(address,'')))=UPPER(TRIM(COALESCE(?,'')))
                ORDER BY customer_site_id LIMIT 1""",
                (customer_id, row["ciudad"], row["direccion1"]),
            ).fetchone()
            connection.execute(
                """INSERT INTO erp_customer_branch_mappings(
                    customer_id,branch_code,customer_site_id,site_label,city,
                    sales_rep,office,mapping_status,evidence
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    customer_id, branch_code,
                    site["customer_site_id"] if site else None,
                    f"{row['razonsocial']} · {row['ciudad']}", row["ciudad"],
                    seller, "Cali" if seller in cali_sellers else "Bogotá",
                    "confirmed" if site else "owner_only",
                    "Mapping industrial inferido por posición de dirección ordenada "
                    "por ID ERP; canales Almacén y WhatsApp excluidos.",
                ),
            )


def _migration_0047_executive_viewer_users(connection: Connection) -> None:
    """Pre-authorize executive viewers for Google Workspace sign-in."""
    users = (
        (
            "Gerencia General",
            "gerencia@lugohermanos.com",
            "commercial_management",
            "all",
        ),
        (
            "Nicolás Lugo",
            "nicolas.lugo@lugohermanos.com",
            "read_only",
            "all",
        ),
    )
    for display_name, email, role, portfolio_scope in users:
        connection.execute(
            """INSERT INTO ws_users (
                display_name,email,email_normalized,role,is_active,portfolio_scope
            )
            SELECT ?,?,LOWER(TRIM(?)),?,1,?
            WHERE NOT EXISTS (
                SELECT 1 FROM ws_users
                WHERE LOWER(TRIM(email))=LOWER(TRIM(?))
            )""",
            (display_name, email, email, role, portfolio_scope, email),
        )


def _migration_0048_rocio_rocha_management_access(connection: Connection) -> None:
    """Authorize Rocío Rocha as active management with global scope."""
    email = "rocio.rocha@lugohermanos.com"
    existing = connection.execute(
        """SELECT id FROM ws_users
        WHERE email_normalized=LOWER(TRIM(?))
           OR LOWER(TRIM(email))=LOWER(TRIM(?))""",
        (email, email),
    ).fetchone()
    if existing:
        connection.execute(
            """UPDATE ws_users
            SET display_name=?, email=?, email_normalized=LOWER(TRIM(?)),
                role='commercial_management', is_active=1,
                portfolio_scope='all', updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            ("Rocío Rocha", email, email, existing["id"]),
        )
        return
    connection.execute(
        """INSERT INTO ws_users (
            display_name,email,email_normalized,role,is_active,portfolio_scope
        ) VALUES (?, ?, LOWER(TRIM(?)), 'commercial_management', 1, 'all')""",
        ("Rocío Rocha", email, email),
    )


def _migration_0049_enable_thomson_stock_planning(connection: Connection) -> None:
    """Expose Thomson using the ERP aliases already present in sales/inventory."""
    connection.execute(
        """INSERT INTO stock_planning_vendor_profiles (
            vendor_name,profile_code,inventory_brand_codes_json,
            sales_suffixes_json,lead_time_day_basis,is_active
        ) VALUES ('Thomson','Thomson','["THO"]','["THO"]','calendar',1)
        ON CONFLICT(profile_code) DO UPDATE SET
            vendor_name=excluded.vendor_name,
            inventory_brand_codes_json=excluded.inventory_brand_codes_json,
            sales_suffixes_json=excluded.sales_suffixes_json,
            is_active=1,
            updated_at=CURRENT_TIMESTAMP"""
    )


def _migration_0050_erp_fob_price_import(connection: Connection) -> None:
    """Retain immutable ERP FOB price extracts and audit their imports."""
    execution_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='erp_import_executions'"
    ).fetchone()["sql"]
    if "'fob_prices'" not in str(execution_sql):
        _execute_statements(connection, (
            """CREATE TABLE erp_import_executions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_type TEXT NOT NULL CHECK(import_type IN (
                    'sales','customers','inventory','crm_opportunities',
                    'fob_prices'
                )),
                original_filename TEXT NOT NULL,
                stored_file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'previewed','processing','completed','failed'
                )),
                rows_read INTEGER NOT NULL DEFAULT 0,
                rows_inserted INTEGER NOT NULL DEFAULT 0,
                rows_updated INTEGER NOT NULL DEFAULT 0,
                rows_skipped INTEGER NOT NULL DEFAULT 0,
                duplicates_count INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT,
                errors_json TEXT,
                execution_log_json TEXT NOT NULL DEFAULT '{}',
                executed_by TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                customers_inserted INTEGER NOT NULL DEFAULT 0,
                customers_updated INTEGER NOT NULL DEFAULT 0,
                customers_unchanged INTEGER NOT NULL DEFAULT 0,
                customer_sites_inserted INTEGER NOT NULL DEFAULT 0,
                customer_sites_updated INTEGER NOT NULL DEFAULT 0,
                customer_sites_unchanged INTEGER NOT NULL DEFAULT 0,
                snapshot_date TEXT,
                mapping_profile_version_id INTEGER REFERENCES
                    opportunity_import_profile_versions(id) ON DELETE RESTRICT,
                groups_identified INTEGER NOT NULL DEFAULT 0,
                groups_to_create INTEGER NOT NULL DEFAULT 0,
                groups_to_update INTEGER NOT NULL DEFAULT 0,
                groups_unchanged INTEGER NOT NULL DEFAULT 0,
                groups_needs_review INTEGER NOT NULL DEFAULT 0,
                groups_blocked INTEGER NOT NULL DEFAULT 0,
                customer_resolutions_json TEXT NOT NULL DEFAULT '{}',
                groups_eligible INTEGER NOT NULL DEFAULT 0,
                groups_imported INTEGER NOT NULL DEFAULT 0,
                groups_deferred INTEGER NOT NULL DEFAULT 0
            )""",
            """INSERT INTO erp_import_executions_new SELECT *
            FROM erp_import_executions""",
            """CREATE TABLE erp_import_issues_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_execution_id INTEGER NOT NULL,
                row_number INTEGER,
                severity TEXT NOT NULL CHECK(severity IN ('warning','error')),
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(import_execution_id)
                    REFERENCES erp_import_executions_new(id) ON DELETE CASCADE
            )""",
            """INSERT INTO erp_import_issues_new SELECT * FROM erp_import_issues""",
            "DROP TABLE erp_import_issues",
            "DROP TABLE erp_import_executions",
            "ALTER TABLE erp_import_executions_new RENAME TO erp_import_executions",
            "ALTER TABLE erp_import_issues_new RENAME TO erp_import_issues",
        ))
    _execute_statements(connection, (
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_type_started
        ON erp_import_executions(import_type, started_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_executions_hash
        ON erp_import_executions(file_hash, import_type)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_import_issues_execution
        ON erp_import_issues(import_execution_id, severity)""",
        """CREATE TABLE IF NOT EXISTS erp_fob_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_execution_id INTEGER NOT NULL,
            idproducto TEXT NOT NULL,
            prefijo TEXT,
            sufijo TEXT NOT NULL,
            idfam2 TEXT,
            fob_usd REAL NOT NULL CHECK(fob_usd >= 0),
            lista1_cop REAL,
            nit TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT,
            UNIQUE(import_execution_id, idproducto, nit)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_erp_fob_product_import
        ON erp_fob_price_history(idproducto, imported_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_erp_fob_suffix_import
        ON erp_fob_price_history(sufijo, imported_at DESC)""",
    ))


def _migration_0051_stock_planning_fob_values(connection: Connection) -> None:
    """Freeze the applicable ERP FOB value with each planning snapshot."""
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_fob_prices (
            snapshot_id INTEGER NOT NULL,
            internal_sku TEXT NOT NULL,
            fob_usd REAL NOT NULL CHECK(fob_usd >= 0),
            lista1_cop REAL,
            supplier_nit TEXT NOT NULL,
            price_import_execution_id INTEGER NOT NULL,
            PRIMARY KEY(snapshot_id, internal_sku),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT,
            FOREIGN KEY(price_import_execution_id)
                REFERENCES erp_import_executions(id) ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_snapshot_fob_import
        ON stock_planning_snapshot_fob_prices(price_import_execution_id)""",
        """INSERT OR IGNORE INTO stock_planning_snapshot_fob_prices (
            snapshot_id,internal_sku,fob_usd,lista1_cop,supplier_nit,
            price_import_execution_id
        )
        SELECT p.snapshot_id,p.internal_sku,h.fob_usd,h.lista1_cop,h.nit,
               h.import_execution_id
        FROM stock_planning_snapshot_products p
        JOIN stock_planning_snapshots s ON s.id=p.snapshot_id
        JOIN stock_planning_vendor_profiles v ON v.id=s.vendor_profile_id
        JOIN erp_fob_price_history h ON h.id=(
            SELECT candidate.id FROM erp_fob_price_history candidate
            WHERE candidate.idproducto=p.internal_sku
              AND UPPER(candidate.sufijo) IN (
                  SELECT UPPER(value) FROM json_each(v.inventory_brand_codes_json)
                  UNION
                  SELECT UPPER(value) FROM json_each(v.sales_suffixes_json)
              )
            ORDER BY candidate.imported_at DESC,
                     candidate.import_execution_id DESC,candidate.id DESC
            LIMIT 1
        )""",
    ))


def _migration_0052_archivable_stock_snapshots(connection: Connection) -> None:
    """Allow administrators to hide test analyses without destroying evidence."""
    _add_column(connection, "stock_planning_snapshots", "archived_at", "TEXT")
    _add_column(connection, "stock_planning_snapshots", "archived_by", "TEXT")
    _execute_statements(connection, (
        "DROP TRIGGER IF EXISTS trg_stock_snapshot_no_update",
        """CREATE TRIGGER trg_stock_snapshot_no_update
        BEFORE UPDATE ON stock_planning_snapshots
        WHEN NEW.vendor_profile_id IS NOT OLD.vendor_profile_id
          OR NEW.snapshot_key IS NOT OLD.snapshot_key
          OR NEW.as_of_date IS NOT OLD.as_of_date
          OR NEW.inventory_snapshot_date IS NOT OLD.inventory_snapshot_date
          OR NEW.sales_through_date IS NOT OLD.sales_through_date
          OR NEW.source_fingerprint IS NOT OLD.source_fingerprint
          OR NEW.status IS NOT OLD.status
          OR NEW.created_by IS NOT OLD.created_by
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'stock planning snapshots are immutable');
        END""",
        """CREATE INDEX IF NOT EXISTS idx_stock_snapshots_active_profile
        ON stock_planning_snapshots(vendor_profile_id,archived_at,created_at DESC)""",
    ))


def _migration_0053_bogota_kr68_stock_planning(connection: Connection) -> None:
    """Include KR 68 as active physical storage in Bogotá planning snapshots."""
    connection.execute(
        """INSERT INTO stock_planning_branches (
            branch_code,branch_name,is_primary_receipt,is_active
        ) VALUES ('16','Bogotá · KR 68',0,1)
        ON CONFLICT(branch_code) DO UPDATE SET
            branch_name=excluded.branch_name,
            is_primary_receipt=0,
            is_active=1,
            updated_at=CURRENT_TIMESTAMP"""
    )


def _migration_0054_stock_planning_sales_evidence(connection: Connection) -> None:
    """Freeze customer-name sales movements used to explain each analysis."""
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_snapshot_sales_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            sale_date TEXT NOT NULL,
            internal_sku TEXT NOT NULL,
            branch_code TEXT NOT NULL,
            warehouse_name TEXT,
            customer_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            net_value_cop REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
                ON DELETE RESTRICT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_snapshot_sales_product
        ON stock_planning_snapshot_sales_movements(
            snapshot_id,internal_sku,branch_code,sale_date DESC
        )""",
    ))
    if not _table_exists(connection, "raw_sales"):
        return
    required = {"fecha", "idproducto", "idbodega", "cantidad", "sufijo"}
    raw_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(raw_sales)")
    }
    if not required.issubset(raw_columns):
        return
    raw_name = (
        "NULLIF(TRIM(r.razonsocial),'')" if "razonsocial" in raw_columns else "NULL"
    )
    customer_name = f"COALESCE({raw_name},'Cliente sin nombre')"
    warehouse_name = (
        "COALESCE(NULLIF(TRIM(r.nombrebodega),''),TRIM(r.idbodega))"
        if "nombrebodega" in raw_columns else "TRIM(r.idbodega)"
    )
    net_value = "COALESCE(r.neto,0)" if "neto" in raw_columns else "0"
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_raw_sales_planning_evidence
        ON raw_sales(sufijo,fecha,idbodega,idproducto)"""
    )
    snapshots = connection.execute(
        """SELECT s.id,s.as_of_date,v.sales_suffixes_json
        FROM stock_planning_snapshots s
        JOIN stock_planning_vendor_profiles v ON v.id=s.vendor_profile_id
        WHERE s.archived_at IS NULL"""
    ).fetchall()
    for snapshot in snapshots:
        suffixes = [
            str(value).strip().upper()
            for value in json.loads(snapshot["sales_suffixes_json"] or "[]")
            if str(value).strip()
        ]
        if not suffixes:
            continue
        marks = ",".join("?" for _ in suffixes)
        connection.execute(
            f"""INSERT INTO stock_planning_snapshot_sales_movements (
                snapshot_id,sale_date,internal_sku,branch_code,warehouse_name,
                customer_name,quantity,net_value_cop
            )
            SELECT ?,date(r.fecha),UPPER(TRIM(r.idproducto)),TRIM(r.idbodega),
                   {warehouse_name},{customer_name},
                   CAST(COALESCE(r.cantidad,0) AS REAL),CAST({net_value} AS REAL)
            FROM raw_sales r
            WHERE r.sufijo IN ({marks})
              AND date(r.fecha)<=date(?)
              AND date(r.fecha)>=date(?,'start of month','-35 months')
              AND TRIM(r.idbodega) IN ('1','16','50')""",
            (snapshot["id"], *suffixes, snapshot["as_of_date"], snapshot["as_of_date"]),
        )


def _migration_0055_periodic_stock_replenishment(connection: Connection) -> None:
    """Configure transfer-only brands and their internal replenishment inbox."""
    _add_column(
        connection, "stock_planning_vendor_profiles", "planning_purpose",
        "TEXT NOT NULL DEFAULT 'purchase_order'",
    )
    for brand in ("SKF", "FAG", "NTN", "NQK", "KMK"):
        connection.execute(
            """INSERT INTO stock_planning_vendor_profiles (
                vendor_name,profile_code,inventory_brand_codes_json,
                sales_suffixes_json,lead_time_day_basis,is_active
            ) VALUES (?,?,?,?, 'calendar',1)
            ON CONFLICT(profile_code) DO UPDATE SET
                vendor_name=excluded.vendor_name,
                inventory_brand_codes_json=excluded.inventory_brand_codes_json,
                sales_suffixes_json=excluded.sales_suffixes_json,
                is_active=1,updated_at=CURRENT_TIMESTAMP""",
            (brand, brand, json.dumps([brand]), json.dumps([brand])),
        )
    connection.execute(
        """UPDATE stock_planning_vendor_profiles
        SET planning_purpose='replenishment'
        WHERE UPPER(profile_code) IN ('SKF','FAG','NTN','NQK','KMK')"""
    )
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS stock_planning_replenishment_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_profile_id INTEGER NOT NULL,
            scheduled_for TEXT NOT NULL,
            inventory_snapshot_date TEXT,
            snapshot_id INTEGER,
            status TEXT NOT NULL CHECK(status IN ('running','completed','skipped','failed')),
            triggered_by TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY(vendor_profile_id) REFERENCES stock_planning_vendor_profiles(id),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id),
            UNIQUE(vendor_profile_id,scheduled_for)
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_import_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            replenishment_run_id INTEGER NOT NULL,
            snapshot_id INTEGER NOT NULL,
            vendor_profile_id INTEGER NOT NULL,
            internal_sku TEXT NOT NULL,
            branch_code TEXT NOT NULL DEFAULT '50',
            suggested_quantity REAL NOT NULL CHECK(suggested_quantity > 0),
            abc_class TEXT NOT NULL,
            xyz_class TEXT NOT NULL,
            assigned_to TEXT,
            status TEXT NOT NULL DEFAULT 'pending_review'
                CHECK(status IN ('ready','pending_review','reviewed','dismissed','resolved')),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(replenishment_run_id) REFERENCES stock_planning_replenishment_runs(id),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id),
            FOREIGN KEY(vendor_profile_id) REFERENCES stock_planning_vendor_profiles(id),
            UNIQUE(snapshot_id,internal_sku,branch_code)
        )""",
        """CREATE TABLE IF NOT EXISTS stock_planning_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            replenishment_run_id INTEGER NOT NULL,
            recipient_email TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            snapshot_id INTEGER,
            read_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(replenishment_run_id) REFERENCES stock_planning_replenishment_runs(id),
            FOREIGN KEY(snapshot_id) REFERENCES stock_planning_snapshots(id)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_stock_import_requests_status
        ON stock_planning_import_requests(status,created_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_stock_notifications_recipient
        ON stock_planning_notifications(recipient_email,read_at,created_at DESC)""",
    ))


def _migration_0056_nicolas_lugo_administrator(connection: Connection) -> None:
    """Grant Nicolás Lugo full application access with global scope."""
    connection.execute(
        """UPDATE ws_users
        SET role='administrator', is_active=1, portfolio_scope='all'
        WHERE email_normalized=LOWER(TRIM(?))
           OR LOWER(TRIM(email))=LOWER(TRIM(?))""",
        (
            "nicolas.lugo@lugohermanos.com",
            "nicolas.lugo@lugohermanos.com",
        ),
    )


def _migration_0057_vendor_rfq_inbox(connection: Connection) -> None:
    """Persist the email conversation for each vendor request."""
    _execute_statements(connection, (
        """CREATE TABLE IF NOT EXISTS rfq_vendor_request_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_request_id INTEGER NOT NULL,
            provider_message_id TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('incoming','outgoing')),
            sender_email TEXT,
            recipient_emails_json TEXT NOT NULL DEFAULT '[]',
            cc_emails_json TEXT NOT NULL DEFAULT '[]',
            subject TEXT,
            body_text TEXT,
            body_html_sanitized TEXT,
            message_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vendor_request_id) REFERENCES rfq_vendor_requests(id)
                ON DELETE CASCADE,
            UNIQUE(vendor_request_id, provider_message_id)
        )""",
        """CREATE INDEX IF NOT EXISTS idx_vendor_rfq_messages_request
        ON rfq_vendor_request_messages(vendor_request_id,message_at,id)""",
        """CREATE INDEX IF NOT EXISTS idx_vendor_rfq_requests_rfq
        ON rfq_vendor_requests(rfq_id,brand,created_at)""",
    ))


def _migration_0058_integration_credentials(connection: Connection) -> None:
    """Store encrypted OAuth credentials for server-side integrations."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS integration_credentials (
            credential_key TEXT PRIMARY KEY,
            encrypted_value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )


MIGRATION_MANIFEST = (
    Migration(1, "core_workspace", _migration_0001_core_workspace),
    Migration(2, "opportunity_mvp", _migration_0002_opportunity_mvp),
    Migration(3, "customer_site", _migration_0003_customer_site),
    Migration(4, "quote_domain", _migration_0004_quote_domain),
    Migration(5, "project_files", _migration_0005_project_files),
    Migration(6, "initiatives", _migration_0006_initiatives),
    Migration(7, "opportunity_closure", _migration_0007_opportunity_closure),
    Migration(8, "agreements", _migration_0008_agreements),
    Migration(9, "agreement_import", _migration_0009_agreement_import),
    Migration(10, "agreement_xls_metadata", _migration_0010_agreement_xls_metadata),
    Migration(11, "agreement_decimal_prices", _migration_0011_agreement_decimal_prices),
    Migration(12, "customer_portfolio_metadata", _migration_0012_customer_portfolio_metadata),
    Migration(13, "customer_responsible_office", _migration_0013_customer_responsible_office),
    Migration(14, "commercial_approvals", _migration_0014_commercial_approvals),
    Migration(15, "approval_monetary_decision", _migration_0015_approval_monetary_decision),
    Migration(16, "approval_erp_price_snapshot", _migration_0016_approval_erp_price_snapshot),
    Migration(17, "commercial_visits", _migration_0017_commercial_visits),
    Migration(18, "erp_import_center", _migration_0018_erp_import_center),
    Migration(19, "commercial_activities", _migration_0019_commercial_activities),
    Migration(20, "rfq_lifecycle", _migration_0020_rfq_lifecycle),
    Migration(21, "normalize_user_table", _migration_0021_normalize_user_table),
    Migration(22, "targeted_rfq_and_oauth", _migration_0022_targeted_rfq_and_oauth),
    Migration(
        23, "customer_import_site_metrics",
        _migration_0023_customer_import_site_metrics,
    ),
    Migration(24, "ask_mvp", _migration_0024_ask_mvp),
    Migration(
        25, "ask_analysis_workspace",
        _migration_0025_ask_analysis_workspace,
    ),
    Migration(26, "inventory_import", _migration_0026_inventory_import),
    Migration(27, "opportunity_origin", _migration_0027_opportunity_origin),
    Migration(
        28,
        "opportunity_import_framework",
        _migration_0028_opportunity_import_framework,
    ),
    Migration(
        29,
        "production_crm_opportunity_import",
        _migration_0029_production_crm_opportunity_import,
    ),
    Migration(
        30,
        "deferred_crm_opportunity_import",
        _migration_0030_deferred_crm_opportunity_import,
    ),
    Migration(
        31,
        "crm_commercial_line_quote_bridge",
        _migration_0031_crm_commercial_line_quote_bridge,
    ),
    Migration(32, "quote_management_system", _migration_0032_quote_management_system),
    Migration(33, "commercial_assignment_fields", _migration_0033_commercial_assignment_fields),
    Migration(34, "account_visit_analysis", _migration_0034_account_visit_analysis),
    Migration(
        35,
        "stock_order_planning_foundation",
        _migration_0035_stock_order_planning_foundation,
    ),
    Migration(
        36,
        "stock_planning_operational_inputs",
        _migration_0036_stock_planning_operational_inputs,
    ),
    Migration(
        37,
        "stock_planning_forecast_evidence",
        _migration_0037_stock_planning_forecast_evidence,
    ),
    Migration(
        38,
        "stock_planning_versioned_forecasts",
        _migration_0038_stock_planning_versioned_forecasts,
    ),
    Migration(
        39,
        "stock_planning_decisions",
        _migration_0039_stock_planning_decisions,
    ),
    Migration(
        40,
        "stock_planning_decision_history",
        _migration_0040_stock_planning_decision_history,
    ),
    Migration(
        41,
        "repair_crm_opportunity_lifecycle",
        _migration_0041_repair_crm_opportunity_lifecycle,
    ),
    Migration(42, "advisor_management", _migration_0042_advisor_management),
    Migration(
        43, "canonical_visit_advisors",
        _migration_0043_canonical_visit_advisors,
    ),
    Migration(44, "customer_branch_mapping", _migration_0044_customer_branch_mapping),
    Migration(
        45, "priority_branch_mappings",
        _migration_0045_priority_branch_mappings,
    ),
    Migration(
        46, "industrial_branch_mappings",
        _migration_0046_industrial_branch_mappings,
    ),
    Migration(
        47, "executive_viewer_users",
        _migration_0047_executive_viewer_users,
    ),
    Migration(
        48, "rocio_rocha_management_access",
        _migration_0048_rocio_rocha_management_access,
    ),
    Migration(
        49, "enable_thomson_stock_planning",
        _migration_0049_enable_thomson_stock_planning,
    ),
    Migration(50, "erp_fob_price_import", _migration_0050_erp_fob_price_import),
    Migration(
        51, "stock_planning_fob_values",
        _migration_0051_stock_planning_fob_values,
    ),
    Migration(
        52, "archivable_stock_snapshots",
        _migration_0052_archivable_stock_snapshots,
    ),
    Migration(
        53, "bogota_kr68_stock_planning",
        _migration_0053_bogota_kr68_stock_planning,
    ),
    Migration(
        54, "stock_planning_sales_evidence",
        _migration_0054_stock_planning_sales_evidence,
    ),
    Migration(
        55, "periodic_stock_replenishment",
        _migration_0055_periodic_stock_replenishment,
    ),
    Migration(
        56, "nicolas_lugo_administrator",
        _migration_0056_nicolas_lugo_administrator,
    ),
    Migration(57, "vendor_rfq_inbox", _migration_0057_vendor_rfq_inbox),
    Migration(58, "integration_credentials", _migration_0058_integration_credentials),
)


def upgrade() -> MigrationReport:
    _validate_manifest()
    connection = get_connection()
    applied_versions: list[int] = []

    try:
        _require_foreign_keys(connection)
        _ensure_migration_ledger(connection)
        connection.commit()
        applied = {
            row["version"]: row["name"]
            for row in connection.execute(
                "SELECT version, name FROM schema_migrations"
            ).fetchall()
        }
        suspend_foreign_keys = (
            28 not in applied or 32 not in applied or 50 not in applied
        )
        baseline_foreign_key_violations = {
            tuple(row) for row in connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        }
        if suspend_foreign_keys:
            connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")

        for migration in MIGRATION_MANIFEST:
            if migration.version in applied:
                if applied[migration.version] != migration.name:
                    raise RuntimeError(
                        "Migration ledger conflict for version "
                        f"{migration.version}: expected {migration.name}, "
                        f"found {applied[migration.version]}."
                    )
                continue

            migration.apply(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    version, name, applied_at
                ) VALUES (?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            applied_versions.append(migration.version)

        if suspend_foreign_keys:
            violations = {
                tuple(row) for row in connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            } - baseline_foreign_key_violations
            if violations:
                raise RuntimeError(
                    "A schema-rebuilding migration produced foreign-key violations."
                )
        connection.commit()
        if suspend_foreign_keys:
            connection.execute("PRAGMA foreign_keys = ON")
        warnings = _integrity_warnings(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return MigrationReport(
        applied_versions=tuple(applied_versions),
        current_version=MIGRATION_MANIFEST[-1].version,
        warnings=tuple(warnings),
    )


def _require_foreign_keys(connection: Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        raise RuntimeError("No fue posible habilitar PRAGMA foreign_keys.")


def _validate_manifest() -> None:
    versions = [migration.version for migration in MIGRATION_MANIFEST]
    names = [migration.name for migration in MIGRATION_MANIFEST]
    expected_versions = list(range(1, len(MIGRATION_MANIFEST) + 1))

    if versions != expected_versions:
        raise RuntimeError(
            "MIGRATION_MANIFEST must use consecutive versions starting at 1."
        )
    if len(names) != len(set(names)):
        raise RuntimeError("Migration names must be unique.")


def _ensure_migration_ledger(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
        """
    )


def _integrity_warnings(connection: Connection) -> list[str]:
    violations: dict[tuple[str, str, int], list[int | None]] = {}
    for row in connection.execute("PRAGMA foreign_key_check").fetchall():
        key = (row[0], row[2], row[3])
        violations.setdefault(key, []).append(row[1])

    warnings = []
    for (table, parent, constraint), rowids in sorted(violations.items()):
        sample = ",".join(str(rowid) for rowid in rowids[:5])
        warnings.append(
            "Foreign-key violations: "
            f"table={table}, parent={parent}, constraint={constraint}, "
            f"rows={len(rowids)}, sample_rowids={sample}"
        )
    return warnings


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade destructivo no soportado; restaure un respaldo verificado."
    )
