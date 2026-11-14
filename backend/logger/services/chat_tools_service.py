"""Anthropic tool-use surface for the chat assistant.

Claude answers questions by calling these read-only tools in a multi-turn loop
(see routers/chat.py). Tools traverse the live Group -> Family -> Category ->
Entry hierarchy so answers reflect the same grouping as the rest of the app.

Design notes
------------
* Names are resolved forgivingly (utils/text_match.TermMatcher): users say
  "Finches" for a category called "FinchesLab", "CSE 257" for "cse257", etc.
  Every lookup that takes a name falls back from families to categories to
  free text instead of dead-ending on an exact family-name match.
* Observations (minutes per category per day) are the single source of truth
  for time totals across imported and live-tracked sessions.
* For live-tracked days, timer/manual stop appends each entry's description
  to that day's text_entries row (observation_service.upsert_text_entry), so
  the daily "narrative" duplicates entry descriptions. _load_narratives strips
  those copies so the same sentence is never reported twice.
* Tools never write to the database.

Each tool has a JSON-schema definition (sent to Anthropic via `tools`) and an
async executor returning a JSON-serializable dict. Errors are returned as
{"error": ...} and flagged as is_error tool results by the router.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import (
    BreakDay,
    Category,
    CategoryFamily,
    CategoryGroup,
    DailyRecord,
    ManualEntry,
    Observation,
    Session,
    TextEntry,
    TimerEntry,
)
from logger.services.timer_service import _user_tz
from logger.utils.text_match import TermMatcher, close_names, snippet


# ── Tool schemas (Anthropic format) ───────────────────────────────────────

_DATE_RANGE = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 2,
    "maxItems": 2,
    "description": "[start_date, end_date] inclusive, YYYY-MM-DD.",
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "find_topic",
        "description": (
            "Resolve any name or topic the user mentions — a project, lab, sub-project, "
            "paper, course, person, tool or place — to everything in the data that refers "
            "to it. Searches group, family and category names AND every entry description "
            "and daily narrative, tolerating spacing/casing/plural differences "
            "('Finches' matches category 'FinchesLab' and text 'Finches Lab'). Returns: "
            "matching groups/families/categories with their time, the direct time logged "
            "in matching categories (by session and month), how often and when the term "
            "is mentioned in descriptions (with minutes of those entries by category), "
            "and the mentioning entries in chronological order. If nothing matches, "
            "returns close spellings to try. Use this FIRST for 'what did I do for X', "
            "'how much time on X', or any name you don't see in the data catalog. Pass "
            "obvious aliases together (e.g. ['Finches', 'FinchesAI'])."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-5 names/aliases for the same topic. Core names only "
                                   "('Finches', not 'the Finches project').",
                },
                "date_range": _DATE_RANGE,
                "max_entries": {
                    "type": "integer",
                    "description": "Max mentioning entries to return (default 40, max 150).",
                },
            },
            "required": ["terms"],
        },
    },
    {
        "name": "get_time_breakdown",
        "description": (
            "Aggregate logged time over ANY date range (across session boundaries), "
            "grouped by group, family, category or session, optionally bucketed by day, "
            "week, month or year. Use for 'how much did I work in October', 'top projects "
            "this year', 'weekly trend of Salk this quarter', 'research vs courses by "
            "month'. Optional filters restrict to specific groups/families/categories "
            "(names resolved forgivingly). Same-named categories from different sessions "
            "are merged when grouping by category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range": _DATE_RANGE,
                "session_ids": {"type": "array", "items": {"type": "integer"}},
                "group_by": {
                    "type": "string",
                    "enum": ["group", "family", "category", "session", "none"],
                    "description": "Default 'family'.",
                },
                "bucket": {
                    "type": "string",
                    "enum": ["total", "day", "week", "month", "year"],
                    "description": "Time bucketing for a series. Default 'total' (no series).",
                },
                "groups": {"type": "array", "items": {"type": "string"},
                           "description": "Only include these groups."},
                "families": {"type": "array", "items": {"type": "string"},
                             "description": "Only include these families."},
                "categories": {"type": "array", "items": {"type": "string"},
                               "description": "Only include these categories (any session)."},
                "top_n": {"type": "integer", "description": "Max items listed (default 25)."},
            },
        },
    },
    {
        "name": "get_family_breakdown",
        "description": (
            "Total time for one project/family (or a single category name), broken down "
            "by session, category and month, with first/last logged dates. Accepts "
            "family_name, family_id or category_name; a name that is not a family falls "
            "back to matching categories. For topics that may only appear in descriptions, "
            "use find_topic instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "family_name": {"type": "string"},
                "family_id": {"type": "integer"},
                "category_name": {"type": "string"},
                "session_ids": {"type": "array", "items": {"type": "integer"}},
                "date_range": _DATE_RANGE,
            },
        },
    },
    {
        "name": "get_group_breakdown",
        "description": (
            "Total time for a whole group (e.g. Research, Courses, Personal, Training), "
            "broken down by family and by session. Use for top-level questions like 'how "
            "much research did I do?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_name": {"type": "string"},
                "session_ids": {"type": "array", "items": {"type": "integer"}},
                "date_range": _DATE_RANGE,
            },
            "required": ["group_name"],
        },
    },
    {
        "name": "get_session_breakdown",
        "description": (
            "Full breakdown of one session's time by group, family or category "
            "(default family), with its logged date span and active days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "integer"},
                "session_label": {"type": "string", "description": "e.g. 'Fall 2026'"},
                "by": {"type": "string", "enum": ["group", "family", "category"]},
            },
        },
    },
    {
        "name": "get_daily_breakdown",
        "description": (
            "Everything logged on one date: minutes per category, each timer/manual entry "
            "(start time, minutes, description, location), the day's narrative notes, and "
            "whether it was marked as a break day. Works for imported and live-tracked days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date"],
        },
    },
    {
        "name": "search_text_entries",
        "description": (
            "Keyword search over every free-text record: timer/manual entry descriptions "
            "and locations, and daily narratives. Matching tolerates casing, spacing and "
            "plurals. Returns snippets centered on the match with date, category, family "
            "and minutes, plus the total match count and minutes on matching entries by "
            "category. Use for content questions like 'when did I work on the rebuttal?' "
            "or 'days at the library'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "mode": {
                    "type": "string",
                    "enum": ["all", "any"],
                    "description": "'all' (default): every keyword in the same record. "
                                   "'any': at least one.",
                },
                "date_range": _DATE_RANGE,
                "sort": {"type": "string", "enum": ["newest", "oldest"],
                         "description": "Default 'newest'."},
                "limit": {"type": "integer", "description": "Max results (default 40)."},
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "summarize_text_in_range",
        "description": (
            "All free-text content in a date range — entry descriptions and daily "
            "narratives, chronological — plus a time summary (total and top categories) "
            "for the same range. Optionally restricted to a family or category. Use for "
            "narrative questions without specific keywords: 'what was I working on last "
            "week?', 'summarize my Salk work this quarter'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range": {**_DATE_RANGE, "description": "Required. [start, end] YYYY-MM-DD."},
                "family_name": {"type": "string"},
                "family_id": {"type": "integer"},
                "category_name": {"type": "string"},
                "limit": {"type": "integer", "description": "Max text records (default 150)."},
            },
            "required": ["date_range"],
        },
    },
    {
        "name": "list_sessions",
        "description": (
            "List sessions with id, label, configured date range, actual first/last logged "
            "dates, days logged, total time and whether they were imported or live-tracked. "
            "The data catalog already lists these; call only for filtering or a refresh."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "season": {"type": "string", "enum": ["fall", "winter", "spring", "summer"]},
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "list_families",
        "description": (
            "List families with group, category names, category count and all-time total. "
            "Optional filters: group_name, session_id. The data catalog already lists these."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_name": {"type": "string"},
                "session_id": {"type": "integer"},
            },
        },
    },
]


# ── Shared helpers ─────────────────────────────────────────────────────────

SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}


def hm(minutes: int | float | None) -> str:
    """Minutes -> '12h 30m' (models convert units unreliably, so we do it)."""
    m = int(round(minutes or 0))
    h, r = divmod(m, 60)
    if h and r:
        return f"{h}h {r}m"
    return f"{h}h" if h else f"{r}m"


def session_label(s: Session) -> str:
    return s.label or f"{s.season.title()} {s.year}"


def merge_key(cat: Category) -> str:
    """Same-named categories in different sessions are the same activity
    (mirrors analytics_service.category_merge_key)."""
    return (cat.display_name or cat.name or "").strip().lower()


def _in_range(d: str | None, date_range: list | None) -> bool:
    if not d:
        return False
    if date_range and len(date_range) == 2:
        if date_range[0] and d < date_range[0]:
            return False
        if date_range[1] and d > date_range[1]:
            return False
    return True


def _valid_range(date_range: Any) -> list[str] | None:
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        return [str(date_range[0] or ""), str(date_range[1] or "")]
    return None


def _month(d: str) -> str:
    return d[:7]


def _week(d: str) -> str:
    dt = date_type.fromisoformat(d)
    return (dt - timedelta(days=dt.weekday())).isoformat()


def _bucket(d: str, bucket: str) -> str:
    if bucket == "day":
        return d
    if bucket == "week":
        return _week(d)
    if bucket == "month":
        return _month(d)
    if bucket == "year":
        return d[:4]
    return "total"


def _clip(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "… [truncated]"


@dataclass
class World:
    """The whole (small) hierarchy loaded once per tool call."""

    groups: dict[int, CategoryGroup]
    families: dict[int, CategoryFamily]
    categories: dict[int, Category]
    sessions: dict[int, Session]

    def family_of(self, cid: int) -> CategoryFamily | None:
        c = self.categories.get(cid)
        return self.families.get(c.family_id) if c and c.family_id else None

    def group_of_family(self, fam: CategoryFamily | None) -> CategoryGroup | None:
        return self.groups.get(fam.group_id) if fam and fam.group_id else None

    def cat_name(self, cid: int) -> str:
        c = self.categories.get(cid)
        return (c.display_name or c.name) if c else f"category#{cid}"

    def fam_name(self, fam: CategoryFamily | None) -> str | None:
        return (fam.display_name or fam.name) if fam else None

    def grp_name(self, grp: CategoryGroup | None) -> str | None:
        return (grp.display_name or grp.name) if grp else None

    def cat_context(self, cid: int) -> dict:
        c = self.categories.get(cid)
        fam = self.family_of(cid)
        s = self.sessions.get(c.session_id) if c else None
        return {
            "category": self.cat_name(cid),
            "family": self.fam_name(fam),
            "group": self.grp_name(self.group_of_family(fam)),
            "session": session_label(s) if s else None,
        }


async def load_world(db: AsyncSession) -> World:
    groups = {g.id: g for g in (await db.execute(select(CategoryGroup))).scalars()}
    families = {f.id: f for f in (await db.execute(select(CategoryFamily))).scalars()}
    categories = {c.id: c for c in (await db.execute(select(Category))).scalars()}
    sessions = {s.id: s for s in (await db.execute(select(Session))).scalars()}
    return World(groups, families, categories, sessions)


@dataclass
class ObsRow:
    date: str
    session_id: int
    category_id: int
    minutes: int


async def load_observations(
    db: AsyncSession,
    *,
    date_range: list | None = None,
    session_ids: list[int] | None = None,
    category_ids: set[int] | None = None,
) -> list[ObsRow]:
    stmt = (
        select(DailyRecord.date, DailyRecord.session_id, Observation.category_id, Observation.minutes)
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
    )
    date_range = _valid_range(date_range)
    if date_range:
        if date_range[0]:
            stmt = stmt.where(DailyRecord.date >= date_range[0])
        if date_range[1]:
            stmt = stmt.where(DailyRecord.date <= date_range[1])
    if session_ids:
        stmt = stmt.where(DailyRecord.session_id.in_([int(s) for s in session_ids]))
    if category_ids is not None:
        if not category_ids:
            return []
        stmt = stmt.where(Observation.category_id.in_(category_ids))
    rows = (await db.execute(stmt)).all()
    return [ObsRow(r[0], r[1], r[2], int(r[3] or 0)) for r in rows if (r[3] or 0) > 0]


@dataclass
class Entry:
    kind: str  # "timer" | "manual"
    id: int
    session_id: int
    category_id: int
    date: str
    minutes: int
    description: str
    location: str | None
    start_time: str | None


async def load_entries(db: AsyncSession, date_range: list | None = None) -> list[Entry]:
    out: list[Entry] = []
    date_range = _valid_range(date_range)
    tstmt = select(TimerEntry).where(TimerEntry.is_active == False)  # noqa: E712
    mstmt = select(ManualEntry)
    if date_range:
        if date_range[0]:
            tstmt = tstmt.where(TimerEntry.date >= date_range[0])
            mstmt = mstmt.where(ManualEntry.date >= date_range[0])
        if date_range[1]:
            tstmt = tstmt.where(TimerEntry.date <= date_range[1])
            mstmt = mstmt.where(ManualEntry.date <= date_range[1])
    for t in (await db.execute(tstmt)).scalars():
        out.append(Entry("timer", t.id, t.session_id, t.category_id, t.date,
                         int(t.duration_minutes or 0), t.description or "", t.location, t.start_time))
    for m in (await db.execute(mstmt)).scalars():
        out.append(Entry("manual", m.id, m.session_id, m.category_id, m.date,
                         int(m.duration_minutes or 0), m.description or "", m.location, m.start_time))
    out.sort(key=lambda e: (e.date, e.start_time or ""))
    return out


@dataclass
class Narrative:
    session_id: int
    date: str
    text: str
    location: str | None


async def load_narratives(
    db: AsyncSession, entries: list[Entry], date_range: list | None = None
) -> list[Narrative]:
    """Daily text_entries with auto-appended copies of entry descriptions removed.

    `entries` must cover the same date range so the copies can be found."""
    stmt = select(TextEntry)
    date_range = _valid_range(date_range)
    if date_range:
        if date_range[0]:
            stmt = stmt.where(TextEntry.date >= date_range[0])
        if date_range[1]:
            stmt = stmt.where(TextEntry.date <= date_range[1])
    descs: dict[tuple[int, str], list[str]] = defaultdict(list)
    for e in entries:
        if e.description.strip():
            descs[(e.session_id, e.date)].append(e.description)

    out: list[Narrative] = []
    for te in (await db.execute(stmt)).scalars():
        rest = te.study_materials or ""
        for d in descs.get((te.session_id, te.date), []):
            idx = rest.find(d)
            if idx >= 0:
                rest = rest[:idx] + rest[idx + len(d):]
        rest = re.sub(r"(?:\s*,\s*){2,}", ", ", rest).strip(" ,\n\t")
        text = "\n".join(p for p in [(te.notes or "").strip(), rest] if p)
        if text:
            out.append(Narrative(te.session_id, te.date, text, te.location))
    out.sort(key=lambda n: n.date)
    return out


def _local_hhmm(iso: str | None, tz_name: str) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")
    except (ValueError, KeyError):
        return None


# ── Name resolution ────────────────────────────────────────────────────────


def resolve_groups(name: str, w: World) -> list[CategoryGroup]:
    needle = (name or "").strip().lower()
    if not needle:
        return []
    exact = [g for g in w.groups.values()
             if needle in {(g.name or "").lower(), (g.display_name or "").lower()}]
    if exact:
        return exact
    m = TermMatcher(name)
    return [g for g in w.groups.values() if m.matches(g.name) or m.matches(g.display_name)]


@dataclass
class Scope:
    """A resolved set of categories a question is about."""

    label: str
    kind: str  # "family" | "category" | "categories"
    category_ids: set[int] = field(default_factory=set)
    family: CategoryFamily | None = None
    note: str | None = None


def _all_names(w: World) -> list[str]:
    names = [g.display_name or g.name for g in w.groups.values()]
    names += [f.display_name or f.name for f in w.families.values()]
    names += [c.display_name or c.name for c in w.categories.values()]
    return names


def resolve_scope(args: dict, w: World) -> Scope | dict:
    """family_id / family_name / category_name -> Scope, or {"error": ...}.

    Order: family id; exact family name; exact category name; fuzzy family;
    fuzzy category. A family-name lookup that fails falls through to
    categories (the old behaviour returned "no family found" for "Finches"
    even though a FinchesLab category exists)."""
    if args.get("family_id") is not None:
        fam = w.families.get(int(args["family_id"]))
        if not fam:
            return {"error": f"No family with id {args['family_id']}"}
        return Scope(w.fam_name(fam), "family",
                     {c.id for c in w.categories.values() if c.family_id == fam.id}, fam)

    name = (args.get("family_name") or args.get("category_name") or "").strip()
    if not name:
        return {"error": "Provide family_name, family_id or category_name."}
    needle = name.lower()
    prefer_category = bool(args.get("category_name")) and not args.get("family_name")

    def fam_scope(fam: CategoryFamily, note: str | None = None) -> Scope:
        return Scope(w.fam_name(fam), "family",
                     {c.id for c in w.categories.values() if c.family_id == fam.id}, fam, note)

    def cat_scope(cats: list[Category], note: str | None = None) -> Scope:
        keys = {merge_key(c) for c in cats}
        fams = {c.family_id for c in cats}
        fam = w.families.get(next(iter(fams))) if len(fams) == 1 and None not in fams else None
        label = ", ".join(sorted({c.display_name or c.name for c in cats}))
        return Scope(label, "category" if len(keys) == 1 else "categories",
                     {c.id for c in cats}, fam, note)

    exact_fams = [f for f in w.families.values()
                  if needle in {(f.name or "").lower(), (f.display_name or "").lower()}]
    exact_cats = [c for c in w.categories.values()
                  if needle in {(c.name or "").lower(), (c.display_name or "").lower()}]
    if prefer_category and exact_cats:
        return cat_scope(exact_cats)
    if exact_fams:
        return fam_scope(exact_fams[0])
    if exact_cats:
        return cat_scope(exact_cats, f"'{name}' is a category, not a family.")
    exact_groups = [g for g in w.groups.values()
                    if needle in {(g.name or "").lower(), (g.display_name or "").lower()}]
    if exact_groups:
        g = exact_groups[0]
        return {
            "error": f"'{name}' is a group, not a family — use get_group_breakdown "
                     f"(group_name='{w.grp_name(g)}').",
            "families_in_group": [w.fam_name(f) for f in w.families.values() if f.group_id == g.id],
        }

    m = TermMatcher(name)
    fuzzy_fams = [f for f in w.families.values() if m.matches(f.name) or m.matches(f.display_name)]
    fuzzy_cats = [c for c in w.categories.values() if m.matches(c.name) or m.matches(c.display_name)]
    if prefer_category and fuzzy_cats:
        return cat_scope(fuzzy_cats, f"Fuzzy category match for '{name}'.")
    if len(fuzzy_fams) == 1:
        return fam_scope(fuzzy_fams[0], f"Fuzzy family match for '{name}'.")
    if fuzzy_cats and not fuzzy_fams:
        return cat_scope(fuzzy_cats, f"'{name}' matched categories, not a family.")
    if len(fuzzy_fams) > 1:
        return {
            "error": f"'{name}' matches several families; pick one by family_id.",
            "candidates": [{"family_id": f.id, "name": w.fam_name(f)} for f in fuzzy_fams],
        }

    groups = resolve_groups(name, w)
    hint = (f" '{name}' is a group — use get_group_breakdown." if groups else
            " It may only appear in descriptions — try find_topic.")
    return {
        "error": f"No family or category matches '{name}'.{hint}",
        "did_you_mean": close_names(name, _all_names(w)),
    }


def _time_summary(rows: list[ObsRow], w: World) -> dict:
    """Totals + by-session / by-category / by-month for a set of observations."""
    total = 0
    days: set[str] = set()
    by_session: dict[int, int] = defaultdict(int)
    by_cat: dict[str, int] = defaultdict(int)
    by_month: dict[str, int] = defaultdict(int)
    cat_label: dict[str, str] = {}
    for r in rows:
        total += r.minutes
        days.add(r.date)
        by_session[r.session_id] += r.minutes
        c = w.categories.get(r.category_id)
        key = merge_key(c) if c else str(r.category_id)
        cat_label.setdefault(key, w.cat_name(r.category_id))
        by_cat[key] += r.minutes
        by_month[_month(r.date)] += r.minutes
    first = min(days) if days else None
    last = max(days) if days else None
    return {
        "total_minutes": total,
        "total": hm(total),
        "active_days": len(days),
        "first_date": first,
        "last_date": last,
        "by_session": [
            {"session_id": sid, "label": session_label(w.sessions[sid]) if sid in w.sessions else "?",
             "minutes": m, "time": hm(m)}
            for sid, m in sorted(by_session.items(), key=lambda kv: -kv[1])
        ],
        "by_category": [
            {"name": cat_label[k], "minutes": m, "time": hm(m)}
            for k, m in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "by_month": [{"month": k, "minutes": m} for k, m in sorted(by_month.items())],
    }


# ── Tool executors ─────────────────────────────────────────────────────────


async def tool_find_topic(args: dict, db: AsyncSession) -> dict:
    terms = [str(t).strip() for t in (args.get("terms") or []) if str(t).strip()][:5]
    if not terms and args.get("term"):
        terms = [str(args["term"]).strip()]
    matchers = [m for m in (TermMatcher(t) for t in terms) if m]
    if not matchers:
        return {"error": "Provide at least one search term in `terms`."}
    date_range = _valid_range(args.get("date_range"))
    max_entries = max(1, min(int(args.get("max_entries") or 40), 150))

    def hit(*texts: str | None) -> re.Match | None:
        for t in texts:
            for m in matchers:
                found = m.search(t)
                if found:
                    return found
        return None

    w = await load_world(db)

    # 1. Entities whose names (or descriptions) match.
    groups = [g for g in w.groups.values() if hit(g.name, g.display_name)]
    families = [f for f in w.families.values() if hit(f.name, f.display_name)]
    families_by_desc = [f for f in w.families.values()
                        if f not in families and hit(f.description)]
    cats = [c for c in w.categories.values() if hit(c.name, c.display_name)]

    direct_ids: set[int] = {c.id for c in cats}
    for f in families:
        direct_ids |= {c.id for c in w.categories.values() if c.family_id == f.id}
    all_obs = await load_observations(db, date_range=date_range)
    obs_by_cat: dict[int, list[ObsRow]] = defaultdict(list)
    for r in all_obs:
        obs_by_cat[r.category_id].append(r)

    def total_for(ids: set[int]) -> int:
        return sum(r.minutes for cid in ids for r in obs_by_cat.get(cid, []))

    cat_groups: dict[str, list[Category]] = defaultdict(list)
    for c in cats:
        cat_groups[merge_key(c)].append(c)
    matched_categories = []
    for key, cs in cat_groups.items():
        ctx = w.cat_context(cs[0].id)
        sess = sorted({c.session_id for c in cs},
                      key=lambda sid: (w.sessions[sid].start_date or "") if sid in w.sessions else "")
        mins = total_for({c.id for c in cs})
        matched_categories.append({
            "name": cs[0].display_name or cs[0].name,
            "family": ctx["family"],
            "group": ctx["group"],
            "sessions": [session_label(w.sessions[s]) for s in sess if s in w.sessions],
            "minutes": mins,
            "time": hm(mins),
        })
    matched_families = []
    for f in families + families_by_desc:
        ids = {c.id for c in w.categories.values() if c.family_id == f.id}
        mins = total_for(ids)
        matched_families.append({
            "family_id": f.id,
            "name": w.fam_name(f),
            "group": w.grp_name(w.group_of_family(f)),
            "matched_on": "description" if f in families_by_desc else "name",
            "minutes": mins,
            "time": hm(mins),
        })

    direct_rows = [r for cid in direct_ids for r in obs_by_cat.get(cid, [])]
    direct = _time_summary(direct_rows, w) if direct_rows else None
    if direct and len(direct["by_month"]) > 24:
        # Multi-year families: by_session already tells the story compactly.
        del direct["by_month"]

    # 2. Mentions in free text.
    entries = await load_entries(db, date_range)
    narratives = await load_narratives(db, entries, date_range)
    mention_entries = []
    for e in entries:
        mt = hit(e.description, e.location)
        if mt:
            mention_entries.append((e, mt))
    mention_narr = []
    for n in narratives:
        mt = hit(n.text, n.location)
        if mt:
            mention_narr.append((n, mt))

    related_by_cat: dict[str, int] = defaultdict(int)
    related_total = 0
    for e, _ in mention_entries:
        if e.category_id not in direct_ids:
            related_by_cat[w.cat_name(e.category_id)] += e.minutes
            related_total += e.minutes
    mention_dates = sorted({e.date for e, _ in mention_entries} | {n.date for n, _ in mention_narr})

    timeline: list[dict] = []
    for e, _ in mention_entries:
        ctx = w.cat_context(e.category_id)
        timeline.append({
            "date": e.date,
            "source": e.kind,
            "category": ctx["category"],
            "family": ctx["family"],
            "minutes": e.minutes,
            "in_direct_category": e.category_id in direct_ids,
            "text": _clip(e.description or e.location, 500),
        })
    for n, mt in mention_narr:
        timeline.append({
            "date": n.date,
            "source": "daily_narrative",
            "category": None,
            "minutes": None,
            "text": snippet(n.text, mt, 360),
        })
    # Entries logged in a matching category but whose text doesn't repeat the
    # name are still part of the topic ("weekly meeting" under FinchesLab).
    seen = {(e.kind, e.id) for e, _ in mention_entries}
    for e in entries:
        if e.category_id in direct_ids and (e.kind, e.id) not in seen and e.description.strip():
            ctx = w.cat_context(e.category_id)
            timeline.append({
                "date": e.date,
                "source": e.kind,
                "category": ctx["category"],
                "family": ctx["family"],
                "minutes": e.minutes,
                "in_direct_category": True,
                "text": _clip(e.description, 500),
            })
    timeline.sort(key=lambda t: t["date"])
    total_timeline = len(timeline)
    if total_timeline > max_entries:
        # Keep the most recent ones; older activity is summarized by the stats.
        timeline = timeline[-max_entries:]

    result: dict[str, Any] = {
        "terms": terms,
        "date_range": date_range,
        "matched_groups": [{"name": w.grp_name(g)} for g in groups],
        "matched_families": matched_families,
        "matched_categories": matched_categories,
        "direct_time": direct,
        "mentions": {
            "entries": len(mention_entries),
            "daily_narratives": len(mention_narr),
            "days": len(mention_dates),
            "first_date": mention_dates[0] if mention_dates else None,
            "last_date": mention_dates[-1] if mention_dates else None,
            "related_minutes_in_other_categories": related_total,
            "related_time_in_other_categories": hm(related_total),
            "related_by_category": [
                {"category": k, "minutes": v, "time": hm(v)}
                for k, v in sorted(related_by_cat.items(), key=lambda kv: -kv[1])
            ],
        },
        "timeline_total": total_timeline,
        "timeline_returned": len(timeline),
        "timeline": timeline,
        "note": (
            "direct_time = minutes logged in matching categories/families. "
            "related_* = minutes of entries in OTHER categories whose text mentions the "
            "term; those minutes belong to their own category, so treat them as an upper "
            "bound on time spent on this topic. Daily narratives carry no per-topic minutes."
        ),
    }
    if total_timeline > len(timeline):
        result["timeline_note"] = (
            f"Showing the latest {len(timeline)} of {total_timeline}; narrow date_range "
            "or raise max_entries to see earlier ones."
        )
    hits = len(groups) + len(families) + len(families_by_desc) + len(cats) \
        + len(mention_entries) + len(mention_narr)
    if hits < 3:
        # Nothing (or almost nothing) found: the user may have misspelled the
        # name, or spelled it differently in their logs. Offer close spellings.
        vocab: set[str] = set()
        for e in entries:
            vocab.update(re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", e.description))
        for n in narratives:
            vocab.update(re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", n.text))
        suggestions: list[str] = []
        for t in terms:
            suggestions += close_names(t, _all_names(w) + sorted(vocab), n=8)
        if hits == 0:
            result["no_match"] = True
        result["did_you_mean"] = list(dict.fromkeys(suggestions))[:10]
    return result


async def tool_get_time_breakdown(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    group_by = args.get("group_by") or "family"
    bucket = args.get("bucket") or "total"
    top_n = max(1, min(int(args.get("top_n") or 25), 100))
    date_range = _valid_range(args.get("date_range"))

    # Resolve optional filters to a category-id allow-list.
    allowed: set[int] | None = None
    filter_desc: dict[str, list[str]] = {}
    unresolved: list[str] = []
    if args.get("groups") or args.get("families") or args.get("categories"):
        allowed = set()
        for gname in args.get("groups") or []:
            gs = resolve_groups(gname, w)
            if not gs:
                unresolved.append(f"group '{gname}'")
            gids = {g.id for g in gs}
            fids = {f.id for f in w.families.values() if f.group_id in gids}
            allowed |= {c.id for c in w.categories.values() if c.family_id in fids}
            filter_desc.setdefault("groups", []).extend(w.grp_name(g) for g in gs)
        for fname in args.get("families") or []:
            sc = resolve_scope({"family_name": fname}, w)
            if isinstance(sc, dict):
                unresolved.append(f"family '{fname}'")
                continue
            allowed |= sc.category_ids
            filter_desc.setdefault("families", []).append(sc.label)
        for cname in args.get("categories") or []:
            sc = resolve_scope({"category_name": cname}, w)
            if isinstance(sc, dict):
                unresolved.append(f"category '{cname}'")
                continue
            allowed |= sc.category_ids
            filter_desc.setdefault("categories", []).append(sc.label)
        if not allowed:
            return {"error": "None of the filters matched anything: " + ", ".join(unresolved),
                    "did_you_mean": close_names(" ".join(unresolved), _all_names(w))}

    rows = await load_observations(db, date_range=date_range,
                                   session_ids=args.get("session_ids"), category_ids=allowed)

    def key_of(r: ObsRow) -> str:
        if group_by == "none":
            return "Total"
        if group_by == "session":
            s = w.sessions.get(r.session_id)
            return session_label(s) if s else "?"
        if group_by == "category":
            return w.cat_name(r.category_id)
        fam = w.family_of(r.category_id)
        if group_by == "group":
            return w.grp_name(w.group_of_family(fam)) or "Unassigned"
        return w.fam_name(fam) or f"{w.cat_name(r.category_id)} (no family)"

    # Category labels merge case-insensitively across sessions.
    canon: dict[str, str] = {}
    totals: dict[str, int] = defaultdict(int)
    days_per: dict[str, set[str]] = defaultdict(set)
    series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_days: set[str] = set()
    total = 0
    for r in rows:
        raw = key_of(r)
        k = canon.setdefault(raw.strip().lower(), raw)
        totals[k] += r.minutes
        days_per[k].add(r.date)
        all_days.add(r.date)
        total += r.minutes
        if bucket != "total":
            series[_bucket(r.date, bucket)][k] += r.minutes

    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    shown = ranked[:top_n]
    out: dict[str, Any] = {
        "date_range": date_range,
        "session_ids": args.get("session_ids"),
        "filters": filter_desc or None,
        "group_by": group_by,
        "total_minutes": total,
        "total": hm(total),
        "active_days": len(all_days),
        "first_date": min(all_days) if all_days else None,
        "last_date": max(all_days) if all_days else None,
        "items": [
            {"name": k, "minutes": m, "time": hm(m),
             "share_pct": round(100 * m / total, 1) if total else 0,
             "active_days": len(days_per[k])}
            for k, m in shown
        ],
    }
    if len(ranked) > len(shown):
        rest = sum(m for _, m in ranked[len(shown):])
        out["other"] = {"items": len(ranked) - len(shown), "minutes": rest, "time": hm(rest)}
    if unresolved:
        out["unresolved_filters"] = unresolved
    if bucket != "total":
        if len(series) > 400:
            return {"error": f"{len(series)} {bucket} buckets is too many; use a coarser bucket "
                             "or a narrower date_range."}
        top_keys = [k for k, _ in shown[:8]]
        out["bucket"] = bucket
        out["series"] = []
        for period in sorted(series):
            vals = series[period]
            point: dict[str, Any] = {"period": period, "minutes": sum(vals.values())}
            if group_by != "none":
                point["by"] = {k: vals[k] for k in top_keys if vals.get(k)}
            out["series"].append(point)
        if group_by != "none" and len(ranked) > len(top_keys):
            out["series_note"] = f"Per-period breakdown lists the top {len(top_keys)} items only."
    if not rows:
        out["note"] = "No time logged for this selection."
    return out


async def tool_get_family_breakdown(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    scope = resolve_scope(args, w)
    if isinstance(scope, dict):
        return scope
    rows = await load_observations(db, date_range=args.get("date_range"),
                                   session_ids=args.get("session_ids"),
                                   category_ids=scope.category_ids)
    summary = _time_summary(rows, w)
    fam = scope.family
    result = {
        "scope": {
            "kind": scope.kind,
            "name": scope.label,
            "family_id": fam.id if fam else None,
            "family": w.fam_name(fam),
            "group": w.grp_name(w.group_of_family(fam)),
        },
        "date_range": _valid_range(args.get("date_range")),
        **summary,
    }
    # Compat: earlier clients/prompts read result["family"]["name"].
    result["family"] = {"id": fam.id if fam else None, "name": scope.label}
    if scope.note:
        result["note"] = scope.note
    return result


async def tool_get_group_breakdown(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    name = args.get("group_name") or ""
    gs = resolve_groups(name, w)
    if not gs:
        return {
            "error": f"No group named '{name}'.",
            "groups": [w.grp_name(g) for g in sorted(w.groups.values(), key=lambda g: g.position or 0)],
        }
    group = gs[0]
    fams = {f.id: f for f in w.families.values() if f.group_id == group.id}
    cat_ids = {c.id for c in w.categories.values() if c.family_id in fams}
    rows = await load_observations(db, date_range=args.get("date_range"),
                                   session_ids=args.get("session_ids"), category_ids=cat_ids)
    by_family: dict[int, int] = defaultdict(int)
    by_session: dict[int, int] = defaultdict(int)
    for r in rows:
        c = w.categories[r.category_id]
        by_family[c.family_id] += r.minutes
        by_session[r.session_id] += r.minutes
    total = sum(by_family.values())
    return {
        "group": {"id": group.id, "name": w.grp_name(group)},
        "date_range": _valid_range(args.get("date_range")),
        "total_minutes": total,
        "total": hm(total),
        "active_days": len({r.date for r in rows}),
        "by_family": [
            {"family_id": fid, "name": w.fam_name(fams.get(fid)), "minutes": m, "time": hm(m),
             "share_pct": round(100 * m / total, 1) if total else 0}
            for fid, m in sorted(by_family.items(), key=lambda kv: -kv[1])
        ],
        "by_session": [
            {"label": session_label(w.sessions[sid]), "minutes": m, "time": hm(m)}
            for sid, m in sorted(by_session.items(), key=lambda kv: -kv[1]) if sid in w.sessions
        ],
    }


async def tool_get_session_breakdown(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    sess = None
    if args.get("session_id"):
        sess = w.sessions.get(int(args["session_id"]))
    elif args.get("session_label"):
        needle = str(args["session_label"]).strip().lower()
        sess = next((s for s in w.sessions.values() if session_label(s).lower() == needle), None)
    if not sess:
        return {
            "error": f"Session {args.get('session_id') or args.get('session_label')} not found.",
            "sessions": [{"id": s.id, "label": session_label(s)} for s in w.sessions.values()],
        }
    by = args.get("by") or "family"
    rows = await load_observations(db, session_ids=[sess.id])
    totals: dict[str, int] = defaultdict(int)
    extra: dict[str, dict] = {}
    for r in rows:
        fam = w.family_of(r.category_id)
        grp = w.grp_name(w.group_of_family(fam))
        if by == "category":
            k = w.cat_name(r.category_id)
            extra[k] = {"family": w.fam_name(fam), "group": grp}
        elif by == "group":
            k = grp or "Unassigned"
        else:
            k = w.fam_name(fam) or f"{w.cat_name(r.category_id)} (no family)"
            extra[k] = {"group": grp}
        totals[k] += r.minutes
    total = sum(totals.values())
    days = sorted({r.date for r in rows})
    return {
        "session": {"id": sess.id, "label": session_label(sess), "is_active": bool(sess.is_active)},
        "by": by,
        "total_minutes": total,
        "total": hm(total),
        "active_days": len(days),
        "first_date": days[0] if days else None,
        "last_date": days[-1] if days else None,
        "items": [
            {"name": k, **extra.get(k, {}), "minutes": m, "time": hm(m),
             "share_pct": round(100 * m / total, 1) if total else 0}
            for k, m in sorted(totals.items(), key=lambda kv: -kv[1])
        ],
    }


async def tool_get_daily_breakdown(args: dict, db: AsyncSession) -> dict:
    d = (args.get("date") or "").strip()
    try:
        weekday = date_type.fromisoformat(d).strftime("%A")
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    w = await load_world(db)
    tz = await _user_tz(db)
    rows = await load_observations(db, date_range=[d, d])
    by_cat: dict[int, int] = defaultdict(int)
    for r in rows:
        by_cat[r.category_id] += r.minutes
    entries = await load_entries(db, [d, d])
    narratives = await load_narratives(db, entries, [d, d])
    brk = (await db.execute(select(BreakDay).where(BreakDay.date == d))).scalar_one_or_none()
    total = sum(by_cat.values())
    return {
        "date": d,
        "weekday": weekday,
        "break_day": (brk.label or "Break") if brk else None,
        "total_minutes": total,
        "total": hm(total),
        "by_category": [
            {**w.cat_context(cid), "minutes": m, "time": hm(m)}
            for cid, m in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "entries": [
            {
                "source": e.kind,
                "start": _local_hhmm(e.start_time, tz),
                "category": w.cat_name(e.category_id),
                "minutes": e.minutes,
                "description": e.description or None,
                "location": e.location,
            }
            for e in entries
        ],
        "narrative": [{"text": n.text, "location": n.location} for n in narratives],
    }


async def tool_search_text_entries(args: dict, db: AsyncSession) -> dict:
    keywords = [str(k).strip() for k in (args.get("keywords") or []) if str(k).strip()]
    matchers = [(k, TermMatcher(k)) for k in keywords]
    matchers = [(k, m) for k, m in matchers if m]
    if not matchers:
        return {"error": "Provide at least one keyword."}
    mode = "any" if str(args.get("mode", "all")).lower() == "any" else "all"
    limit = max(1, min(int(args.get("limit") or 40), 200))
    newest_first = str(args.get("sort") or "newest") != "oldest"
    date_range = _valid_range(args.get("date_range"))

    def check(*texts: str | None) -> tuple[list[str], re.Match | None] | None:
        hits: list[str] = []
        first: re.Match | None = None
        for k, m in matchers:
            found = None
            for t in texts:
                found = m.search(t)
                if found:
                    break
            if found:
                hits.append(k)
                first = first or found
        if (mode == "all" and len(hits) != len(matchers)) or not hits:
            return None
        return hits, first

    w = await load_world(db)
    entries = await load_entries(db, date_range)
    narratives = await load_narratives(db, entries, date_range)
    out: list[dict] = []
    minutes_by_cat: dict[str, int] = defaultdict(int)
    for e in entries:
        res = check(e.description, e.location)
        if not res:
            continue
        hits, mt = res
        ctx = w.cat_context(e.category_id)
        minutes_by_cat[ctx["category"]] += e.minutes
        out.append({
            "date": e.date,
            "source": e.kind,
            "category": ctx["category"],
            "family": ctx["family"],
            "minutes": e.minutes,
            "location": e.location,
            "matched": hits,
            "snippet": snippet(e.description or e.location or "", mt, 360),
        })
    for n in narratives:
        res = check(n.text, n.location)
        if not res:
            continue
        hits, mt = res
        out.append({
            "date": n.date,
            "source": "daily_narrative",
            "location": n.location,
            "matched": hits,
            "snippet": snippet(n.text, mt, 360),
        })
    out.sort(key=lambda x: x["date"], reverse=newest_first)
    total_minutes = sum(minutes_by_cat.values())
    return {
        "keywords": keywords,
        "mode": mode,
        "date_range": date_range,
        "total_matches": len(out),
        "returned": min(len(out), limit),
        "minutes_on_matching_entries": total_minutes,
        "time_on_matching_entries": hm(total_minutes),
        "minutes_by_category": [
            {"category": k, "minutes": v, "time": hm(v)}
            for k, v in sorted(minutes_by_cat.items(), key=lambda kv: -kv[1])
        ],
        "matches": out[:limit],
        # Compat with the chat UI's progress summary.
        "count": len(out),
    }


async def tool_summarize_text_in_range(args: dict, db: AsyncSession) -> dict:
    date_range = _valid_range(args.get("date_range"))
    if not date_range or not all(date_range):
        return {"error": "date_range [start, end] is required"}
    limit = max(1, min(int(args.get("limit") or 150), 400))
    w = await load_world(db)

    scope = None
    if args.get("family_name") or args.get("category_name") or args.get("family_id") is not None:
        scope = resolve_scope(args, w)
        if isinstance(scope, dict):
            return scope
    allowed = scope.category_ids if scope else None

    obs = await load_observations(db, date_range=date_range, category_ids=allowed)
    summary = _time_summary(obs, w)
    entries = await load_entries(db, date_range)
    records: list[dict] = []
    for e in entries:
        if allowed is not None and e.category_id not in allowed:
            continue
        if not e.description.strip():
            continue
        records.append({
            "date": e.date,
            "source": e.kind,
            "category": w.cat_name(e.category_id),
            "minutes": e.minutes,
            "location": e.location,
            "text": _clip(e.description, 800),
        })
    # Narratives are day-level, not per-category, so they're only included for
    # unscoped requests (with entry-description duplicates already stripped).
    if scope is None:
        for n in await load_narratives(db, entries, date_range):
            records.append({
                "date": n.date,
                "source": "daily_narrative",
                "location": n.location,
                "text": _clip(n.text, 1500),
            })
    records.sort(key=lambda r: r["date"])
    result: dict[str, Any] = {
        "date_range": date_range,
        "scope": {"name": scope.label, "kind": scope.kind} if scope else None,
        "time_summary": {
            "total_minutes": summary["total_minutes"],
            "total": summary["total"],
            "active_days": summary["active_days"],
            "by_category": summary["by_category"][:20],
        },
        "total_records": len(records),
        "returned_records": min(len(records), limit),
        "records": records[:limit],
        # Compat with older summaries.
        "total_entries": len(records),
        "returned_entries": min(len(records), limit),
    }
    if len(records) > limit:
        result["note"] = (f"Only the first {limit} of {len(records)} records (chronological) are "
                          "included; narrow date_range or raise limit for the rest.")
    return result


async def tool_list_sessions(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    stats_rows = (await db.execute(select(DailyRecord.session_id, DailyRecord.date,
                                          DailyRecord.total_minutes))).all()
    stats: dict[int, dict] = defaultdict(lambda: {"minutes": 0, "dates": []})
    for sid, d, mins in stats_rows:
        if (mins or 0) > 0:
            stats[sid]["minutes"] += int(mins)
            stats[sid]["dates"].append(d)
    live = {sid for (sid,) in (await db.execute(select(TimerEntry.session_id).distinct())).all()}
    live |= {sid for (sid,) in (await db.execute(select(ManualEntry.session_id).distinct())).all()}
    imported = {sid for (sid,) in (await db.execute(
        select(DailyRecord.session_id).join(Observation, Observation.daily_record_id == DailyRecord.id)
        .where(Observation.source == "import").distinct()
    )).all()}

    sessions = list(w.sessions.values())
    if args.get("year") is not None:
        sessions = [s for s in sessions if s.year == int(args["year"])]
    if args.get("season"):
        sessions = [s for s in sessions if s.season == args["season"]]
    if args.get("active_only"):
        sessions = [s for s in sessions if s.is_active]
    sessions.sort(key=lambda s: (s.year, SEASON_ORDER.get(s.season, 0)), reverse=True)

    out = []
    for s in sessions:
        st = stats.get(s.id, {"minutes": 0, "dates": []})
        dates = sorted(st["dates"])
        mode = ("imported + live" if s.id in live and s.id in imported
                else "live" if s.id in live else "imported" if s.id in imported else "empty")
        out.append({
            "id": s.id,
            "label": session_label(s),
            "year": s.year,
            "season": s.season,
            "is_active": bool(s.is_active),
            "configured_range": [s.start_date, s.end_date],
            "first_logged": dates[0] if dates else None,
            "last_logged": dates[-1] if dates else None,
            "days_logged": len(dates),
            "total_minutes": st["minutes"],
            "total": hm(st["minutes"]),
            "tracking": mode,
        })
    return {"sessions": out, "count": len(out)}


async def tool_list_families(args: dict, db: AsyncSession) -> dict:
    w = await load_world(db)
    fams = list(w.families.values())
    if args.get("group_name"):
        gs = resolve_groups(args["group_name"], w)
        if not gs:
            return {"families": [], "count": 0, "warning": f"No group named '{args['group_name']}'"}
        gids = {g.id for g in gs}
        fams = [f for f in fams if f.group_id in gids]
    if args.get("session_id"):
        sid = int(args["session_id"])
        in_session = {c.family_id for c in w.categories.values() if c.session_id == sid}
        fams = [f for f in fams if f.id in in_session]
    totals: dict[int, int] = defaultdict(int)
    for r in await load_observations(db):
        c = w.categories.get(r.category_id)
        if c and c.family_id:
            totals[c.family_id] += r.minutes
    out = []
    for f in sorted(fams, key=lambda f: -totals.get(f.id, 0)):
        cats = [c for c in w.categories.values() if c.family_id == f.id]
        out.append({
            "id": f.id,
            "name": f.name,
            "display_name": f.display_name,
            "group": w.grp_name(w.group_of_family(f)),
            "description": f.description,
            "category_names": sorted({c.display_name or c.name for c in cats}),
            "category_count": len(cats),
            "total_minutes": totals.get(f.id, 0),
            "total": hm(totals.get(f.id, 0)),
        })
    return {"families": out, "count": len(out)}


TOOL_EXECUTORS: dict[str, Callable[[dict, AsyncSession], Awaitable[dict]]] = {
    "find_topic": tool_find_topic,
    "get_time_breakdown": tool_get_time_breakdown,
    "get_family_breakdown": tool_get_family_breakdown,
    "get_group_breakdown": tool_get_group_breakdown,
    "get_session_breakdown": tool_get_session_breakdown,
    "get_daily_breakdown": tool_get_daily_breakdown,
    "search_text_entries": tool_search_text_entries,
    "summarize_text_in_range": tool_summarize_text_in_range,
    "list_sessions": tool_list_sessions,
    "list_families": tool_list_families,
}


async def execute_tool(name: str, args: dict, db: AsyncSession) -> dict:
    fn = TOOL_EXECUTORS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await fn(args or {}, db)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Tool {name} failed: {type(e).__name__}: {e!s}"}
