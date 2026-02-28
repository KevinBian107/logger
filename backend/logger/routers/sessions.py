from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from logger.database import get_db
from logger.models import Session, Category, DailyRecord, Observation, CategoryFamily
from logger.schemas import (
    SessionCreate, SessionResponse, SessionListResponse, SessionUpdate,
    CategoryResponse,
)
from logger.services.family_service import (
    detect_family, get_or_create_family, KNOWN_FAMILIES, DEPARTMENT_FAMILIES,
)

router = APIRouter(tags=["sessions"])

SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}


async def _build_session_response(session: Session, db: AsyncSession) -> SessionResponse:
    """Build a full SessionResponse with computed fields."""
    # Get categories with totals
    cat_responses = []
    for cat in session.categories:
        total = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .where(Observation.category_id == cat.id)
        )
        total_min = total.scalar()

        family_name = None
        family_display_name = None
        family_type = None
        if cat.family_id:
            fam = await db.get(CategoryFamily, cat.family_id)
            if fam:
                family_name = fam.name
                family_display_name = fam.display_name
                family_type = fam.family_type

        cat_responses.append(CategoryResponse(
            id=cat.id,
            session_id=cat.session_id,
            name=cat.name,
            display_name=cat.display_name,
            family_id=cat.family_id,
            family_name=family_name,
            family_display_name=family_display_name,
            family_type=family_type,
            position=cat.position,
            total_minutes=total_min,
        ))

    # Session totals
    total_result = await db.execute(
        select(func.coalesce(func.sum(DailyRecord.total_minutes), 0))
        .where(DailyRecord.session_id == session.id)
    )
    total_minutes = total_result.scalar()

    days_result = await db.execute(
        select(func.count(DailyRecord.id))
        .where(DailyRecord.session_id == session.id)
    )
    days_logged = days_result.scalar()

    return SessionResponse(
        id=session.id,
        year=session.year,
        season=session.season,
        label=session.label,
        start_date=session.start_date,
        end_date=session.end_date,
        is_active=session.is_active,
        source_file=session.source_file,
        created_at=session.created_at,
        categories=cat_responses,
        total_minutes=total_minutes,
        days_logged=days_logged,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).options(selectinload(Session.categories)).order_by(
            Session.year.desc(),
            # Sort by season order
        )
    )
    sessions = result.scalars().all()
    # Sort by year desc, then season desc
    sessions = sorted(
        sessions,
        key=lambda s: (s.year, SEASON_ORDER.get(s.season, 0)),
        reverse=True,
    )

    responses = []
    for s in sessions:
        resp = await _build_session_response(s, db)
        responses.append(resp)

    return SessionListResponse(sessions=responses)


@router.get("/sessions/active", response_model=SessionResponse | None)
async def get_active_session(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.categories))
        .where(Session.is_active == True)
    )
    session = result.scalar_one_or_none()
    if not session:
        return None
    return await _build_session_response(session, db)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.categories))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await _build_session_response(session, db)


@router.post("/sessions", response_model=SessionResponse)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = await db.execute(
        select(Session).where(Session.year == data.year, Session.season == data.season)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Session {data.season} {data.year} already exists")

    session = Session(
        year=data.year,
        season=data.season,
        label=data.label or f"{data.season.capitalize()} {data.year}",
    )
    db.add(session)
    await db.flush()

    # If continuing from another session, copy categories
    if data.continue_from_session_id:
        prev = await db.execute(
            select(Session)
            .options(selectinload(Session.categories))
            .where(Session.id == data.continue_from_session_id)
        )
        prev_session = prev.scalar_one_or_none()
        if prev_session:
            for cat in prev_session.categories:
                new_cat = Category(
                    session_id=session.id,
                    name=cat.name,
                    display_name=cat.display_name,
                    family_id=cat.family_id,
                    position=cat.position,
                )
                db.add(new_cat)

    # Add explicitly specified categories
    for i, cat_data in enumerate(data.categories):
        family_id = None
        if cat_data.family:
            family = await get_or_create_family(cat_data.family, db)
            family_id = family.id

        display = cat_data.display_name
        if not display:
            detected = detect_family(cat_data.name)
            if detected:
                display = KNOWN_FAMILIES.get(detected) or DEPARTMENT_FAMILIES.get(detected) or cat_data.name
            else:
                display = cat_data.name

        cat = Category(
            session_id=session.id,
            name=cat_data.name,
            display_name=display,
            family_id=family_id,
            position=i,
        )
        db.add(cat)

    await db.commit()

    # Reload with categories
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.categories))
        .where(Session.id == session.id)
    )
    session = result.scalar_one()
    return await _build_session_response(session, db)


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int, data: SessionUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.categories))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.label is not None:
        session.label = data.label
    if data.start_date is not None:
        session.start_date = data.start_date
    if data.end_date is not None:
        session.end_date = data.end_date
    if data.is_active is not None:
        if data.is_active:
            # Deactivate all other sessions first
            await db.execute(
                select(Session).where(Session.is_active == True)
            )
            for s in (await db.execute(select(Session).where(Session.is_active == True))).scalars():
                s.is_active = False
        session.is_active = data.is_active

    await db.commit()
    await db.refresh(session)
    return await _build_session_response(session, db)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
    return {"detail": "Session deleted"}
