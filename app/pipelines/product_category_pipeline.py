from app.database.reader import read_table
from app.database.writer import save_dataframe

import pandas as pd


class ProductDimensionPipeline:

    def run(self):

        print("Reading raw_product_classification...")

        df = read_table("raw_product_classification")

        df = self.transform(df)

        print(f"Writing {len(df)} products...")

        save_dataframe(
            df,
            "dim_product"
        )

        print("✅ dim_product created")

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
        )

        return df

class ProductCategoryPipeline:

    TABLE_IN = "raw_product_classification"

    TABLE_OUT = "dim_product_category"

    def run(self):

        print(f"Reading {self.TABLE_IN}...")

        df = self.extract()

        print("Transforming...")

        df = self.transform(df)

        print(f"Writing {len(df)} rows...")

        self.load(df)

        print("✅ Product Category Dimension created.")

    def extract(self) -> pd.DataFrame:

        return read_table(self.TABLE_IN)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        # Normalize column names
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
        )

        # Preserve original dataframe for family lookup
        raw_df = df.copy()

        # Fill family values down to group rows
        df["familia"] = df["familia"].ffill()

        # Keep only group rows (ignore subgroups)
        df = df[
            (df["grupo"].notna()) &
            (df["subgrupo"].isna())
        ].copy()

        # IDs as strings
        df["familia"] = (
            df["familia"]
            .astype(int)
            .astype(str)
        )

        df["grupo"] = (
            df["grupo"]
            .astype(int)
            .astype(str)
        )

        # Build product category dimension
        df = df.rename(columns={
            "familia": "family_id",
            "grupo": "group_id",
            "denominación": "group_name"
        })

        # Build family dimension from original dataframe
        family_df = raw_df[
            (raw_df["familia"].notna()) &
            (raw_df["grupo"].isna())
        ].copy()

        family_df["familia"] = (
            family_df["familia"]
            .astype(int)
            .astype(str)
        )

        family_df = family_df.rename(columns={
            "familia": "family_id",
            "denominación": "family_name"
        })

        family_df = family_df[
            [
                "family_id",
                "family_name"
            ]
        ]

        # Join family names
        df = df.merge(
            family_df,
            on="family_id",
            how="left"
        )

        # Final dimension
        df = df[
            [
                "family_id",
                "family_name",
                "group_id",
                "group_name"
            ]
        ]

        df = df.sort_values(
            [
                "family_id",
                "group_id"
            ]
        ).reset_index(drop=True)

        return df
    def load(self, df: pd.DataFrame):

        save_dataframe(

            df=df,

            table_name=self.TABLE_OUT

        )