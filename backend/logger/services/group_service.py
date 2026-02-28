"""Category group service: auto-generation, CRUD, bubble data."""

import re

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from logger.models import (
    CategoryGroup, CategoryGroupMember, Category, CategoryFamily, Observation,
)
from logger.services.family_service import DEPARTMENT_FAMILIES


# ── Auto-generation ──────────────────────────────────────

async def auto_generate_groups(db: AsyncSession) -> dict:
    """Create auto groups based on category data. Deletes existing auto groups first."""
    # Remove old auto groups
    await db.execute(
        delete(CategoryGroup).where(CategoryGroup.is_auto == True)  # noqa: E712
    )
    await db.flush()

    # Load all categories with their families
    result = await db.execute(
        select(Category).options(selectinload(Category.family))
    )
    all_cats = result.scalars().all()

    groups_created = 0

    # 1. Department groups: one per dept containing all courses in that dept
    dept_cats: dict[str, list[Category]] = {}
    for cat in all_cats:
        if not cat.family:
            continue
        family_name = cat.family.name
        if family_name in DEPARTMENT_FAMILIES:
            dept_cats.setdefault(family_name, []).append(cat)

    for dept, cats in dept_cats.items():
        display = DEPARTMENT_FAMILIES[dept]
        group = CategoryGroup(
            name=f"dept:{dept}",
            display_name=display,
            description=f"All {display} courses",
            is_auto=True,
        )
        db.add(group)
        await db.flush()
        for cat in cats:
            db.add(CategoryGroupMember(group_id=group.id, category_id=cat.id))
        groups_created += 1

    # 2. Type groups: Courses, Research, Personal
    type_map: dict[str, list[Category]] = {"course": [], "research": [], "personal": []}
    for cat in all_cats:
        if cat.family and cat.family.family_type in type_map:
            type_map[cat.family.family_type].append(cat)

    type_display = {"course": "Courses", "research": "Research", "personal": "Personal"}
    for ftype, cats in type_map.items():
        if not cats:
            continue
        group = CategoryGroup(
            name=f"type:{ftype}",
            display_name=type_display[ftype],
            description=f"All {type_display[ftype].lower()} categories",
            is_auto=True,
        )
        db.add(group)
        await db.flush()
        # Deduplicate category IDs (a category may appear in multiple sessions)
        seen_ids = set()
        for cat in cats:
            if cat.id not in seen_ids:
                db.add(CategoryGroupMember(group_id=group.id, category_id=cat.id))
                seen_ids.add(cat.id)
        groups_created += 1

    # 3. Project groups: one per known family spanning 2+ sessions
    family_result = await db.execute(select(CategoryFamily))
    families = family_result.scalars().all()

    for family in families:
        # Skip department families — they're handled above
        if family.name in DEPARTMENT_FAMILIES:
            continue
        # Find all categories in this family
        fam_cats = [c for c in all_cats if c.family_id == family.id]
        # Only create group if the family spans 2+ sessions
        session_ids = {c.session_id for c in fam_cats}
        if len(session_ids) < 2:
            continue

        group = CategoryGroup(
            name=f"project:{family.name}",
            display_name=family.display_name or family.name.title(),
            description=f"{family.display_name or family.name} across {len(session_ids)} sessions",
            color=family.color,
            is_auto=True,
        )
        db.add(group)
        await db.flush()
        for cat in fam_cats:
            db.add(CategoryGroupMember(group_id=group.id, category_id=cat.id))
        groups_created += 1

    await db.commit()
    return {"groups_created": groups_created}


# ── CRUD ─────────────────────────────────────────────────

async def get_groups(db: AsyncSession) -> list[dict]:
    """List all groups with member count and total minutes."""
    result = await db.execute(
        select(CategoryGroup).order_by(CategoryGroup.name)
    )
    groups = result.scalars().all()

    out = []
    for g in groups:
        # Get member count
        count_result = await db.execute(
            select(func.count(CategoryGroupMember.id))
            .where(CategoryGroupMember.group_id == g.id)
        )
        member_count = count_result.scalar()

        # Get total minutes
        mins_result = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .select_from(CategoryGroupMember)
            .join(Category, CategoryGroupMember.category_id == Category.id)
            .join(Observation, Observation.category_id == Category.id)
            .where(CategoryGroupMember.group_id == g.id)
        )
        total_minutes = mins_result.scalar()

        out.append({
            "id": g.id,
            "name": g.name,
            "display_name": g.display_name,
            "description": g.description,
            "color": g.color,
            "is_auto": g.is_auto,
            "member_count": member_count,
            "total_minutes": int(total_minutes),
        })
    return out


async def get_group(group_id: int, db: AsyncSession) -> dict | None:
    """Get a single group with its members."""
    result = await db.execute(
        select(CategoryGroup)
        .options(selectinload(CategoryGroup.members).selectinload(CategoryGroupMember.category))
        .where(CategoryGroup.id == group_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        return None

    members = []
    for m in g.members:
        cat = m.category
        # Get total minutes for this category
        mins_result = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .where(Observation.category_id == cat.id)
        )
        total_mins = mins_result.scalar()

        members.append({
            "category_id": cat.id,
            "category_name": cat.name,
            "display_name": cat.display_name,
            "session_id": cat.session_id,
            "total_minutes": int(total_mins),
        })

    return {
        "id": g.id,
        "name": g.name,
        "display_name": g.display_name,
        "description": g.description,
        "color": g.color,
        "is_auto": g.is_auto,
        "members": members,
    }


async def create_group(name: str, display_name: str | None, description: str | None, color: str | None, db: AsyncSession) -> dict:
    group = CategoryGroup(
        name=name,
        display_name=display_name or name,
        description=description,
        color=color,
        is_auto=False,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return {"id": group.id, "name": group.name, "display_name": group.display_name}


async def update_group(group_id: int, data: dict, db: AsyncSession) -> dict | None:
    result = await db.execute(
        select(CategoryGroup).where(CategoryGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return None

    for key in ("display_name", "description", "color"):
        if key in data and data[key] is not None:
            setattr(group, key, data[key])

    await db.commit()
    await db.refresh(group)
    return {"id": group.id, "name": group.name, "display_name": group.display_name}


async def delete_group(group_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        select(CategoryGroup).where(CategoryGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return False
    await db.delete(group)
    await db.commit()
    return True


async def add_members(group_id: int, category_ids: list[int], db: AsyncSession) -> int:
    added = 0
    for cat_id in category_ids:
        # Check not already a member
        existing = await db.execute(
            select(CategoryGroupMember).where(
                CategoryGroupMember.group_id == group_id,
                CategoryGroupMember.category_id == cat_id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        db.add(CategoryGroupMember(group_id=group_id, category_id=cat_id))
        added += 1
    await db.commit()
    return added


async def remove_members(group_id: int, category_ids: list[int], db: AsyncSession) -> int:
    result = await db.execute(
        delete(CategoryGroupMember).where(
            CategoryGroupMember.group_id == group_id,
            CategoryGroupMember.category_id.in_(category_ids),
        )
    )
    await db.commit()
    return result.rowcount


# ── Bubble Data ──────────────────────────────────────────

async def get_bubble_data(db: AsyncSession) -> dict:
    """Build hierarchy for bubble visualization: root → groups → categories."""
    result = await db.execute(
        select(CategoryGroup)
        .options(
            selectinload(CategoryGroup.members)
            .selectinload(CategoryGroupMember.category)
            .selectinload(Category.session)
        )
        .order_by(CategoryGroup.name)
    )
    groups = result.scalars().all()

    # Track which categories are in at least one group
    grouped_cat_ids: set[int] = set()

    group_data = []
    for g in groups:
        children = []
        for m in g.members:
            cat = m.category
            grouped_cat_ids.add(cat.id)

            mins_result = await db.execute(
                select(func.coalesce(func.sum(Observation.minutes), 0))
                .where(Observation.category_id == cat.id)
            )
            total_mins = int(mins_result.scalar())

            session_label = cat.session.label if cat.session else None

            children.append({
                "category_id": cat.id,
                "name": cat.display_name or cat.name,
                "merge_key": cat.name,
                "total_minutes": total_mins,
                "session_label": session_label,
            })

        if children:
            group_data.append({
                "group_id": g.id,
                "name": g.display_name or g.name,
                "color": g.color,
                "is_auto": g.is_auto,
                "categories": children,
                "total_minutes": sum(c["total_minutes"] for c in children),
            })

    # Ungrouped categories
    ungrouped_result = await db.execute(
        select(Category)
        .options(selectinload(Category.session))
        .where(Category.id.notin_(grouped_cat_ids)) if grouped_cat_ids
        else select(Category).options(selectinload(Category.session))
    )
    ungrouped = ungrouped_result.scalars().all()

    ungrouped_children = []
    for cat in ungrouped:
        mins_result = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .where(Observation.category_id == cat.id)
        )
        total_mins = int(mins_result.scalar())
        if total_mins > 0:
            session_label = cat.session.label if cat.session else None
            ungrouped_children.append({
                "category_id": cat.id,
                "name": cat.display_name or cat.name,
                "merge_key": cat.name,
                "total_minutes": total_mins,
                "session_label": session_label,
            })

    if ungrouped_children:
        group_data.append({
            "group_id": None,
            "name": "Other",
            "color": None,
            "is_auto": True,
            "categories": ungrouped_children,
            "total_minutes": sum(c["total_minutes"] for c in ungrouped_children),
        })

    # Compute deduplicated total (each category counted once)
    all_cat_minutes: dict[int, int] = {}
    for g in group_data:
        for c in g["categories"]:
            cat_id = c["category_id"]
            if cat_id not in all_cat_minutes:
                all_cat_minutes[cat_id] = c["total_minutes"]

    return {
        "groups": group_data,
        "total_minutes": sum(all_cat_minutes.values()),
    }
