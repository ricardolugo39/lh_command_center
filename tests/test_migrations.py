import shutil
import sqlite3
from pathlib import Path

import pytest

from app.database.migrations import MIGRATION_MANIFEST, upgrade
from app.database.schema import OPERATIONAL_TABLES
from app import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DATABASE = PROJECT_ROOT / "database" / "commercial.db"


@pytest.fixture
def migration_database(tmp_path, monkeypatch):
    path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    return path


def _connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _schema_signature(path: Path) -> dict:
    signature = {}
    with _connection(path) as connection:
        for table_name in OPERATIONAL_TABLES:
            columns = {
                row["name"]: (
                    row["type"].upper(),
                    row["notnull"],
                    row["dflt_value"],
                    row["pk"],
                )
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            foreign_keys = {
                (
                    row["table"],
                    row["from"],
                    row["to"],
                    row["on_update"],
                    row["on_delete"],
                )
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({table_name})"
                ).fetchall()
            }
            indexes = {}
            for row in connection.execute(
                f"PRAGMA index_list({table_name})"
            ).fetchall():
                index_columns = tuple(
                    item["name"]
                    for item in connection.execute(
                        f"PRAGMA index_info({row['name']})"
                    ).fetchall()
                )
                index_sql_row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                    (row["name"],),
                ).fetchone()
                index_sql = index_sql_row[0] if index_sql_row else None
                predicate = None
                normalized_index_sql = (
                    " ".join(index_sql.lower().split()) if index_sql else ""
                )
                if " where " in normalized_index_sql:
                    predicate = normalized_index_sql.split(" where ", 1)[1]
                indexes[index_columns] = (
                    row["unique"],
                    row["partial"],
                    predicate,
                )
            signature[table_name] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": indexes,
            }
    return signature


def _row_counts(path: Path) -> dict[str, int]:
    counts = {}
    with _connection(path) as connection:
        tables = [
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        for table_name in tables:
            counts[table_name] = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
    return counts


def test_fresh_installation_creates_complete_schema(migration_database):
    report = upgrade()

    assert report.applied_versions == tuple(
        migration.version for migration in MIGRATION_MANIFEST
    )
    assert report.current_version == MIGRATION_MANIFEST[-1].version

    with _connection(migration_database) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        versions = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        executive_users = connection.execute(
            """SELECT email_normalized,role,portfolio_scope
            FROM ws_users
            WHERE email_normalized IN (
                'gerencia@lugohermanos.com',
                'nicolas.lugo@lugohermanos.com',
                'rocio.rocha@lugohermanos.com'
            ) ORDER BY email_normalized"""
        ).fetchall()

    assert set(OPERATIONAL_TABLES).issubset(tables)
    assert len(versions) == len(MIGRATION_MANIFEST)
    assert [tuple(row) for row in executive_users] == [
        ("gerencia@lugohermanos.com", "commercial_management", "all"),
        ("nicolas.lugo@lugohermanos.com", "read_only", "all"),
        ("rocio.rocha@lugohermanos.com", "commercial_management", "all"),
    ]
    assert "ws_customer_portfolio_metadata" in tables
    assert {
        "erp_import_executions",
        "erp_import_issues",
        "inventario_snapshot",
        "rfqs",
        "rfq_items",
        "rfq_status_history",
        "rfq_conclusions",
        "rfq_documents",
        "ws_users",
        "ask_artifacts",
    }.issubset(tables)
    with _connection(migration_database) as connection:
        ask_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(ask_analyses)"
            ).fetchall()
        }
        inventory_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(inventario_snapshot)"
            ).fetchall()
        }
    assert "lifecycle_status" in ask_columns
    assert {
        "fecha_snapshot", "idbodega", "idproducto", "unidad_medida",
        "idfam3", "marca_codigo", "grupo_fabricante_codigo",
        "transito_1", "transito_2", "transito_3",
        "unidades_transito", "costo_unitario", "codigo_barras",
    }.issubset(inventory_columns)


def test_application_startup_automatically_migrates_fresh_database(
    migration_database,
):
    application = create_app({
        "TESTING": True, "TEST_AUTH_BYPASS": True,
    })

    with _connection(migration_database) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == MIGRATION_MANIFEST[-1].version
    assert set(OPERATIONAL_TABLES).issubset(tables)
    client = application.test_client()
    assert client.get("/imports/").status_code == 200
    assert client.get("/rfqs/").status_code == 200


def test_application_startup_upgrades_existing_version_17_database(
    migration_database,
):
    with _connection(migration_database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )"""
        )
        for migration in MIGRATION_MANIFEST[:17]:
            migration.apply(connection)
            connection.execute(
                """INSERT INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (migration.version, migration.name),
            )

    application = create_app({
        "TESTING": True, "TEST_AUTH_BYPASS": True,
    })

    with _connection(migration_database) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        import_table = connection.execute(
            """SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'erp_import_executions'"""
        ).fetchone()
        rfq_table = connection.execute(
            """SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'rfqs'"""
        ).fetchone()

    assert version == MIGRATION_MANIFEST[-1].version
    assert import_table is not None
    assert rfq_table is not None
    assert application.test_client().get("/rfqs/").status_code == 200


def test_version_20_user_table_is_normalized_without_data_loss(
    migration_database,
):
    with _connection(migration_database) as connection:
        connection.execute(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )"""
        )
        connection.executemany(
            """INSERT INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)""",
            [
                (migration.version, migration.name)
                for migration in MIGRATION_MANIFEST[:20]
            ],
        )
        connection.executescript(
            """CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO users (
                id, display_name, email, role
            ) VALUES (
                7, 'Usuario existente', 'usuario@example.com', 'advisor'
            );"""
        )

    upgrade()

    with _connection(migration_database) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        user = connection.execute(
            "SELECT id, display_name, email FROM ws_users WHERE id = 7"
        ).fetchone()

    assert "ws_users" in tables
    assert "users" not in tables
    assert tuple(user) == (7, "Usuario existente", "usuario@example.com")


def test_connection_factory_enables_foreign_keys(
    migration_database,
):
    from app.database.connection import get_connection

    connection = get_connection()
    try:
        assert connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_upgrade_fails_fast_when_foreign_keys_cannot_be_enabled(
    migration_database,
):
    connection = _connection(migration_database)
    connection.execute("BEGIN")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.database.migrations.get_connection",
            lambda: connection,
        )
        with pytest.raises(RuntimeError, match="foreign_keys"):
            upgrade()


def test_core_legacy_database_upgrades_without_data_loss(
    migration_database,
):
    with _connection(migration_database) as connection:
        connection.executescript(
            """
            CREATE TABLE ws_customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                erp_customer_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ws_projects (
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
                FOREIGN KEY(customer_id) REFERENCES ws_customers(id)
            );
            INSERT INTO ws_customers (name) VALUES ('Cliente legado');
            INSERT INTO ws_projects (
                customer_id, name, status, objective
            ) VALUES (1, 'Proyecto legado', 'prospect', 'Objetivo');
            """
        )

    report = upgrade()

    assert not report.warnings
    with _connection(migration_database) as connection:
        project = connection.execute(
            "SELECT name, status FROM ws_projects WHERE id = 1"
        ).fetchone()
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(ws_projects)"
            ).fetchall()
        }

    assert tuple(project) == ("Proyecto legado", "prospect")
    assert {"customer_site_id", "initiative_id", "result_changer"} <= columns


def test_intermediate_database_upgrades_and_preserves_quote(
    migration_database,
):
    with _connection(migration_database) as connection:
        connection.executescript(
            """
            CREATE TABLE ws_customers (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                erp_customer_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ws_projects (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
                name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'prospect',
                objective TEXT NOT NULL, proposed_solution TEXT,
                current_blocker TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP, closed_at TEXT,
                sales_rep TEXT
            );
            CREATE TABLE ws_project_quotes (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
                quote_number TEXT NOT NULL, branch TEXT, prefix TEXT NOT NULL,
                quote_date TEXT, amount REAL, quote_status TEXT, erp_user TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, prefix, quote_number)
            );
            CREATE TABLE ws_project_brands (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
                brand TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, brand)
            );
            INSERT INTO ws_customers VALUES (1, 'Cliente', 'ERP-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO ws_projects (
                id, customer_id, name, status, objective, sales_rep
            ) VALUES (1, 1, 'Proyecto', 'quoting', 'Objetivo', 'Ana');
            INSERT INTO ws_project_quotes (
                id, project_id, quote_number, prefix, amount
            ) VALUES (1, 1, '100', 'CTC', 250);
            """
        )

    upgrade()

    with _connection(migration_database) as connection:
        quote = connection.execute(
            """
            SELECT quote_number, currency_code, normalized_amount, revision
            FROM ws_project_quotes WHERE id = 1
            """
        ).fetchone()

    assert tuple(quote) == ("100", "COP", 250.0, 0)


def test_repeated_upgrade_is_safe(migration_database):
    first = upgrade()
    first_signature = _schema_signature(migration_database)
    second = upgrade()

    assert first.applied_versions
    assert second.applied_versions == ()
    assert _schema_signature(migration_database) == first_signature


def test_production_upgrade_preserves_data_and_matches_fresh_schema(
    tmp_path,
    monkeypatch,
):
    if not PRODUCTION_DATABASE.exists():
        pytest.skip("Production database snapshot is not available.")
    upgraded_path = tmp_path / "production-copy.db"
    fresh_path = tmp_path / "fresh.db"
    shutil.copy2(PRODUCTION_DATABASE, upgraded_path)

    before_counts = _row_counts(upgraded_path)
    monkeypatch.setattr("app.database.connection.DB_PATH", upgraded_path)
    report = upgrade()
    after_counts = _row_counts(upgraded_path)

    assert all(
        after_counts.get(table_name, 0) >= count
        for table_name, count in before_counts.items()
        if table_name != "schema_migrations"
    )
    assert any("ws_agreement_items" in warning for warning in report.warnings)

    monkeypatch.setattr("app.database.connection.DB_PATH", fresh_path)
    upgrade()

    assert _schema_signature(fresh_path) == _schema_signature(upgraded_path)
