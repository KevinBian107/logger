"""Planner item CRUD.

A PlanItem is an itinerary entry on the Planner timeline. It carries its own
date range (and, for single-day items, an optional time-of-day) independent of
whatever timer/manual entries later get logged against it — see the module
docstring on PlanItem in models.py for the linking semantics.
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import PlanItem, Category, TimerEntry, ManualEntry


def _clamp_time_fields(start_date: str, end_date: str, start_time: str | None, end_time: str | None) -> tuple[str | None, str | None]:
    """Time-of-day only means something for a single-day item. The moment an
    item spans more than one day (on create, or after a resize-drag), drop it."""
    if start_date != end_date:
        return None, None
    return start_time, end_time


async def _validate_category(category_id: int, db: AsyncSession) -> Category:
    cat = await db.get(Category, category_id)
    if not cat:
        raise ValueError("Category not found")
    return cat


def _validate_importance(importance: str | None) -> str | None:
    if importance and importance not in ("low", "medium", "high"):
        raise ValueError("importance must be 'low', 'medium', or 'high'")
    return importance or None


async def create_item(
    *,
    title: str,
    category_id: int,
    start_date: str,
    end_date: str | None,
    start_time: str | None,
    end_time: str | None,
    notes: str | None,
    db: AsyncSession,
    importance: str | None = None,
) -> PlanItem:
    await _validate_category(category_id, db)

    end_date = end_date or start_date
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    start_time, end_time = _clamp_time_fields(start_date, end_date, start_time, end_time)
    importance = _validate_importance(importance)

    item = PlanItem(
        title=title.strip() or "Untitled",
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time or None,
        end_time=end_time or None,
        notes=notes or None,
        status="planned",
        importance=importance,
    )
    db.add(item)
    await db.flush()
    return item


async def update_item(
    item_id: int,
    db: AsyncSession,
    *,
    title: str | None = None,
    category_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    importance: str | None = None,
) -> PlanItem:
    item = await db.get(PlanItem, item_id)
    if not item:
        raise ValueError("Plan item not found")

    if importance is not None:
        item.importance = _validate_importance(importance)
    if title is not None:
        item.title = title.strip() or "Untitled"
    if category_id is not None:
        await _validate_category(category_id, db)
        item.category_id = category_id
    if start_date is not None:
        item.start_date = start_date
    if end_date is not None:
        item.end_date = end_date
    if notes is not None:
        item.notes = notes or None
    if status is not None:
        if status not in ("planned", "done"):
            raise ValueError("status must be 'planned' or 'done'")
        item.status = status

    if item.end_date < item.start_date:
        raise ValueError("end_date must be on or after start_date")

    # Explicit time edits (including "" to clear) only apply while it's still
    # a single-day item — _clamp_time_fields below re-derives the final value
    # from whatever start_time/end_time currently are after any date change.
    if start_time is not None:
        item.start_time = start_time or None
    if end_time is not None:
        item.end_time = end_time or None
    item.start_time, item.end_time = _clamp_time_fields(
        item.start_date, item.end_date, item.start_time, item.end_time
    )

    await db.flush()
    return item


async def delete_item(item_id: int, db: AsyncSession) -> None:
    item = await db.get(PlanItem, item_id)
    if not item:
        raise ValueError("Plan item not found")
    await db.delete(item)
    await db.flush()


async def _progress_by_item(item_ids: list[int], db: AsyncSession) -> dict[int, dict]:
    """Aggregate {plan_item_id: {timer_count, manual_count, logged_minutes}}."""
    progress: dict[int, dict] = {
        i: {"timer_count": 0, "manual_count": 0, "logged_minutes": 0} for i in item_ids
    }
    if not item_ids:
        return progress

    timer_rows = await db.execute(
        select(
            TimerEntry.plan_item_id,
            func.count(TimerEntry.id),
            func.coalesce(func.sum(TimerEntry.duration_minutes), 0),
        )
        .where(TimerEntry.plan_item_id.in_(item_ids))
        .group_by(TimerEntry.plan_item_id)
    )
    for plan_item_id, count, minutes in timer_rows.all():
        progress[plan_item_id]["timer_count"] = count
        progress[plan_item_id]["logged_minutes"] += minutes or 0

    manual_rows = await db.execute(
        select(
            ManualEntry.plan_item_id,
            func.count(ManualEntry.id),
            func.coalesce(func.sum(ManualEntry.duration_minutes), 0),
        )
        .where(ManualEntry.plan_item_id.in_(item_ids))
        .group_by(ManualEntry.plan_item_id)
    )
    for plan_item_id, count, minutes in manual_rows.all():
        progress[plan_item_id]["manual_count"] = count
        progress[plan_item_id]["logged_minutes"] += minutes or 0

    return progress


async def list_items_in_range(start: str, end: str, db: AsyncSession) -> list[tuple[PlanItem, dict]]:
    """Items whose [start_date, end_date] overlaps [start, end], each paired
    with its logged-time progress dict."""
    result = await db.execute(
        select(PlanItem)
        .where(PlanItem.end_date >= start, PlanItem.start_date <= end)
        .order_by(PlanItem.start_date)
    )
    items = list(result.scalars().all())
    progress = await _progress_by_item([i.id for i in items], db)
    return [(item, progress[item.id]) for item in items]


async def get_item_with_links(item_id: int, db: AsyncSession) -> tuple[PlanItem, dict, list[TimerEntry], list[ManualEntry]] | None:
    item = await db.get(PlanItem, item_id)
    if not item:
        return None
    progress = await _progress_by_item([item.id], db)

    timer_result = await db.execute(
        select(TimerEntry).where(TimerEntry.plan_item_id == item_id).order_by(TimerEntry.start_time.desc())
    )
    manual_result = await db.execute(
        select(ManualEntry).where(ManualEntry.plan_item_id == item_id).order_by(ManualEntry.created_at.desc())
    )
    return item, progress[item_id], list(timer_result.scalars().all()), list(manual_result.scalars().all())
