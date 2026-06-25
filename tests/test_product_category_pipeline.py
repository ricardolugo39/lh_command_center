from app.database.reader import read_table


def test_product_category_dimension():

    df = read_table("dim_product_category")

    assert len(df) > 0

    expected_columns = {
        "family_id",
        "family_name",
        "group_id",
        "group_name",
    }

    assert expected_columns.issubset(df.columns)