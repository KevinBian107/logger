"""Timer lifecycle management."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import Category, Setting, TimerEntry
from logger.services.observation_service import (
    upsert_observation,
    upsert_text_entry,
    subtract_observation,
)


DEFAULT_TIMEZONE = "America/Los_Angeles"


async def _user_tz(db: AsyncSession) -> str:
    """Read the user's chosen timezone from settings, default to LA."""
    result = await db.execute(select(Setting).where(Setting.key == "timezone"))
    row = result.scalar_one_or_none()
    return (row.value if row else None) or DEFAULT_TIMEZONE


def _iso_to_local_date(iso_str: str, tz_name: str) -> str:
    """ISO-8601 timestamp → YYYY-MM-DD in the named IANA timezone.

    The DB stores timestamps in UTC; the user wants date-bucketing in their
    local timezone. Stop-time of 23:50 PDT May 26 = 06:50 UTC May 27, and the
    entry belongs to May 26 in the user's view.
    """
    if not iso_str:
        return ""
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except (ValueError, KeyError):
        return ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def start_timer(
    session_id: int, category_id: int, db: AsyncSession
) -> TimerEntry:
    now = _now_iso()
    tz_name = await _user_tz(db)
    today = _iso_to_local_date(now, tz_name)
    timer = TimerEntry(
        session_id=session_id,
        category_id=category_id,
        date=today,
        start_time=now,
        is_active=True,
        is_paused=False,
        total_paused_seconds=0,
    )
    db.add(timer)
    await db.flush()
    return timer


async def pause_timer(timer_id: int, db: AsyncSession) -> TimerEntry:
    timer = await db.get(TimerEntry, timer_id)
    if not timer or not timer.is_active:
        raise ValueError("Timer not found or not active")
    if timer.is_paused:
        raise ValueError("Timer already paused")

    timer.is_paused = True
    timer.pause_start = _now_iso()
    timer.updated_at = _now_iso()
    await db.flush()
    return timer


async def resume_timer(timer_id: int, db: AsyncSession) -> TimerEntry:
    timer = await db.get(TimerEntry, timer_id)
    if not timer or not timer.is_active:
        raise ValueError("Timer not found or not active")
    if not timer.is_paused:
        raise ValueError("Timer not paused")

    pause_start = datetime.fromisoformat(timer.pause_start)
    pause_duration = (_now() - pause_start).total_seconds()
    timer.total_paused_seconds = (timer.total_paused_seconds or 0) + int(pause_duration)
    timer.is_paused = False
    timer.pause_start = None
    timer.updated_at = _now_iso()
    await db.flush()
    return timer


async def stop_timer(
    timer_id: int,
    description: str | None,
    location: str | None,
    db: AsyncSession,
    override_date: str | None = None,
) -> TimerEntry:
    timer = await db.get(TimerEntry, timer_id)
    if not timer or not timer.is_active:
        raise ValueError("Timer not found or not active")

    now = _now()

    # If paused, account for current pause duration
    paused_seconds = timer.total_paused_seconds or 0
    if timer.is_paused and timer.pause_start:
        pause_start = datetime.fromisoformat(timer.pause_start)
        paused_seconds += int((now - pause_start).total_seconds())

    # Calculate duration
    start_time = datetime.fromisoformat(timer.start_time)
    elapsed_seconds = (now - start_time).total_seconds() - paused_seconds
    duration_minutes = max(1, round(elapsed_seconds / 60))

    timer.end_time = now.isoformat()
    timer.duration_minutes = duration_minutes
    timer.total_paused_seconds = paused_seconds
    timer.is_active = False
    timer.is_paused = False
    timer.pause_start = None
    timer.description = description
    timer.location = location
    timer.updated_at = now.isoformat()

    # Late-night date override: lets the user attribute a timer that crossed
    # (or was started after) midnight to "yesterday" instead of the wall-clock
    # date the timer was originally tagged with.
    if override_date and override_date != timer.date:
        timer.date = override_date

    # Upsert observation under the (possibly overridden) date
    await upsert_observation(
        session_id=timer.session_id,
        category_id=timer.category_id,
        date=timer.date,
        minutes=duration_minutes,
        source="timer",
        db=db,
    )

    # Upsert text entry
    await upsert_text_entry(
        session_id=timer.session_id,
        date=timer.date,
        description=description,
        location=location,
        db=db,
    )

    await db.flush()
    return timer


async def update_timer_entry(
    timer_id: int,
    db: AsyncSession,
    *,
    category_id: int | None = None,
    date: str | None = None,
    duration_minutes: int | None = None,
    description: str | None = None,
    location: str | None = None,
) -> TimerEntry:
    """Edit a stopped timer entry. Re-balances observations if (date, category,
    duration) changes — subtracts the old aggregate, then adds the new one.

    Active (un-stopped) timers can't be edited; stop them first.
    None means "don't change this field".
    """
    timer = await db.get(TimerEntry, timer_id)
    if not timer:
        raise ValueError("Timer not found")
    if timer.is_active:
        raise ValueError("Cannot edit an active timer — stop it first")

    old_date = timer.date
    old_cat = timer.category_id
    old_mins = timer.duration_minutes or 0

    if category_id is not None and category_id != timer.category_id:
        cat = await db.get(Category, category_id)
        if not cat or cat.session_id != timer.session_id:
            raise ValueError("Category not found or not in this session")
        timer.category_id = category_id

    if date is not None:
        timer.date = date
    if duration_minutes is not None:
        if duration_minutes < 1:
            raise ValueError("duration_minutes must be >= 1")
        timer.duration_minutes = duration_minutes
    if description is not None:
        timer.description = description or None
    if location is not None:
        timer.location = location or None

    new_mins = timer.duration_minutes or 0
    # Rebalance observations if any key field changed
    if (timer.date != old_date) or (timer.category_id != old_cat) or (new_mins != old_mins):
        if old_mins > 0:
            await subtract_observation(
                session_id=timer.session_id,
                category_id=old_cat,
                date=old_date,
                minutes=old_mins,
                db=db,
            )
        if new_mins > 0:
            await upsert_observation(
                session_id=timer.session_id,
                category_id=timer.category_id,
                date=timer.date,
                minutes=new_mins,
                source="timer",
                db=db,
            )

    timer.updated_at = _now_iso()
    await db.flush()
    return timer


async def discard_timer(timer_id: int, db: AsyncSession) -> None:
    timer = await db.get(TimerEntry, timer_id)
    if not timer:
        raise ValueError("Timer not found")

    # If completed, subtract its minutes from the observation
    if not timer.is_active and timer.duration_minutes:
        from logger.services.observation_service import subtract_observation
        await subtract_observation(
            session_id=timer.session_id,
            category_id=timer.category_id,
            date=timer.date,
            minutes=timer.duration_minutes,
            db=db,
        )

    await db.delete(timer)
    await db.flush()


async def get_active_timers(session_id: int, db: AsyncSession) -> list[TimerEntry]:
    result = await db.execute(
        select(TimerEntry).where(
            TimerEntry.session_id == session_id,
            TimerEntry.is_active == True,
        ).order_by(TimerEntry.start_time.desc())
    )
    return list(result.scalars().all())


async def realign_timer_dates_to_user_tz(db: AsyncSession) -> dict:
    """For each stopped timer, recompute its `date` from start_time in the user's
    timezone. If the stored date is wrong (UTC-derived from a prior build), fix it
    and rebalance the aggregated observation (subtract from old date, add to new).

    Idempotent: only touches rows where the recomputed date differs.
    """
    tz_name = await _user_tz(db)

    timers_q = await db.execute(
        select(TimerEntry).where(TimerEntry.is_active == False)  # noqa: E712
    )
    fixed = 0
    for t in timers_q.scalars().all():
        if not t.start_time:
            continue
        correct = _iso_to_local_date(t.start_time, tz_name)
        if not correct or correct == t.date:
            continue

        old_date = t.date
        # Move the aggregate to the correct day
        if t.duration_minutes and t.duration_minutes > 0:
            await subtract_observation(
                session_id=t.session_id,
                category_id=t.category_id,
                date=old_date,
                minutes=t.duration_minutes,
                db=db,
            )
            await upsert_observation(
                session_id=t.session_id,
                category_id=t.category_id,
                date=correct,
                minutes=t.duration_minutes,
                source="timer",
                db=db,
            )

        t.date = correct
        fixed += 1

    if fixed:
        await db.commit()
    return {"timers_realigned": fixed}


async def get_timers_for_date(
    session_id: int, date: str, db: AsyncSession
) -> list[TimerEntry]:
    result = await db.execute(
        select(TimerEntry).where(
            TimerEntry.session_id == session_id,
            TimerEntry.date == date,
            TimerEntry.is_active == False,
        ).order_by(TimerEntry.end_time.desc())
    )
    return list(result.scalars().all())
