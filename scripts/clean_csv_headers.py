"""Rewrite all legacy study CSV files to have clean category column names.

Before: training_fall24, cogs107a, math18hw, pp_spring23
After:  Training, COGS 107A, Math 18, PP

Session info comes from the filename, not from column suffixes.
Sub-variant columns (math18hw, math18review) are merged into one (Math 18)
and their minute values are summed per row.
"""

import csv
import io
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

STRUCTURAL = {"week", "date", "day", "type", "total"}

# Session suffix pattern
SUFFIX_RE = re.compile(r"_(fall|winter|spring|summer|sumer|f|w|s|u)\d*$", re.IGNORECASE)

# Course sub-variant suffixes to strip (math18review → math18, dsc10hw → dsc10)
SUBVARIANT_RE = re.compile(r"^([a-zA-Z]+\d+[a-zA-Z]?)(review|hw|matlab|lab|project|disc)$")

# Course code: letters + digits (optional trailing letter)
COURSE_RE = re.compile(r"^([a-zA-Z]+)\s*(\d+[a-zA-Z]?)$")

# DS project merge
DS_PROJECT_RE = re.compile(r"^ds_project", re.IGNORECASE)

# Special-case mappings (after suffix strip)
SPECIAL_DISPLAY = {
    "exam": "Exam",
    "driving": "Driving",
    "gradapp": "Grad App",
    "startup": "Startup",
    "ex_phys": "Ex Phys",
    "kdd/ds3/tnt": "KDD/DS3/TNT",
    "ds": "Data Science",
}

# Known project display names
PROJECT_DISPLAY = {
    "training": "Training",
    "salk": "Salk",
    "mpi": "MPI",
    "pp": "PP",
    "reading": "Reading",
    "swl": "SWL",
    "fmp": "FMP",
    "rplh": "RPLH",
    "fd": "FD",
    "cse257": "CSE 257",
}


def clean_column_name(raw: str) -> tuple[str, str]:
    """Convert raw CSV column name to (merge_key, display_name).

    Returns merge_key for grouping sub-variants, display_name for the CSV header.
    """
    # Strip whitespace
    raw = raw.strip()

    # Step 1: strip session suffix
    base = SUFFIX_RE.sub("", raw)

    # Step 2: DS project merge
    if DS_PROJECT_RE.match(base):
        return "data_science", "Data Science"

    # Step 3: special cases (case-insensitive lookup)
    base_lower = base.lower()
    if base_lower in SPECIAL_DISPLAY:
        return base_lower, SPECIAL_DISPLAY[base_lower]

    # Step 4: known projects (case-insensitive lookup)
    if base_lower in PROJECT_DISPLAY:
        return base_lower, PROJECT_DISPLAY[base_lower]

    # Step 5: sub-variant detection (math18review → math18)
    m = SUBVARIANT_RE.match(base)
    if m:
        base = m.group(1)

    # Step 6: course code formatting (cogs107a → COGS 107A, "Cogs 118C" → COGS 118C)
    m = COURSE_RE.match(base)
    if m:
        dept = m.group(1).upper()
        num = m.group(2).upper()
        merge_key = f"{dept.lower()}{num.lower()}"
        display = f"{dept} {num}"
        return merge_key, display

    # Step 7: fallback — preserve original casing, just clean underscores
    merge_key = base.lower().replace(" ", "_")
    display = base.replace("_", " ")
    return merge_key, display


def rewrite_csv(filepath: Path) -> dict:
    """Rewrite a study CSV with clean column headers, merging sub-variants."""
    content = filepath.read_bytes()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return {"file": filepath.name, "status": "empty"}

    headers = list(rows[0].keys())
    cat_columns = [h for h in headers if h.strip().lower() not in STRUCTURAL and h.strip()]
    structural_columns = [h for h in headers if h.strip().lower() in STRUCTURAL]

    # Build merge plan: raw_col → (merge_key, display_name)
    col_map: dict[str, tuple[str, str]] = {}
    for col in cat_columns:
        col_map[col] = clean_column_name(col)

    # Group raw columns by merge_key
    merge_groups: dict[str, list[str]] = defaultdict(list)
    merge_display: dict[str, str] = {}
    for col, (mk, dn) in col_map.items():
        merge_groups[mk].append(col)
        merge_display[mk] = dn

    # Build output: structural columns + unique display names (in order of first appearance)
    seen_keys = []
    for col in cat_columns:
        mk = col_map[col][0]
        if mk not in seen_keys:
            seen_keys.append(mk)

    new_headers = structural_columns + [merge_display[mk] for mk in seen_keys]

    # Build new rows
    new_rows = []
    for row in rows:
        new_row = {}
        for sc in structural_columns:
            new_row[sc] = row.get(sc, "")

        for mk in seen_keys:
            # Sum all source columns for this merge key
            total = 0
            for src_col in merge_groups[mk]:
                val = row.get(src_col, "").strip()
                if val:
                    try:
                        total += int(float(val))
                    except (ValueError, TypeError):
                        pass
            new_row[merge_display[mk]] = str(total) if total > 0 else "0"

        new_rows.append(new_row)

    # Write back
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=new_headers)
    writer.writeheader()
    writer.writerows(new_rows)

    filepath.write_text(output.getvalue(), encoding="utf-8")

    # Report changes
    changes = {}
    for mk in seen_keys:
        srcs = merge_groups[mk]
        display = merge_display[mk]
        if len(srcs) == 1 and srcs[0] == display:
            continue  # No change
        changes[display] = srcs

    return {
        "file": filepath.name,
        "status": "rewritten",
        "categories": len(seen_keys),
        "changes": changes,
    }


def main():
    study_files = sorted(DATA_DIR.glob("*_study.csv"))
    print(f"Found {len(study_files)} study CSV files\n")

    for f in study_files:
        result = rewrite_csv(f)
        print(f"=== {result['file']} ===")
        print(f"  Status: {result['status']}")
        if result.get("changes"):
            for new_name, old_cols in result["changes"].items():
                print(f"  {old_cols} → {new_name}")
        else:
            print("  No column name changes needed")
        print()


if __name__ == "__main__":
    main()
