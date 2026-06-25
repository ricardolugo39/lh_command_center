from pathlib import Path
import sys

sys.path.append(str(Path.cwd()))

from app.importers.access_importer import list_tables, get_table_data


ACCESS_FILE = Path("/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/LH/Reports/sales_lh.accdb")

tables = ["sales", "customers"]

print("\nACCESS FILE")
print(ACCESS_FILE)

print("\nAVAILABLE TABLES")
for table in list_tables(ACCESS_FILE):
    print("-", table)

for table in tables:
    print(f"\nTABLE: {table}")
    df = get_table_data(ACCESS_FILE, table)
    print("Shape:", df.shape)
    print("Columns:")
    for col in df.columns:
        print("-", col)

    print("\nPreview:")
    print(df.head())