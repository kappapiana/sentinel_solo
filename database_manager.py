"""
Database manager for Sentinel Solo: matters and time entries.
"""
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base, Matter, TimeEntry

DB_PATH = Path(__file__).resolve().parent / "sentinel.db"
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=ENGINE, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create tables if they do not exist."""
    Base.metadata.create_all(ENGINE)


def get_session() -> Session:
    """Return a new session (caller should close or use as context)."""
    return SessionLocal()


def add_matter(name: str, matter_code: str, parent_id: int | None = None) -> Matter:
    """Add a new matter. Returns the created Matter."""
    with get_session() as session:
        matter = Matter(name=name, matter_code=matter_code, parent_id=parent_id)
        session.add(matter)
        session.commit()
        session.refresh(matter)
        return matter


def get_matters_with_full_paths() -> list[tuple[int, str]]:
    """Return list of (matter_id, full_path) for dropdown, using Matter.get_full_path()."""
    with get_session() as session:
        matters = session.query(Matter).order_by(Matter.matter_code).all()
        return [(m.id, m.get_full_path(session)) for m in matters]


def get_all_matters() -> list[Matter]:
    """Return all matters (for Manage Matters tab)."""
    with get_session() as session:
        return list(session.query(Matter).order_by(Matter.matter_code).all())


def start_timer(matter_id: int, description: str | None = None) -> TimeEntry:
    """Start a new time entry for the given matter. Returns the created TimeEntry."""
    with get_session() as session:
        entry = TimeEntry(matter_id=matter_id, description=description or "")
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def stop_timer() -> TimeEntry | None:
    """Stop the current running timer (most recent entry with end_time None). Returns that TimeEntry or None."""
    with get_session() as session:
        entry = (
            session.query(TimeEntry)
            .filter(TimeEntry.end_time.is_(None))
            .order_by(TimeEntry.start_time.desc())
            .first()
        )
        if not entry:
            return None
        entry.end_time = datetime.now()
        entry.duration_seconds = (entry.end_time - entry.start_time).total_seconds()
        session.commit()
        session.refresh(entry)
        return entry


def get_running_entry() -> TimeEntry | None:
    """Return the current running time entry, if any."""
    with get_session() as session:
        return (
            session.query(TimeEntry)
            .filter(TimeEntry.end_time.is_(None))
            .order_by(TimeEntry.start_time.desc())
            .first()
        )
