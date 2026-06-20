"""Break / rest / vacation days.

Breaks are global (not session-scoped) neutral day markers. They add no time and
they bridge the activity streak (see daily.get_streak). Each calendar date holds
at most one break (unique on date); creating a range upserts one row per day.
"""

from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import BreakDay
from logger.schemas import BreakDayCreate, BreakDayResponse

router = APIRouter(prefix="/breaks", tags=["breaks"])

# Guard against a fat-fingered range marking years of days at once.
MAX_RANGE_DAYS = 366


def _daterange(start: date_type, end: date_type):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


@router.post("", response_model=list[BreakDayResponse])
async def create_breaks(data: BreakDayCreate, db: AsyncSession = Depends(get_db)):
    try:
        start = date_type.fromisoformat(data.start_date)
        end = date_type.fromisoformat(data.end_date) if data.end_date else start
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date (expected YYYY-MM-DD)")

    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Range too large (max {MAX_RANGE_DAYS} days)")

    label = (data.label or "").strip() or None

    out: list[BreakDay] = []
    for d in _daterange(start, end):
        ymd = d.isoformat()
        existing = await db.execute(select(BreakDay).where(BreakDay.date == ymd))
        row = existing.scalar_one_or_none()
        if row:
            row.label = label  # re-marking a day updates its label
        else:
            row = BreakDay(date=ymd, label=label)
            db.add(row)
        out.append(row)

    await db.commit()
    for row in out:
        await db.refresh(row)
    return out


@router.get("", response_model=list[BreakDayResponse])
async def list_breaks(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(BreakDay)
    if start:
        query = query.where(BreakDay.date >= start)
    if end:
        query = query.where(BreakDay.date <= end)
    query = query.order_by(BreakDay.date.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.delete("")
async def delete_break_range(
    start: str = Query(...),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    end = end or start
    result = await db.execute(
        delete(BreakDay).where(BreakDay.date >= start, BreakDay.date <= end)
    )
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.delete("/{date}")
async def delete_break(date: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BreakDay).where(BreakDay.date == date))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No break on that date")
    await db.delete(row)
    await db.commit()
    return {"deleted": 1}
