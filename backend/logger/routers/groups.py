from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.schemas import (
    CategoryGroupCreate,
    CategoryGroupUpdate,
    CategoryGroupResponse,
    CategoryGroupDetailResponse,
    GroupMembersUpdate,
    BubbleDataResponse,
)
from logger.services import group_service

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[CategoryGroupResponse])
async def list_groups(db: AsyncSession = Depends(get_db)):
    return await group_service.get_groups(db)


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
    if not await group_service.delete_group(group_id, db):
        raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.post("/{group_id}/members")
async def add_members(group_id: int, data: GroupMembersUpdate, db: AsyncSession = Depends(get_db)):
    added = await group_service.add_members(group_id, data.category_ids, db)
    return {"added": added}


@router.delete("/{group_id}/members")
async def remove_members(group_id: int, data: GroupMembersUpdate, db: AsyncSession = Depends(get_db)):
    removed = await group_service.remove_members(group_id, data.category_ids, db)
    return {"removed": removed}


@router.post("/auto-generate")
async def auto_generate(db: AsyncSession = Depends(get_db)):
    return await group_service.auto_generate_groups(db)
