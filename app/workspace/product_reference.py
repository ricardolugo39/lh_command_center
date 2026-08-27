import re
import unicodedata
from typing import Any


MANUFACTURER_SUFFIXES = (
    "TIMKEN", "DODGE", "GATES", "SKF", "FAG", "INA", "NTN", "THK",
)


def normalize_product_reference(value: Any) -> str:
    """Return a comparison key without changing technical punctuation."""
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\s+", "", text)
    for suffix in MANUFACTURER_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[:-len(suffix)]
    return text
