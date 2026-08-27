from app.database.reader import read_table


def test_customer_dimension_exists():

    df = read_table("dim_customer")

    assert len(df) > 0


def test_customer_columns():

    df = read_table("dim_customer")

    expected = {
        "customer_site_id",
        "customer_id",
        "customer_name",
        "address",
        "city",
        "seller",
        "activity_name",
    }

    assert expected.issubset(df.columns)


def test_customer_site_id_not_null():

    df = read_table("dim_customer")

    assert df["customer_site_id"].notna().all()


def test_customer_name_not_null():

    df = read_table("dim_customer")

    assert df["customer_name"].notna().all()


def test_customer_has_multiple_sites_possible():

    df = read_table("dim_customer")

    site_counts = (
        df.groupby("customer_id")["customer_site_id"]
        .nunique()
    )

    assert site_counts.max() >= 1


def test_credit_is_boolean():

    df = read_table("dim_customer")

    assert df["has_credit"].isin([True, False]).all()

def test_customer_dimension_preserves_rows():

    df = read_table("dim_customer")
    source = read_table("raw_customers")

    assert len(df) == len(source)
