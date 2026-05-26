"""Anthropic tool-use surface for the chat assistant.

Replaces the old "regex parser → flat markdown dump → single Claude call"
flow with a multi-turn loop where Claude can call these tools to fetch only
the data it actually needs. Tools traverse the live Group → Family →
Category → Entry hierarchy so chat responses naturally reflect the same
grouping as the rest of the app.

Each tool has:
  - A JSON-schema definition (sent to Anthropic via the `tools` param)
  - An async executor that queries the DB and returns a JSON-serializable dict

Tools are READ-ONLY by design. No tool writes to the database.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any, Callable, Awaitable

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import (
    Session,
    Category,
    CategoryFamily,
    CategoryGroup,
    DailyRecord,
    Observation,
    TextEntry,
    TimerEntry,
    ManualEntry,
)


# ── Tool schemas (Anthropic format) ───────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_sessions",
        "description": (
            "List the user's tracking sessions (one per academic quarter or work cycle). "
            "Use this to discover which session_id corresponds to a season/year, or to "
            "find the currently active session. Returns id, label, year, season, date "
            "range, and total minutes per session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Filter to a specific year (e.g. 2026)."},
                "season": {
                    "type": "string",
                    "enum": ["fall", "winter", "spring", "summer"],
                    "description": "Filter to a specific season.",
                },
                "active_only": {
                    "type": "boolean",
                    "description": "If true, return only the currently active session.",
                },
            },
        },
    },
    {
        "name": "list_families",
        "description": (
            "List category families with optional filters. Families are cross-session "
            "projects (e.g. 'Salk Research', 'COGS'). Use to discover what families "
            "exist or to find them by group (research/training/personal/courses)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_name": {
                    "type": "string",
                    "description": "Filter to families belonging to this group "
                                   "(research, training, personal, courses).",
                },
                "session_id": {
                    "type": "integer",
                    "description": "Filter to families that have at least one category in "
                                   "this session.",
                },
            },
        },
    },
    {
        "name": "get_family_breakdown",
        "description": (
            "Get total minutes for a specific family, broken down by session and by "
            "category. Use this to answer 'how much time on X?' for any project/family. "
            "Specify either family_name (case-insensitive match on name or display_name) "
            "or family_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "family_name": {"type": "string"},
                "family_id": {"type": "integer"},
                "session_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Restrict the breakdown to these sessions.",
                },
                "date_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[start_date, end_date] in YYYY-MM-DD.",
                },
            },
        },
    },
    {
        "name": "get_group_breakdown",
        "description": (
            "Get total minutes for an entire group (research / training / personal / "
            "courses), broken down by family. Use this for top-level questions like "
            "'how much research did I do?' Returns the families inside the group with "
            "their totals, so the chat can refer to projects by their family name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_name": {
                    "type": "string",
                    "description": "research | training | personal | courses",
                },
                "session_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "date_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "required": ["group_name"],
        },
    },
    {
        "name": "get_session_breakdown",
        "description": (
            "Get a full breakdown of one session's time by group, family, or category. "
            "Use 'group' for the top-level view (Research/Courses/etc), 'family' for "
            "per-project, 'category' for the most-detailed list. Default 'family'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "integer"},
                "by": {
                    "type": "string",
                    "enum": ["group", "family", "category"],
                    "description": "Aggregation level.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_daily_breakdown",
        "description": (
            "List every entry on a specific date — timer + manual entries with their "
            "descriptions and locations, plus any free-form text notes. Use this for "
            "'what did I do on X day?' or to verify a peak day in some other breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "search_text_entries",
        "description": (
            "Substring search over all free-form text the user has written: "
            "timer_entries.description, manual_entries.description, and the daily "
            "narrative in text_entries (notes + study_materials + location). "
            "Returns matching entries with date, source, snippet, and (for timer/"
            "manual) the category. Use for content questions like 'when did I work "
            "on the rebuttal?' or 'days I was at the library'. Case-insensitive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Substrings to match (case-insensitive).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["all", "any"],
                    "description": "'all' (default): every keyword must appear in the same "
                                   "entry. 'any': match if any keyword appears.",
                },
                "date_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "limit": {"type": "integer", "description": "Max snippets (default 30)."},
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "summarize_text_in_range",
        "description": (
            "Return ALL free-form text content (timer descriptions, manual entry "
            "descriptions, daily notes) within a date range, optionally restricted "
            "to a specific family. Use this when the user asks for a narrative "
            "summary or 'what was I working on' without specific keywords — Claude "
            "can read the raw prose and synthesize. Output is capped to keep "
            "context manageable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[start_date, end_date] in YYYY-MM-DD. Required.",
                },
                "family_name": {"type": "string"},
                "family_id": {"type": "integer"},
                "limit": {"type": "integer", "description": "Max entries returned (default 100)."},
            },
            "required": ["date_range"],
        },
    },
]


# ── Tool executors ────────────────────────────────────────────────────────


def _apply_date_range(stmt, col, date_range: list[str] | None):
    if date_range and len(date_range) == 2:
        if date_range[0]:
            stmt = stmt.where(col >= date_range[0])
        if date_range[1]:
            stmt = stmt.where(col <= date_range[1])
    return stmt


async def tool_list_sessions(args: dict, db: AsyncSession) -> dict:
    stmt = select(Session)
    if args.get("year") is not None:
        stmt = stmt.where(Session.year == args["year"])
    if args.get("season"):
        stmt = stmt.where(Session.season == args["season"])
    if args.get("active_only"):
        stmt = stmt.where(Session.is_active == True)  # noqa: E712
    result = await db.execute(stmt.order_by(Session.year.desc(), Session.season))
    sessions = result.scalars().all()

    out = []
    for s in sessions:
        # Compute total minutes via daily_records
        total_q = await db.execute(
            select(func.coalesce(func.sum(DailyRecord.total_minutes), 0))
            .where(DailyRecord.session_id == s.id)
        )
        total = int(total_q.scalar() or 0)
        days_q = await db.execute(
            select(func.count(DailyRecord.id)).where(DailyRecord.session_id == s.id)
        )
        days = int(days_q.scalar() or 0)
        out.append({
            "id": s.id,
            "label": s.label or f"{s.season.title()} {s.year}",
            "year": s.year,
            "season": s.season,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "is_active": bool(s.is_active),
            "total_minutes": total,
            "days_logged": days,
        })
    return {"sessions": out, "count": len(out)}


async def tool_list_families(args: dict, db: AsyncSession) -> dict:
    stmt = select(CategoryFamily)

    if args.get("group_name"):
        group_q = await db.execute(
            select(CategoryGroup).where(CategoryGroup.name == args["group_name"].lower())
        )
        group = group_q.scalar_one_or_none()
        if group:
            stmt = stmt.where(CategoryFamily.group_id == group.id)
        else:
            return {"families": [], "count": 0, "warning": f"No group named '{args['group_name']}'"}

    if args.get("session_id"):
        # Families that have at least one category in this session
        cat_subq = (
            select(Category.family_id)
            .where(Category.session_id == args["session_id"])
            .where(Category.family_id.is_not(None))
            .distinct()
        )
        stmt = stmt.where(CategoryFamily.id.in_(cat_subq))

    result = await db.execute(stmt.order_by(CategoryFamily.name))
    families = result.scalars().all()

    out = []
    for f in families:
        cat_count_q = await db.execute(
            select(func.count(Category.id)).where(Category.family_id == f.id)
        )
        total_q = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .join(Category, Observation.category_id == Category.id)
            .where(Category.family_id == f.id)
        )
        group_name = None
        if f.group_id:
            g = await db.get(CategoryGroup, f.group_id)
            group_name = g.display_name if g else None
        out.append({
            "id": f.id,
            "name": f.name,
            "display_name": f.display_name,
            "group": group_name,
            "color": f.color,
            "category_count": int(cat_count_q.scalar() or 0),
            "total_minutes": int(total_q.scalar() or 0),
        })
    return {"families": out, "count": len(out)}


async def _resolve_family(args: dict, db: AsyncSession) -> CategoryFamily | None:
    if args.get("family_id") is not None:
        return await db.get(CategoryFamily, int(args["family_id"]))
    name = args.get("family_name")
    if not name:
        return None
    needle = name.strip().lower()
    stmt = select(CategoryFamily).where(
        or_(
            func.lower(CategoryFamily.name) == needle,
            func.lower(CategoryFamily.display_name) == needle,
        )
    )
    result = await db.execute(stmt)
    fam = result.scalar_one_or_none()
    if fam:
        return fam
    # Try partial match
    like = f"%{needle}%"
    stmt2 = select(CategoryFamily).where(
        or_(
            func.lower(CategoryFamily.name).like(like),
            func.lower(CategoryFamily.display_name).like(like),
        )
    )
    return (await db.execute(stmt2)).scalars().first()


async def tool_get_family_breakdown(args: dict, db: AsyncSession) -> dict:
    fam = await _resolve_family(args, db)
    if not fam:
        return {"error": f"No family found matching {args.get('family_name') or args.get('family_id')}"}

    # All categories in this family
    cats_q = await db.execute(select(Category).where(Category.family_id == fam.id))
    cats = cats_q.scalars().all()
    cat_ids = [c.id for c in cats]
    if not cat_ids:
        return {
            "family": {"id": fam.id, "name": fam.display_name or fam.name},
            "total_minutes": 0,
            "by_session": [],
            "by_category": [],
        }

    # Observation join is the most accurate aggregate
    obs_stmt = (
        select(
            Observation.category_id,
            DailyRecord.session_id,
            DailyRecord.date,
            func.coalesce(func.sum(Observation.minutes), 0).label("mins"),
        )
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
        .where(Observation.category_id.in_(cat_ids))
        .group_by(Observation.category_id, DailyRecord.session_id, DailyRecord.date)
    )
    if args.get("session_ids"):
        obs_stmt = obs_stmt.where(DailyRecord.session_id.in_(args["session_ids"]))
    obs_stmt = _apply_date_range(obs_stmt, DailyRecord.date, args.get("date_range"))

    rows = (await db.execute(obs_stmt)).all()

    # Aggregate by session
    by_session: dict[int, int] = {}
    by_category: dict[int, int] = {}
    total = 0
    for r in rows:
        by_session[r.session_id] = by_session.get(r.session_id, 0) + int(r.mins or 0)
        by_category[r.category_id] = by_category.get(r.category_id, 0) + int(r.mins or 0)
        total += int(r.mins or 0)

    # Hydrate labels
    sess_q = await db.execute(select(Session).where(Session.id.in_(by_session.keys() or [-1])))
    sess_label = {s.id: (s.label or f"{s.season.title()} {s.year}") for s in sess_q.scalars().all()}
    cat_label = {c.id: (c.display_name or c.name) for c in cats}

    return {
        "family": {
            "id": fam.id,
            "name": fam.display_name or fam.name,
            "group": (await db.get(CategoryGroup, fam.group_id)).display_name if fam.group_id else None,
        },
        "total_minutes": total,
        "by_session": sorted(
            [{"session_id": k, "label": sess_label.get(k, "?"), "minutes": v} for k, v in by_session.items()],
            key=lambda x: -x["minutes"],
        ),
        "by_category": sorted(
            [{"category_id": k, "name": cat_label.get(k, "?"), "minutes": v} for k, v in by_category.items()],
            key=lambda x: -x["minutes"],
        ),
    }


async def tool_get_group_breakdown(args: dict, db: AsyncSession) -> dict:
    group_name = (args.get("group_name") or "").strip().lower()
    g_q = await db.execute(select(CategoryGroup).where(CategoryGroup.name == group_name))
    group = g_q.scalar_one_or_none()
    if not group:
        return {"error": f"No group named '{group_name}'. Try research/training/personal/courses."}

    # Sum observations through category → family → this group
    obs_stmt = (
        select(
            CategoryFamily.id.label("family_id"),
            CategoryFamily.display_name.label("family_label"),
            CategoryFamily.name.label("family_slug"),
            func.coalesce(func.sum(Observation.minutes), 0).label("mins"),
        )
        .join(Category, Category.family_id == CategoryFamily.id)
        .join(Observation, Observation.category_id == Category.id)
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
        .where(CategoryFamily.group_id == group.id)
    )
    if args.get("session_ids"):
        obs_stmt = obs_stmt.where(DailyRecord.session_id.in_(args["session_ids"]))
    obs_stmt = _apply_date_range(obs_stmt, DailyRecord.date, args.get("date_range"))
    obs_stmt = obs_stmt.group_by(CategoryFamily.id).order_by(func.sum(Observation.minutes).desc())

    rows = (await db.execute(obs_stmt)).all()
    by_family = [
        {"family_id": r.family_id, "name": r.family_label or r.family_slug, "minutes": int(r.mins or 0)}
        for r in rows
    ]
    total = sum(f["minutes"] for f in by_family)
    return {
        "group": {"id": group.id, "name": group.display_name or group.name},
        "total_minutes": total,
        "by_family": by_family,
    }


async def tool_get_session_breakdown(args: dict, db: AsyncSession) -> dict:
    session_id = int(args.get("session_id", 0))
    sess = await db.get(Session, session_id) if session_id else None
    if not sess:
        return {"error": f"Session {session_id} not found"}

    by = args.get("by", "family")

    if by == "category":
        rows_q = await db.execute(
            select(
                Category.id, Category.display_name, Category.name,
                CategoryFamily.display_name.label("family"),
                func.coalesce(func.sum(Observation.minutes), 0).label("mins"),
            )
            .join(Observation, Observation.category_id == Category.id)
            .outerjoin(CategoryFamily, Category.family_id == CategoryFamily.id)
            .where(Category.session_id == session_id)
            .group_by(Category.id)
            .order_by(func.sum(Observation.minutes).desc())
        )
        items = [
            {
                "name": r.display_name or r.name,
                "family": r.family,
                "minutes": int(r.mins or 0),
            }
            for r in rows_q.all()
        ]
    elif by == "group":
        rows_q = await db.execute(
            select(
                CategoryGroup.id, CategoryGroup.display_name,
                func.coalesce(func.sum(Observation.minutes), 0).label("mins"),
            )
            .join(CategoryFamily, CategoryFamily.group_id == CategoryGroup.id)
            .join(Category, Category.family_id == CategoryFamily.id)
            .join(Observation, Observation.category_id == Category.id)
            .where(Category.session_id == session_id)
            .group_by(CategoryGroup.id)
            .order_by(func.sum(Observation.minutes).desc())
        )
        items = [
            {"name": r.display_name, "minutes": int(r.mins or 0)}
            for r in rows_q.all()
        ]
    else:  # family
        rows_q = await db.execute(
            select(
                CategoryFamily.id, CategoryFamily.display_name, CategoryFamily.name,
                CategoryGroup.display_name.label("group"),
                func.coalesce(func.sum(Observation.minutes), 0).label("mins"),
            )
            .join(Category, Category.family_id == CategoryFamily.id)
            .join(Observation, Observation.category_id == Category.id)
            .outerjoin(CategoryGroup, CategoryFamily.group_id == CategoryGroup.id)
            .where(Category.session_id == session_id)
            .group_by(CategoryFamily.id)
            .order_by(func.sum(Observation.minutes).desc())
        )
        items = [
            {
                "name": r.display_name or r.name,
                "group": r.group,
                "minutes": int(r.mins or 0),
            }
            for r in rows_q.all()
        ]

    total = sum(i["minutes"] for i in items)
    return {
        "session": {"id": sess.id, "label": sess.label or f"{sess.season.title()} {sess.year}"},
        "by": by,
        "items": items,
        "total_minutes": total,
    }


async def tool_get_daily_breakdown(args: dict, db: AsyncSession) -> dict:
    d = args.get("date")
    if not d:
        return {"error": "date is required"}

    # Find which session contains this date (the active one most likely)
    timers = (await db.execute(
        select(TimerEntry).where(TimerEntry.date == d, TimerEntry.is_active == False)  # noqa: E712
    )).scalars().all()
    manuals = (await db.execute(
        select(ManualEntry).where(ManualEntry.date == d)
    )).scalars().all()
    texts = (await db.execute(
        select(TextEntry).where(TextEntry.date == d)
    )).scalars().all()

    async def cat_name(cid: int) -> str:
        c = await db.get(Category, cid)
        return (c.display_name or c.name) if c else f"category#{cid}"

    timer_items = []
    for t in timers:
        timer_items.append({
            "type": "timer",
            "category": await cat_name(t.category_id),
            "duration_minutes": t.duration_minutes,
            "description": t.description,
            "location": t.location,
            "end_time": t.end_time,
        })
    manual_items = []
    for m in manuals:
        manual_items.append({
            "type": "manual",
            "category": await cat_name(m.category_id),
            "duration_minutes": m.duration_minutes,
            "description": m.description,
            "location": m.location,
        })
    notes = [
        {"location": t.location, "notes": t.notes, "study_materials": t.study_materials}
        for t in texts
    ]
    total = sum(t.duration_minutes or 0 for t in timers) + sum(m.duration_minutes or 0 for m in manuals)
    return {
        "date": d,
        "total_minutes": total,
        "timer_entries": timer_items,
        "manual_entries": manual_items,
        "notes": notes,
    }


async def tool_search_text_entries(args: dict, db: AsyncSession) -> dict:
    """Substring search across timer descriptions, manual descriptions, and
    daily text entries. Default match mode is ALL keywords required in the
    same entry; mode='any' loosens to OR-match.
    """
    keywords: list[str] = [k.strip().lower() for k in (args.get("keywords") or []) if k.strip()]
    if not keywords:
        return {"matches": [], "count": 0}
    mode = args.get("mode", "all").lower()
    if mode not in ("all", "any"):
        mode = "all"
    limit = int(args.get("limit", 30))
    date_range = args.get("date_range")

    def matches(hay: str) -> list[str] | None:
        """Return matched keywords if `mode` is satisfied, else None."""
        hay_l = hay.lower()
        hits = [k for k in keywords if k in hay_l]
        if mode == "all" and len(hits) != len(keywords):
            return None
        if mode == "any" and not hits:
            return None
        return hits

    # --- 1. Timer entries (each one has its own description + location) ---
    tstmt = (
        select(TimerEntry, Category)
        .outerjoin(Category, TimerEntry.category_id == Category.id)
        .where(TimerEntry.is_active == False)  # noqa: E712
    )
    tstmt = _apply_date_range(tstmt, TimerEntry.date, date_range)
    tstmt = tstmt.order_by(TimerEntry.date.desc())
    timer_rows = (await db.execute(tstmt)).all()

    out: list[dict] = []

    for te_row in timer_rows:
        timer, cat = te_row
        hay = " ".join([timer.description or "", timer.location or ""])
        if not hay.strip():
            continue
        hits = matches(hay)
        if hits is None:
            continue
        snippet = (timer.description or timer.location or "")[:300]
        out.append({
            "date": timer.date,
            "source": "timer",
            "snippet": snippet,
            "matched_keywords": hits,
            "category": (cat.display_name or cat.name) if cat else None,
            "minutes": timer.duration_minutes,
            "location": timer.location,
        })
        if len(out) >= limit:
            return {"matches": out, "count": len(out), "keywords": keywords, "mode": mode}

    # --- 2. Manual entries (description + location) ---
    mstmt = (
        select(ManualEntry, Category)
        .outerjoin(Category, ManualEntry.category_id == Category.id)
    )
    mstmt = _apply_date_range(mstmt, ManualEntry.date, date_range)
    mstmt = mstmt.order_by(ManualEntry.date.desc())
    manual_rows = (await db.execute(mstmt)).all()

    for me_row in manual_rows:
        manual, cat = me_row
        hay = " ".join([manual.description or "", manual.location or ""])
        if not hay.strip():
            continue
        hits = matches(hay)
        if hits is None:
            continue
        snippet = (manual.description or manual.location or "")[:300]
        out.append({
            "date": manual.date,
            "source": "manual",
            "snippet": snippet,
            "matched_keywords": hits,
            "category": (cat.display_name or cat.name) if cat else None,
            "minutes": manual.duration_minutes,
            "location": manual.location,
        })
        if len(out) >= limit:
            return {"matches": out, "count": len(out), "keywords": keywords, "mode": mode}

    # --- 3. Daily text_entries (aggregated narrative, location, notes) ---
    estmt = select(TextEntry)
    estmt = _apply_date_range(estmt, TextEntry.date, date_range)
    estmt = estmt.order_by(TextEntry.date.desc())
    text_rows = (await db.execute(estmt)).scalars().all()

    for te in text_rows:
        hay = " ".join([te.notes or "", te.study_materials or "", te.location or ""])
        if not hay.strip():
            continue
        hits = matches(hay)
        if hits is None:
            continue
        snippet = (te.study_materials or te.notes or "")[:300]
        out.append({
            "date": te.date,
            "source": "text_entry",
            "snippet": snippet,
            "matched_keywords": hits,
            "location": te.location,
        })
        if len(out) >= limit:
            return {"matches": out, "count": len(out), "keywords": keywords, "mode": mode}

    return {"matches": out, "count": len(out), "keywords": keywords, "mode": mode}


async def tool_summarize_text_in_range(args: dict, db: AsyncSession) -> dict:
    """Return ALL free-form text within a date range, optionally restricted to
    a family. No keyword filtering — gives Claude the raw prose to read and
    synthesize when the user asks for an open-ended summary.
    """
    date_range = args.get("date_range")
    if not date_range or len(date_range) != 2 or not all(date_range):
        return {"error": "date_range [start, end] is required"}
    limit = int(args.get("limit", 100))

    # Optional family filter via name or id
    family_filter_cat_ids: set[int] | None = None
    family_info: dict | None = None
    if args.get("family_name") or args.get("family_id") is not None:
        fam = await _resolve_family(args, db)
        if not fam:
            return {"error": f"No family found matching {args.get('family_name') or args.get('family_id')}"}
        cats_q = await db.execute(select(Category.id).where(Category.family_id == fam.id))
        family_filter_cat_ids = {row[0] for row in cats_q.all()}
        family_info = {
            "id": fam.id,
            "name": fam.display_name or fam.name,
        }

    entries: list[dict] = []

    # Timer entries with descriptions
    tstmt = (
        select(TimerEntry, Category)
        .outerjoin(Category, TimerEntry.category_id == Category.id)
        .where(TimerEntry.is_active == False)  # noqa: E712
        .where(TimerEntry.date >= date_range[0])
        .where(TimerEntry.date <= date_range[1])
        .order_by(TimerEntry.date.desc())
    )
    timer_rows = (await db.execute(tstmt)).all()
    for timer, cat in timer_rows:
        if family_filter_cat_ids is not None and timer.category_id not in family_filter_cat_ids:
            continue
        if not (timer.description or "").strip():
            continue
        entries.append({
            "date": timer.date,
            "source": "timer",
            "category": (cat.display_name or cat.name) if cat else None,
            "text": timer.description,
            "minutes": timer.duration_minutes,
            "location": timer.location,
        })

    # Manual entries with descriptions
    mstmt = (
        select(ManualEntry, Category)
        .outerjoin(Category, ManualEntry.category_id == Category.id)
        .where(ManualEntry.date >= date_range[0])
        .where(ManualEntry.date <= date_range[1])
        .order_by(ManualEntry.date.desc())
    )
    manual_rows = (await db.execute(mstmt)).all()
    for manual, cat in manual_rows:
        if family_filter_cat_ids is not None and manual.category_id not in family_filter_cat_ids:
            continue
        if not (manual.description or "").strip():
            continue
        entries.append({
            "date": manual.date,
            "source": "manual",
            "category": (cat.display_name or cat.name) if cat else None,
            "text": manual.description,
            "minutes": manual.duration_minutes,
            "location": manual.location,
        })

    # Daily text_entries — only when there's NO family filter (text_entries are
    # day-level, not per-family). Including these gives a richer narrative view.
    if family_filter_cat_ids is None:
        estmt = (
            select(TextEntry)
            .where(TextEntry.date >= date_range[0])
            .where(TextEntry.date <= date_range[1])
            .order_by(TextEntry.date.desc())
        )
        text_rows = (await db.execute(estmt)).scalars().all()
        for te in text_rows:
            raw = te.study_materials or te.notes
            if not raw or not raw.strip():
                continue
            entries.append({
                "date": te.date,
                "source": "text_entry",
                "category": None,
                "text": raw,
                "minutes": None,
                "location": te.location,
            })

    # Sort by date desc, then truncate to limit
    entries.sort(key=lambda e: e["date"], reverse=True)
    truncated = entries[:limit]
    return {
        "date_range": date_range,
        "family": family_info,
        "total_entries": len(entries),
        "returned_entries": len(truncated),
        "entries": truncated,
    }


TOOL_EXECUTORS: dict[str, Callable[[dict, AsyncSession], Awaitable[dict]]] = {
    "list_sessions": tool_list_sessions,
    "list_families": tool_list_families,
    "get_family_breakdown": tool_get_family_breakdown,
    "get_group_breakdown": tool_get_group_breakdown,
    "get_session_breakdown": tool_get_session_breakdown,
    "get_daily_breakdown": tool_get_daily_breakdown,
    "search_text_entries": tool_search_text_entries,
    "summarize_text_in_range": tool_summarize_text_in_range,
}


async def execute_tool(name: str, args: dict, db: AsyncSession) -> dict:
    fn = TOOL_EXECUTORS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await fn(args or {}, db)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Tool {name} failed: {e!s}"}
