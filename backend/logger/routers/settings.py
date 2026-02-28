import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.config import DB_PATH
from logger.database import get_db
from logger.models import Setting, Session, Observation, TextEntry
from logger.schemas import SettingResponse, SettingUpdate, DBInfoResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[SettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    return result.scalars().all()


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str, data: SettingUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=key, value=data.value)
        db.add(setting)

    await db.commit()
    await db.refresh(setting)
    return setting


@router.get("/db-info", response_model=DBInfoResponse)
async def db_info(db: AsyncSession = Depends(get_db)):
    db_size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0

    session_count = (await db.execute(select(func.count(Session.id)))).scalar()
    obs_count = (await db.execute(select(func.count(Observation.id)))).scalar()
    text_count = (await db.execute(select(func.count(TextEntry.id)))).scalar()

    return DBInfoResponse(
        db_path=str(DB_PATH),
        db_size_bytes=db_size,
        session_count=session_count,
        observation_count=obs_count,
        text_entry_count=text_count,
    )
