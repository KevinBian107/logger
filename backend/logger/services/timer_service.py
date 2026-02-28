"""Timer lifecycle management."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import TimerEntry
from logger.services.observation_service import upsert_observation, upsert_text_entry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def start_timer(
    session_id: int, category_id: int, db: AsyncSession
) -> TimerEntry:
    now = _now_iso()
    today = _now().strftime("%Y-%m-%d")
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

    # Upsert observation
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


async def discard_timer(timer_id: int, db: AsyncSession) -> None:
    timer = await db.get(TimerEntry, timer_id)
    if not timer:
        raise ValueError("Timer not found")
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
