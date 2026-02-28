"""Build markdown context from a parsed query for sending to Claude."""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import (
    Session, Category, CategoryFamily, DailyRecord, Observation, TextEntry,
)
from logger.services.chat_query_service import ParsedQuery


async def build_context(parsed: ParsedQuery, db: AsyncSession) -> dict:
    """
    Takes a ParsedQuery + db, returns:
    {
        context_markdown: str,
        summary: str,
        sessions_included: list[str],
        categories_included: list[str],
        date_range: [str | None, str | None],
        data_points: int,
    }
    """
    # ── 1. Resolve sessions ──
    stmt = select(Session)
    session_filters = parsed.session_filters

    if session_filters:
        from sqlalchemy import or_
        conditions = []
        for sf in session_filters:
            conds = []
            if sf.year is not None:
                conds.append(Session.year == sf.year)
            if sf.season is not None:
                conds.append(Session.season == sf.season)
            if conds:
                conditions.append(func.coalesce(*conds) if len(conds) == 1 else conds[0] if len(conds) == 1 else None)

        # Build proper OR conditions
        or_conditions = []
        for sf in session_filters:
            parts = []
            if sf.year is not None:
                parts.append(Session.year == sf.year)
            if sf.season is not None:
                parts.append(Session.season == sf.season)
            if parts:
                if len(parts) == 1:
                    or_conditions.append(parts[0])
                else:
                    from sqlalchemy import and_
                    or_conditions.append(and_(*parts))

        if or_conditions:
            from sqlalchemy import or_
            stmt = stmt.where(or_(*or_conditions))

    result = await db.execute(stmt.order_by(Session.year, Session.season))
    sessions = result.scalars().all()

    if not sessions:
        # Fallback: use all sessions
        result = await db.execute(select(Session).order_by(Session.year, Session.season))
        sessions = result.scalars().all()

    session_ids = [s.id for s in sessions]
    session_labels = [s.label or f"{s.season.title()} {s.year}" for s in sessions]

    # ── 2. Fetch per-category totals ──
    cat_stmt = (
        select(
            Category.name,
            Category.display_name,
            CategoryFamily.name.label("family_name"),
            Session.label.label("session_label"),
            Session.year,
            Session.season,
            func.sum(Observation.minutes).label("total_minutes"),
        )
        .select_from(Observation)
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
        .join(Category, Observation.category_id == Category.id)
        .join(Session, Category.session_id == Session.id)
        .outerjoin(CategoryFamily, Category.family_id == CategoryFamily.id)
        .where(DailyRecord.session_id.in_(session_ids))
    )

    # Filter by family keywords if provided
    if parsed.family_keywords:
        cat_stmt = cat_stmt.where(CategoryFamily.name.in_(parsed.family_keywords))

    # Apply date range
    if parsed.date_range[0]:
        cat_stmt = cat_stmt.where(DailyRecord.date >= parsed.date_range[0])
    if parsed.date_range[1]:
        cat_stmt = cat_stmt.where(DailyRecord.date <= parsed.date_range[1])

    cat_stmt = cat_stmt.group_by(
        Category.name, Category.display_name, CategoryFamily.name,
        Session.label, Session.year, Session.season,
    ).order_by(func.sum(Observation.minutes).desc())

    cat_result = await db.execute(cat_stmt)
    cat_rows = cat_result.all()

    # ── 3. Fetch text entries ──
    text_stmt = (
        select(TextEntry)
        .where(TextEntry.session_id.in_(session_ids))
        .order_by(TextEntry.date)
    )
    if parsed.date_range[0]:
        text_stmt = text_stmt.where(TextEntry.date >= parsed.date_range[0])
    if parsed.date_range[1]:
        text_stmt = text_stmt.where(TextEntry.date <= parsed.date_range[1])

    text_result = await db.execute(text_stmt)
    text_entries = text_result.scalars().all()

    # ── 4. Build date range info ──
    date_stmt = (
        select(
            func.min(DailyRecord.date).label("min_date"),
            func.max(DailyRecord.date).label("max_date"),
        )
        .where(DailyRecord.session_id.in_(session_ids))
    )
    if parsed.date_range[0]:
        date_stmt = date_stmt.where(DailyRecord.date >= parsed.date_range[0])
    if parsed.date_range[1]:
        date_stmt = date_stmt.where(DailyRecord.date <= parsed.date_range[1])

    date_result = await db.execute(date_stmt)
    date_row = date_result.one()
    actual_date_range = [date_row.min_date, date_row.max_date]

    # ── 5. Format as markdown ──
    categories_included: list[str] = []
    data_points = len(cat_rows) + len(text_entries)

    md_parts: list[str] = []
    md_parts.append("# Productivity Data Context\n")

    # Sessions overview
    md_parts.append("## Sessions Included")
    for s in sessions:
        label = s.label or f"{s.season.title()} {s.year}"
        md_parts.append(f"- **{label}** ({s.year}, {s.season})")

    if actual_date_range[0]:
        md_parts.append(f"\nDate range: {actual_date_range[0]} to {actual_date_range[1]}")

    # Category breakdowns by session
    md_parts.append("\n## Category Time Totals")

    current_session = None
    for row in cat_rows:
        session_label = row.session_label or f"{row.season.title()} {row.year}"
        if session_label != current_session:
            current_session = session_label
            md_parts.append(f"\n### {session_label}")

        display = row.display_name or row.name
        minutes = int(row.total_minutes)
        hours = minutes / 60
        family_tag = f" [{row.family_name}]" if row.family_name else ""
        md_parts.append(f"- {display}{family_tag}: **{hours:.1f}h** ({minutes}m)")

        if display not in categories_included:
            categories_included.append(display)

    # Text entries (truncated)
    if text_entries:
        md_parts.append("\n## Activity Notes")
        shown = 0
        for te in text_entries:
            if shown >= 50:
                md_parts.append(f"\n... and {len(text_entries) - 50} more entries")
                break
            parts = []
            if te.notes:
                parts.append(te.notes)
            if te.study_materials:
                parts.append(te.study_materials)
            if te.location:
                parts.append(f"({te.location})")
            if parts:
                md_parts.append(f"- **{te.date}**: {' — '.join(parts)}")
                shown += 1

    context_markdown = "\n".join(md_parts)

    # ── 6. Truncate if too long (~6000 words ≈ ~30000 chars) ──
    if len(context_markdown) > 30000:
        context_markdown = context_markdown[:30000] + "\n\n... [truncated for length]"

    # Build summary
    total_minutes = sum(int(r.total_minutes) for r in cat_rows)
    summary = (
        f"{len(sessions)} session(s), {len(categories_included)} categories, "
        f"{total_minutes // 60}h {total_minutes % 60}m total, "
        f"{len(text_entries)} text entries"
    )

    return {
        "context_markdown": context_markdown,
        "summary": summary,
        "sessions_included": session_labels,
        "categories_included": categories_included,
        "date_range": actual_date_range,
        "data_points": data_points,
    }
