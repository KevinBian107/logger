"""GitHub API integration service — supports personal access tokens for private repos."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import GitHubRepoCache, GitHubRepoLink, Setting

GITHUB_API = "https://api.github.com"
CACHE_TTL = timedelta(hours=1)


async def get_github_username(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(Setting.value).where(Setting.key == "github_username")
    )
    row = result.scalar_one_or_none()
    return row if row else None


async def get_github_public_only(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Setting.value).where(Setting.key == "github_public_only")
    )
    row = result.scalar_one_or_none()
    return row == "true"


async def get_github_token(db: AsyncSession) -> str | None:
    # Respect public-only mode — skip token even if one is saved
    if await get_github_public_only(db):
        return None
    result = await db.execute(
        select(Setting.value).where(Setting.key == "github_token")
    )
    row = result.scalar_one_or_none()
    return row if row else None


def _auth_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _is_cache_fresh(fetched_at: str | None) -> bool:
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        try:
            fetched = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return False
    now = datetime.now(timezone.utc)
    return (now - fetched) < CACHE_TTL


def _repo_to_dict(r: GitHubRepoCache) -> dict:
    return {
        "full_name": r.repo_full_name,
        "name": r.repo_name,
        "description": r.description,
        "language": r.language,
        "stars": r.stars,
        "html_url": r.html_url,
        "private": bool(r.description and r.description.startswith("[PRIVATE] ")),
    }


async def fetch_user_repos(username: str, db: AsyncSession) -> list[dict]:
    """Fetch repos for a user. Uses token if available (includes private repos)."""
    token = await get_github_token(db)

    # Check cache first
    cached = await db.execute(
        select(GitHubRepoCache).where(GitHubRepoCache.username == username)
    )
    cached_repos = cached.scalars().all()

    if cached_repos and await _is_cache_fresh(cached_repos[0].fetched_at):
        return [_repo_to_dict(r) for r in cached_repos]

    # Fetch fresh from GitHub
    all_repos: list[dict] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            # With token: use /user/repos for private access; without: /users/{}/repos
            if token:
                url = f"{GITHUB_API}/user/repos"
                params = {
                    "per_page": 100,
                    "sort": "updated",
                    "page": page,
                    "affiliation": "owner,collaborator",
                }
            else:
                url = f"{GITHUB_API}/users/{username}/repos"
                params = {"per_page": 100, "sort": "updated", "page": page}

            resp = await client.get(
                url,
                params=params,
                headers=_auth_headers(token),
                timeout=15.0,
            )
            # If token auth fails, fall back to unauthenticated
            if resp.status_code == 401 and token:
                token = None
                url = f"{GITHUB_API}/users/{username}/repos"
                params = {"per_page": 100, "sort": "updated", "page": page}
                resp = await client.get(
                    url,
                    params=params,
                    headers=_auth_headers(None),
                    timeout=15.0,
                )
            if resp.status_code != 200:
                if cached_repos:
                    return [_repo_to_dict(r) for r in cached_repos]
                return []

            batch = resp.json()
            if not batch:
                break
            all_repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
            if page > 3:  # cap at 300 repos
                break

        # Supplement with repos from push events (catches org repos you contribute to)
        if token:
            seen_names = {r["full_name"] for r in all_repos}
            try:
                for pg in range(1, 4):
                    ev_resp = await client.get(
                        f"{GITHUB_API}/users/{username}/events",
                        params={"per_page": 100, "page": pg},
                        headers=_auth_headers(token),
                        timeout=10.0,
                    )
                    if ev_resp.status_code != 200:
                        break
                    events = ev_resp.json()
                    if not events:
                        break
                    for ev in events:
                        if ev.get("type") != "PushEvent":
                            continue
                        repo_name = ev.get("repo", {}).get("name")
                        if not repo_name or repo_name in seen_names:
                            continue
                        seen_names.add(repo_name)
                        # Fetch full repo info
                        repo_resp = await client.get(
                            f"{GITHUB_API}/repos/{repo_name}",
                            headers=_auth_headers(token),
                            timeout=10.0,
                        )
                        if repo_resp.status_code == 200:
                            all_repos.append(repo_resp.json())
            except httpx.TimeoutException:
                pass  # best-effort

    # Clear old cache for this user
    await db.execute(
        delete(GitHubRepoCache).where(GitHubRepoCache.username == username)
    )

    results = []
    for repo in all_repos:
        if repo.get("fork"):
            continue
        desc = repo.get("description") or ""
        if repo.get("private"):
            desc = f"[PRIVATE] {desc}" if desc else "[PRIVATE]"
        cache_entry = GitHubRepoCache(
            username=username,
            repo_full_name=repo["full_name"],
            repo_name=repo["name"],
            description=desc,
            language=repo.get("language"),
            stars=repo.get("stargazers_count", 0),
            html_url=repo.get("html_url"),
        )
        db.add(cache_entry)
        results.append(
            {
                "full_name": repo["full_name"],
                "name": repo["name"],
                "description": desc,
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "html_url": repo.get("html_url"),
                "private": repo.get("private", False),
            }
        )

    await db.commit()
    return results


async def fetch_repo_details(
    repo_full_name: str, db: AsyncSession
) -> dict | None:
    """Fetch README + recent commits for a repo. Updates cache entry."""
    token = await get_github_token(db)
    readme_text = None
    commits_list: list[dict] = []

    async with httpx.AsyncClient() as client:
        # Fetch README
        headers = _auth_headers(token)
        headers["Accept"] = "application/vnd.github.v3.raw"
        readme_resp = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/readme",
            headers=headers,
            timeout=10.0,
        )
        if readme_resp.status_code == 200:
            readme_text = readme_resp.text[:1500]

        # Fetch recent commits
        commits_resp = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/commits",
            params={"per_page": 15},
            headers=_auth_headers(token),
            timeout=10.0,
        )
        if commits_resp.status_code == 200:
            for c in commits_resp.json():
                commits_list.append(
                    {
                        "sha": c["sha"][:7],
                        "message": (c.get("commit", {}).get("message", "") or "")[:120],
                        "date": c.get("commit", {})
                        .get("author", {})
                        .get("date", ""),
                    }
                )

    # Update cache entry if it exists
    result = await db.execute(
        select(GitHubRepoCache).where(
            GitHubRepoCache.repo_full_name == repo_full_name
        )
    )
    cache_entry = result.scalar_one_or_none()
    if cache_entry:
        cache_entry.readme_excerpt = readme_text
        cache_entry.recent_commits = json.dumps(commits_list)
        await db.commit()

    return {
        "readme_excerpt": readme_text,
        "recent_commits": commits_list,
    }


# ── Multi-repo link operations ───────────────────────────

async def get_linked_repos(family_id: int, db: AsyncSession) -> list[str]:
    """Return all linked repo full_names for a family."""
    result = await db.execute(
        select(GitHubRepoLink.repo_full_name).where(
            GitHubRepoLink.family_id == family_id
        )
    )
    return [r[0] for r in result]


async def link_repo(
    family_id: int, repo_full_name: str, db: AsyncSession
) -> None:
    """Add a family-to-repo link (no-op if already linked)."""
    result = await db.execute(
        select(GitHubRepoLink)
        .where(GitHubRepoLink.family_id == family_id)
        .where(GitHubRepoLink.repo_full_name == repo_full_name)
    )
    if result.scalar_one_or_none():
        return  # already linked
    db.add(GitHubRepoLink(family_id=family_id, repo_full_name=repo_full_name))
    await db.commit()


async def unlink_repo(
    family_id: int, repo_full_name: str, db: AsyncSession
) -> bool:
    """Remove a specific family-to-repo link."""
    result = await db.execute(
        select(GitHubRepoLink)
        .where(GitHubRepoLink.family_id == family_id)
        .where(GitHubRepoLink.repo_full_name == repo_full_name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
        return True
    return False


async def auto_match_repos(
    family_name: str, username: str, db: AsyncSession
) -> list[str]:
    """Fuzzy match a family name against cached repo names. Returns list."""
    if len(family_name) < 3:
        return []

    result = await db.execute(
        select(GitHubRepoCache).where(GitHubRepoCache.username == username)
    )
    repos = result.scalars().all()

    family_lower = family_name.lower()
    matches = []

    # Exact name match first
    for repo in repos:
        if repo.repo_name.lower() == family_lower:
            matches.append(repo.repo_full_name)

    if matches:
        return matches

    # Substring match
    for repo in repos:
        repo_lower = repo.repo_name.lower()
        if family_lower in repo_lower or repo_lower in family_lower:
            matches.append(repo.repo_full_name)

    return matches


async def get_cached_repo_info(
    repo_full_name: str, db: AsyncSession
) -> dict | None:
    """Get cached info for a repo."""
    result = await db.execute(
        select(GitHubRepoCache).where(
            GitHubRepoCache.repo_full_name == repo_full_name
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        return None

    commits = []
    if repo.recent_commits:
        try:
            commits = json.loads(repo.recent_commits)
        except json.JSONDecodeError:
            pass

    return {
        "full_name": repo.repo_full_name,
        "name": repo.repo_name,
        "description": repo.description,
        "language": repo.language,
        "stars": repo.stars,
        "html_url": repo.html_url,
        "readme_excerpt": repo.readme_excerpt,
        "recent_commits": commits,
    }
