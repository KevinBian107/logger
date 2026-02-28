"""Shared observation and text entry upsert logic."""

from datetime import date as date_type

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import DailyRecord, Observation, TextEntry


async def upsert_observation(
    session_id: int,
    category_id: int,
    date: str,
    minutes: int,
    source: str,
    db: AsyncSession,
) -> Observation:
    """Add minutes to the observation for (session, category, date), creating records as needed."""
    # Get or create daily_record
    dr_result = await db.execute(
        select(DailyRecord).where(
            DailyRecord.session_id == session_id,
            DailyRecord.date == date,
        )
    )
    daily_record = dr_result.scalar_one_or_none()

    if not daily_record:
        dt = date_type.fromisoformat(date)
        daily_record = DailyRecord(
            session_id=session_id,
            date=date,
            day_of_week=dt.strftime("%a"),
            week_number=dt.isocalendar()[1],
            total_minutes=0,
        )
        db.add(daily_record)
        await db.flush()

    # Get or create observation
    obs_result = await db.execute(
        select(Observation).where(
            Observation.daily_record_id == daily_record.id,
            Observation.category_id == category_id,
        )
    )
    observation = obs_result.scalar_one_or_none()

    if observation:
        observation.minutes += minutes
        if source != "import":
            observation.source = source
    else:
        observation = Observation(
            daily_record_id=daily_record.id,
            category_id=category_id,
            minutes=minutes,
            source=source,
        )
        db.add(observation)

    # Recalculate daily total
    await db.flush()
    total_result = await db.execute(
        select(func.coalesce(func.sum(Observation.minutes), 0)).where(
            Observation.daily_record_id == daily_record.id
        )
    )
    daily_record.total_minutes = total_result.scalar()

    return observation


async def subtract_observation(
    session_id: int,
    category_id: int,
    date: str,
    minutes: int,
    db: AsyncSession,
) -> None:
    """Subtract minutes from an observation, deleting it if zero or negative."""
    dr_result = await db.execute(
        select(DailyRecord).where(
            DailyRecord.session_id == session_id,
            DailyRecord.date == date,
        )
    )
    daily_record = dr_result.scalar_one_or_none()
    if not daily_record:
        return

    obs_result = await db.execute(
        select(Observation).where(
            Observation.daily_record_id == daily_record.id,
            Observation.category_id == category_id,
        )
    )
    observation = obs_result.scalar_one_or_none()
    if not observation:
        return

    observation.minutes -= minutes
    if observation.minutes <= 0:
        await db.delete(observation)

    # Recalculate daily total
    await db.flush()
    total_result = await db.execute(
        select(func.coalesce(func.sum(Observation.minutes), 0)).where(
            Observation.daily_record_id == daily_record.id
        )
    )
    daily_record.total_minutes = total_result.scalar()


async def upsert_text_entry(
    session_id: int,
    date: str,
    description: str | None,
    location: str | None,
    db: AsyncSession,
) -> TextEntry | None:
    """Append description to the text entry for (session, date), creating if needed."""
    if not description:
        return None

    te_result = await db.execute(
        select(TextEntry).where(
            TextEntry.session_id == session_id,
            TextEntry.date == date,
        )
    )
    text_entry = te_result.scalar_one_or_none()

    if text_entry:
        if text_entry.study_materials:
            text_entry.study_materials += f", {description}"
        else:
            text_entry.study_materials = description
        if location and not text_entry.location:
            text_entry.location = location
    else:
        text_entry = TextEntry(
            session_id=session_id,
            date=date,
            location=location,
            study_materials=description,
        )
        db.add(text_entry)

    return text_entry
