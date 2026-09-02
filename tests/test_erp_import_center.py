import io
import sqlite3

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.database.migrations import upgrade
from app.workspace.services.erp_import_service import (
    ERPImportService,
    ERPImportValidationError,
)


@pytest.fixture
def import_database(tmp_path, monkeypatch):
    database = tmp_path / "erp-import.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", database)
    monkeypatch.setattr(
        ERPImportService, "STORAGE_ROOT", tmp_path / "retained-imports"
    )
    upgrade()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE raw_sales (
                nit TEXT, razonsocial TEXT, prefijo TEXT, numero INTEGER,
                fecha TEXT, idproducto TEXT, nombreproducto TEXT,
                cantidad REAL, idfam1 REAL, idfam2 REAL,
                valorbruto REAL, costo REAL, sales_line_key TEXT
            );
            CREATE UNIQUE INDEX idx_raw_sales_line_key
                ON raw_sales(sales_line_key);
            CREATE TABLE raw_customers (
                nit TEXT, razonsocial TEXT, ciudad TEXT, vendedor TEXT,
                cliente_credito TEXT, cupocreditocc TEXT, plazopagocc TEXT,
                idciiu TEXT, direccion1 TEXT
            );
            CREATE TABLE dim_customer_activity (
                activity_id TEXT, activity_name TEXT,
                classification_name TEXT, commercial_group_name TEXT
            );
            INSERT INTO dim_customer_activity VALUES ('1','Industria','A','Industrial');
            """
        )
    return database


def _upload(dataframe: pd.DataFrame, filename: str) -> FileStorage:
    stream = io.BytesIO()
    if filename.endswith(".csv"):
        stream.write(dataframe.to_csv(index=False).encode())
    else:
        dataframe.to_excel(stream, index=False)
    stream.seek(0)
    return FileStorage(stream=stream, filename=filename)


def _sales() -> pd.DataFrame:
    return pd.DataFrame([{
        "nit": "9001", "razonsocial": "Cliente Uno", "prefijo": "FV",
        "numero": 10, "fecha": "2026-07-10", "idproducto": "SKU-1",
        "nombreproducto": "Rodamiento", "cantidad": 2, "idfam1": 1,
        "idfam2": 2, "valorbruto": 1000, "costo": 700,
    }])


def _inventory(*, available: object = 2, warehouse: str = "54") -> pd.DataFrame:
    columns = [
        "Código", "Nombre Producto", "Cód", "Denominación", "Cód Unidad",
        "Unidades", "Promedio", "Total", "Cód", "Denominación", "Cód",
        "Denominación", "Cód", "Denominación", "Cód", "Denominación",
        "Cód", "Denominación", "Ultimo Costo", "Ultima Entrada",
        "Reservado", "Remisionado", "Disponible", "1", "2", "3",
        "Ubicación", "Código barras",
    ]
    return pd.DataFrame([[
        "SKU-1", "Rodamiento", warehouse, "Bodega Cali", "Und",
        2, 100, 200, "1000", "RODAMIENTOS", "1010", "RIGIDOS",
        "1011", "Bearings", "SKF", "SKF", "DA", "BEARINGS AND UNITS",
        None, None, 0, 0, available, 1, 2, 3, "1D20", "123456",
    ]], columns=columns)


def _fob_prices(*, fob: object = "7,000.00") -> pd.DataFrame:
    return pd.DataFrame([{
        "idproducto": "AD-5248ARB", "prefijo": "AD-5248",
        "sufijo": "ARB", "idfam2": 1330, "fob": fob,
        "lista1": "23,000,000.00", "nit": "444,444,060",
    }, {
        "idproducto": "4T-27620BOW", "prefijo": "4T-27620",
        "sufijo": "BOW", "idfam2": 1290, "fob": "7.73",
        "lista1": "45,400.00", "nit": "444,444,010",
    }])


def test_sales_import_is_append_only_and_idempotent(import_database):
    first = ERPImportService.prepare(
        import_type="sales", upload=_upload(_sales(), "ventas.csv"),
        executed_by="tester",
    )
    first_result = ERPImportService.confirm(first.execution_id)
    second = ERPImportService.prepare(
        import_type="sales", upload=_upload(_sales(), "ventas.csv"),
        executed_by="tester",
    )
    second_result = ERPImportService.confirm(second.execution_id)

    assert first_result["rows_inserted"] == 1
    assert second_result["rows_inserted"] == 0
    assert second_result["duplicates_count"] == 1
    with sqlite3.connect(import_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_sales").fetchone()[0] == 1


def test_customer_import_upserts_customer_and_site_by_nit(import_database):
    columns = {
        "nit": "9001", "razonsocial": "Nombre inicial",
        "ciudad": "Cali", "vendedor": "Ana", "cliente_credito": "S",
        "cupocreditocc": "100", "plazopagocc": "30", "idciiu": "1",
        "direccion1": "Calle 1",
    }
    preview = ERPImportService.prepare(
        import_type="customers",
        upload=_upload(pd.DataFrame([columns]), "clientes.xlsx"),
        executed_by="tester",
    )
    created = ERPImportService.confirm(preview.execution_id)
    with sqlite3.connect(import_database) as connection:
        original_internal_id = connection.execute(
            "SELECT id FROM ws_customers WHERE erp_customer_id='9001'"
        ).fetchone()[0]
    columns["razonsocial"] = "Nombre actualizado"
    preview = ERPImportService.prepare(
        import_type="customers",
        upload=_upload(pd.DataFrame([columns]), "clientes.xlsx"),
        executed_by="tester",
    )
    updated = ERPImportService.confirm(preview.execution_id)

    assert created["customers_inserted"] == 1
    assert created["customer_sites_inserted"] == 1
    assert updated["customers_updated"] == 1
    assert updated["customer_sites_updated"] == 1
    with sqlite3.connect(import_database) as connection:
        sites = connection.execute(
            "SELECT razonsocial FROM raw_customers WHERE nit='9001'"
        ).fetchall()
        customers = connection.execute(
            "SELECT id,name FROM ws_customers WHERE erp_customer_id='9001'"
        ).fetchall()
    assert sites == [("Nombre actualizado",)]
    assert len(customers) == 1
    assert customers[0][0] == original_internal_id
    assert customers[0][1] == "Nombre actualizado"


def test_same_nit_preserves_multiple_customer_sites(import_database):
    base = {
        "nit": "902.020.100", "razonsocial": "CEMEX",
        "vendedor": "Ana", "cliente_credito": "S",
        "cupocreditocc": "100", "plazopagocc": "30", "idciiu": "1",
    }
    rows = [
        {**base, "direccion1": "KM 3.5 Vía Buenos Aires", "ciudad": "Ibagué"},
        {**base, "direccion1": "Avenida El Llano", "ciudad": "Bogotá"},
        {**base, "direccion1": "Tocancipá", "ciudad": "Tocancipá"},
    ]
    preview = ERPImportService.prepare(
        import_type="customers",
        upload=_upload(pd.DataFrame(rows), "clientes.xlsx"),
        executed_by="tester",
    )
    assert preview.sync_metrics["customers_inserted"] == 1
    assert preview.sync_metrics["customer_sites_inserted"] == 3
    result = ERPImportService.confirm(preview.execution_id)
    assert result["customers_inserted"] == 1
    assert result["customer_sites_inserted"] == 3

    second = ERPImportService.prepare(
        import_type="customers",
        upload=_upload(pd.DataFrame(rows), "clientes.xlsx"),
        executed_by="tester",
    )
    unchanged = ERPImportService.confirm(second.execution_id)
    assert unchanged["customers_unchanged"] == 1
    assert unchanged["customer_sites_unchanged"] == 3

    changed_rows = [dict(row) for row in rows]
    changed_rows[1]["vendedor"] = "Beatriz"
    third = ERPImportService.prepare(
        import_type="customers",
        upload=_upload(pd.DataFrame(changed_rows), "clientes.xlsx"),
        executed_by="tester",
    )
    changed = ERPImportService.confirm(third.execution_id)
    assert changed["customers_unchanged"] == 1
    assert changed["customer_sites_updated"] == 1
    assert changed["customer_sites_unchanged"] == 2
    with sqlite3.connect(import_database) as connection:
        customer = connection.execute(
            "SELECT id FROM ws_customers WHERE erp_customer_id='902020100'"
        ).fetchall()
        sites = connection.execute(
            "SELECT direccion1 FROM raw_customers WHERE nit='902020100'"
        ).fetchall()
    assert len(customer) == 1
    assert len(sites) == 3


def test_missing_required_columns_stop_before_execution(import_database):
    with pytest.raises(ERPImportValidationError, match="Faltan columnas"):
        ERPImportService.prepare(
            import_type="sales",
            upload=_upload(pd.DataFrame([{"nit": "1"}]), "ventas.csv"),
            executed_by="tester",
        )


def test_execution_retains_hash_file_and_metrics(import_database):
    preview = ERPImportService.prepare(
        import_type="sales", upload=_upload(_sales(), "ventas.csv"),
        executed_by="tester",
    )
    result = ERPImportService.confirm(preview.execution_id)

    assert len(result["file_hash"]) == 64
    assert result["status"] == "completed"
    assert result["rows_read"] == 1
    assert ERPImportService.STORAGE_ROOT.joinpath(
        f"{result['file_hash']}.csv"
    ).exists()


def test_inventory_preview_and_upsert_require_explicit_overwrite(
    import_database,
):
    preview = ERPImportService.prepare(
        import_type="inventory",
        upload=_upload(_inventory(), "inventario.xlsx"),
        executed_by="tester",
        snapshot_date="2026-07-01",
    )

    assert preview.can_confirm
    assert preview.snapshot_date == "2026-07-01"
    assert preview.sync_metrics["warehouses_count"] == 1
    assert preview.sync_metrics["new_warehouse_codes"] == ["54"]
    assert preview.sync_metrics["total_transit"] == 6
    assert not any(
        issue["code"] == "BALANCE_INVENTARIO"
        for issue in preview.validation_issues
    )
    first = ERPImportService.confirm(preview.execution_id)
    assert first["rows_inserted"] == 1
    assert first["rows_updated"] == 0

    repeated = ERPImportService.prepare(
        import_type="inventory",
        upload=_upload(_inventory(available=1), "inventario.xlsx"),
        executed_by="tester",
        snapshot_date="2026-07-01",
    )
    assert repeated.sync_metrics["existing_keys"] == 1
    assert repeated.sync_metrics["new_warehouses"] == 0
    with pytest.raises(ERPImportValidationError, match="sobrescritura"):
        ERPImportService.confirm(repeated.execution_id)
    updated = ERPImportService.confirm(
        repeated.execution_id, overwrite_existing=True
    )
    assert updated["rows_inserted"] == 0
    assert updated["rows_updated"] == 1

    with sqlite3.connect(import_database) as connection:
        row = connection.execute(
            """SELECT fecha_snapshot, idbodega, idproducto,
                unidades_disponible, transito_1, transito_2, transito_3,
                unidades_transito, costo_unitario, unidad_medida,
                marca_codigo, codigo_barras
            FROM inventario_snapshot"""
        ).fetchone()
    assert row == (
        "2026-07-01", "54", "SKU-1", 1.0, 1.0, 2.0, 3.0,
        6.0, 100.0, "Und", "SKF", "123456",
    )


def test_inventory_invalid_quantity_is_visible_and_blocks_confirmation(
    import_database,
):
    preview = ERPImportService.prepare(
        import_type="inventory",
        upload=_upload(_inventory(available="no-numérico"), "inventario.xlsx"),
        executed_by="tester",
        snapshot_date="2026-07-01",
    )

    assert not preview.can_confirm
    assert any(
        issue["code"] == "CANTIDAD_NO_NUMERICA"
        for issue in preview.validation_issues
    )
    with pytest.raises(ERPImportValidationError, match="errores de validación"):
        ERPImportService.confirm(preview.execution_id)


def test_inventory_requires_snapshot_date(import_database):
    with pytest.raises(ERPImportValidationError, match="obligatoria"):
        ERPImportService.prepare(
            import_type="inventory",
            upload=_upload(_inventory(), "inventario.xlsx"),
            executed_by="tester",
        )


def test_fob_price_import_preserves_complete_historical_extract(
    import_database,
):
    preview = ERPImportService.prepare(
        import_type="fob_prices",
        upload=_upload(_fob_prices(), "precios-fob.xlsx"),
        executed_by="tester",
    )

    assert preview.can_confirm
    assert preview.snapshot_date is None
    assert preview.sync_metrics == {
        "rows_valid": 2, "products_count": 2, "brands_count": 2,
        "suppliers_count": 2, "zero_fob_count": 0,
    }
    assert ("fob", "fob_usd") in preview.header_mapping
    result = ERPImportService.confirm(preview.execution_id)
    assert result["rows_inserted"] == 2

    second = ERPImportService.prepare(
        import_type="fob_prices",
        upload=_upload(_fob_prices(fob="7100"), "precios-fob-nuevo.xlsx"),
        executed_by="tester",
    )
    ERPImportService.confirm(second.execution_id)
    with sqlite3.connect(import_database) as connection:
        rows = connection.execute(
            """SELECT idproducto,sufijo,fob_usd,lista1_cop,nit
            FROM erp_fob_price_history
            WHERE idproducto='AD-5248ARB' ORDER BY id"""
        ).fetchall()
    assert rows == [
        ("AD-5248ARB", "ARB", 7000.0, 23000000.0, "444444060"),
        ("AD-5248ARB", "ARB", 7100.0, 23000000.0, "444444060"),
    ]


def test_fob_price_import_reports_zero_and_blocks_invalid_rows(import_database):
    zero = ERPImportService.prepare(
        import_type="fob_prices",
        upload=_upload(_fob_prices(fob=0), "precios-fob.xlsx"),
        executed_by="tester",
    )
    assert zero.can_confirm
    assert zero.sync_metrics["zero_fob_count"] == 1
    assert any(issue["code"] == "FOB_CERO" for issue in zero.validation_issues)

    invalid = ERPImportService.prepare(
        import_type="fob_prices",
        upload=_upload(_fob_prices(fob="no-numérico"), "precios-mal.xlsx"),
        executed_by="tester",
    )
    assert not invalid.can_confirm
    with pytest.raises(ERPImportValidationError, match="errores de validación"):
        ERPImportService.confirm(invalid.execution_id)


def test_fob_price_import_blocks_duplicate_product_supplier(import_database):
    duplicated = pd.concat([_fob_prices().iloc[[0]], _fob_prices().iloc[[0]]])
    preview = ERPImportService.prepare(
        import_type="fob_prices",
        upload=_upload(duplicated, "precios-duplicados.xlsx"),
        executed_by="tester",
    )
    assert not preview.can_confirm
    assert any(
        issue["code"] == "PRODUCTO_PROVEEDOR_DUPLICADO"
        for issue in preview.validation_issues
    )
