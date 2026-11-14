"""Compact "data catalog" injected into the chat system prompt.

Without it Claude starts every question blind: it doesn't know today's date
(so "last week" is unresolvable), which sessions exist, or that "FinchesLab"
is a category under the AI4Science family. Spending ~2-3k tokens on a map of
the hierarchy lets it pick the right tool and names on the first try, and
answer simple all-time questions straight from the catalog.

The catalog is rebuilt per chat turn (it's cheap: one pass over a small DB)
and is identical across the tool-loop iterations of that turn, so it sits in
the cached system-prompt prefix.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import ManualEntry, Observation, DailyRecord, TimerEntry
from logger.services.chat_tools_service import (
    SEASON_ORDER, World, hm, load_observations, load_world, merge_key, session_label,
)
from logger.services.timer_service import _user_tz

_SEASON_ABBR = {"winter": "W", "spring": "Sp", "summer": "Su", "fall": "F"}


def _abbr(w: World, sid: int) -> str:
    s = w.sessions.get(sid)
    if not s:
        return "?"
    return f"{_SEASON_ABBR.get(s.season, s.season[:2].title())}{str(s.year)[-2:]}"


def _session_sort_key(w: World, sid: int):
    s = w.sessions.get(sid)
    return (s.year, SEASON_ORDER.get(s.season, 0)) if s else (0, 0)


async def build_data_catalog(db: AsyncSession) -> str:
    tz_name = await _user_tz(db)
    now = datetime.now(ZoneInfo(tz_name))
    w = await load_world(db)
    obs = await load_observations(db)

    sess_minutes: dict[int, int] = defaultdict(int)
    sess_dates: dict[int, set[str]] = defaultdict(set)
    cat_minutes: dict[int, int] = defaultdict(int)
    for r in obs:
        sess_minutes[r.session_id] += r.minutes
        sess_dates[r.session_id].add(r.date)
        cat_minutes[r.category_id] += r.minutes

    live = {sid for (sid,) in (await db.execute(select(TimerEntry.session_id).distinct())).all()}
    live |= {sid for (sid,) in (await db.execute(select(ManualEntry.session_id).distinct())).all()}
    imported = {sid for (sid,) in (await db.execute(
        select(DailyRecord.session_id).join(Observation, Observation.daily_record_id == DailyRecord.id)
        .where(Observation.source == "import").distinct()
    )).all()}

    lines: list[str] = []
    lines.append("# Data catalog (generated from the database for this conversation turn)")
    lines.append(f"Today: {now.strftime('%A, %Y-%m-%d')} ({tz_name}).")
    active = [s for s in w.sessions.values() if s.is_active]
    if active:
        a = active[0]
        lines.append(f"Active session: {session_label(a)} (id {a.id}), configured "
                     f"{a.start_date} to {a.end_date}.")
    total_all = sum(sess_minutes.values())
    lines.append(f"All-time total: {hm(total_all)} across {len(w.sessions)} sessions.")

    lines.append("")
    lines.append("## Sessions (newest first)")
    lines.append("id | label | abbr | first-last logged day | days | total | data")
    for s in sorted(w.sessions.values(), key=lambda s: (s.year, SEASON_ORDER.get(s.season, 0)),
                    reverse=True):
        dates = sorted(sess_dates.get(s.id, ()))
        span = f"{dates[0]} to {dates[-1]}" if dates else "nothing logged"
        mode = ("imported + live" if s.id in live and s.id in imported
                else "live" if s.id in live else "imported" if s.id in imported else "-")
        flag = " [ACTIVE]" if s.is_active else ""
        lines.append(f"{s.id} | {session_label(s)}{flag} | {_abbr(w, s.id)} | {span} | "
                     f"{len(dates)} | {hm(sess_minutes.get(s.id, 0))} | {mode}")
    lines.append("Data: 'imported' = per-category daily minutes + one free-text narrative per day "
                 "(older CSV data). 'live' = individual timer/manual entries with descriptions.")

    # Merge same-named categories across sessions: name -> sessions + minutes.
    def merged(cat_ids: list[int]) -> list[tuple[str, list[int], int]]:
        by_key: dict[str, dict] = {}
        for cid in cat_ids:
            c = w.categories[cid]
            d = by_key.setdefault(merge_key(c), {"name": c.display_name or c.name,
                                                 "sessions": set(), "minutes": 0})
            d["sessions"].add(c.session_id)
            d["minutes"] += cat_minutes.get(cid, 0)
        out = [(d["name"], sorted(d["sessions"], key=lambda sid: _session_sort_key(w, sid)),
                d["minutes"]) for d in by_key.values()]
        return sorted(out, key=lambda t: -t[2])

    def fmt_cats(cat_ids: list[int]) -> str:
        parts = []
        for name, sids, mins in merged(cat_ids):
            sess = ", ".join(_abbr(w, sid) for sid in sids)
            parts.append(f"{name} [{sess}] {hm(mins)}")
        return "; ".join(parts)

    cats_by_family: dict[int | None, list[int]] = defaultdict(list)
    for c in w.categories.values():
        cats_by_family[c.family_id if c.family_id in w.families else None].append(c.id)
    fam_minutes = {fid: sum(cat_minutes.get(cid, 0) for cid in cids)
                   for fid, cids in cats_by_family.items()}

    lines.append("")
    lines.append("## Projects: Group > Family (family_id, all-time total) — categories "
                 "[sessions they appear in] total")
    lines.append("Session abbreviations: W=Winter, Sp=Spring, Su=Summer, F=Fall + 2-digit year "
                 "(F26 = Fall 2026).")
    fams_by_group: dict[int | None, list] = defaultdict(list)
    for f in w.families.values():
        fams_by_group[f.group_id if f.group_id in w.groups else None].append(f)
    ordered_groups = sorted(w.groups.values(), key=lambda g: (g.position or 0, g.id))
    for g in ordered_groups + [None]:
        fams = fams_by_group.get(g.id if g else None, [])
        fams = [f for f in fams if cats_by_family.get(f.id)]
        if not fams:
            continue
        gtotal = sum(fam_minutes.get(f.id, 0) for f in fams)
        lines.append(f"### {(g.display_name or g.name) if g else 'No group'} ({hm(gtotal)})")
        for f in sorted(fams, key=lambda f: -fam_minutes.get(f.id, 0)):
            desc = f" — {f.description.strip()}" if (f.description or "").strip() else ""
            lines.append(f"- {f.display_name or f.name} (id {f.id}, {hm(fam_minutes.get(f.id, 0))})"
                         f"{desc}: {fmt_cats(cats_by_family[f.id])}")
    if cats_by_family.get(None):
        lines.append("### Categories not linked to any family")
        lines.append(f"- {fmt_cats(cats_by_family[None])}")
    return "\n".join(lines)
