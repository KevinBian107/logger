"""Analytics service: overview, daily series, category breakdown, heatmap, session comparison."""

from collections import defaultdict

from sqlalchemy import select, func, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import (
    Session, DailyRecord, Observation, Category, CategoryFamily,
)


def _apply_filters(stmt, filters: dict, *, table=DailyRecord):
    """Apply optional session_ids / from_date / to_date / week_number filters to a query."""
    session_ids = filters.get("session_ids")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    week_number = filters.get("week_number")

    if session_ids:
        stmt = stmt.where(table.session_id.in_(session_ids))
    if from_date:
        stmt = stmt.where(table.date >= from_date)
    if to_date:
        stmt = stmt.where(table.date <= to_date)
    if week_number is not None:
        stmt = stmt.where(table.week_number == week_number)
    return stmt


async def get_overview(db: AsyncSession, filters: dict) -> dict:
    """Aggregate overview stats: total minutes, days tracked, daily average, active categories."""
    # Total minutes and days from DailyRecord
    stmt = select(
        func.coalesce(func.sum(DailyRecord.total_minutes), 0).label("total_minutes"),
        func.count(DailyRecord.id).label("days_tracked"),
    )
    stmt = _apply_filters(stmt, filters)
    result = await db.execute(stmt)
    row = result.one()
    total_minutes = int(row.total_minutes)
    days_tracked = int(row.days_tracked)
    daily_average = total_minutes // days_tracked if days_tracked > 0 else 0

    # Active categories count
    cat_stmt = (
        select(func.count(func.distinct(Observation.category_id)))
        .select_from(Observation)
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
    )
    cat_stmt = _apply_filters(cat_stmt, filters)
    cat_result = await db.execute(cat_stmt)
    active_categories = int(cat_result.scalar())

    return {
        "total_minutes": total_minutes,
        "days_tracked": days_tracked,
        "daily_average": daily_average,
        "active_categories": active_categories,
    }


async def get_daily_series(db: AsyncSession, filters: dict) -> list[dict]:
    """Daily time series with per-category breakdown (top 8 + Other)."""
    # Use the v_daily_totals view
    where_clauses = []
    params: dict = {}
    if filters.get("session_ids"):
        placeholders = ", ".join(f":sid_{i}" for i in range(len(filters["session_ids"])))
        where_clauses.append(f"session_id IN ({placeholders})")
        for i, sid in enumerate(filters["session_ids"]):
            params[f"sid_{i}"] = sid
    if filters.get("from_date"):
        where_clauses.append("date >= :from_date")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        where_clauses.append("date <= :to_date")
        params["to_date"] = filters["to_date"]
    if filters.get("week_number") is not None:
        where_clauses.append("week_number = :week_number")
        params["week_number"] = filters["week_number"]

    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    sql = sa_text(f"""
        SELECT date, category_name, family_color, SUM(minutes) as total_mins
        FROM v_daily_totals
        {where}
        GROUP BY date, category_name
        ORDER BY date
    """)
    result = await db.execute(sql, params)
    rows = result.all()

    # Find top 8 categories by total minutes
    cat_totals: dict[str, int] = defaultdict(int)
    cat_colors: dict[str, str | None] = {}
    for row in rows:
        cat_totals[row.category_name] += int(row.total_mins)
        if row.family_color:
            cat_colors[row.category_name] = row.family_color

    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    top_cats = {name for name, _ in sorted_cats[:8]}

    # Group by date
    daily: dict[str, dict] = {}
    for row in rows:
        date = row.date
        if date not in daily:
            daily[date] = {"date": date, "total_minutes": 0, "categories": {}}

        cat_name = row.category_name if row.category_name in top_cats else "Other"
        mins = int(row.total_mins)
        daily[date]["total_minutes"] += mins

        if cat_name not in daily[date]["categories"]:
            color = cat_colors.get(row.category_name) if cat_name != "Other" else None
            daily[date]["categories"][cat_name] = {"name": cat_name, "minutes": 0, "color": color}
        daily[date]["categories"][cat_name]["minutes"] += mins

    return [
        {
            "date": d["date"],
            "total_minutes": d["total_minutes"],
            "categories": list(d["categories"].values()),
        }
        for d in daily.values()
    ]


async def get_category_breakdown(db: AsyncSession, filters: dict) -> list[dict]:
    """Category breakdown: total minutes per category per session."""
    stmt = (
        select(
            Category.name,
            Category.display_name,
            CategoryFamily.name.label("family_name"),
            CategoryFamily.color.label("color"),
            func.sum(Observation.minutes).label("total_minutes"),
            func.count(func.distinct(DailyRecord.session_id)).label("session_count"),
            Session.label.label("session_label"),
            Session.year.label("session_year"),
            Session.season.label("session_season"),
        )
        .select_from(Observation)
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
        .join(Category, Observation.category_id == Category.id)
        .join(Session, DailyRecord.session_id == Session.id)
        .outerjoin(CategoryFamily, Category.family_id == CategoryFamily.id)
    )
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.group_by(
        Category.name, Category.display_name,
        CategoryFamily.name, CategoryFamily.color,
        Session.id,
    )
    stmt = stmt.order_by(func.sum(Observation.minutes).desc())

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "name": row.name,
            "display_name": row.display_name,
            "family_name": row.family_name,
            "color": row.color,
            "total_minutes": int(row.total_minutes),
            "session_count": int(row.session_count),
            "session_label": row.session_label or f"{row.session_season} {row.session_year}",
        }
        for row in rows
    ]


async def get_heatmap(db: AsyncSession, filters: dict) -> list[dict]:
    """Heatmap data: date + day_of_week + total_minutes."""
    stmt = select(DailyRecord.date, DailyRecord.total_minutes)
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.order_by(DailyRecord.date)

    result = await db.execute(stmt)
    rows = result.all()

    points = []
    for row in rows:
        # Parse date string to get day_of_week (0=Mon, 6=Sun)
        # Dates are stored as YYYY-MM-DD
        from datetime import date as dt_date
        parts = row.date.split("-")
        d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
        points.append({
            "date": row.date,
            "day_of_week": d.weekday(),  # 0=Mon, 6=Sun
            "total_minutes": int(row.total_minutes),
        })

    return points


async def get_session_comparison(db: AsyncSession) -> list[dict]:
    """Per-session stats with family-based composition."""
    # Get sessions with aggregates
    stmt = (
        select(
            Session.id,
            Session.label,
            Session.year,
            Session.season,
            func.coalesce(func.sum(DailyRecord.total_minutes), 0).label("total_minutes"),
            func.count(DailyRecord.id).label("days_logged"),
        )
        .outerjoin(DailyRecord, DailyRecord.session_id == Session.id)
        .group_by(Session.id)
        .order_by(Session.year, Session.season)
    )
    result = await db.execute(stmt)
    sessions = result.all()

    # Preload all families for color/display_name lookup
    fam_result = await db.execute(select(CategoryFamily))
    all_families = {f.id: f for f in fam_result.scalars().all()}

    out = []
    for s in sessions:
        # Get per-family minutes for this session
        fam_stmt = (
            select(
                Category.family_id,
                func.sum(Observation.minutes).label("minutes"),
            )
            .select_from(Observation)
            .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
            .join(Category, Observation.category_id == Category.id)
            .where(DailyRecord.session_id == s.id)
            .group_by(Category.family_id)
        )
        fam_result_rows = await db.execute(fam_stmt)

        groups = []
        for r in fam_result_rows.all():
            mins = int(r.minutes)
            fid = r.family_id
            if fid is not None and fid in all_families:
                f = all_families[fid]
                groups.append({
                    "name": f.display_name or f.name,
                    "minutes": mins,
                    "color": f.color,
                })
            else:
                groups.append({"name": "Other", "minutes": mins, "color": None})

        # Sort by minutes descending
        groups.sort(key=lambda g: g["minutes"], reverse=True)

        out.append({
            "session_id": s.id,
            "label": s.label or f"{s.season} {s.year}",
            "year": s.year,
            "season": s.season,
            "total_minutes": int(s.total_minutes),
            "days_logged": int(s.days_logged),
            "groups": groups,
        })

    return out
