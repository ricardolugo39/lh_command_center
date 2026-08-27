import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def data_path(*parts: str) -> Path:
    """Return a persistent app-data path when APP_DATA_DIR is configured."""
    configured = os.getenv("APP_DATA_DIR", "").strip()
    root = Path(configured).expanduser() if configured else PROJECT_ROOT
    return root.joinpath(*parts)


def upload_path(*parts: str) -> Path:
    return data_path("uploads", *parts)
