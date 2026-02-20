"""
Database manager for Sentinel Solo: matters and time entries.
"""
from pathlib import Path
from datetime import datetime, date

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


def _get_root_matter_name(session: Session, matter: Matter) -> str:
    """Resolve root matter (parent_id is None) and return its name."""
    current = matter
    while current.parent_id is not None:
        current = session.query(Matter).get(current.parent_id)
        if current is None:
            return matter.name
    return current.name


def get_time_by_client_and_matter(
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[tuple[str, str, float]]:
    """
    Return aggregated time by client (root matter) and matter (full path).
    Only completed entries (end_time set) are included.
    Returns list of (client_name, matter_full_path, total_seconds), sorted by client then matter.
    """
    with get_session() as session:
        q = session.query(TimeEntry).filter(TimeEntry.end_time.isnot(None))
        if date_from is not None:
            start_dt = datetime.combine(date_from, datetime.min.time())
            q = q.filter(TimeEntry.start_time >= start_dt)
        if date_to is not None:
            end_dt = datetime.combine(date_to, datetime.max.time())
            q = q.filter(TimeEntry.start_time <= end_dt)
        entries = q.all()
        agg: dict[tuple[str, str], float] = {}
        for entry in entries:
            matter = session.query(Matter).get(entry.matter_id)
            if matter is None:
                continue
            client_name = _get_root_matter_name(session, matter)
            full_path = matter.get_full_path(session)
            key = (client_name, full_path)
            agg[key] = agg.get(key, 0.0) + (entry.duration_seconds or 0.0)
        result = [(client, path, total) for (client, path), total in agg.items()]
        result.sort(key=lambda r: (r[0], r[1]))
        return result
