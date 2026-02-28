"""Family detection for categories.

Category names are now clean display names (e.g., "Training", "COGS 118C", "PP").
Family detection works by matching the category name (case-insensitive) against
known project names or extracting the department prefix from course codes.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import CategoryFamily

# Exact-match families (projects, recurring activities)
# Keys are lowercase versions of the display names
KNOWN_FAMILIES: dict[str, str] = {
    "training": "Training",
    "salk": "Salk Research",
    "mpi": "MPI Research",
    "pp": "Personal Projects",
    "reading": "Reading",
    "swl": "SWL Research",
    "fmp": "FMP Research",
    "cse 257": "CSE 257",
    "rplh": "RPLH",
    "data science": "Data Science",
    "fd": "Future Directions",
}

# Department-prefix families (courses grouped by department)
DEPARTMENT_FAMILIES: dict[str, str] = {
    "cogs": "COGS",
    "cse": "CSE",
    "dsc": "DSC",
    "math": "Math",
    "psyc": "PSYC",
    "bild": "BILD",
    "ece": "ECE",
    "mus": "MUS",
    "chem": "CHEM",
    "doc": "DOC",
    "hild": "HILD",
}

FAMILY_TYPES: dict[str, str] = {
    "training": "personal",
    "salk": "research",
    "mpi": "research",
    "pp": "personal",
    "reading": "personal",
    "swl": "research",
    "fmp": "research",
    "cse 257": "course",
    "rplh": "research",
    "data science": "research",
    "fd": "research",
    "cogs": "course",
    "cse": "course",
    "dsc": "course",
    "math": "course",
    "psyc": "course",
    "bild": "course",
    "ece": "course",
    "mus": "course",
    "chem": "course",
    "doc": "course",
    "hild": "course",
}

FAMILY_COLORS: dict[str, str] = {
    "training": "#EF4444",
    "salk": "#3B82F6",
    "mpi": "#8B5CF6",
    "pp": "#F59E0B",
    "reading": "#10B981",
    "swl": "#06B6D4",
    "fmp": "#EC4899",
    "cse 257": "#6366F1",
    "cogs": "#A855F7",
    "cse": "#6366F1",
    "dsc": "#0EA5E9",
    "math": "#F97316",
    "psyc": "#D946EF",
    "bild": "#84CC16",
    "ece": "#14B8A6",
    "mus": "#F43F5E",
    "chem": "#22C55E",
    "doc": "#78716C",
    "hild": "#78716C",
}


def detect_family(category_name: str) -> str | None:
    """Match a clean category name against known families or department prefixes.

    category_name is already a clean display name (e.g., "Training", "COGS 118C").
    """
    name_lower = category_name.strip().lower()

    # Exact match against known families
    if name_lower in KNOWN_FAMILIES:
        return name_lower

    # Department prefix match: "COGS 118C" → "cogs", "MATH 20B" → "math"
    match = re.match(r"^([a-zA-Z]+)\s+\d", name_lower)
    if match:
        dept = match.group(1)
        # Don't re-match "cse 257" as "cse" — it already matched exactly above
        if dept in DEPARTMENT_FAMILIES:
            return dept

    return None


async def get_or_create_family(
    family_key: str, db: AsyncSession
) -> CategoryFamily:
    """Get existing family or create a new one."""
    result = await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == family_key)
    )
    family = result.scalar_one_or_none()
    if family:
        return family

    all_names = {**KNOWN_FAMILIES, **DEPARTMENT_FAMILIES}
    family = CategoryFamily(
        name=family_key,
        display_name=all_names.get(family_key, family_key.title()),
        family_type=FAMILY_TYPES.get(family_key, "other"),
        color=FAMILY_COLORS.get(family_key),
    )
    db.add(family)
    await db.flush()
    return family
