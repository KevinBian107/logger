from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import Session, ManualEntry, Category
from logger.schemas import ManualEntryCreate, ManualEntryResponse
from logger.services import manual_entry_service

router = APIRouter(prefix="/manual-entries", tags=["manual-entries"])


async def _entry_response(entry: ManualEntry, db: AsyncSession) -> ManualEntryResponse:
    cat = await db.get(Category, entry.category_id)
    return ManualEntryResponse(
        id=entry.id,
        session_id=entry.session_id,
        category_id=entry.category_id,
        category_name=cat.display_name or cat.name if cat else None,
        date=entry.date,
        duration_minutes=entry.duration_minutes,
        description=entry.description,
        location=entry.location,
        created_at=entry.created_at,
    )


@router.post("", response_model=ManualEntryResponse)
async def create_manual_entry(
    data: ManualEntryCreate, db: AsyncSession = Depends(get_db)
):
    session = await _get_active_session(db)
    if not session:
        raise HTTPException(status_code=400, detail="No active session")

    try:
        entry = await manual_entry_service.create_manual_entry(
            session_id=session.id,
            category_id=data.category_id,
            date=data.date,
            duration_minutes=data.duration_minutes,
            description=data.description,
            location=data.location,
            db=db,
        )
        await db.commit()
        return await _entry_response(entry, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[ManualEntryResponse])
async def list_manual_entries(
    date: str | None = Query(None),
    session_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(ManualEntry)

    if session_id:
        query = query.where(ManualEntry.session_id == session_id)
    else:
        session = await _get_active_session(db)
        if session:
            query = query.where(ManualEntry.session_id == session.id)

    if date:
        query = query.where(ManualEntry.date == date)

    query = query.order_by(ManualEntry.created_at.desc())
    result = await db.execute(query)
    entries = result.scalars().all()
    return [await _entry_response(e, db) for e in entries]


@router.delete("/{entry_id}")
async def delete_manual_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await manual_entry_service.delete_manual_entry(entry_id, db)
        await db.commit()
        return {"detail": "Manual entry deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _get_active_session(db: AsyncSession) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.is_active == True)
    )
    return result.scalar_one_or_none()
