from sqlalchemy import (
    Boolean, Column, Integer, Text, ForeignKey, UniqueConstraint, Index,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    season = Column(Text, nullable=False)
    label = Column(Text)
    start_date = Column(Text)
    end_date = Column(Text)
    is_active = Column(Boolean, default=False)
    source_file = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("year", "season"),)

    categories = relationship("Category", back_populates="session", cascade="all, delete-orphan")
    daily_records = relationship("DailyRecord", back_populates="session", cascade="all, delete-orphan")
    text_entries = relationship("TextEntry", back_populates="session", cascade="all, delete-orphan")


class CategoryFamily(Base):
    __tablename__ = "category_families"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    display_name = Column(Text)
    description = Column(Text)
    color = Column(Text)
    family_type = Column(Text, default="other")
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    categories = relationship("Category", back_populates="family")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    display_name = Column(Text)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="SET NULL"))
    position = Column(Integer, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("session_id", "name"),
        Index("idx_categories_family", "family_id"),
        Index("idx_categories_session", "session_id"),
    )

    session = relationship("Session", back_populates="categories")
    family = relationship("CategoryFamily", back_populates="categories")
    observations = relationship("Observation", back_populates="category")


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    day_of_week = Column(Text)
    week_number = Column(Integer)
    total_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("session_id", "date"),
        Index("idx_daily_records_date", "date"),
        Index("idx_daily_records_session", "session_id"),
    )

    session = relationship("Session", back_populates="daily_records")
    observations = relationship("Observation", back_populates="daily_record", cascade="all, delete-orphan")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    minutes = Column(Integer, nullable=False, default=0)
    source = Column(Text, default="import")
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("daily_record_id", "category_id"),
        Index("idx_observations_category", "category_id"),
        Index("idx_observations_daily", "daily_record_id"),
    )

    daily_record = relationship("DailyRecord", back_populates="observations")
    category = relationship("Category", back_populates="observations")


class TextEntry(Base):
    __tablename__ = "text_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    location = Column(Text)
    notes = Column(Text)
    study_materials = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_text_entries_date", "date"),
        Index("idx_text_entries_session", "session_id"),
    )

    session = relationship("Session", back_populates="text_entries")


class TimerEntry(Base):
    __tablename__ = "timer_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    start_time = Column(Text, nullable=False)
    end_time = Column(Text)
    pause_start = Column(Text)
    total_paused_seconds = Column(Integer, default=0)
    duration_minutes = Column(Integer)
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    description = Column(Text)
    location = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))
    updated_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_timer_active", "is_active", sqlite_where=text("is_active = 1")),
        Index("idx_timer_date", "date"),
        Index("idx_timer_category", "category_id"),
    )


class ManualEntry(Base):
    __tablename__ = "manual_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    description = Column(Text)
    location = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_manual_date", "date"),
        Index("idx_manual_category", "category_id"),
    )


class AIDescription(Base):
    __tablename__ = "ai_descriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    model_used = Column(Text)
    generated_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("family_id", "session_id"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    display_name = Column(Text)
    description = Column(Text)
    color = Column(Text)
    is_auto = Column(Boolean, default=False)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    members = relationship("CategoryGroupMember", back_populates="group", cascade="all, delete-orphan")


class CategoryGroupMember(Base):
    __tablename__ = "category_group_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "category_id"),
        Index("idx_group_members_group", "group_id"),
        Index("idx_group_members_category", "category_id"),
    )

    group = relationship("CategoryGroup", back_populates="members")
    category = relationship("Category")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(Text, server_default=text("(datetime('now'))"))


class GitHubRepoCache(Base):
    __tablename__ = "github_repo_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(Text, nullable=False)
    repo_full_name = Column(Text, nullable=False)
    repo_name = Column(Text, nullable=False)
    description = Column(Text)
    readme_excerpt = Column(Text)
    recent_commits = Column(Text)  # JSON string
    language = Column(Text)
    stars = Column(Integer, default=0)
    html_url = Column(Text)
    fetched_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("username", "repo_full_name"),)


class GitHubRepoLink(Base):
    __tablename__ = "github_repo_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="CASCADE"), nullable=False)
    repo_full_name = Column(Text, nullable=False)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("family_id", "repo_full_name"),
        Index("idx_github_links_family", "family_id"),
    )
