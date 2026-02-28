# Database Schema

SQLite database managed by SQLAlchemy 2 (async). All timestamps are stored as ISO 8601 text strings (`datetime('now')`). The schema is auto-created on startup via `init_db()` in `database.py`.

## Entity Relationship Diagram

```
sessions ──────────┬──< categories ──< observations >── daily_records
  │                │        │
  │                │        ├──< timer_entries
  │                │        ├──< manual_entries
  │                │        └──< category_group_members >── category_groups
  │                │
  ├──< daily_records        category_families >──< categories
  ├──< text_entries                │
  └──< ai_descriptions ───────────┘
                                   │
                            github_repo_links

chat_messages          (standalone)
settings               (standalone key-value)
github_repo_cache      (standalone cache)
```

## Tables

### sessions

One row per academic term (e.g., Winter 2026). The active session is the one currently being tracked.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| year | INTEGER | NOT NULL | Academic year (e.g., 2026) |
| season | TEXT | NOT NULL | `fall`, `winter`, `spring`, `summer` |
| label | TEXT | | Human-readable label (e.g., "Winter 2026") |
| start_date | TEXT | | ISO date of first logged day |
| end_date | TEXT | | ISO date of last logged day |
| is_active | BOOLEAN | default FALSE | Only one session should be active at a time |
| source_file | TEXT | | Original CSV filename if imported |
| created_at | TEXT | default now | |

**Unique**: `(year, season)`
**Cascade**: Deleting a session cascades to categories, daily_records, text_entries.

---

### category_families

Links related categories across sessions. A family like "salk" groups `salk_winter24`, `salk_spring25`, etc. The `family_type` field provides group-level classification.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| name | TEXT | NOT NULL, UNIQUE | Internal key (e.g., `salk`, `training`, `dsc`) |
| display_name | TEXT | | Human-readable (e.g., "Salk Research") |
| description | TEXT | | Optional description |
| color | TEXT | | Hex color (e.g., `#6366f1`) |
| family_type | TEXT | default `other` | `research`, `course`, `personal`, or `other` |
| created_at | TEXT | default now | |

**Design note**: Families are auto-detected during CSV import based on category name patterns (see `family_service.py`). They can also be created/edited/deleted manually via the Families tab.

---

### categories

Individual tracked activities within a session. Each category belongs to exactly one session and optionally one family.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| name | TEXT | NOT NULL | Normalized merge key (e.g., `cogs118c`) |
| display_name | TEXT | | Clean name from CSV (e.g., "COGS 118C") |
| family_id | INTEGER | FK category_families.id, SET NULL on delete | |
| position | INTEGER | default 0 | Display order within session |
| created_at | TEXT | default now | |

**Unique**: `(session_id, name)`
**Indexes**: `family_id`, `session_id`

---

### daily_records

One row per date per session. Stores the aggregate total and metadata from the CSV row.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| date | TEXT | NOT NULL | ISO date (e.g., `2026-01-15`) |
| day_of_week | TEXT | | `Mon`, `Tue`, etc. |
| week_number | INTEGER | | Academic week number from CSV |
| total_minutes | INTEGER | NOT NULL, default 0 | Sum of all observations for this day |
| created_at | TEXT | default now | |

**Unique**: `(session_id, date)`
**Indexes**: `date`, `session_id`
**Cascade**: Deleting a daily_record cascades to its observations.

---

### observations

Long-format time data: one row per (day, category) pair. This is the core data table — every minute of logged time lives here.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| daily_record_id | INTEGER | FK daily_records.id, NOT NULL | |
| category_id | INTEGER | FK categories.id, NOT NULL | |
| minutes | INTEGER | NOT NULL, default 0 | Minutes spent |
| source | TEXT | default `import` | `import`, `timer`, or `manual` |
| created_at | TEXT | default now | |

**Unique**: `(daily_record_id, category_id)`
**Indexes**: `category_id`, `daily_record_id`

---

### text_entries

Free-text daily descriptions imported from text CSVs. One per date per session.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| date | TEXT | NOT NULL | ISO date |
| location | TEXT | | Where the work happened (e.g., "UCSD") |
| notes | TEXT | | General notes |
| study_materials | TEXT | | Detailed activity descriptions with time annotations |
| created_at | TEXT | default now | |

**Indexes**: `date`, `session_id`

---

### timer_entries

Real-time timer sessions with pause/resume support. When stopped, creates an observation in the corresponding daily_record.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| category_id | INTEGER | FK categories.id, NOT NULL | |
| date | TEXT | NOT NULL | ISO date when timer was started |
| start_time | TEXT | NOT NULL | ISO datetime |
| end_time | TEXT | | ISO datetime (NULL while active) |
| pause_start | TEXT | | ISO datetime of current pause (NULL if not paused) |
| total_paused_seconds | INTEGER | default 0 | Accumulated pause time |
| duration_minutes | INTEGER | | Final duration rounded to nearest minute |
| is_active | BOOLEAN | default TRUE | |
| is_paused | BOOLEAN | default FALSE | |
| description | TEXT | | User-provided on stop |
| location | TEXT | | User-provided on stop |
| created_at | TEXT | default now | |
| updated_at | TEXT | default now | |

**Indexes**: `is_active` (partial, where active=1), `date`, `category_id`

---

### manual_entries

Retroactive time entries for sessions the user forgot to time.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| category_id | INTEGER | FK categories.id, NOT NULL | |
| date | TEXT | NOT NULL | ISO date |
| duration_minutes | INTEGER | NOT NULL | |
| description | TEXT | | |
| location | TEXT | | |
| created_at | TEXT | default now | |

**Indexes**: `date`, `category_id`

---

### category_groups

Auto-generated or user-created groupings for bubble visualization. Distinct from families — groups are a flat visualization tool, families are the semantic hierarchy.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| name | TEXT | NOT NULL, UNIQUE | |
| display_name | TEXT | | |
| description | TEXT | | |
| color | TEXT | | |
| is_auto | BOOLEAN | default FALSE | TRUE if auto-generated from families |
| created_at | TEXT | default now | |

---

### category_group_members

Join table: which categories belong to which groups.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| group_id | INTEGER | FK category_groups.id, NOT NULL | |
| category_id | INTEGER | FK categories.id, NOT NULL | |

**Unique**: `(group_id, category_id)`
**Indexes**: `group_id`, `category_id`

---

### ai_descriptions

Cached AI-generated descriptions for family+session pairs (project progression view).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| family_id | INTEGER | FK category_families.id, NOT NULL | |
| session_id | INTEGER | FK sessions.id, NOT NULL | |
| description | TEXT | NOT NULL | Generated text |
| model_used | TEXT | | Claude model ID |
| generated_at | TEXT | default now | |

**Unique**: `(family_id, session_id)`

---

### chat_messages

Persistent chat history for the AI chat interface.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| role | TEXT | NOT NULL | `user` or `assistant` |
| content | TEXT | NOT NULL | Message text |
| metadata | TEXT | | JSON string for extra context |
| created_at | TEXT | default now | |

---

### settings

Key-value store for app configuration (API keys, theme, selected model, etc.).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| key | TEXT | PK | Setting name |
| value | TEXT | NOT NULL | Setting value |
| updated_at | TEXT | default now | |

---

### github_repo_cache

Cached GitHub repository metadata to avoid repeated API calls.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| username | TEXT | NOT NULL | GitHub username |
| repo_full_name | TEXT | NOT NULL | `owner/repo` |
| repo_name | TEXT | NOT NULL | Short name |
| description | TEXT | | Repo description |
| readme_excerpt | TEXT | | First ~500 chars of README |
| recent_commits | TEXT | | JSON array of recent commits |
| language | TEXT | | Primary language |
| stars | INTEGER | default 0 | |
| html_url | TEXT | | |
| fetched_at | TEXT | default now | |

**Unique**: `(username, repo_full_name)`

---

### github_repo_links

Maps families to GitHub repositories for the project progression view.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, autoincrement | |
| family_id | INTEGER | FK category_families.id, NOT NULL | |
| repo_full_name | TEXT | NOT NULL | `owner/repo` |
| created_at | TEXT | default now | |

**Unique**: `(family_id, repo_full_name)`
**Indexes**: `family_id`

## Views

### v_daily_totals

Denormalized view joining daily_records, sessions, observations, categories, and families. Used by analytics queries.

```sql
SELECT dr.date, dr.session_id, s.label, c.id, c.display_name,
       cf.name, cf.color, dr.week_number, COALESCE(o.minutes, 0), o.source
FROM daily_records dr
JOIN sessions s ON dr.session_id = s.id
JOIN observations o ON o.daily_record_id = dr.id
JOIN categories c ON o.category_id = c.id
LEFT JOIN category_families cf ON c.family_id = cf.id
```

### v_family_totals

Aggregated view of total minutes and active days per family per session. Used by project timeline and research views.

```sql
SELECT cf.id, cf.name, cf.display_name, cf.color,
       s.id, s.label, s.year, s.season,
       SUM(o.minutes), COUNT(DISTINCT dr.date)
FROM category_families cf
JOIN categories c ON c.family_id = cf.id
JOIN observations o ON o.category_id = c.id
JOIN daily_records dr ON o.daily_record_id = dr.id
JOIN sessions s ON c.session_id = s.id
GROUP BY cf.id, s.id
```

## Design Decisions

**Text timestamps over native SQLite dates**: All date/datetime columns use TEXT with ISO 8601 format. This simplifies serialization to/from JSON and avoids SQLite datetime type ambiguity. The tradeoff is that date arithmetic requires `date()` / `datetime()` functions in queries.

**Long-format observations**: Time data is stored as one row per (day, category) rather than wide-format (one column per category). This makes queries and aggregations simpler and avoids schema changes when categories are added.

**Families vs. Groups**: Two separate grouping mechanisms exist:
- **Families** are semantic — they represent the same project/activity across academic sessions (e.g., "Salk Research" links `salk_winter24` and `salk_spring25`). They have a `family_type` for higher-level classification.
- **Groups** are for visualization — auto-generated or manual groupings used by the bubble chart. A group can contain any categories regardless of family.

**Cascade deletes**: Deleting a session removes all its categories, daily records, observations, and text entries. Deleting a family sets `family_id = NULL` on linked categories (SET NULL) rather than deleting them.

**Import idempotency**: Sessions are uniquely identified by `(year, season)`. The import pipeline rejects duplicate sessions rather than merging, so reimporting requires deleting the existing session first.
