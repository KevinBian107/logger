<p align="center">
  <img src="frontend/static/logo.svg" alt="log(ger)" width="120" />
</p>

<h1 align="center">log(ger)</h1>

<p align="center">
  A personal productivity tracking web app — because every minute is worth logging.
</p>

---

A ground-up rebuild of [Chatable-Study-Database](https://github.com/KevinBian107/Chatable-Study-Database) (Python/Jupyter) as a modern web application. Tracks study and work time across academic sessions with real-time timers, analytics dashboards, AI-powered chat, and project progression visualization.

## Features

- **Timer-based logging** — Start/pause/stop timers per category with parallel sessions
- **Manual entry** — Retroactive time logging for sessions you forgot to time
- **Analytics dashboard** — Time-scale-aware filtering (Overall / Year / Month / Week) with stacked area charts, category breakdowns, session comparison by family groups, and weekly heatmaps
- **AI chat** — Claude API-powered conversational interface to query past activity and generate summaries
- **CSV import** — Import legacy data with two-panel upload (timesheet CSV + text/notes CSV). 14 sessions from Fall 2022 through Winter 2026
- **Category families & groups** — Two-level hierarchy: groups (Research, Courses, Personal) → families (Salk Research, COGS, Training) → categories. Full family management UI (create, edit, rename, delete) with inline editing on the Data page
- **Project progression** — Bubble visualization of how project families evolve across sessions
- **Smart normalization** — CSV columns are clean display names; session info comes from filenames, not column name suffixes
- **Auto-active sessions** — Imported sessions whose date range includes today are automatically marked active

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | SvelteKit 2, Svelte 5 (runes), Tailwind CSS 4, D3.js, TypeScript |
| Backend | FastAPI, SQLAlchemy 2 (async), Pydantic 2 |
| Database | SQLite (local) |
| AI | Claude API (Anthropic Python SDK) |
| Package managers | uv (Python), pnpm (Node) |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (Node package manager)

### Install

```bash
# Backend
cd backend
uv sync

# Frontend
cd frontend
pnpm install
```

### Import Legacy Data

If you have CSV data in `data/`, run the batch import:

```bash
# Start backend first
cd backend
uv run uvicorn logger.main:app --port 8000

# In another terminal, trigger batch import
curl -X POST http://localhost:8000/api/import/batch
```

CSV files follow the naming convention `{year}_{season}_study.csv` and `{year}_{season}_text.csv` (e.g., `2024_fall_study.csv`). Category columns should be clean display names — session context comes from the filename.

### Run

```bash
# Terminal 1 — Backend (port 8000)
cd backend
uv run uvicorn logger.main:app --reload --port 8000

# Terminal 2 — Frontend (port 5173)
cd frontend
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173).

## Project Structure

```
logger/
├── backend/
│   ├── pyproject.toml
│   ├── import_all.py              # Batch CSV import script
│   └── logger/
│       ├── main.py                # FastAPI app + CORS + lifespan
│       ├── config.py              # Paths, DB URL, CORS origins
│       ├── database.py            # Async SQLAlchemy engine, init_db()
│       ├── models.py              # ORM models (Session, Category, etc.)
│       ├── schemas.py             # Pydantic request/response schemas
│       ├── routers/
│       │   ├── sessions.py        # CRUD + active session
│       │   ├── categories.py      # Categories + families CRUD
│       │   ├── analytics.py       # Overview, daily series, categories, heatmap
│       │   ├── daily.py           # Daily activity + streak
│       │   ├── timers.py          # Timer start/pause/resume/stop
│       │   ├── manual_entries.py  # Manual time entries
│       │   ├── import_csv.py      # CSV preview + confirm + batch
│       │   ├── chat.py            # AI chat endpoints
│       │   └── settings.py        # Key-value settings + DB info
│       ├── services/
│       │   ├── import_service.py       # CSV parsing + DB writes
│       │   ├── family_service.py       # Family auto-detection
│       │   ├── category_normalization.py # Clean name → merge key
│       │   ├── analytics_service.py    # Analytics queries
│       │   ├── timer_service.py        # Timer logic
│       │   └── chat_*.py              # Chat context + query services
│       └── utils/
│           ├── csv_utils.py        # BOM handling, header parsing
│           └── date_utils.py       # Date parsing, day normalization
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── app.css                 # Tailwind + theme variables
│       ├── app.html
│       ├── lib/
│       │   ├── api/client.ts       # Typed API client
│       │   ├── stores/             # Session, timer, theme, chat stores
│       │   ├── assets/             # Logo SVGs
│       │   └── components/
│       │       ├── layout/         # Sidebar, TopBar
│       │       ├── dashboard/      # StatCard, ActiveTimers
│       │       ├── timer/          # TimerCard, StopDialog, ManualEntryForm, TodayLog
│       │       ├── analytics/      # FilterBar, DailyAreaChart, CategoryBars, SessionBars, WeeklyHeatmap
│       │       ├── data/           # SessionList, SessionDetail, ImportDropzone, BubbleVisualization, FamilyManager
│       │       └── chat/           # ChatMessage, ChatInput
│       └── routes/
│           ├── +layout.svelte      # App shell
│           ├── +page.svelte        # Dashboard
│           ├── timer/              # Timer + manual entry
│           ├── analytics/          # Analytics with time-scale filtering
│           ├── chat/               # AI chat interface
│           ├── projects/           # Project progression
│           ├── data/               # Session list + CSV import + family manager (3 tabs)
│           └── settings/           # Theme, DB info, API key
├── data/                           # CSV files (gitignored)
├── scripts/                        # Data cleaning scripts
└── logger.db                       # SQLite database (gitignored)
```

## Data Model

- **sessions** — One per academic term (e.g., Winter 2026)
- **category_families** — Links related categories across sessions (e.g., "Salk Research"), with `family_type` for group-level classification (research/course/personal)
- **categories** — Individual tracked activities within a session, linked to a family
- **daily_records** — One row per date per session with total minutes and week number
- **observations** — Time-per-category data (long format, one row per day/category pair)
- **text_entries** — Free-text daily descriptions (location, notes, study materials)
- **timer_entries** — Real-time timer sessions with pause/resume support
- **manual_entries** — Retroactive time entries
- **category_groups** — Auto-generated groupings for visualization
- **ai_descriptions** / **chat_messages** — AI-generated content and chat history
- **v_daily_totals** / **v_family_totals** — Materialized views for analytics

## Implementation Status

- [x] **Foundation** — Backend, database, CSV import, app shell, data page
- [x] **Timer & Manual Entry** — Real-time timers, manual logging, dashboard with today's log
- [x] **Analytics** — Time-scale filtering, stacked area chart, category breakdown with session labels, session comparison by family groups, weekly heatmap
- [x] **Data Management** — Two-panel CSV import, full family CRUD (create/edit/rename/delete), bubble visualization, three-tab data page (Sessions, Groups, Families)
- [x] **CSV Normalization** — Clean column names in CSVs, simplified import pipeline, family auto-detection from display names, auto-active session detection on import
- [ ] **AI Chat** — Claude API integration with approval flow
- [ ] **Projects** — Family timeline with AI-generated descriptions
- [ ] **Polish** — Responsive layout, loading states, error handling

## License

Private project.
