import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.config import DB_PATH
from logger.database import export_db_bytes, get_db, replace_db_file
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


@router.post("/db/replace")
async def db_replace(file: UploadFile = File(...)):
    """Replace the current SQLite database with an uploaded .db file.

    Backs up the existing DB to <path>.bak.<timestamp> before swapping.
    Runs schema migrations against the new file so older schemas still load.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > 200 * 1024 * 1024:  # 200 MB safety cap for a personal app
        raise HTTPException(status_code=413, detail="File too large (limit 200 MB)")

    try:
        result = await replace_db_file(contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Replace failed: {e!s}")
    return result


@router.get("/db/download")
async def db_download():
    """Stream the current SQLite database back so the user can keep a copy."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="DB file not found")
    data = await export_db_bytes()
    return Response(
        content=data,
        media_type="application/vnd.sqlite3",
        headers={"Content-Disposition": 'attachment; filename="logger.db"'},
    )
