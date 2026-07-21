"""Manual time entry management."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import ManualEntry, Category, PlanItem
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
    start_time: str | None = None,
    plan_item_id: int | None = None,
) -> ManualEntry:
    if duration_minutes < 1:
        raise ValueError("Duration must be at least 1 minute")

    # Validate category belongs to session
    cat = await db.get(Category, category_id)
    if not cat or cat.session_id != session_id:
        raise ValueError("Category not found or does not belong to session")

    if plan_item_id is not None:
        plan_item = await db.get(PlanItem, plan_item_id)
        if not plan_item:
            raise ValueError("Plan item not found")

    entry = ManualEntry(
        session_id=session_id,
        category_id=category_id,
        date=date,
        duration_minutes=duration_minutes,
        description=description,
        location=location,
        # Empty string clears it; otherwise store the ISO as given.
        start_time=start_time or None,
        plan_item_id=plan_item_id,
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


async def update_manual_entry(
    entry_id: int,
    db: AsyncSession,
    *,
    category_id: int | None = None,
    date: str | None = None,
    duration_minutes: int | None = None,
    description: str | None = None,
    location: str | None = None,
    start_time: str | None = None,
) -> ManualEntry:
    """Edit a manual entry, rebalancing the aggregated observation if the date,
    category, or duration changes. None means "don't change this field"."""
    entry = await db.get(ManualEntry, entry_id)
    if not entry:
        raise ValueError("Manual entry not found")

    old_date = entry.date
    old_cat = entry.category_id
    old_mins = entry.duration_minutes or 0

    if category_id is not None and category_id != entry.category_id:
        cat = await db.get(Category, category_id)
        if not cat or cat.session_id != entry.session_id:
            raise ValueError("Category not found or not in this session")
        entry.category_id = category_id

    if date is not None:
        entry.date = date
    if duration_minutes is not None:
        if duration_minutes < 1:
            raise ValueError("duration_minutes must be >= 1")
        entry.duration_minutes = duration_minutes
    if description is not None:
        entry.description = description or None
    if location is not None:
        entry.location = location or None
    if start_time is not None:
        # Empty string clears it; otherwise store the ISO as given.
        entry.start_time = start_time or None

    new_mins = entry.duration_minutes or 0
    if (entry.date != old_date) or (entry.category_id != old_cat) or (new_mins != old_mins):
        if old_mins > 0:
            await subtract_observation(
                session_id=entry.session_id,
                category_id=old_cat,
                date=old_date,
                minutes=old_mins,
                db=db,
            )
        if new_mins > 0:
            await upsert_observation(
                session_id=entry.session_id,
                category_id=entry.category_id,
                date=entry.date,
                minutes=new_mins,
                source="manual",
                db=db,
            )

    await db.flush()
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
