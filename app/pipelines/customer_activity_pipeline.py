import pandas as pd

from app.database.reader import read_table
from app.database.writer import save_dataframe
from app.pipelines.base_pipeline import BasePipeline


class CustomerActivityPipeline(BasePipeline):

    TABLE_IN = "raw_customer_segments"
    TABLE_OUT = "dim_customer_activity"

    REQUIRED_COLUMNS = [
        "ID Actividad",
        "actividad",
        "CLASIFICACION",
        "GRUPO",
        "Clasificacion2",
        "Grupo2",
    ]

    def extract(self):

        print(f"Reading {self.TABLE_IN}")

        return read_table(self.TABLE_IN)

    def clean(self, df):

        df = df.copy()

        df.columns = df.columns.str.strip()

        return df

    def validate(self, df):

        missing = [
            col
            for col in self.REQUIRED_COLUMNS
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing columns: {missing}"
            )

        return df

    def transform(self, df):

        df = df.rename(columns={
            "ID Actividad": "activity_id",
            "actividad": "activity_name",
            "CLASIFICACION": "classification_id",
            "Clasificacion2": "classification_name",
            "GRUPO": "commercial_group_id",
            "Grupo2": "commercial_group_name",
        })

        return df[
            [
                "activity_id",
                "activity_name",
                "classification_id",
                "classification_name",
                "commercial_group_id",
                "commercial_group_name",
            ]
        ]

    def load(self, df):

        save_dataframe(
            df,
            self.TABLE_OUT
        )

        print(
            f"✅ {self.TABLE_OUT} created ({len(df)} rows)"
        )