import subprocess
import pandas as pd
import csv
from io import StringIO
from pathlib import Path
import sqlite3


def list_tables(access_file):
    command = ["mdb-tables", "-1", access_file]
    result = subprocess.run(command, capture_output=True, text=True)
    return [t.strip() for t in result.stdout.splitlines() if t.strip()]


def get_table_data(access_file, table_name):
    command = ["mdb-export", "-d", "\t", access_file, table_name]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error exporting {table_name}: {result.stderr}")
        return pd.DataFrame()

    reader = csv.reader(StringIO(result.stdout), delimiter="\t")
    rows = list(reader)

    if not rows:
        return pd.DataFrame()

    columns = rows[0]
    data_rows = rows[1:]

    clean_rows = [
        row[:len(columns)] if len(row) > len(columns)
        else row + [""] * (len(columns) - len(row))
        for row in data_rows
    ]

    return pd.DataFrame(clean_rows, columns=columns)


def load_tables(access_file, tables):
    """
    Load multiple tables into a dictionary
    """
    data = {}

    for table in tables:
        print(f"Loading {table}...")
        df = get_table_data(access_file, table)

        if df.empty:
            print(f"{table} is empty or failed.")
        else:
            print(f"{table} loaded: {df.shape}")

        data[table] = df

    return data
