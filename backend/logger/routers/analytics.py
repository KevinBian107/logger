from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.schemas import (
    AnalyticsOverviewResponse,
    DailySeriesPoint,
    CategoryBreakdownItem,
    HeatmapPoint,
    SessionComparisonItem,
)
from logger.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _parse_filters(
    session_ids: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    week_number: int | None = Query(None),
) -> dict:
    filters: dict = {}
    if session_ids:
        filters["session_ids"] = [int(s) for s in session_ids.split(",")]
    if from_date:
        filters["from_date"] = from_date
    if to_date:
        filters["to_date"] = to_date
    if week_number is not None:
        filters["week_number"] = week_number
    return filters


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def overview(
    session_ids: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    week_number: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = _parse_filters(session_ids, from_date, to_date, week_number)
    return await analytics_service.get_overview(db, filters)


@router.get("/daily", response_model=list[DailySeriesPoint])
async def daily(
    session_ids: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    week_number: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = _parse_filters(session_ids, from_date, to_date, week_number)
    return await analytics_service.get_daily_series(db, filters)


@router.get("/categories", response_model=list[CategoryBreakdownItem])
async def categories(
    session_ids: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    week_number: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = _parse_filters(session_ids, from_date, to_date, week_number)
    return await analytics_service.get_category_breakdown(db, filters)


@router.get("/heatmap", response_model=list[HeatmapPoint])
async def heatmap(
    session_ids: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    week_number: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = _parse_filters(session_ids, from_date, to_date, week_number)
    return await analytics_service.get_heatmap(db, filters)


@router.get("/sessions", response_model=list[SessionComparisonItem])
async def session_comparison(db: AsyncSession = Depends(get_db)):
    return await analytics_service.get_session_comparison(db)
