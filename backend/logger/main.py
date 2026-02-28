from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logger.config import CORS_ORIGINS
from logger.database import init_db
from logger.routers import sessions, categories, import_csv, settings, timers, manual_entries, daily, groups, analytics, chat, projects


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(title="Logger", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(import_csv.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(timers.router, prefix="/api")
app.include_router(manual_entries.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(groups.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(projects.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
