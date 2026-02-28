import csv
import io
import re

STRUCTURAL_COLUMNS = {"week", "date", "day", "type", "total"}


def read_csv_safe(content: bytes) -> list[dict[str, str]]:
    """Read CSV content handling BOM and encoding issues."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def detect_session_from_filename(filename: str) -> tuple[int, str]:
    """Parse '2024_fall_study.csv' → (2024, 'fall')."""
    match = re.match(r"(\d{4})_(fall|winter|spring|summer)_(study|text)\.csv", filename, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot parse session from filename: {filename}")
    return int(match.group(1)), match.group(2).lower()


def extract_category_columns(headers: list[str]) -> list[str]:
    """Filter out structural columns to get category names."""
    return [h for h in headers if h.lower() not in STRUCTURAL_COLUMNS and h.strip()]


def make_session_label(year: int, season: str) -> str:
    return f"{season.capitalize()} {year}"
