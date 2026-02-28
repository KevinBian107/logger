import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import (
    Session, Category, DailyRecord, Observation, TextEntry, CategoryFamily,
)
from logger.services.family_service import (
    detect_family, get_or_create_family, KNOWN_FAMILIES, DEPARTMENT_FAMILIES,
)
from logger.services.category_normalization import compute_merge_plan
from logger.utils.csv_utils import (
    read_csv_safe, detect_session_from_filename, extract_category_columns,
    make_session_label,
)
from logger.utils.date_utils import parse_date, normalize_day

# In-memory cache for previews (simple dict; fine for single-user local app)
_preview_cache: dict[str, dict] = {}


def _parse_study_csv(rows: list[dict[str, str]], filename: str) -> dict:
    """Parse a study CSV into structured data for preview/import."""
    year, season = detect_session_from_filename(filename)
    warnings: list[str] = []

    if not rows:
        raise ValueError("Study CSV is empty")

    headers = list(rows[0].keys())
    cat_columns = extract_category_columns(headers)

    has_week = "week" in {h.lower() for h in headers}
    has_day = "day" in {h.lower() for h in headers}

    # Find the actual key names (case-sensitive as in CSV)
    date_key = next((h for h in headers if h.lower() == "date"), None)
    day_key = next((h for h in headers if h.lower() == "day"), None) if has_day else None
    week_key = next((h for h in headers if h.lower() == "week"), None) if has_week else None
    type_key = next((h for h in headers if h.lower() == "type"), None)
    total_key = next((h for h in headers if h.lower() == "total"), None)

    if not date_key:
        raise ValueError("No 'date' column found in study CSV")

    # Aggregate by date (handles multi-row-per-date like 2022_fall)
    daily_data: dict[str, dict] = {}

    for row in rows:
        raw_date = row.get(date_key, "").strip()
        if not raw_date:
            continue

        try:
            iso_date = parse_date(raw_date)
        except ValueError:
            warnings.append(f"Skipped unparseable date: {raw_date}")
            continue

        day_val = normalize_day(row.get(day_key, "")) if day_key else None

        week_val = None
        if week_key:
            w = row.get(week_key, "").strip()
            if w and w.lower() not in ("n/a", "na", ""):
                try:
                    week_val = int(w)
                except ValueError:
                    pass

        if iso_date not in daily_data:
            daily_data[iso_date] = {
                "date": iso_date,
                "day_of_week": day_val,
                "week_number": week_val,
                "categories": defaultdict(int),
            }
        else:
            # Multi-row: keep first non-None day/week
            if day_val and not daily_data[iso_date]["day_of_week"]:
                daily_data[iso_date]["day_of_week"] = day_val
            if week_val is not None and daily_data[iso_date]["week_number"] is None:
                daily_data[iso_date]["week_number"] = week_val

        for cat_col in cat_columns:
            val = row.get(cat_col, "").strip()
            if val:
                try:
                    minutes = int(float(val))
                    if minutes > 0:
                        # Store by raw column name first; we'll merge below
                        daily_data[iso_date]["categories"][cat_col] += minutes
                except (ValueError, TypeError):
                    pass

    # Compute merge plan: group raw columns by merge_key
    merge_plan = compute_merge_plan(cat_columns)

    # Re-aggregate daily_data by merge_key (summing columns that share a key)
    for date_str, day_data in daily_data.items():
        raw_cats = day_data["categories"]
        merged: dict[str, int] = defaultdict(int)
        for plan in merge_plan.values():
            total = 0
            for src_col in plan.source_columns:
                total += raw_cats.get(src_col, 0)
            if total > 0:
                merged[plan.merge_key] = total
        day_data["categories"] = merged

    # Build category previews from merge plan
    cat_previews = []
    existing_families = set()
    for plan in merge_plan.values():
        # Use display_name for family detection (clean names from CSV)
        family_key = detect_family(plan.display_name)
        is_new = family_key is not None and family_key not in existing_families
        if family_key:
            existing_families.add(family_key)
        cat_previews.append({
            "name": plan.merge_key,
            "display_name": plan.display_name,
            "auto_family": family_key,
            "family_display_name": (
                KNOWN_FAMILIES.get(family_key) or DEPARTMENT_FAMILIES.get(family_key) or family_key
            ) if family_key else None,
            "is_new_family": is_new,
            "source_columns": plan.source_columns,
        })

    dates_sorted = sorted(daily_data.keys())
    multi_row_dates = len(rows) - len(daily_data)
    if multi_row_dates > 0:
        warnings.append(f"Aggregated {multi_row_dates} duplicate date rows")

    return {
        "year": year,
        "season": season,
        "label": make_session_label(year, season),
        "categories": cat_previews,
        "cat_columns": list(merge_plan.keys()),
        "daily_data": daily_data,
        "date_range": [dates_sorted[0], dates_sorted[-1]] if dates_sorted else [],
        "row_count": len(daily_data),
        "warnings": warnings,
    }


def _parse_text_csv(rows: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    """Parse a text CSV into structured entries."""
    warnings: list[str] = []
    entries: list[dict] = []

    if not rows:
        return entries, warnings

    headers = list(rows[0].keys())

    # Find columns — names vary across years
    time_key = next((h for h in headers if h.lower() in ("time",)), None)
    location_key = next((h for h in headers if h.lower() == "location"), None)
    notes_key = next((h for h in headers if h.lower() == "notes"), None)
    materials_key = next(
        (h for h in headers if "study" in h.lower() or "material" in h.lower()),
        None,
    )

    if not time_key:
        warnings.append("No 'Time' column found in text CSV")
        return entries, warnings

    for row in rows:
        raw_date = row.get(time_key, "").strip()
        if not raw_date:
            continue

        try:
            iso_date = parse_date(raw_date)
        except ValueError:
            continue

        location = row.get(location_key, "").strip() if location_key else None
        notes = row.get(notes_key, "").strip() if notes_key else None
        materials = row.get(materials_key, "").strip() if materials_key else None

        # Skip rows where all text fields are empty or N/A
        if location and location.upper() == "N/A":
            location = location  # keep location even if N/A — it's data
        if notes and notes.upper() == "N/A":
            notes = None
        if materials and materials.upper() == "N/A":
            materials = None

        entries.append({
            "date": iso_date,
            "location": location or None,
            "notes": notes or None,
            "study_materials": materials or None,
        })

    return entries, warnings


async def preview_import(
    study_content: bytes,
    study_filename: str,
    text_content: bytes | None = None,
    text_filename: str | None = None,
) -> dict:
    """Parse CSVs and return a preview without writing to DB."""
    study_rows = read_csv_safe(study_content)
    parsed = _parse_study_csv(study_rows, study_filename)

    text_entries: list[dict] = []
    text_warnings: list[str] = []
    if text_content:
        text_rows = read_csv_safe(text_content)
        text_entries, text_warnings = _parse_text_csv(text_rows)
        parsed["warnings"].extend(text_warnings)

    preview_id = str(uuid.uuid4())
    _preview_cache[preview_id] = {
        "parsed": parsed,
        "text_entries": text_entries,
        "study_filename": study_filename,
        "text_filename": text_filename,
    }

    return {
        "preview_id": preview_id,
        "session_year": parsed["year"],
        "session_season": parsed["season"],
        "session_label": parsed["label"],
        "row_count": parsed["row_count"],
        "date_range": parsed["date_range"],
        "categories": parsed["categories"],
        "text_row_count": len(text_entries),
        "warnings": parsed["warnings"],
    }


async def confirm_import(preview_id: str, db: AsyncSession) -> dict:
    """Write previewed data to the database."""
    cached = _preview_cache.pop(preview_id, None)
    if not cached:
        raise ValueError(f"Preview {preview_id} not found or expired")

    parsed = cached["parsed"]
    text_entries = cached["text_entries"]
    year = parsed["year"]
    season = parsed["season"]

    # Check for existing session
    existing = await db.execute(
        select(Session).where(Session.year == year, Session.season == season)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Session {season} {year} already exists")

    # Auto-detect active: if date range includes today, mark active
    today = date.today().isoformat()
    end_date = parsed["date_range"][1] if len(parsed["date_range"]) > 1 else None
    start_date = parsed["date_range"][0] if parsed["date_range"] else None
    is_active = bool(start_date and end_date and start_date <= today <= end_date)

    # Create session
    session = Session(
        year=year,
        season=season,
        label=parsed["label"],
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
        source_file=cached["study_filename"],
    )
    db.add(session)
    await db.flush()

    # Create categories with family linking (one per merge_key)
    cat_map: dict[str, Category] = {}
    for i, cat_info in enumerate(parsed["categories"]):
        merge_key = cat_info["name"]  # already the merge_key after normalization
        display_name = cat_info.get("display_name") or merge_key
        family_key = cat_info["auto_family"]
        family_id = None

        if family_key:
            family = await get_or_create_family(family_key, db)
            family_id = family.id

        cat = Category(
            session_id=session.id,
            name=merge_key,
            display_name=display_name,
            family_id=family_id,
            position=i,
        )
        db.add(cat)
        await db.flush()
        cat_map[merge_key] = cat

    # Create daily records and observations
    total_observations = 0
    for date_str, day_data in sorted(parsed["daily_data"].items()):
        total_minutes = sum(day_data["categories"].values())

        dr = DailyRecord(
            session_id=session.id,
            date=day_data["date"],
            day_of_week=day_data["day_of_week"],
            week_number=day_data["week_number"],
            total_minutes=total_minutes,
        )
        db.add(dr)
        await db.flush()

        for cat_name, minutes in day_data["categories"].items():
            if minutes > 0 and cat_name in cat_map:
                obs = Observation(
                    daily_record_id=dr.id,
                    category_id=cat_map[cat_name].id,
                    minutes=minutes,
                    source="import",
                )
                db.add(obs)
                total_observations += 1

    # Create text entries
    for te in text_entries:
        entry = TextEntry(
            session_id=session.id,
            date=te["date"],
            location=te["location"],
            notes=te["notes"],
            study_materials=te["study_materials"],
        )
        db.add(entry)

    await db.commit()

    return {
        "session_id": session.id,
        "session_label": session.label,
        "categories_created": len(cat_map),
        "daily_records_created": len(parsed["daily_data"]),
        "observations_created": total_observations,
        "text_entries_created": len(text_entries),
    }
