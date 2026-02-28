from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import (
    Session, DailyRecord, Observation, TimerEntry, ManualEntry, Category,
)
from logger.schemas import (
    DailyActivityResponse, TimerEntryResponse, ManualEntryResponse,
    ObservationResponse, StreakResponse,
)

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("/{date}", response_model=DailyActivityResponse)
async def get_daily_activity(date: str, db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(db)
    if not session:
        raise HTTPException(status_code=400, detail="No active session")

    # Daily record + observations
    dr_result = await db.execute(
        select(DailyRecord).where(
            DailyRecord.session_id == session.id,
            DailyRecord.date == date,
        )
    )
    daily_record = dr_result.scalar_one_or_none()

    observations = []
    total_minutes = 0
    if daily_record:
        total_minutes = daily_record.total_minutes
        obs_result = await db.execute(
            select(Observation).where(
                Observation.daily_record_id == daily_record.id
            )
        )
        for obs in obs_result.scalars().all():
            cat = await db.get(Category, obs.category_id)
            observations.append(ObservationResponse(
                id=obs.id,
                category_id=obs.category_id,
                category_name=cat.display_name or cat.name if cat else None,
                minutes=obs.minutes,
                source=obs.source,
            ))

    # Completed timer entries for this date
    timer_result = await db.execute(
        select(TimerEntry).where(
            TimerEntry.session_id == session.id,
            TimerEntry.date == date,
            TimerEntry.is_active == False,
        ).order_by(TimerEntry.end_time.desc())
    )
    timer_entries = []
    for t in timer_result.scalars().all():
        cat = await db.get(Category, t.category_id)
        timer_entries.append(TimerEntryResponse(
            id=t.id,
            session_id=t.session_id,
            category_id=t.category_id,
            category_name=cat.display_name or cat.name if cat else None,
            date=t.date,
            start_time=t.start_time,
            end_time=t.end_time,
            pause_start=t.pause_start,
            total_paused_seconds=t.total_paused_seconds or 0,
            duration_minutes=t.duration_minutes,
            is_active=t.is_active,
            is_paused=t.is_paused,
            description=t.description,
            location=t.location,
        ))

    # Manual entries for this date
    manual_result = await db.execute(
        select(ManualEntry).where(
            ManualEntry.session_id == session.id,
            ManualEntry.date == date,
        ).order_by(ManualEntry.created_at.desc())
    )
    manual_entries = []
    for m in manual_result.scalars().all():
        cat = await db.get(Category, m.category_id)
        manual_entries.append(ManualEntryResponse(
            id=m.id,
            session_id=m.session_id,
            category_id=m.category_id,
            category_name=cat.display_name or cat.name if cat else None,
            date=m.date,
            duration_minutes=m.duration_minutes,
            description=m.description,
            location=m.location,
            created_at=m.created_at,
        ))

    return DailyActivityResponse(
        date=date,
        total_minutes=total_minutes,
        timer_entries=timer_entries,
        manual_entries=manual_entries,
        observations=observations,
    )


@router.get("/streak/current", response_model=StreakResponse)
async def get_streak(db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(db)
    if not session:
        return StreakResponse(current=0, longest=0)

    # Get all dates with logged time, ordered
    result = await db.execute(
        select(DailyRecord.date)
        .where(
            DailyRecord.session_id == session.id,
            DailyRecord.total_minutes > 0,
        )
        .order_by(DailyRecord.date.desc())
    )
    dates = [date_type.fromisoformat(row[0]) for row in result.all()]

    if not dates:
        return StreakResponse(current=0, longest=0)

    # Current streak: consecutive days walking back from today
    today = date_type.today()
    current = 0
    check_date = today
    date_set = set(dates)

    while check_date in date_set:
        current += 1
        check_date -= timedelta(days=1)

    # If today has no entry but yesterday did, check from yesterday
    if current == 0:
        check_date = today - timedelta(days=1)
        while check_date in date_set:
            current += 1
            check_date -= timedelta(days=1)

    # Longest streak across all dates
    sorted_dates = sorted(dates)
    longest = 0
    streak = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            streak += 1
        else:
            longest = max(longest, streak)
            streak = 1
    longest = max(longest, streak)

    return StreakResponse(current=current, longest=longest)


async def _get_active_session(db: AsyncSession) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.is_active == True)
    )
    return result.scalar_one_or_none()
