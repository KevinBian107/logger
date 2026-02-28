"""Regex/keyword query parser for chat messages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import CategoryFamily


SEASON_MAP: dict[str, str] = {
    "fall": "fall", "autumn": "fall", "f": "fall",
    "winter": "winter", "w": "winter",
    "spring": "spring", "s": "spring",
    "summer": "summer", "u": "summer",
}

QUERY_TYPE_KEYWORDS: dict[str, list[str]] = {
    "comparison": ["compare", "comparison", "versus", "vs", "difference between", "differences"],
    "trend": ["trend", "over time", "progression", "growth", "change", "evolve"],
    "summary": ["summary", "summarize", "overview", "what was", "what did", "how much", "total"],
    "detail": ["detail", "breakdown", "specific", "drill", "deep dive", "daily"],
}


@dataclass
class SessionFilter:
    year: int | None = None
    season: str | None = None


@dataclass
class ParsedQuery:
    raw_query: str
    session_filters: list[SessionFilter] = field(default_factory=list)
    family_keywords: list[str] = field(default_factory=list)
    query_type: str = "general"
    date_range: tuple[str | None, str | None] = (None, None)
    mentions_all_time: bool = False


async def parse_query(query: str, db: AsyncSession) -> ParsedQuery:
    """Parse a user chat query into structured filters."""
    q = query.lower()
    parsed = ParsedQuery(raw_query=query)

    # ── Extract years ──
    years = [int(m) for m in re.findall(r"\b(20\d{2})\b", q)]

    # ── Extract seasons ──
    seasons: list[str] = []
    for word, canonical in SEASON_MAP.items():
        # Match whole words only for short abbreviations
        if len(word) <= 1:
            continue
        if re.search(rf"\b{re.escape(word)}\b", q):
            if canonical not in seasons:
                seasons.append(canonical)

    # ── Build session filters ──
    if years and seasons:
        for year in years:
            for season in seasons:
                parsed.session_filters.append(SessionFilter(year=year, season=season))
    elif years:
        for year in years:
            parsed.session_filters.append(SessionFilter(year=year))
    elif seasons:
        for season in seasons:
            parsed.session_filters.append(SessionFilter(season=season))

    # ── Extract family keywords ──
    result = await db.execute(select(CategoryFamily.name))
    family_names = [row[0] for row in result.all()]
    for fname in family_names:
        if re.search(rf"\b{re.escape(fname)}\b", q):
            parsed.family_keywords.append(fname)

    # ── Determine query type ──
    for qtype, keywords in QUERY_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                parsed.query_type = qtype
                break
        if parsed.query_type != "general":
            break

    # ── Date range patterns ──
    # "last month", "last week", "past N months"
    if "all time" in q or "all-time" in q or "ever" in q:
        parsed.mentions_all_time = True

    month_match = re.search(r"(?:last|past)\s+(\d+)\s+months?", q)
    if month_match:
        from datetime import date, timedelta
        n = int(month_match.group(1))
        today = date.today()
        start = today - timedelta(days=n * 30)
        parsed.date_range = (start.isoformat(), today.isoformat())
    elif "last month" in q:
        from datetime import date, timedelta
        today = date.today()
        start = today.replace(day=1) - timedelta(days=1)
        start = start.replace(day=1)
        end = today.replace(day=1) - timedelta(days=1)
        parsed.date_range = (start.isoformat(), end.isoformat())
    elif "last week" in q:
        from datetime import date, timedelta
        today = date.today()
        start = today - timedelta(days=7)
        parsed.date_range = (start.isoformat(), today.isoformat())

    return parsed
