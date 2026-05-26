"""Family detection backed by the `family_match_rules` table.

Matching used to live in four hand-curated Python dicts (KNOWN_FAMILIES,
DEPARTMENT_FAMILIES, FAMILY_TYPES, FAMILY_COLORS). Those were Kevin-specific
data baked into source. They're now seeded into the DB on first init_db()
and editable via /api/family-rules — so any user can configure their own
project list without touching code.

Match types:
  - "exact":  lowercased category display name equals the pattern
              (e.g. "training" matches "Training")
  - "prefix": pattern matches the department slug of "<dept> <num>"
              (e.g. "cogs" matches "COGS 118C" via the COURSE_PREFIX regex)

Exact rules win over prefix rules (mirrors prior behavior where "cse 257"
took precedence over the "cse" department rule).
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import CategoryFamily, FamilyMatchRule

COURSE_PREFIX = re.compile(r"^([a-zA-Z]+)\s+\d")


# ── Seed data (only used on first init_db()) ──────────────────────────────

@dataclass
class _SeedFamily:
    name: str
    display_name: str
    family_type: str
    color: str | None = None
    exact_patterns: list[str] = field(default_factory=list)
    prefix_patterns: list[str] = field(default_factory=list)


DEFAULT_SEED_FAMILIES: list[_SeedFamily] = [
    # Personal/recurring projects (exact match)
    _SeedFamily("training",      "Training",          "personal", "#EF4444", exact_patterns=["training"]),
    _SeedFamily("pp",            "Personal Projects", "personal", "#F59E0B", exact_patterns=["pp"]),
    _SeedFamily("reading",       "Reading",           "personal", "#10B981", exact_patterns=["reading"]),
    # Research projects
    # Salk Research absorbs TopoMIMIC and Code2Action — these are Salk-lab projects,
    # not standalone research families. The exact-patterns list ensures future imports
    # of categories named "TopoMIMIC" or "Code2Action" auto-link to Salk.
    _SeedFamily("salk",          "Salk Research",     "research", "#3B82F6", exact_patterns=["salk", "topomimic", "code2action"]),
    _SeedFamily("mpi",           "MPI Research",      "research", "#8B5CF6", exact_patterns=["mpi"]),
    _SeedFamily("swl",           "SWL Research",      "research", "#06B6D4", exact_patterns=["swl"]),
    _SeedFamily("fmp",           "FMP Research",      "research", "#EC4899", exact_patterns=["fmp"]),
    _SeedFamily("rplh",          "RPLH",              "research", None,       exact_patterns=["rplh"]),
    _SeedFamily("data science",  "Data Science",      "research", None,       exact_patterns=["data science"]),
    _SeedFamily("fd",            "Future Directions", "research", None,       exact_patterns=["fd"]),
    _SeedFamily("enigmorphic",   "Enigmorphic",       "research", "#06B6D4",  exact_patterns=["enigmorphic"]),
    # A specific course pinned by exact match (precedence over the "cse" dept rule)
    _SeedFamily("cse 257",       "CSE 257",           "course",   "#6366F1", exact_patterns=["cse 257"]),
    # Department prefixes (course families)
    _SeedFamily("cogs", "COGS", "course", "#A855F7", prefix_patterns=["cogs"]),
    _SeedFamily("cse",  "CSE",  "course", "#6366F1", prefix_patterns=["cse"]),
    _SeedFamily("dsc",  "DSC",  "course", "#0EA5E9", prefix_patterns=["dsc"]),
    _SeedFamily("math", "Math", "course", "#F97316", prefix_patterns=["math"]),
    _SeedFamily("psyc", "PSYC", "course", "#D946EF", prefix_patterns=["psyc"]),
    _SeedFamily("bild", "BILD", "course", "#84CC16", prefix_patterns=["bild"]),
    _SeedFamily("ece",  "ECE",  "course", "#14B8A6", prefix_patterns=["ece"]),
    _SeedFamily("mus",  "MUS",  "course", "#F43F5E", prefix_patterns=["mus"]),
    _SeedFamily("chem", "CHEM", "course", "#22C55E", prefix_patterns=["chem"]),
    _SeedFamily("doc",  "DOC",  "course", "#78716C", prefix_patterns=["doc"]),
    _SeedFamily("hild", "HILD", "course", "#78716C", prefix_patterns=["hild"]),
]


async def link_orphans_to_seed_families(db: AsyncSession) -> dict:
    """Find categories with family_id IS NULL whose display name matches an
    exact_pattern of any seed family, and link them.

    Use case: when a new seed family is added (e.g. Enigmorphic), any existing
    orphan categories with that name should be retroactively linked to the new
    family. Without this, only future imports would benefit from the seed.

    Idempotent: only touches categories where family_id is currently NULL.
    """
    from logger.models import Category  # avoid circular import at module level

    # Build pattern → family_id from the rules in the DB (rules already point
    # at the right families post-seed; using the DB as source of truth here
    # rather than the seed list keeps this in sync with any user-added rules too).
    rules_result = await db.execute(
        select(FamilyMatchRule).where(FamilyMatchRule.match_type == "exact")
    )
    pattern_to_family: dict[str, int] = {}
    for rule in rules_result.scalars().all():
        pattern_to_family[rule.pattern] = rule.family_id

    if not pattern_to_family:
        return {"linked": 0}

    orphans_result = await db.execute(
        select(Category).where(Category.family_id.is_(None))
    )
    orphans = orphans_result.scalars().all()

    linked = 0
    for cat in orphans:
        display = (cat.display_name or cat.name or "").strip().lower()
        if display in pattern_to_family:
            cat.family_id = pattern_to_family[display]
            linked += 1

    if linked:
        await db.commit()
    return {"linked": linked}


async def seed_default_families_and_rules(db: AsyncSession) -> dict:
    """Idempotent seed. Creates default families/rules that don't already exist.

    Run from init_db on every startup. Safe to re-run:
      - Existing families are left untouched (user edits preserved).
      - Existing rules (by unique match_type+pattern) are not duplicated.
    """
    created_families = 0
    created_rules = 0

    for seed in DEFAULT_SEED_FAMILIES:
        # Find or create family by name
        existing = await db.execute(
            select(CategoryFamily).where(CategoryFamily.name == seed.name)
        )
        family = existing.scalar_one_or_none()
        if not family:
            family = CategoryFamily(
                name=seed.name,
                display_name=seed.display_name,
                family_type=seed.family_type,
                color=seed.color,
            )
            db.add(family)
            await db.flush()
            created_families += 1

        for pattern in seed.exact_patterns:
            if await _rule_exists(db, "exact", pattern):
                continue
            db.add(FamilyMatchRule(family_id=family.id, match_type="exact", pattern=pattern))
            created_rules += 1
        for pattern in seed.prefix_patterns:
            if await _rule_exists(db, "prefix", pattern):
                continue
            db.add(FamilyMatchRule(family_id=family.id, match_type="prefix", pattern=pattern))
            created_rules += 1

    await db.commit()
    return {"families_seeded": created_families, "rules_seeded": created_rules}


async def _rule_exists(db: AsyncSession, match_type: str, pattern: str) -> bool:
    result = await db.execute(
        select(FamilyMatchRule.id)
        .where(FamilyMatchRule.match_type == match_type)
        .where(FamilyMatchRule.pattern == pattern)
    )
    return result.scalar_one_or_none() is not None


# ── Runtime detection ─────────────────────────────────────────────────────

@dataclass
class LoadedRules:
    """Snapshot of all match rules + family display names, used for in-memory detection."""
    exact: dict[str, int]                  # lowercased pattern -> family_id
    prefix: dict[str, int]                 # dept slug -> family_id
    family_display: dict[int, str]         # family_id -> display_name


async def load_match_rules(db: AsyncSession) -> LoadedRules:
    """Read all rules + family display names in two queries. Cheap; called once per import."""
    rules_result = await db.execute(select(FamilyMatchRule))
    fam_result = await db.execute(select(CategoryFamily.id, CategoryFamily.display_name, CategoryFamily.name))

    exact: dict[str, int] = {}
    prefix: dict[str, int] = {}
    for rule in rules_result.scalars():
        if rule.match_type == "exact":
            exact[rule.pattern] = rule.family_id
        elif rule.match_type == "prefix":
            prefix[rule.pattern] = rule.family_id

    family_display: dict[int, str] = {}
    for fid, display, name in fam_result.all():
        family_display[fid] = display or name

    return LoadedRules(exact=exact, prefix=prefix, family_display=family_display)


def detect_family(category_name: str, rules: LoadedRules) -> int | None:
    """Return family_id for a category display name, or None if no rule matches.

    Exact rules are checked first; prefix rules use the COURSE_PREFIX regex
    to extract the department slug from "<dept> <num>" style names.
    """
    name_lower = category_name.strip().lower()

    if name_lower in rules.exact:
        return rules.exact[name_lower]

    m = COURSE_PREFIX.match(name_lower)
    if m:
        dept = m.group(1)
        if dept in rules.prefix:
            return rules.prefix[dept]

    return None


async def detect_family_by_name(category_name: str, db: AsyncSession) -> int | None:
    """Convenience: load rules + detect in one call. Use sparingly (1 detect = 2 queries).

    For batch detection (import flow), call load_match_rules() once and reuse.
    """
    rules = await load_match_rules(db)
    return detect_family(category_name, rules)


async def get_family_by_id(family_id: int, db: AsyncSession) -> CategoryFamily | None:
    return await db.get(CategoryFamily, family_id)


async def get_or_create_family_by_name(
    name: str, db: AsyncSession, *, display_name: str | None = None, family_type: str = "other"
) -> CategoryFamily:
    """Look up a family by name; create a barebones one if it doesn't exist.

    Used when a caller explicitly names a family (e.g., the categories router
    accepts a `family` string from the UI). Has no knowledge of rules — the
    user can add rules via /api/family-rules afterwards.
    """
    result = await db.execute(
        select(CategoryFamily).where(CategoryFamily.name == name.lower())
    )
    family = result.scalar_one_or_none()
    if family:
        return family
    family = CategoryFamily(
        name=name.lower(),
        display_name=display_name or name.title(),
        family_type=family_type,
    )
    db.add(family)
    await db.flush()
    return family
