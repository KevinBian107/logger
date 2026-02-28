from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from logger.config import DATA_DIR
from logger.database import get_db
from logger.schemas import ImportPreviewResponse, ImportConfirmRequest, BatchImportRequest
from logger.services.import_service import preview_import, confirm_import

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview", response_model=ImportPreviewResponse)
async def import_preview(
    study_csv: UploadFile = File(...),
    text_csv: UploadFile | None = File(None),
):
    study_content = await study_csv.read()
    text_content = None
    text_filename = None

    if text_csv:
        text_content = await text_csv.read()
        text_filename = text_csv.filename

    try:
        result = await preview_import(
            study_content=study_content,
            study_filename=study_csv.filename,
            text_content=text_content,
            text_filename=text_filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportPreviewResponse(**result)


@router.post("/confirm")
async def import_confirm(
    data: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await confirm_import(data.preview_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.post("/batch")
async def import_batch(
    data: BatchImportRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Import all CSV pairs from the data directory in one call."""
    data_dir = Path(data.data_dir) if data and data.data_dir else DATA_DIR

    if not data_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {data_dir}")

    # Find all study CSVs and their matching text CSVs
    study_files = sorted(data_dir.glob("*_study.csv"))
    if not study_files:
        raise HTTPException(status_code=400, detail="No study CSV files found")

    results = []
    errors = []

    for study_path in study_files:
        study_filename = study_path.name
        # Find matching text CSV
        text_filename = study_filename.replace("_study.csv", "_text.csv")
        text_path = data_dir / text_filename

        study_content = study_path.read_bytes()
        text_content = text_path.read_bytes() if text_path.exists() else None

        try:
            preview = await preview_import(
                study_content=study_content,
                study_filename=study_filename,
                text_content=text_content,
                text_filename=text_filename if text_content else None,
            )
            result = await confirm_import(preview["preview_id"], db)
            results.append(result)
        except ValueError as e:
            errors.append({"file": study_filename, "error": str(e)})

    return {
        "imported": len(results),
        "errors": errors,
        "sessions": results,
    }
