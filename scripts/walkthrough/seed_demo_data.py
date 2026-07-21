"""Seed a throwaway demo database for capturing walkthrough screenshots/video.

Run against a scratch DB via LOGGER_DB_PATH -- never the real dev DB:

    LOGGER_DB_PATH=/path/to/scratch/walkthrough.db uv run --project backend \\
        python scripts/walkthrough/seed_demo_data.py

Creates a fake "Spring 2026" active session with three categories and ~8
weeks of plausible history (source="import"), a couple of scene-setting
plan items, and a couple of break days -- entirely synthetic, no real logged
hours. Today itself is left with zero logged time on purpose, so the live
capture (starting/stopping a real timer) has a clean before/after.

Also copies the anthropic_api_key setting from the real dev DB (if present)
so the live chat step in the walkthrough can make a real API call -- the raw
key is never decoded here, just the obfuscated blob is copied row to row.
"""
import asyncio
import math
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import select  # noqa: E402

from logger.database import init_db, async_session, DB_PATH  # noqa: E402
from logger.models import Session, Category, CategoryFamily, CategoryGroup, BreakDay, PlanItem  # noqa: E402
from logger.services.observation_service import upsert_observation  # noqa: E402
from logger.services.group_service import seed_default_groups  # noqa: E402
from logger.services.family_service import seed_default_families_and_rules  # noqa: E402

REAL_DEV_DB = Path(__file__).resolve().parents[2] / "logger.db"

# category display name -> (family display name, default group slug)
# Linked to real families/groups so the chat's group/family-breakdown tools
# (and the Projects tab) have something real to walk, not orphaned categories.
CATEGORIES = {
    "Research": ("Demo Research", "research"),
    "Course Work": ("Demo Coursework", "courses"),
    "Personal Project": ("Demo Project", "personal"),
}
WEEKS = 8
BREAK_OFFSETS_DAYS_AGO = [11, 12, 33]  # a short break + one scattered rest day


async def main() -> None:
    await init_db()
    async with async_session() as db:
        await seed_default_groups(db)
        await seed_default_families_and_rules(db)
        await db.commit()

        session = Session(year=2026, season="spring", label="Spring 2026", is_active=True)
        db.add(session)
        await db.flush()

        category_ids: dict[str, int] = {}
        for name, (family_display, group_slug) in CATEGORIES.items():
            group = (await db.execute(select(CategoryGroup).where(CategoryGroup.name == group_slug))).scalar_one()
            family = CategoryFamily(
                name=family_display.lower().replace(" ", "_"),
                display_name=family_display,
                group_id=group.id,
                color=group.color,
            )
            db.add(family)
            await db.flush()

            cat = Category(
                session_id=session.id, name=name.lower().replace(" ", "_"), display_name=name,
                family_id=family.id,
            )
            db.add(cat)
            await db.flush()
            category_ids[name] = cat.id

        today = date.today()
        start = today - timedelta(days=WEEKS * 7)
        break_dates = {today - timedelta(days=o) for o in BREAK_OFFSETS_DAYS_AGO}
        for d in break_dates:
            db.add(BreakDay(date=d.isoformat(), label="Rest"))

        d = start
        while d < today:  # stop before today -- today stays clean for the live demo
            if d not in break_dates:
                is_weekday = d.weekday() < 5
                weeks_in = (d - start).days / 7
                ramp = min(1.0, weeks_in / 2)  # ramp up over the first ~2 weeks
                wave = 0.5 + 0.5 * math.sin(weeks_in * 0.9 + d.toordinal() * 0.3)
                base = (90 + wave * 90) if is_weekday else (20 + wave * 60)
                total = int(ramp * base)
                if total > 5:
                    names = ["Research", "Course Work"] if is_weekday else ["Personal Project"]
                    per = total // len(names)
                    if per > 0:
                        for name in names:
                            await upsert_observation(
                                session_id=session.id, category_id=category_ids[name],
                                date=d.isoformat(), minutes=per, source="import", db=db,
                            )
            d += timedelta(days=1)

        # Scene-setting plan items already on the timeline before the live
        # "drag to create" demo adds a new one alongside them.
        db.add(PlanItem(
            title="Draft quarterly review", category_id=category_ids["Research"],
            start_date=(today + timedelta(days=2)).isoformat(),
            end_date=(today + timedelta(days=2)).isoformat(),
            status="planned", importance="medium",
        ))
        db.add(PlanItem(
            title="Problem set 4", category_id=category_ids["Course Work"],
            start_date=(today + timedelta(days=4)).isoformat(),
            end_date=(today + timedelta(days=5)).isoformat(),
            status="planned", importance="low",
        ))

        await db.commit()

    if REAL_DEV_DB.exists():
        src = sqlite3.connect(str(REAL_DEV_DB))
        row = src.execute("SELECT value FROM settings WHERE key='anthropic_api_key'").fetchone()
        src.close()
        if row:
            dst = sqlite3.connect(str(DB_PATH))
            dst.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('anthropic_api_key', ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (row[0],),
            )
            dst.commit()
            dst.close()
            print("Copied API key setting from the real dev DB (blob only, never decoded).")
        else:
            print("WARNING: no anthropic_api_key found in the real dev DB -- the chat step will need a key set manually.")

    print(f"Seeded demo DB at {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
