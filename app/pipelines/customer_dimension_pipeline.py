import pandas as pd

from app.database.reader import read_table
from app.database.writer import save_dataframe
from app.pipelines.base_pipeline import BasePipeline


class CustomerDimensionPipeline(BasePipeline):

    TABLE_CUSTOMERS = "raw_customers"
    TABLE_ACTIVITY = "dim_customer_activity"
    TABLE_OUT = "dim_customer"

    REQUIRED_CUSTOMER_COLUMNS = [
        "nit",
        "razonsocial",
        "ciudad",
        "vendedor",
        "cliente_credito",
        "cupocreditocc",
        "plazopagocc",
        "idciiu",
    ]

    REQUIRED_ACTIVITY_COLUMNS = [
        "activity_id",
        "activity_name",
        "classification_name",
        "commercial_group_name",
    ]

    def extract(self):

        customers = read_table(self.TABLE_CUSTOMERS)
        activities = read_table(self.TABLE_ACTIVITY)

        return {
            "customers": customers,
            "activities": activities,
        }

    def clean(self, data):

        customers = data["customers"].copy()
        activities = data["activities"].copy()

        customers.columns = customers.columns.str.strip().str.lower()
        activities.columns = activities.columns.str.strip().str.lower()

        customers["nit"] = customers["nit"].astype(str).str.strip()
        customers["razonsocial"] = customers["razonsocial"].astype(str).str.strip()
        customers["ciudad"] = customers["ciudad"].astype(str).str.strip().str.upper()
        customers["vendedor"] = customers["vendedor"].astype(str).str.strip().str.upper()
        customers["cliente_credito"] = customers["cliente_credito"].astype(str).str.strip().str.upper()
        customers["idciiu"] = customers["idciiu"].astype(str).str.strip()

        activities["activity_id"] = activities["activity_id"].astype(str).str.strip()

        data["customers"] = customers
        data["activities"] = activities

        return data

    def validate(self, data):

        customers = data["customers"]
        activities = data["activities"]

        missing_customers = [
            col for col in self.REQUIRED_CUSTOMER_COLUMNS
            if col not in customers.columns
        ]

        missing_activities = [
            col for col in self.REQUIRED_ACTIVITY_COLUMNS
            if col not in activities.columns
        ]

        if missing_customers:
            raise ValueError(f"Missing customer columns: {missing_customers}")

        if missing_activities:
            raise ValueError(f"Missing activity columns: {missing_activities}")

        return data

    def transform(self, data):

        customers = data["customers"]
        activities = data["activities"]

        customers = customers.copy()

        # Normalize text fields
        customers["nit"] = (
            customers["nit"]
            .astype(str)
            .str.strip()
        )

        customers["razonsocial"] = (
            customers["razonsocial"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        customers["direccion1"] = (
            customers["direccion1"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        customers["ciudad"] = (
            customers["ciudad"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        customers["vendedor"] = (
            customers["vendedor"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        customers["idciiu"] = (
            customers["idciiu"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        # Temporary site key (Sprint 3 MVP)
        customers["customer_site_id"] = (
            customers["nit"]
            + "_"
            + customers["ciudad"]
            + "_"
            + customers["direccion1"]
        )

        # Join with activity dimension
        df = customers.merge(
            activities[
                [
                    "activity_id",
                    "activity_name",
                    "classification_name",
                    "commercial_group_name",
                ]
            ],
            left_on="idciiu",
            right_on="activity_id",
            how="left",
        )

        # Business fields
        df["has_credit"] = (
            df["cliente_credito"]
            .astype(str)
            .str.upper()
            .eq("S")
        )

        df["credit_limit"] = pd.to_numeric(
            df["cupocreditocc"],
            errors="coerce",
        ).fillna(0)

        df["payment_terms"] = pd.to_numeric(
            df["plazopagocc"],
            errors="coerce",
        ).fillna(0).astype(int)

        # Rename business columns
        df = df.rename(
            columns={
                "nit": "customer_id",
                "razonsocial": "customer_name",
                "ciudad": "city",
                "direccion1": "address",
                "vendedor": "seller",
                "idciiu": "activity_id_source",
            }
        )

        # Final dimension
        df = df[
            [
                "customer_site_id",
                "customer_id",
                "customer_name",
                "address",
                "city",
                "seller",
                "has_credit",
                "credit_limit",
                "payment_terms",
                "activity_id_source",
                "activity_name",
                "classification_name",
                "commercial_group_name",
            ]
        ]

        return df

    def load(self, df):

        save_dataframe(
            df=df,
            table_name=self.TABLE_OUT,
        )