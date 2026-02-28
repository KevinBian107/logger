"""Category name normalization: CSV column names → merge keys + display names.

CSV columns are already clean display names (e.g., "Training", "COGS 118C", "PP").
Session info comes from the filename, not from column name suffixes.
This module just generates stable merge keys for grouping.
"""

import re
from dataclasses import dataclass, field


@dataclass
class MergePlan:
    merge_key: str
    display_name: str
    source_columns: list[str] = field(default_factory=list)


# Course code pattern: "COGS 118C", "MATH 20B", "DSC 120", "HILD 11"
_COURSE_RE = re.compile(r"^([a-zA-Z]+)\s*(\d+[a-zA-Z]?)$")


def normalize_category(raw_name: str) -> tuple[str, str]:
    """Normalize a CSV category column name.

    CSV columns are already clean display names. This just creates
    a stable lowercase merge_key and preserves the display_name.

    Returns (merge_key, display_name).
    """
    name = raw_name.strip()

    # Special slash case
    if name.upper() == "KDD/DS3/TNT":
        return "kdd_ds3_tnt", "KDD/DS3/TNT"

    # Course code: normalize casing (COGS 118C, Math 173B → both "cogs118c")
    m = _COURSE_RE.match(name)
    if m:
        dept = m.group(1).upper()
        num = m.group(2).upper()
        merge_key = f"{dept.lower()}{num.lower()}"
        display = f"{dept} {num}"
        return merge_key, display

    # Everything else: merge_key is lowercased with spaces → underscores
    merge_key = name.lower().replace(" ", "_")
    display = name
    return merge_key, display


def compute_merge_plan(raw_columns: list[str]) -> dict[str, MergePlan]:
    """Group raw CSV column names by merge_key.

    Returns dict mapping merge_key → MergePlan.
    """
    plans: dict[str, MergePlan] = {}

    for col in raw_columns:
        merge_key, display_name = normalize_category(col)

        if merge_key not in plans:
            plans[merge_key] = MergePlan(
                merge_key=merge_key,
                display_name=display_name,
                source_columns=[col],
            )
        else:
            plans[merge_key].source_columns.append(col)

    return plans
