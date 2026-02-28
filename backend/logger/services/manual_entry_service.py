"""Manual time entry management."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import ManualEntry, Category
from logger.services.observation_service import (
    upsert_observation,
    upsert_text_entry,
    subtract_observation,
)


async def create_manual_entry(
    session_id: int,
    category_id: int,
    date: str,
    duration_minutes: int,
    description: str | None,
    location: str | None,
    db: AsyncSession,
) -> ManualEntry:
    if duration_minutes < 1:
        raise ValueError("Duration must be at least 1 minute")

    # Validate category belongs to session
    cat = await db.get(Category, category_id)
    if not cat or cat.session_id != session_id:
        raise ValueError("Category not found or does not belong to session")

    entry = ManualEntry(
        session_id=session_id,
        category_id=category_id,
        date=date,
        duration_minutes=duration_minutes,
        description=description,
        location=location,
    )
    db.add(entry)
    await db.flush()

    await upsert_observation(
        session_id=session_id,
        category_id=category_id,
        date=date,
        minutes=duration_minutes,
        source="manual",
        db=db,
    )

    await upsert_text_entry(
        session_id=session_id,
        date=date,
        description=description,
        location=location,
        db=db,
    )

    return entry


async def delete_manual_entry(entry_id: int, db: AsyncSession) -> None:
    entry = await db.get(ManualEntry, entry_id)
    if not entry:
        raise ValueError("Manual entry not found")

    await subtract_observation(
        session_id=entry.session_id,
        category_id=entry.category_id,
        date=entry.date,
        minutes=entry.duration_minutes,
        db=db,
    )

    await db.delete(entry)
    await db.flush()


async def get_manual_entries_for_date(
    session_id: int, date: str, db: AsyncSession
) -> list[ManualEntry]:
    result = await db.execute(
        select(ManualEntry).where(
            ManualEntry.session_id == session_id,
            ManualEntry.date == date,
        ).order_by(ManualEntry.created_at.desc())
    )
    return list(result.scalars().all())
