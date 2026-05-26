"""Group endpoints. A Group is the top-level semantic bucket (Research,
Training, Personal, Courses) that contains CategoryFamilies.

The bubble-data endpoint walks the full Group → Family → Category tree.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.schemas import (
    CategoryGroupCreate,
    CategoryGroupUpdate,
    CategoryGroupResponse,
    CategoryGroupDetailResponse,
    FamilyGroupAssignment,
    BubbleDataResponse,
)
from logger.services import group_service

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[CategoryGroupResponse])
async def list_groups(db: AsyncSession = Depends(get_db)):
    return await group_service.list_groups(db)


@router.get("/bubble-data", response_model=BubbleDataResponse)
async def bubble_data(db: AsyncSession = Depends(get_db)):
    return await group_service.get_bubble_data(db)


@router.get("/{group_id}", response_model=CategoryGroupDetailResponse)
async def get_group(group_id: int, db: AsyncSession = Depends(get_db)):
    result = await group_service.get_group(group_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


@router.post("", response_model=dict)
async def create_group(data: CategoryGroupCreate, db: AsyncSession = Depends(get_db)):
    return await group_service.create_group(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        color=data.color,
        db=db,
    )


@router.put("/{group_id}", response_model=dict)
async def update_group(group_id: int, data: CategoryGroupUpdate, db: AsyncSession = Depends(get_db)):
    result = await group_service.update_group(group_id, data.model_dump(exclude_unset=True), db)
    if not result:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


@router.delete("/{group_id}")
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    try:
        ok = await group_service.delete_group(group_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.put("/families/{family_id}/group")
async def set_family_group(family_id: int, data: FamilyGroupAssignment, db: AsyncSession = Depends(get_db)):
    """Assign a family to a group (or detach via group_id=null)."""
    ok = await group_service.assign_family_to_group(family_id, data.group_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Family not found")
    return {"ok": True, "family_id": family_id, "group_id": data.group_id}
