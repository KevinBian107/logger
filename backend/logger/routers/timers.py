from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import Session, Category, PlanItem
from logger.schemas import TimerStartRequest, TimerStopRequest, TimerEntryResponse, TimerEntryUpdate
from logger.services import timer_service

router = APIRouter(prefix="/timers", tags=["timers"])


async def _timer_response(timer, db: AsyncSession) -> TimerEntryResponse:
    cat = await db.get(Category, timer.category_id)
    plan_item = await db.get(PlanItem, timer.plan_item_id) if timer.plan_item_id else None
    return TimerEntryResponse(
        id=timer.id,
        session_id=timer.session_id,
        category_id=timer.category_id,
        category_name=cat.display_name or cat.name if cat else None,
        date=timer.date,
        start_time=timer.start_time,
        end_time=timer.end_time,
        pause_start=timer.pause_start,
        total_paused_seconds=timer.total_paused_seconds or 0,
        duration_minutes=timer.duration_minutes,
        is_active=timer.is_active,
        is_paused=timer.is_paused,
        description=timer.description,
        location=timer.location,
        plan_item_id=timer.plan_item_id,
        plan_item_title=plan_item.title if plan_item else None,
    )


@router.get("/active", response_model=list[TimerEntryResponse])
async def get_active_timers(db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(db)
    if not session:
        return []
    timers = await timer_service.get_active_timers(session.id, db)
    return [await _timer_response(t, db) for t in timers]


@router.post("/start", response_model=TimerEntryResponse)
async def start_timer(data: TimerStartRequest, db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(db)
    if not session:
        raise HTTPException(status_code=400, detail="No active session")

    # Validate category belongs to active session
    cat = await db.get(Category, data.category_id)
    if not cat or cat.session_id != session.id:
        raise HTTPException(status_code=400, detail="Category not in active session")

    try:
        timer = await timer_service.start_timer(session.id, data.category_id, db, plan_item_id=data.plan_item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return await _timer_response(timer, db)


@router.post("/{timer_id}/pause", response_model=TimerEntryResponse)
async def pause_timer(timer_id: int, db: AsyncSession = Depends(get_db)):
    try:
        timer = await timer_service.pause_timer(timer_id, db)
        await db.commit()
        return await _timer_response(timer, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{timer_id}/resume", response_model=TimerEntryResponse)
async def resume_timer(timer_id: int, db: AsyncSession = Depends(get_db)):
    try:
        timer = await timer_service.resume_timer(timer_id, db)
        await db.commit()
        return await _timer_response(timer, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{timer_id}/stop", response_model=TimerEntryResponse)
async def stop_timer(
    timer_id: int, data: TimerStopRequest, db: AsyncSession = Depends(get_db)
):
    try:
        timer = await timer_service.stop_timer(
            timer_id,
            description=data.description,
            location=data.location,
            db=db,
            override_date=data.override_date,
        )
        await db.commit()
        return await _timer_response(timer, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{timer_id}", response_model=TimerEntryResponse)
async def update_timer(
    timer_id: int, data: TimerEntryUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        timer = await timer_service.update_timer_entry(
            timer_id,
            db,
            category_id=data.category_id,
            date=data.date,
            duration_minutes=data.duration_minutes,
            description=data.description,
            location=data.location,
        )
        await db.commit()
        return await _timer_response(timer, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{timer_id}")
async def discard_timer(timer_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await timer_service.discard_timer(timer_id, db)
        await db.commit()
        return {"detail": "Timer discarded"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _get_active_session(db: AsyncSession) -> Session | None:
    from sqlalchemy import select
    result = await db.execute(
        select(Session).where(Session.is_active == True)
    )
    return result.scalar_one_or_none()
