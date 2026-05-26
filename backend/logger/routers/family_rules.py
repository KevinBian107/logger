"""CRUD for `family_match_rules`.

Used to define how raw category names (from CSV imports or manual entry)
get auto-linked to a CategoryFamily. Two match types are supported:

  - "exact":  category display name (lowercased) == pattern
  - "prefix": category looks like "<pattern> <number>...", e.g. pattern="cogs"
              matches "COGS 118C"

No UI yet — call these endpoints from the Settings page, curl, or sqlite.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import CategoryFamily, FamilyMatchRule
from logger.schemas import FamilyMatchRuleCreate, FamilyMatchRuleResponse

router = APIRouter(prefix="/family-rules", tags=["family-rules"])

VALID_MATCH_TYPES = {"exact", "prefix"}


async def _to_response(rule: FamilyMatchRule, db: AsyncSession) -> FamilyMatchRuleResponse:
    fam = await db.get(CategoryFamily, rule.family_id)
    return FamilyMatchRuleResponse(
        id=rule.id,
        family_id=rule.family_id,
        family_name=fam.name if fam else None,
        family_display_name=fam.display_name if fam else None,
        match_type=rule.match_type,
        pattern=rule.pattern,
        position=rule.position or 0,
    )


@router.get("", response_model=list[FamilyMatchRuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FamilyMatchRule).order_by(FamilyMatchRule.match_type, FamilyMatchRule.pattern)
    )
    rules = result.scalars().all()
    return [await _to_response(r, db) for r in rules]


@router.post("", response_model=FamilyMatchRuleResponse)
async def create_rule(data: FamilyMatchRuleCreate, db: AsyncSession = Depends(get_db)):
    if data.match_type not in VALID_MATCH_TYPES:
        raise HTTPException(status_code=400, detail=f"match_type must be one of {sorted(VALID_MATCH_TYPES)}")

    family = await db.get(CategoryFamily, data.family_id)
    if not family:
        raise HTTPException(status_code=404, detail=f"Family {data.family_id} not found")

    pattern = data.pattern.strip().lower()
    if not pattern:
        raise HTTPException(status_code=400, detail="pattern cannot be empty")

    # Reject duplicates on (match_type, pattern)
    existing = await db.execute(
        select(FamilyMatchRule)
        .where(FamilyMatchRule.match_type == data.match_type)
        .where(FamilyMatchRule.pattern == pattern)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A {data.match_type} rule for pattern '{pattern}' already exists",
        )

    rule = FamilyMatchRule(
        family_id=data.family_id,
        match_type=data.match_type,
        pattern=pattern,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return await _to_response(rule, db)


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(FamilyMatchRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": True}
