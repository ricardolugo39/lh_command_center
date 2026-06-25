from pathlib import Path

import pandas as pd


class ExcelSource:
    """
    Generic Excel data source.
    Responsible only for reading Excel files.
    """

    @staticmethod
    def read(path: str | Path) -> pd.DataFrame:
        """
        Read the first sheet of an Excel file.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        return pd.read_excel(path)

    @staticmethod
    def read_sheet(path: str | Path, sheet_name: str) -> pd.DataFrame:
        """
        Read a specific sheet from an Excel file.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        return pd.read_excel(path, sheet_name=sheet_name)

    @staticmethod
    def sheets(path: str | Path) -> list[str]:
        """
        Return all sheet names in an Excel file.
        """
        path = Path(path)

        excel = pd.ExcelFile(path)

        return excel.sheet_names