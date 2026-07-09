from pathlib import Path
import shutil
from datetime import datetime

from app.loaders.raw_sales_loader import load_raw_sales


INBOX_DIR = Path("data/inbox/sales")
ARCHIVE_DIR = Path("data/archive/sales")
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def get_files_to_import() -> list[Path]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    return [
        file
        for file in INBOX_DIR.iterdir()
        if file.is_file()
        and file.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def archive_file(file_path: Path) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"{file_path.stem}_{timestamp}{file_path.suffix}"

    shutil.move(str(file_path), str(archive_path))

    return archive_path


def main():
    files = get_files_to_import()

    if not files:
        print("No sales files found in data/inbox/sales")
        return

    for file_path in files:
        print("=" * 80)
        print(f"Importing: {file_path}")
        print("=" * 80)

        result = load_raw_sales(file_path)

        print("✅ Raw sales import completed")
        print(f"Rows before:        {result['before_rows']:,}")
        print(f"Rows imported:      {result['imported_rows']:,}")
        print(f"Rows after:         {result['after_rows']:,}")
        print(f"Duplicates removed: {result['duplicates_removed']:,}")
        print(f"Date range:         {result['min_date']} → {result['max_date']}")

        archived = archive_file(file_path)
        print(f"Archived to:        {archived}")


if __name__ == "__main__":
    main()