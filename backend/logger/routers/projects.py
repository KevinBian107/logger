"""Projects router: family timeline, research projects, and AI-generated descriptions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import (
    AIDescription, CategoryFamily, Category, Session, TextEntry, GitHubRepoLink,
)
from logger.schemas import (
    ProjectSessionEntry,
    ProjectFamilyTimeline,
    ProjectTimelineResponse,
    DescribeRequest,
    DescribeResponse,
    ResearchFamilyListItem,
    ResearchFamiliesResponse,
    ResearchFamilyDetail,
    ResearchSessionEntry,
    GitHubRepoInfo,
    GitHubSearchResult,
    GitHubLinkRequest,
    GitHubUnlinkRequest,
    EnrichedDescribeRequest,
    EnrichedDescribeResponse,
    GroupFamilyItem,
    GroupSummary,
    GroupDetailResponse,
    GroupListResponse,
)
from logger.services.api_key_service import get_api_key, has_api_key
from logger.services import github_service

router = APIRouter(prefix="/projects", tags=["projects"])

SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}


def _session_sort_key(row: dict) -> tuple[int, int]:
    return (row["year"], SEASON_ORDER.get(row["season"].lower(), 4))


# ── Legacy endpoints (backward compat) ──────────────────

@router.get("/timeline", response_model=ProjectTimelineResponse)
async def get_timeline(db: AsyncSession = Depends(get_db)):
    """Return family timeline data from v_family_totals view."""
    result = await db.execute(text(
        "SELECT family_id, family_name, display_name, color, "
        "session_id, session_label, year, season, total_minutes, active_days "
        "FROM v_family_totals"
    ))
    rows = [dict(r._mapping) for r in result]

    family_ids = {r["family_id"] for r in rows}
    family_types: dict[int, str | None] = {}
    if family_ids:
        ft_result = await db.execute(
            select(CategoryFamily.id, CategoryFamily.family_type)
            .where(CategoryFamily.id.in_(family_ids))
        )
        family_types = {r.id: r.family_type for r in ft_result}

    desc_result = await db.execute(select(AIDescription))
    descriptions: dict[tuple[int, int], str] = {
        (d.family_id, d.session_id): d.description
        for d in desc_result.scalars().all()
    }

    sessions_map: dict[int, dict] = {}
    for r in rows:
        sid = r["session_id"]
        if sid not in sessions_map:
            sessions_map[sid] = {
                "id": sid,
                "label": r["session_label"],
                "year": r["year"],
                "season": r["season"],
            }
    all_sessions = sorted(sessions_map.values(), key=_session_sort_key)

    families_map: dict[int, dict] = {}
    for r in rows:
        fid = r["family_id"]
        if fid not in families_map:
            families_map[fid] = {
                "family_id": fid,
                "family_name": r["family_name"],
                "display_name": r["display_name"],
                "family_type": family_types.get(fid),
                "color": r["color"],
                "total_minutes": 0,
                "sessions": [],
            }

        ai_desc = descriptions.get((fid, r["session_id"]))
        families_map[fid]["sessions"].append(
            ProjectSessionEntry(
                session_id=r["session_id"],
                session_label=r["session_label"],
                year=r["year"],
                season=r["season"],
                total_minutes=r["total_minutes"],
                active_days=r["active_days"],
                ai_description=ai_desc,
            )
        )
        families_map[fid]["total_minutes"] += r["total_minutes"]

    for f in families_map.values():
        f["sessions"].sort(key=lambda s: (s.year, SEASON_ORDER.get(s.season.lower(), 4)))

    families_list = sorted(families_map.values(), key=lambda f: f["total_minutes"], reverse=True)
    families = [ProjectFamilyTimeline(**f) for f in families_list]

    return ProjectTimelineResponse(families=families, sessions=all_sessions)


@router.post("/describe", response_model=DescribeResponse)
async def describe_family_session(
    req: DescribeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI description for a family+session pair (legacy)."""
    if not await has_api_key(db):
        raise HTTPException(status_code=400, detail="API key not configured. Add one in Settings.")

    family = await db.get(CategoryFamily, req.family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    session = await db.get(Session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cat_result = await db.execute(
        select(Category.name, Category.display_name)
        .where(Category.family_id == req.family_id)
        .where(Category.session_id == req.session_id)
    )
    categories = [r.display_name or r.name for r in cat_result]

    totals_result = await db.execute(text(
        "SELECT total_minutes, active_days FROM v_family_totals "
        "WHERE family_id = :fid AND session_id = :sid"
    ), {"fid": req.family_id, "sid": req.session_id})
    totals_row = totals_result.first()
    if not totals_row:
        raise HTTPException(status_code=404, detail="No data for this family+session")

    total_minutes = totals_row.total_minutes
    active_days = totals_row.active_days
    hours = total_minutes // 60
    mins = total_minutes % 60

    session_label = session.label or f"{session.season.title()} {session.year}"
    family_display = family.display_name or family.name

    prompt = (
        f"Write a 1-2 sentence summary of what this person likely worked on.\n\n"
        f"Project: {family_display}\n"
        f"Session: {session_label}\n"
        f"Categories: {', '.join(categories) if categories else family_display}\n"
        f"Total time: {hours}h {mins}m across {active_days} active days\n"
        f"Date range: {session.start_date or 'unknown'} to {session.end_date or 'unknown'}\n\n"
        f"Be specific and concise. Do not speculate beyond what the data shows."
    )

    api_key = await get_api_key(db)

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        description = response.content[0].text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    existing = await db.execute(
        select(AIDescription)
        .where(AIDescription.family_id == req.family_id)
        .where(AIDescription.session_id == req.session_id)
    )
    ai_desc = existing.scalar_one_or_none()
    if ai_desc:
        ai_desc.description = description
        ai_desc.model_used = "claude-haiku-4-5-20251001"
    else:
        ai_desc = AIDescription(
            family_id=req.family_id,
            session_id=req.session_id,
            description=description,
            model_used="claude-haiku-4-5-20251001",
        )
        db.add(ai_desc)
    await db.commit()

    return DescribeResponse(
        family_id=req.family_id,
        session_id=req.session_id,
        description=description,
    )


GROUP_LABELS = {
    "research": "Research",
    "course": "Courses",
    "personal": "Personal",
    "other": "Other",
}


# ── Group endpoints ──────────────────────────────────────

@router.get("/groups", response_model=GroupListResponse)
async def get_project_groups(db: AsyncSession = Depends(get_db)):
    """List available groups with summary stats."""
    result = await db.execute(text(
        "SELECT family_id, total_minutes, session_id FROM v_family_totals"
    ))
    rows = [dict(r._mapping) for r in result]

    family_ids = {r["family_id"] for r in rows}
    family_types: dict[int, str] = {}
    if family_ids:
        ft_result = await db.execute(
            select(CategoryFamily.id, CategoryFamily.family_type)
            .where(CategoryFamily.id.in_(family_ids))
        )
        family_types = {r.id: (r.family_type or "other") for r in ft_result}

    # Aggregate by group type
    group_stats: dict[str, dict] = {}
    for r in rows:
        gt = family_types.get(r["family_id"], "other")
        if gt not in group_stats:
            group_stats[gt] = {"total_minutes": 0, "family_ids": set()}
        group_stats[gt]["total_minutes"] += r["total_minutes"]
        group_stats[gt]["family_ids"].add(r["family_id"])

    groups = sorted(
        [
            GroupSummary(
                group_type=gt,
                label=GROUP_LABELS.get(gt, gt.title()),
                family_count=len(stats["family_ids"]),
                total_minutes=stats["total_minutes"],
            )
            for gt, stats in group_stats.items()
        ],
        key=lambda g: g.total_minutes,
        reverse=True,
    )

    username = await github_service.get_github_username(db)
    return GroupListResponse(groups=groups, github_username=username)


@router.get("/group/{group_type}", response_model=GroupDetailResponse)
async def get_group_detail(
    group_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all families in a group type with full session detail."""
    result = await db.execute(text(
        "SELECT family_id, family_name, display_name, color, "
        "session_id, session_label, year, season, total_minutes, active_days "
        "FROM v_family_totals"
    ))
    rows = [dict(r._mapping) for r in result]

    # Filter by group type
    family_ids = {r["family_id"] for r in rows}
    family_types: dict[int, str] = {}
    if family_ids:
        ft_result = await db.execute(
            select(CategoryFamily.id, CategoryFamily.family_type)
            .where(CategoryFamily.id.in_(family_ids))
        )
        family_types = {r.id: (r.family_type or "other") for r in ft_result}

    filtered_rows = [
        r for r in rows if family_types.get(r["family_id"]) == group_type
    ]

    # AI descriptions
    desc_result = await db.execute(select(AIDescription))
    descriptions: dict[tuple[int, int], str] = {
        (d.family_id, d.session_id): d.description
        for d in desc_result.scalars().all()
    }

    # Text entry counts
    all_session_ids = list({r["session_id"] for r in filtered_rows})
    text_counts: dict[int, int] = {}
    if all_session_ids:
        tc_result = await db.execute(
            select(TextEntry.session_id, func.count(TextEntry.id))
            .where(TextEntry.session_id.in_(all_session_ids))
            .group_by(TextEntry.session_id)
        )
        text_counts = {r[0]: r[1] for r in tc_result}

    # GitHub links (multi-repo: family_id -> list of repo_full_names)
    link_result = await db.execute(select(GitHubRepoLink))
    all_links = link_result.scalars().all()
    linked_families: dict[int, list[str]] = {}
    for link in all_links:
        linked_families.setdefault(link.family_id, []).append(link.repo_full_name)

    username = await github_service.get_github_username(db)

    # Build families
    families_map: dict[int, dict] = {}
    for r in filtered_rows:
        fid = r["family_id"]
        if fid not in families_map:
            families_map[fid] = {
                "family_id": fid,
                "family_name": r["family_name"],
                "display_name": r["display_name"],
                "color": r["color"],
                "total_minutes": 0,
                "sessions": [],
            }

        families_map[fid]["sessions"].append(
            ResearchSessionEntry(
                session_id=r["session_id"],
                session_label=r["session_label"],
                year=r["year"],
                season=r["season"],
                total_minutes=r["total_minutes"],
                active_days=r["active_days"],
                ai_description=descriptions.get((fid, r["session_id"])),
                text_entries_count=text_counts.get(r["session_id"], 0),
            )
        )
        families_map[fid]["total_minutes"] += r["total_minutes"]

    # Sort sessions within each family, then resolve GitHub info
    families: list[GroupFamilyItem] = []
    for f in sorted(families_map.values(), key=lambda x: x["total_minutes"], reverse=True):
        f["sessions"].sort(
            key=lambda s: (s.year, SEASON_ORDER.get(s.season.lower(), 4))
        )

        fid = f["family_id"]
        repo_names = linked_families.get(fid, [])
        github_repos = []
        for rn in repo_names:
            cached = await github_service.get_cached_repo_info(rn, db)
            if cached:
                github_repos.append(GitHubRepoInfo(**cached))

        families.append(GroupFamilyItem(
            family_id=f["family_id"],
            family_name=f["family_name"],
            display_name=f["display_name"],
            color=f["color"],
            total_minutes=f["total_minutes"],
            sessions=f["sessions"],
            github_repos=github_repos,
            linked_repo_count=len(repo_names),
        ))

    return GroupDetailResponse(
        group_type=group_type,
        label=GROUP_LABELS.get(group_type, group_type.title()),
        families=families,
        github_username=username,
    )


# ── Research endpoints (kept for backward compat) ────────

@router.get("/research", response_model=ResearchFamiliesResponse)
async def get_research_families(db: AsyncSession = Depends(get_db)):
    """List research families only with summary info."""
    result = await db.execute(text(
        "SELECT family_id, family_name, display_name, color, "
        "session_id, total_minutes "
        "FROM v_family_totals"
    ))
    rows = [dict(r._mapping) for r in result]

    # Get family types
    family_ids = {r["family_id"] for r in rows}
    family_types: dict[int, str | None] = {}
    if family_ids:
        ft_result = await db.execute(
            select(CategoryFamily.id, CategoryFamily.family_type)
            .where(CategoryFamily.id.in_(family_ids))
        )
        family_types = {r.id: r.family_type for r in ft_result}

    # Get linked repos
    link_result = await db.execute(select(GitHubRepoLink))
    linked_families = {link.family_id for link in link_result.scalars().all()}

    # Build research-only families
    families_map: dict[int, dict] = {}
    for r in rows:
        fid = r["family_id"]
        if family_types.get(fid) != "research":
            continue
        if fid not in families_map:
            families_map[fid] = {
                "family_id": fid,
                "family_name": r["family_name"],
                "display_name": r["display_name"],
                "color": r["color"],
                "total_minutes": 0,
                "session_ids": set(),
                "github_linked": fid in linked_families,
            }
        families_map[fid]["total_minutes"] += r["total_minutes"]
        families_map[fid]["session_ids"].add(r["session_id"])

    families = sorted(
        [
            ResearchFamilyListItem(
                family_id=f["family_id"],
                family_name=f["family_name"],
                display_name=f["display_name"],
                color=f["color"],
                total_minutes=f["total_minutes"],
                session_count=len(f["session_ids"]),
                github_linked=f["github_linked"],
            )
            for f in families_map.values()
        ],
        key=lambda x: x.total_minutes,
        reverse=True,
    )

    username = await github_service.get_github_username(db)

    return ResearchFamiliesResponse(families=families, github_username=username)


@router.get("/research/{family_id}", response_model=ResearchFamilyDetail)
async def get_research_family_detail(
    family_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Full detail for one research family with sessions and GitHub info."""
    family = await db.get(CategoryFamily, family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    # Get session data from view
    result = await db.execute(text(
        "SELECT session_id, session_label, year, season, total_minutes, active_days "
        "FROM v_family_totals WHERE family_id = :fid"
    ), {"fid": family_id})
    rows = [dict(r._mapping) for r in result]

    if not rows:
        raise HTTPException(status_code=404, detail="No data for this family")

    # Get AI descriptions
    desc_result = await db.execute(
        select(AIDescription)
        .where(AIDescription.family_id == family_id)
    )
    descriptions = {
        d.session_id: d.description for d in desc_result.scalars().all()
    }

    # Count text entries per session
    text_counts: dict[int, int] = {}
    session_ids = [r["session_id"] for r in rows]
    if session_ids:
        tc_result = await db.execute(
            select(TextEntry.session_id, func.count(TextEntry.id))
            .where(TextEntry.session_id.in_(session_ids))
            .group_by(TextEntry.session_id)
        )
        text_counts = {r[0]: r[1] for r in tc_result}

    # Build sessions list
    sessions = sorted(
        [
            ResearchSessionEntry(
                session_id=r["session_id"],
                session_label=r["session_label"],
                year=r["year"],
                season=r["season"],
                total_minutes=r["total_minutes"],
                active_days=r["active_days"],
                ai_description=descriptions.get(r["session_id"]),
                text_entries_count=text_counts.get(r["session_id"], 0),
            )
            for r in rows
        ],
        key=lambda s: (s.year, SEASON_ORDER.get(s.season.lower(), 4)),
    )

    total_minutes = sum(s.total_minutes for s in sessions)

    # GitHub info (multi-repo)
    linked_repos = await github_service.get_linked_repos(family_id, db)
    github_repos: list[GitHubRepoInfo] = []

    for repo_full_name in linked_repos:
        cached = await github_service.get_cached_repo_info(repo_full_name, db)
        if cached:
            if not cached.get("readme_excerpt"):
                details = await github_service.fetch_repo_details(repo_full_name, db)
                if details:
                    cached["readme_excerpt"] = details["readme_excerpt"]
                    cached["recent_commits"] = details["recent_commits"]
            github_repos.append(GitHubRepoInfo(**cached))
        else:
            details = await github_service.fetch_repo_details(repo_full_name, db)
            if details:
                github_repos.append(GitHubRepoInfo(
                    full_name=repo_full_name,
                    name=repo_full_name.split("/")[-1],
                    readme_excerpt=details["readme_excerpt"],
                    recent_commits=details["recent_commits"],
                ))

    return ResearchFamilyDetail(
        family_id=family_id,
        family_name=family.name,
        display_name=family.display_name,
        color=family.color,
        total_minutes=total_minutes,
        sessions=sessions,
        github_repos=github_repos,
        linked_repo_count=len(linked_repos),
    )


@router.post("/describe/enriched", response_model=EnrichedDescribeResponse)
async def describe_enriched(
    req: EnrichedDescribeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate an enriched AI research narrative for a family+session pair."""
    if not await has_api_key(db):
        raise HTTPException(
            status_code=400,
            detail="API key not configured. Add one in Settings.",
        )

    family = await db.get(CategoryFamily, req.family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    session = await db.get(Session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get totals
    totals_result = await db.execute(text(
        "SELECT total_minutes, active_days FROM v_family_totals "
        "WHERE family_id = :fid AND session_id = :sid"
    ), {"fid": req.family_id, "sid": req.session_id})
    totals_row = totals_result.first()
    if not totals_row:
        raise HTTPException(status_code=404, detail="No data for this family+session")

    total_minutes = totals_row.total_minutes
    active_days = totals_row.active_days
    hours = total_minutes // 60
    mins = total_minutes % 60

    session_label = session.label or f"{session.season.title()} {session.year}"
    family_display = family.display_name or family.name

    # Get category names for this family in this session (used for text filtering)
    cat_result = await db.execute(
        select(Category.name, Category.display_name)
        .where(Category.family_id == req.family_id)
        .where(Category.session_id == req.session_id)
    )
    category_names = []
    search_terms = set()
    for r in cat_result:
        cat_name = r.display_name or r.name
        category_names.append(cat_name)
        # Build search terms: full name + key parts
        search_terms.add(cat_name.lower())
        # Also add family name and individual words >2 chars
        search_terms.add(family.name.lower())
        if family.display_name:
            for word in family.display_name.lower().split():
                if len(word) > 2:
                    search_terms.add(word)

    # Get dates where this family had observations (not all session dates)
    active_dates_result = await db.execute(text(
        "SELECT DISTINCT dr.date "
        "FROM observations o "
        "JOIN categories c ON o.category_id = c.id "
        "JOIN daily_records dr ON o.daily_record_id = dr.id "
        "WHERE c.family_id = :fid AND c.session_id = :sid"
    ), {"fid": req.family_id, "sid": req.session_id})
    active_dates = {r[0] for r in active_dates_result}

    # Get text entries only for active dates
    text_context = ""
    if active_dates:
        text_result = await db.execute(
            select(TextEntry)
            .where(TextEntry.session_id == req.session_id)
            .where(TextEntry.date.in_(active_dates))
            .order_by(TextEntry.date)
        )
        text_entries = text_result.scalars().all()

        snippets = []
        for te in text_entries:
            # Extract only relevant parts from study_materials
            relevant_parts = []
            if te.study_materials:
                # study_materials is comma-separated like "salk lab (180m), mus 8 (60m), ..."
                for item in te.study_materials.split(","):
                    item_stripped = item.strip()
                    item_lower = item_stripped.lower()
                    if any(term in item_lower for term in search_terms):
                        relevant_parts.append(item_stripped)

            # Also check notes for relevance
            relevant_notes = ""
            if te.notes:
                notes_lower = te.notes.lower()
                if any(term in notes_lower for term in search_terms):
                    relevant_notes = te.notes

            if relevant_parts or relevant_notes:
                parts = []
                if relevant_parts:
                    parts.append(", ".join(relevant_parts))
                if relevant_notes:
                    parts.append(relevant_notes)
                snippets.append(f"  - {te.date}: {'; '.join(parts)}")

        if snippets:
            text_context = (
                f"\n\nDaily log entries mentioning {family_display}:\n"
                + "\n".join(snippets[:20])
            )

    # GitHub context (multi-repo)
    github_context = ""
    github_context_used = False
    if req.include_github:
        linked_repos = await github_service.get_linked_repos(req.family_id, db)

        for repo_full_name in linked_repos:
            cached = await github_service.get_cached_repo_info(
                repo_full_name, db
            )
            if cached:
                github_context_used = True
                github_context += f"\n\nGitHub repository: {repo_full_name}"
                if cached.get("description"):
                    github_context += f"\nRepo description: {cached['description']}"
                if cached.get("readme_excerpt"):
                    excerpt = cached["readme_excerpt"][:600]
                    github_context += f"\nREADME excerpt:\n{excerpt}"
                if cached.get("recent_commits"):
                    commits = cached["recent_commits"][:5]
                    commit_lines = [
                        f"  - {c.get('sha', '')}: {c.get('message', '')}"
                        for c in commits
                    ]
                    github_context += "\nRecent commits:\n" + "\n".join(commit_lines)

    categories_str = ", ".join(category_names) if category_names else family_display

    prompt = (
        f"Write a 3-5 sentence narrative about ONLY the project \"{family_display}\" during this session. "
        f"Focus on what was done specifically for this project. "
        f"Do NOT mention other projects or unrelated activities. "
        f"Do NOT just restate hours — describe the work.\n\n"
        f"Project: {family_display}\n"
        f"Categories logged under this project: {categories_str}\n"
        f"Session: {session_label}\n"
        f"Total time on this project: {hours}h {mins}m across {active_days} active days\n"
        f"Date range: {session.start_date or 'unknown'} to {session.end_date or 'unknown'}"
        f"{text_context}"
        f"{github_context}\n\n"
        f"Write ONLY about \"{family_display}\". Be specific based on the available context. "
        f"If the log entries don't provide enough detail, write a brief factual summary of the time spent."
    )

    api_key = await get_api_key(db)

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        description = response.content[0].text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    # Upsert AIDescription
    existing = await db.execute(
        select(AIDescription)
        .where(AIDescription.family_id == req.family_id)
        .where(AIDescription.session_id == req.session_id)
    )
    ai_desc = existing.scalar_one_or_none()
    if ai_desc:
        ai_desc.description = description
        ai_desc.model_used = "claude-haiku-4-5-20251001"
    else:
        ai_desc = AIDescription(
            family_id=req.family_id,
            session_id=req.session_id,
            description=description,
            model_used="claude-haiku-4-5-20251001",
        )
        db.add(ai_desc)
    await db.commit()

    return EnrichedDescribeResponse(
        family_id=req.family_id,
        session_id=req.session_id,
        description=description,
        github_context_used=github_context_used,
    )


# ── GitHub endpoints ─────────────────────────────────────

@router.post("/github/search", response_model=GitHubSearchResult)
async def search_github_repos(db: AsyncSession = Depends(get_db)):
    """Fetch repos for the configured GitHub username."""
    username = await github_service.get_github_username(db)
    if not username:
        raise HTTPException(
            status_code=400,
            detail="GitHub username not configured. Set it in Settings.",
        )

    repos = await github_service.fetch_user_repos(username, db)
    return GitHubSearchResult(
        repos=[
            GitHubRepoInfo(
                full_name=r["full_name"],
                name=r["name"],
                description=r.get("description"),
                language=r.get("language"),
                stars=r.get("stars", 0),
                html_url=r.get("html_url"),
            )
            for r in repos
        ]
    )


@router.put("/github/link")
async def link_github_repo(
    req: GitHubLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """Link a GitHub repo to a family."""
    family = await db.get(CategoryFamily, req.family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    await github_service.link_repo(req.family_id, req.repo_full_name, db)
    return {"status": "linked", "family_id": req.family_id, "repo": req.repo_full_name}


@router.post("/github/unlink")
async def unlink_github_repo(
    req: GitHubUnlinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """Unlink a specific GitHub repo from a family."""
    removed = await github_service.unlink_repo(req.family_id, req.repo_full_name, db)
    if not removed:
        raise HTTPException(status_code=404, detail="No link found")
    return {"status": "unlinked", "family_id": req.family_id, "repo": req.repo_full_name}


@router.post("/github/clear-cache")
async def clear_github_cache(db: AsyncSession = Depends(get_db)):
    """Clear the GitHub repo cache so next search re-fetches with current token."""
    from sqlalchemy import delete as sa_delete
    from logger.models import GitHubRepoCache
    await db.execute(sa_delete(GitHubRepoCache))
    await db.commit()
    return {"status": "cleared"}
