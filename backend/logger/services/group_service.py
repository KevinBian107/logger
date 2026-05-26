"""Groups are the top-level semantic bucket: Research / Training / Personal / Courses.

Hierarchy:
    Group  → CategoryFamily → Category (per session)

A group has many families (FK: category_families.group_id). The bubble
visualization walks Groups → Families → Categories. There is no longer a
direct group↔category membership table; the chain is implicit through
family_id and group_id.

Old behavior — auto-generated "dept:foo / type:bar / project:baz" rows
in `category_groups` — has been removed. Migration code wipes those.
"""

from dataclasses import dataclass

from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from logger.models import (
    CategoryGroup, Category, CategoryFamily, Observation,
)


# ── Default group seed data ───────────────────────────────────────────────

@dataclass
class _SeedGroup:
    name: str            # slug, lowercased
    display_name: str
    color: str
    position: int
    description: str
    legacy_family_types: tuple[str, ...] = ()  # family_type values that map here


DEFAULT_SEED_GROUPS: list[_SeedGroup] = [
    _SeedGroup("research", "Research", "#3B82F6", 0, "Research projects spanning sessions",
               legacy_family_types=("research",)),
    _SeedGroup("training", "Training", "#EF4444", 1, "Physical training",
               legacy_family_types=()),  # mapped by family name, see migrate_family_types_to_groups
    _SeedGroup("personal", "Personal", "#F59E0B", 2, "Personal projects, reading, life",
               legacy_family_types=("personal",)),
    _SeedGroup("courses", "Courses", "#A855F7", 3, "Academic courses by department",
               legacy_family_types=("course",)),
]


async def seed_default_groups(db: AsyncSession) -> dict:
    """Insert default groups if they don't already exist. Idempotent."""
    # Wipe any legacy auto-generated rows from the previous design
    # (rows whose name starts with "dept:" / "type:" / "project:")
    legacy = await db.execute(
        delete(CategoryGroup).where(
            (CategoryGroup.name.like("dept:%"))
            | (CategoryGroup.name.like("type:%"))
            | (CategoryGroup.name.like("project:%"))
        )
    )
    legacy_deleted = legacy.rowcount

    created = 0
    for seed in DEFAULT_SEED_GROUPS:
        existing = await db.execute(
            select(CategoryGroup).where(CategoryGroup.name == seed.name)
        )
        if existing.scalar_one_or_none():
            continue
        db.add(CategoryGroup(
            name=seed.name,
            display_name=seed.display_name,
            description=seed.description,
            color=seed.color,
            position=seed.position,
            is_system=True,
            is_auto=False,
        ))
        created += 1

    await db.commit()
    return {"groups_created": created, "legacy_auto_groups_purged": legacy_deleted}


async def migrate_family_types_to_groups(db: AsyncSession) -> dict:
    """Backfill category_families.group_id from the legacy family_type column.

    Idempotent: only sets group_id where it's NULL. Special-cases:
      - family named 'training' → Training group (regardless of family_type)
      - family named 'cse 257' → merged into 'cse' (handled in fix_cse_257)
    """
    # Cache group ids
    groups_result = await db.execute(select(CategoryGroup))
    groups_by_name = {g.name: g for g in groups_result.scalars().all()}

    families_result = await db.execute(
        select(CategoryFamily).where(CategoryFamily.group_id.is_(None))
    )
    families = families_result.scalars().all()

    updated = 0
    for fam in families:
        target = None
        if fam.name == "training":
            target = groups_by_name.get("training")
        elif fam.family_type == "research":
            target = groups_by_name.get("research")
        elif fam.family_type == "course":
            target = groups_by_name.get("courses")
        elif fam.family_type == "personal":
            target = groups_by_name.get("personal")
        if target:
            fam.group_id = target.id
            updated += 1

    await db.commit()

    # Post-migration data fixes
    await fix_cse_257(db)
    await fold_into_salk(db, ["topomimic", "code2action"])
    await promote_multi_session_orphans(db)

    return {"families_migrated": updated}


async def fold_into_salk(db: AsyncSession, family_names: list[str]) -> dict:
    """Merge one or more existing families into the `salk` family.

    For each named family that exists: re-link its categories to salk, then
    delete the family (cascades to its match rules — replacement rules pointing
    to salk are seeded separately by family_service.seed_default_families_and_rules).
    Idempotent: skipped per-name once that family no longer exists.
    """
    salk = (await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == "salk")
    )).scalar_one_or_none()
    if not salk:
        return {"folded": 0, "reason": "salk family missing"}

    folded = 0
    relinked = 0
    for name in family_names:
        fam = (await db.execute(
            select(CategoryFamily).where(CategoryFamily.name == name)
        )).scalar_one_or_none()
        if not fam:
            continue
        result = await db.execute(
            update(Category).where(Category.family_id == fam.id).values(family_id=salk.id)
        )
        relinked += result.rowcount
        await db.delete(fam)
        folded += 1
    if folded:
        await db.commit()
    return {"folded": folded, "categories_relinked": relinked}


# ── One-off data corrections ──────────────────────────────────────────────

async def fix_cse_257(db: AsyncSession) -> dict:
    """Merge the 'cse 257' family into 'cse' and delete the redundant family.

    Idempotent: skipped once the cse_257 family no longer exists.
    """
    cse_257 = (await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == "cse 257")
    )).scalar_one_or_none()
    if not cse_257:
        return {"merged": 0, "deleted_family": False}

    cse = (await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == "cse")
    )).scalar_one_or_none()
    if not cse:
        return {"merged": 0, "deleted_family": False, "warning": "cse family missing"}

    # Re-link categories
    merge_result = await db.execute(
        update(Category).where(Category.family_id == cse_257.id).values(family_id=cse.id)
    )
    merged = merge_result.rowcount

    # Delete the redundant family (cascades to its match rules)
    await db.delete(cse_257)
    await db.commit()
    return {"merged": merged, "deleted_family": True}


async def promote_multi_session_orphans(db: AsyncSession) -> dict:
    """For categories named identically across 2+ sessions but with family_id IS NULL,
    create a family + exact match rule and link them. Assigns to the Research group
    by default (these are typically ongoing projects).

    Idempotent: skips display names that already have a family with the same exact rule.
    """
    from logger.models import FamilyMatchRule

    # Group orphans by display_name; require 2+ sessions
    result = await db.execute(
        select(Category.display_name, func.count(func.distinct(Category.session_id)))
        .where(Category.family_id.is_(None))
        .group_by(Category.display_name)
        .having(func.count(func.distinct(Category.session_id)) >= 2)
    )
    orphan_groups = result.all()

    research_group = (await db.execute(
        select(CategoryGroup).where(CategoryGroup.name == "research")
    )).scalar_one_or_none()
    research_group_id = research_group.id if research_group else None

    created_families = 0
    linked_categories = 0
    for display_name, _session_count in orphan_groups:
        pattern = display_name.strip().lower()
        # Skip if an exact rule already exists for this pattern
        existing_rule = await db.execute(
            select(FamilyMatchRule)
            .where(FamilyMatchRule.match_type == "exact")
            .where(FamilyMatchRule.pattern == pattern)
        )
        if existing_rule.scalar_one_or_none():
            continue

        family_name = pattern.replace(" ", "_")
        # Avoid colliding with an existing family name
        existing_family = await db.execute(
            select(CategoryFamily).where(CategoryFamily.name == family_name)
        )
        if existing_family.scalar_one_or_none():
            continue

        fam = CategoryFamily(
            name=family_name,
            display_name=display_name,
            family_type="research",
            group_id=research_group_id,
        )
        db.add(fam)
        await db.flush()
        db.add(FamilyMatchRule(family_id=fam.id, match_type="exact", pattern=pattern))
        created_families += 1

        # Link existing orphan categories with the same display name
        link_result = await db.execute(
            update(Category)
            .where(Category.family_id.is_(None))
            .where(Category.display_name == display_name)
            .values(family_id=fam.id)
        )
        linked_categories += link_result.rowcount

    await db.commit()
    return {"created_families": created_families, "linked_categories": linked_categories}


# ── CRUD ──────────────────────────────────────────────────────────────────

async def list_groups(db: AsyncSession) -> list[dict]:
    """Return all groups with family + minute counts."""
    result = await db.execute(
        select(CategoryGroup).order_by(CategoryGroup.position, CategoryGroup.name)
    )
    groups = result.scalars().all()

    out = []
    for g in groups:
        fam_count_result = await db.execute(
            select(func.count(CategoryFamily.id)).where(CategoryFamily.group_id == g.id)
        )
        mins_result = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .select_from(Observation)
            .join(Category, Observation.category_id == Category.id)
            .join(CategoryFamily, Category.family_id == CategoryFamily.id)
            .where(CategoryFamily.group_id == g.id)
        )
        out.append({
            "id": g.id,
            "name": g.name,
            "display_name": g.display_name,
            "description": g.description,
            "color": g.color,
            "position": g.position or 0,
            "is_system": bool(g.is_system),
            "family_count": fam_count_result.scalar() or 0,
            "total_minutes": int(mins_result.scalar() or 0),
        })
    return out


async def get_group(group_id: int, db: AsyncSession) -> dict | None:
    """Single group with families nested."""
    g = await db.get(CategoryGroup, group_id)
    if not g:
        return None

    fam_result = await db.execute(
        select(CategoryFamily).where(CategoryFamily.group_id == group_id).order_by(CategoryFamily.name)
    )
    families = fam_result.scalars().all()

    family_data = []
    for fam in families:
        mins_result = await db.execute(
            select(func.coalesce(func.sum(Observation.minutes), 0))
            .select_from(Observation)
            .join(Category, Observation.category_id == Category.id)
            .where(Category.family_id == fam.id)
        )
        cat_count_result = await db.execute(
            select(func.count(Category.id)).where(Category.family_id == fam.id)
        )
        family_data.append({
            "id": fam.id,
            "name": fam.name,
            "display_name": fam.display_name,
            "color": fam.color,
            "category_count": cat_count_result.scalar() or 0,
            "total_minutes": int(mins_result.scalar() or 0),
        })

    return {
        "id": g.id,
        "name": g.name,
        "display_name": g.display_name,
        "description": g.description,
        "color": g.color,
        "position": g.position or 0,
        "is_system": bool(g.is_system),
        "families": family_data,
    }


async def create_group(name: str, display_name: str | None, description: str | None,
                       color: str | None, db: AsyncSession) -> dict:
    g = CategoryGroup(
        name=name.strip().lower(),
        display_name=display_name or name,
        description=description,
        color=color,
        is_system=False,
        is_auto=False,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return {"id": g.id, "name": g.name, "display_name": g.display_name}


async def update_group(group_id: int, data: dict, db: AsyncSession) -> dict | None:
    g = await db.get(CategoryGroup, group_id)
    if not g:
        return None
    for key in ("display_name", "description", "color", "position"):
        if key in data and data[key] is not None:
            setattr(g, key, data[key])
    await db.commit()
    await db.refresh(g)
    return {"id": g.id, "name": g.name, "display_name": g.display_name}


async def delete_group(group_id: int, db: AsyncSession) -> bool:
    g = await db.get(CategoryGroup, group_id)
    if not g:
        return False
    if g.is_system:
        raise ValueError("Cannot delete a system group")
    await db.delete(g)  # FK on families.group_id is SET NULL
    await db.commit()
    return True


async def assign_family_to_group(family_id: int, group_id: int | None, db: AsyncSession) -> bool:
    fam = await db.get(CategoryFamily, family_id)
    if not fam:
        return False
    fam.group_id = group_id
    await db.commit()
    return True


# ── Bubble visualization data ─────────────────────────────────────────────

async def get_bubble_data(db: AsyncSession) -> dict:
    """Hierarchical data for the bubble viz: groups → families → categories.

    Returns a tree where each group lists its families, each family lists its
    distinct categories (deduplicated by display_name across sessions, with
    per-category total minutes summed across all sessions).
    """
    # Pre-fetch everything in a few queries
    groups_result = await db.execute(
        select(CategoryGroup).order_by(CategoryGroup.position, CategoryGroup.name)
    )
    groups = groups_result.scalars().all()

    families_result = await db.execute(
        select(CategoryFamily).order_by(CategoryFamily.name)
    )
    families = families_result.scalars().all()

    cats_result = await db.execute(
        select(Category)
        .options(selectinload(Category.session))
    )
    all_cats = cats_result.scalars().all()

    # Minute sums per category id (one query)
    mins_result = await db.execute(
        select(Observation.category_id, func.sum(Observation.minutes))
        .group_by(Observation.category_id)
    )
    cat_minutes: dict[int, int] = dict(mins_result.all())

    cats_by_family: dict[int, list[Category]] = {}
    cats_orphan: list[Category] = []
    for cat in all_cats:
        if cat.family_id is None:
            cats_orphan.append(cat)
        else:
            cats_by_family.setdefault(cat.family_id, []).append(cat)

    families_by_group: dict[int | None, list[CategoryFamily]] = {}
    for fam in families:
        families_by_group.setdefault(fam.group_id, []).append(fam)

    def serialize_family(fam: CategoryFamily) -> dict:
        cats = cats_by_family.get(fam.id, [])
        cat_entries = []
        for cat in cats:
            mins = int(cat_minutes.get(cat.id, 0) or 0)
            cat_entries.append({
                "category_id": cat.id,
                "name": cat.display_name or cat.name,
                "merge_key": cat.name,
                "session_id": cat.session_id,
                "session_label": cat.session.label if cat.session else None,
                "total_minutes": mins,
            })
        cat_entries.sort(key=lambda c: -c["total_minutes"])
        return {
            "family_id": fam.id,
            "name": fam.display_name or fam.name,
            "slug": fam.name,
            "color": fam.color,
            "total_minutes": sum(c["total_minutes"] for c in cat_entries),
            "categories": cat_entries,
        }

    group_entries = []
    for g in groups:
        fams = [serialize_family(f) for f in families_by_group.get(g.id, [])]
        fams.sort(key=lambda f: -f["total_minutes"])
        if not fams:
            continue
        group_entries.append({
            "group_id": g.id,
            "name": g.display_name or g.name,
            "slug": g.name,
            "color": g.color,
            "families": fams,
            "total_minutes": sum(f["total_minutes"] for f in fams),
        })

    # Families with no group + standalone orphan categories live under "Other"
    other_families = [serialize_family(f) for f in families_by_group.get(None, [])]
    other_families.sort(key=lambda f: -f["total_minutes"])

    orphan_entries = []
    for cat in cats_orphan:
        mins = int(cat_minutes.get(cat.id, 0) or 0)
        if mins == 0:
            continue
        orphan_entries.append({
            "category_id": cat.id,
            "name": cat.display_name or cat.name,
            "merge_key": cat.name,
            "session_id": cat.session_id,
            "session_label": cat.session.label if cat.session else None,
            "total_minutes": mins,
        })
    orphan_entries.sort(key=lambda c: -c["total_minutes"])

    if other_families or orphan_entries:
        other_payload = {
            "group_id": None,
            "name": "Other",
            "slug": "other",
            "color": None,
            "families": other_families,
            "ungrouped_categories": orphan_entries,
            "total_minutes": (
                sum(f["total_minutes"] for f in other_families)
                + sum(c["total_minutes"] for c in orphan_entries)
            ),
        }
        group_entries.append(other_payload)

    group_entries.sort(key=lambda g: -g["total_minutes"])

    return {
        "groups": group_entries,
        "total_minutes": sum(g["total_minutes"] for g in group_entries),
    }
