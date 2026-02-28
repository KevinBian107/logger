from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text as sa_text

from logger.config import DATABASE_URL
from logger.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

V_DAILY_TOTALS = """
CREATE VIEW v_daily_totals AS
SELECT
    dr.date,
    dr.session_id,
    s.label AS session_label,
    c.id AS category_id,
    c.display_name AS category_name,
    cf.name AS family_name,
    cf.color AS family_color,
    dr.week_number,
    COALESCE(o.minutes, 0) AS minutes,
    o.source
FROM daily_records dr
JOIN sessions s ON dr.session_id = s.id
JOIN observations o ON o.daily_record_id = dr.id
JOIN categories c ON o.category_id = c.id
LEFT JOIN category_families cf ON c.family_id = cf.id
"""

V_FAMILY_TOTALS = """
CREATE VIEW v_family_totals AS
SELECT
    cf.id AS family_id,
    cf.name AS family_name,
    cf.display_name,
    cf.color,
    s.id AS session_id,
    s.label AS session_label,
    s.year,
    s.season,
    SUM(o.minutes) AS total_minutes,
    COUNT(DISTINCT dr.date) AS active_days
FROM category_families cf
JOIN categories c ON c.family_id = cf.id
JOIN observations o ON o.category_id = c.id
JOIN daily_records dr ON o.daily_record_id = dr.id
JOIN sessions s ON c.session_id = s.id
GROUP BY cf.id, s.id
"""


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Recreate views to pick up schema changes
        await conn.execute(sa_text("DROP VIEW IF EXISTS v_daily_totals"))
        await conn.execute(sa_text(V_DAILY_TOTALS))
        await conn.execute(sa_text("DROP VIEW IF EXISTS v_family_totals"))
        await conn.execute(sa_text(V_FAMILY_TOTALS))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
