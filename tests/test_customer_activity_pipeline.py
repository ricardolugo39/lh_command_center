from app.database.reader import read_table


def test_customer_activity_dimension_exists():

    df = read_table("dim_customer_activity")

    assert len(df) > 0


def test_customer_activity_columns():

    df = read_table("dim_customer_activity")

    expected = {
        "activity_id",
        "activity_name",
        "classification_id",
        "classification_name",
        "commercial_group_id",
        "commercial_group_name",
    }

    assert expected.issubset(df.columns)


def test_activity_id_unique():

    df = read_table("dim_customer_activity")

    assert df["activity_id"].is_unique