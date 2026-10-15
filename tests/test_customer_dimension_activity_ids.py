import pandas as pd

from app.pipelines.customer_dimension_pipeline import CustomerDimensionPipeline


def test_activity_ids_drop_excel_decimal_suffix_without_changing_text_codes():
    values = pd.Series([4752.0, "3312.0", "2394", "", None, "0111"])

    result = CustomerDimensionPipeline.normalize_activity_id(values).tolist()

    assert result == ["4752", "3312", "2394", "", "", "0111"]


def test_customer_dimension_matches_numeric_excel_ciiu_to_activity_catalog():
    pipeline = CustomerDimensionPipeline()
    customers = pd.DataFrame([{
        "nit": "9001", "razonsocial": "Cliente", "direccion1": "Calle 1",
        "ciudad": "Cali", "vendedor": "Asesor", "cliente_credito": "S",
        "cupocreditocc": 100, "plazopagocc": 30, "idciiu": "4752.0",
    }])
    activities = pd.DataFrame([{
        "activity_id": "4752", "activity_name": "Ferretería",
        "classification_name": "COMERCIALIZADORES",
        "commercial_group_name": "COMERCIO DE RODAMIENTOS Y AFINES",
    }])

    cleaned = pipeline.clean({"customers": customers, "activities": activities})
    result = pipeline.transform(cleaned)

    assert result.iloc[0]["activity_id_source"] == "4752"
    assert result.iloc[0]["classification_name"] == "COMERCIALIZADORES"
