"""
Database manager for Sentinel Solo: matters and time entries.
"""
import re
from pathlib import Path
from datetime import datetime, date, timedelta

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


def _slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric with hyphen, strip. Empty -> 'matter'."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s if s else "matter"


def suggest_unique_code(name: str) -> str:
    """Return a unique matter_code from name: slugify, then slug, slug-2, slug-3, ... as needed."""
    slug = _slugify(name)
    with get_session() as session:
        # Codes that are exactly slug or slug-N
        rows = session.query(Matter.matter_code).filter(
            (Matter.matter_code == slug) | (Matter.matter_code.like(f"{slug}-%"))
        ).all()
        used = {r[0] for r in rows}
    if slug not in used:
        return slug
    n = 2
    while f"{slug}-{n}" in used:
        n += 1
    return f"{slug}-{n}"


def add_matter(name: str, matter_code: str, parent_id: int | None = None) -> Matter:
    """Add a new matter. Returns the created Matter."""
    with get_session() as session:
        matter = Matter(name=name, matter_code=matter_code, parent_id=parent_id)
        session.add(matter)
        session.commit()
        session.refresh(matter)
        return matter


def get_matters_with_full_paths(for_timer: bool = False) -> list[tuple[int, str]]:
    """Return list of (matter_id, full_path) for dropdown, using Matter.get_full_path().
    When for_timer=True, only matters with a parent (non-root) are returned."""
    with get_session() as session:
        q = session.query(Matter).order_by(Matter.matter_code)
        if for_timer:
            q = q.filter(Matter.parent_id.isnot(None))
        matters = q.all()
        return [(m.id, m.get_full_path(session)) for m in matters]


def get_all_matters() -> list[Matter]:
    """Return all matters (for Manage Matters tab)."""
    with get_session() as session:
        return list(session.query(Matter).order_by(Matter.matter_code).all())


def start_timer(matter_id: int, description: str | None = None) -> TimeEntry:
    """Start a new time entry for the given matter. Returns the created TimeEntry.
    Raises ValueError if matter is a root (client); time can only be logged to a matter under a client."""
    with get_session() as session:
        matter = session.query(Matter).get(matter_id)
        if matter is None:
            raise ValueError("Matter not found.")
        if matter.parent_id is None:
            raise ValueError("Time cannot be logged to a client; select a matter under a client.")
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


def get_time_entries_by_matter(matter_id: int) -> list[TimeEntry]:
    """Return all time entries for the matter, newest first."""
    with get_session() as session:
        return list(
            session.query(TimeEntry)
            .filter(TimeEntry.matter_id == matter_id)
            .order_by(TimeEntry.start_time.desc())
            .all()
        )


def _resolve_time_trio(
    start_time: datetime | None,
    end_time: datetime | None,
    duration_seconds: float | None,
) -> tuple[datetime, datetime | None, float]:
    """
    Given any two of start_time, end_time, duration_seconds, compute the third.
    Returns (start_time, end_time, duration_seconds). Raises ValueError if not exactly two provided.
    """
    provided = sum(x is not None for x in (start_time, end_time, duration_seconds))
    if provided != 2:
        raise ValueError("Provide exactly two of start_time, end_time, duration_seconds.")
    if start_time is not None and end_time is not None:
        duration_seconds = (end_time - start_time).total_seconds()
        if duration_seconds < 0:
            raise ValueError("End time must be after start time.")
    elif start_time is not None and duration_seconds is not None:
        if duration_seconds < 0:
            raise ValueError("Duration must be non-negative.")
        end_time = start_time + timedelta(seconds=duration_seconds)
    else:
        assert end_time is not None and duration_seconds is not None
        if duration_seconds < 0:
            raise ValueError("Duration must be non-negative.")
        start_time = end_time - timedelta(seconds=duration_seconds)
    return (start_time, end_time, duration_seconds)


def update_time_entry(
    entry_id: int,
    description: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    duration_seconds: float | None = None,
) -> None:
    """
    Update a time entry. If description is provided, set it.
    Provide either all three of start_time, end_time, duration_seconds (must be consistent),
    or exactly two and the third is computed.
    """
    with get_session() as session:
        entry = session.query(TimeEntry).get(entry_id)
        if entry is None:
            raise ValueError("Time entry not found.")
        if description is not None:
            entry.description = description
        time_args = [start_time, end_time, duration_seconds]
        if any(x is not None for x in time_args):
            provided = sum(x is not None for x in time_args)
            if provided == 3:
                if duration_seconds is not None and duration_seconds < 0:
                    raise ValueError("Duration must be non-negative.")
                if start_time and end_time and end_time < start_time:
                    raise ValueError("End time must be after start time.")
                entry.start_time = start_time
                entry.end_time = end_time
                entry.duration_seconds = duration_seconds or 0.0
            else:
                start_t, end_t, dur = _resolve_time_trio(start_time, end_time, duration_seconds)
                entry.start_time = start_t
                entry.end_time = end_t
                entry.duration_seconds = dur
        session.commit()


def add_manual_time_entry(
    matter_id: int,
    description: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    duration_seconds: float | None = None,
) -> TimeEntry:
    """
    Add a completed time entry manually. Provide either all three of start_time, end_time, duration_seconds
    (must be consistent) or exactly two and the third is computed. Matter must exist and not be a root.
    """
    with get_session() as session:
        matter = session.query(Matter).get(matter_id)
        if matter is None:
            raise ValueError("Matter not found.")
        if matter.parent_id is None:
            raise ValueError("Time cannot be logged to a client.")
        provided = sum(x is not None for x in (start_time, end_time, duration_seconds))
        if provided == 3:
            if duration_seconds is not None and duration_seconds < 0:
                raise ValueError("Duration must be non-negative.")
            if start_time and end_time and end_time < start_time:
                raise ValueError("End time must be after start time.")
            start_t, end_t, dur = start_time, end_time, duration_seconds or 0.0
        else:
            start_t, end_t, dur = _resolve_time_trio(start_time, end_time, duration_seconds)
        entry = TimeEntry(
            matter_id=matter_id,
            description=description or "",
            start_time=start_t,
            end_time=end_t,
            duration_seconds=dur,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def _get_root_matter_name(session: Session, matter: Matter) -> str:
    """Resolve root matter (parent_id is None) and return its name."""
    current = matter
    while current.parent_id is not None:
        current = session.query(Matter).get(current.parent_id)
        if current is None:
            return matter.name
    return current.name


def _is_descendant_of(session: Session, matter_id: int, ancestor_id: int) -> bool:
    """Walk from matter_id upward via parent_id; return True if ancestor_id is reached."""
    current = session.query(Matter).get(matter_id)
    while current is not None and current.parent_id is not None:
        if current.parent_id == ancestor_id:
            return True
        current = session.query(Matter).get(current.parent_id)
    return False


def get_matters_with_full_paths_excluding(
    exclude_matter_id: int,
    for_timer: bool = False,
    include_root_option: bool = True,
) -> list[tuple[int | None, str]]:
    """
    Like get_matters_with_full_paths but excludes exclude_matter_id and any matter
    that is a descendant of it. If include_root_option, includes (None, "— Root (new client) —").
    Returns list of (matter_id_or_None, full_path).
    """
    with get_session() as session:
        q = session.query(Matter).order_by(Matter.matter_code)
        if for_timer:
            q = q.filter(Matter.parent_id.isnot(None))
        matters = q.all()
        result: list[tuple[int | None, str]] = (
            [(None, "— Root (new client) —")] if include_root_option else []
        )
        for m in matters:
            if m.id == exclude_matter_id:
                continue
            if _is_descendant_of(session, m.id, exclude_matter_id):
                continue
            result.append((m.id, m.get_full_path(session)))
        return result


def move_matter(matter_id: int, new_parent_id: int | None) -> None:
    """
    Move a matter to another client (new_parent_id None) or under another matter.
    Time entries stay attached. Raises ValueError if new parent is self or a descendant.
    """
    with get_session() as session:
        matter = session.query(Matter).get(matter_id)
        if matter is None:
            raise ValueError("Matter not found.")
        if new_parent_id is not None:
            if new_parent_id == matter_id:
                raise ValueError("Cannot move a matter to itself.")
            parent = session.query(Matter).get(new_parent_id)
            if parent is None:
                raise ValueError("New parent matter not found.")
            if _is_descendant_of(session, new_parent_id, matter_id):
                raise ValueError("Cannot move a matter under one of its descendants.")
        matter.parent_id = new_parent_id
        session.commit()


def merge_matter_into(source_matter_id: int, target_matter_id: int) -> None:
    """
    Merge source matter into target: reassign all time entries and reparent children
    to target, then delete source. Target must not be source or a descendant of source.
    If source has a running timer, that entry is reassigned to target.
    """
    with get_session() as session:
        source = session.query(Matter).get(source_matter_id)
        target = session.query(Matter).get(target_matter_id)
        if source is None:
            raise ValueError("Source matter not found.")
        if target is None:
            raise ValueError("Target matter not found.")
        if source_matter_id == target_matter_id:
            raise ValueError("Cannot merge a matter into itself.")
        if _is_descendant_of(session, target_matter_id, source_matter_id):
            raise ValueError("Cannot merge into a descendant of the source matter.")
        # Reassign all time entries (including any running) to target
        session.query(TimeEntry).filter(TimeEntry.matter_id == source_matter_id).update(
            {"matter_id": target_matter_id}
        )
        # Reparent children of source to target
        session.query(Matter).filter(Matter.parent_id == source_matter_id).update(
            {"parent_id": target_matter_id}
        )
        session.delete(source)
        session.commit()


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
