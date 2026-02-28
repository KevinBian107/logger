from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import Category, CategoryFamily, Session, Observation
from logger.schemas import (
    CategoryCreate, CategoryResponse, CategoryUpdate,
    FamilyCreate, FamilyResponse, FamilyUpdate,
)
from logger.services.family_service import (
    detect_family, get_or_create_family, KNOWN_FAMILIES, DEPARTMENT_FAMILIES,
)

router = APIRouter(tags=["categories"])


async def _build_cat_response(cat: Category, db: AsyncSession) -> CategoryResponse:
    """Build a CategoryResponse with family info and total minutes."""
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

    return CategoryResponse(
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
    )


@router.get("/sessions/{session_id}/categories", response_model=list[CategoryResponse])
async def list_categories(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category)
        .where(Category.session_id == session_id)
        .order_by(Category.position)
    )
    categories = result.scalars().all()
    return [await _build_cat_response(cat, db) for cat in categories]


@router.post("/sessions/{session_id}/categories", response_model=CategoryResponse)
async def add_category(
    session_id: int, data: CategoryCreate, db: AsyncSession = Depends(get_db)
):
    # Verify session exists
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check uniqueness
    existing = await db.execute(
        select(Category).where(
            Category.session_id == session_id,
            Category.name == data.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Category '{data.name}' already exists in this session")

    family_id = None
    family_name = None
    if data.family:
        family = await get_or_create_family(data.family, db)
        family_id = family.id
        family_name = family.name
    elif not data.family:
        detected = detect_family(data.name)
        if detected:
            family = await get_or_create_family(detected, db)
            family_id = family.id
            family_name = family.name

    display = data.display_name
    if not display:
        detected = detect_family(data.name)
        if detected:
            display = KNOWN_FAMILIES.get(detected) or DEPARTMENT_FAMILIES.get(detected) or data.name
        else:
            display = data.name

    # Get max position
    max_pos = await db.execute(
        select(func.coalesce(func.max(Category.position), -1))
        .where(Category.session_id == session_id)
    )
    position = max_pos.scalar() + 1

    cat = Category(
        session_id=session_id,
        name=data.name,
        display_name=display,
        family_id=family_id,
        position=position,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return await _build_cat_response(cat, db)


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int, data: CategoryUpdate, db: AsyncSession = Depends(get_db)
):
    cat = await db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    if data.display_name is not None:
        cat.display_name = data.display_name
    if data.family_id is not None:
        # 0 means "remove family"
        cat.family_id = data.family_id if data.family_id != 0 else None

    await db.commit()
    await db.refresh(cat)
    return await _build_cat_response(cat, db)


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    cat = await db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for observations
    obs_count = await db.execute(
        select(func.count(Observation.id)).where(Observation.category_id == category_id)
    )
    if obs_count.scalar() > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete category with existing observations",
        )

    await db.delete(cat)
    await db.commit()
    return {"detail": "Category deleted"}


# ── Families ──────────────────────────────────────────────


@router.get("/families", response_model=list[FamilyResponse])
async def list_families(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CategoryFamily).order_by(CategoryFamily.name))
    families = result.scalars().all()

    responses = []
    for fam in families:
        cat_count = await db.execute(
            select(func.count(Category.id)).where(Category.family_id == fam.id)
        )
        total = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .join(Category, Observation.category_id == Category.id)
            .where(Category.family_id == fam.id)
        )
        responses.append(FamilyResponse(
            id=fam.id,
            name=fam.name,
            display_name=fam.display_name,
            description=fam.description,
            color=fam.color,
            family_type=fam.family_type,
            category_count=cat_count.scalar(),
            total_minutes=total.scalar(),
        ))

    return responses


@router.get("/families/{family_id}", response_model=FamilyResponse)
async def get_family(family_id: int, db: AsyncSession = Depends(get_db)):
    fam = await db.get(CategoryFamily, family_id)
    if not fam:
        raise HTTPException(status_code=404, detail="Family not found")

    cat_count = await db.execute(
        select(func.count(Category.id)).where(Category.family_id == fam.id)
    )
    total = await db.execute(
        select(func.coalesce(func.sum(Observation.minutes), 0))
        .join(Category, Observation.category_id == Category.id)
        .where(Category.family_id == fam.id)
    )

    return FamilyResponse(
        id=fam.id,
        name=fam.name,
        display_name=fam.display_name,
        description=fam.description,
        color=fam.color,
        family_type=fam.family_type,
        category_count=cat_count.scalar(),
        total_minutes=total.scalar(),
    )


@router.post("/families", response_model=FamilyResponse)
async def create_family(data: FamilyCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Family '{data.name}' already exists")

    fam = CategoryFamily(
        name=data.name,
        display_name=data.display_name or data.name.title(),
        description=data.description,
        color=data.color,
        family_type=data.family_type,
    )
    db.add(fam)
    await db.commit()
    await db.refresh(fam)

    return FamilyResponse(
        id=fam.id,
        name=fam.name,
        display_name=fam.display_name,
        description=fam.description,
        color=fam.color,
        family_type=fam.family_type,
        category_count=0,
        total_minutes=0,
    )


@router.put("/families/{family_id}", response_model=FamilyResponse)
async def update_family(
    family_id: int, data: FamilyUpdate, db: AsyncSession = Depends(get_db)
):
    fam = await db.get(CategoryFamily, family_id)
    if not fam:
        raise HTTPException(status_code=404, detail="Family not found")

    if data.name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(CategoryFamily).where(
                CategoryFamily.name == data.name,
                CategoryFamily.id != family_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Family name '{data.name}' already exists")
        fam.name = data.name
    if data.display_name is not None:
        fam.display_name = data.display_name
    if data.color is not None:
        fam.color = data.color
    if data.description is not None:
        fam.description = data.description
    if data.family_type is not None:
        fam.family_type = data.family_type

    await db.commit()
    await db.refresh(fam)

    cat_count = await db.execute(
        select(func.count(Category.id)).where(Category.family_id == fam.id)
    )
    total = await db.execute(
        select(func.coalesce(func.sum(Observation.minutes), 0))
        .join(Category, Observation.category_id == Category.id)
        .where(Category.family_id == fam.id)
    )

    return FamilyResponse(
        id=fam.id,
        name=fam.name,
        display_name=fam.display_name,
        description=fam.description,
        color=fam.color,
        family_type=fam.family_type,
        category_count=cat_count.scalar(),
        total_minutes=total.scalar(),
    )


@router.delete("/families/{family_id}")
async def delete_family(family_id: int, db: AsyncSession = Depends(get_db)):
    fam = await db.get(CategoryFamily, family_id)
    if not fam:
        raise HTTPException(status_code=404, detail="Family not found")

    # Unlink all categories from this family
    result = await db.execute(
        select(Category).where(Category.family_id == family_id)
    )
    linked_cats = result.scalars().all()
    for cat in linked_cats:
        cat.family_id = None

    await db.delete(fam)
    await db.commit()

    return {"deleted": True, "categories_unlinked": len(linked_cats)}
