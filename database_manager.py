"""
Database manager for Sentinel Solo: matters and time entries.
"""
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from models import Base, Matter, TimeEntry


class DatabaseManager:
    """Database as an object: owns engine and sessions, exposes operations as methods."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent / "sentinel.db"
        path_str = str(db_path)
        self._engine = create_engine(f"sqlite:///{path_str}", echo=False)
        self._session_factory = sessionmaker(
            bind=self._engine, autocommit=False, autoflush=False
        )

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        """Yield a new session (context manager)."""
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def init_db(self) -> None:
        """Create tables if they do not exist. Add invoiced column to time_entries if missing."""
        Base.metadata.create_all(self._engine)
        # Migration: add invoiced column if it doesn't exist (e.g. existing DBs from before timesheet)
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT 1 FROM pragma_table_info('time_entries') WHERE name='invoiced'")
            )
            if r.fetchone() is None:
                conn.execute(
                    text("ALTER TABLE time_entries ADD COLUMN invoiced BOOLEAN NOT NULL DEFAULT 0")
                )
                conn.commit()

    def _slugify(self, name: str) -> str:
        """Lowercase, replace non-alphanumeric with hyphen, strip. Empty -> 'matter'."""
        s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
        return s if s else "matter"

    def suggest_unique_code(self, name: str) -> str:
        """Return a unique matter_code from name: slugify, then slug, slug-2, slug-3, ... as needed."""
        slug = self._slugify(name)
        with self._session() as session:
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

    def add_matter(
        self, name: str, matter_code: str, parent_id: int | None = None
    ) -> Matter:
        """Add a new matter. Returns the created Matter."""
        with self._session() as session:
            matter = Matter(name=name, matter_code=matter_code, parent_id=parent_id)
            session.add(matter)
            session.commit()
            session.refresh(matter)
            return matter

    def get_matters_with_full_paths(
        self, for_timer: bool = False
    ) -> list[tuple[int, str]]:
        """Return list of (matter_id, full_path) for dropdown.
        When for_timer=True, only matters with a parent (non-root) are returned."""
        with self._session() as session:
            q = session.query(Matter).order_by(Matter.matter_code)
            if for_timer:
                q = q.filter(Matter.parent_id.isnot(None))
            matters = q.all()
            return [(m.id, m.get_full_path(session)) for m in matters]

    def get_all_matters(self) -> list[Matter]:
        """Return all matters (for Manage Matters tab)."""
        with self._session() as session:
            return list(session.query(Matter).order_by(Matter.matter_code).all())

    def start_timer(
        self, matter_id: int, description: str | None = None
    ) -> TimeEntry:
        """Start a new time entry for the given matter.
        Raises ValueError if matter is a root (client)."""
        with self._session() as session:
            matter = session.query(Matter).get(matter_id)
            if matter is None:
                raise ValueError("Matter not found.")
            if matter.parent_id is None:
                raise ValueError(
                    "Time cannot be logged to a client; select a matter under a client."
                )
            entry = TimeEntry(matter_id=matter_id, description=description or "")
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def stop_timer(self) -> TimeEntry | None:
        """Stop the current running timer. Returns that TimeEntry or None."""
        with self._session() as session:
            entry = (
                session.query(TimeEntry)
                .filter(TimeEntry.end_time.is_(None))
                .order_by(TimeEntry.start_time.desc())
                .first()
            )
            if not entry:
                return None
            entry.end_time = datetime.now()
            entry.duration_seconds = (
                entry.end_time - entry.start_time
            ).total_seconds()
            session.commit()
            session.refresh(entry)
            return entry

    def get_running_entry(self) -> TimeEntry | None:
        """Return the current running time entry, if any."""
        with self._session() as session:
            return (
                session.query(TimeEntry)
                .filter(TimeEntry.end_time.is_(None))
                .order_by(TimeEntry.start_time.desc())
                .first()
            )

    def update_running_entry_start_time(self, new_start: datetime) -> TimeEntry | None:
        """Update the current running entry's start_time. Returns the entry or None."""
        with self._session() as session:
            entry = (
                session.query(TimeEntry)
                .filter(TimeEntry.end_time.is_(None))
                .order_by(TimeEntry.start_time.desc())
                .first()
            )
            if not entry:
                return None
            entry.start_time = new_start
            session.commit()
            session.refresh(entry)
            return entry

    def update_running_entry_description(self, description: str) -> bool:
        """Update the current running entry's description. Returns True if updated."""
        with self._session() as session:
            entry = (
                session.query(TimeEntry)
                .filter(TimeEntry.end_time.is_(None))
                .order_by(TimeEntry.start_time.desc())
                .first()
            )
            if not entry:
                return False
            entry.description = description or ""
            session.commit()
            return True

    def get_time_entries_by_matter(self, matter_id: int) -> list[TimeEntry]:
        """Return all time entries for the matter, newest first."""
        with self._session() as session:
            return list(
                session.query(TimeEntry)
                .filter(TimeEntry.matter_id == matter_id)
                .order_by(TimeEntry.start_time.desc())
                .all()
            )

    def get_time_entries_for_day(self, day: date) -> list[TimeEntry]:
        """Return time entries whose start_time falls on the given day (including running). Chronological order."""
        with self._session() as session:
            start_dt = datetime.combine(day, datetime.min.time())
            end_dt = datetime.combine(day, datetime.max.time()) + timedelta(seconds=1)
            return list(
                session.query(TimeEntry)
                .filter(TimeEntry.start_time >= start_dt, TimeEntry.start_time < end_dt)
                .order_by(TimeEntry.start_time.asc())
                .all()
            )

    def get_descendant_matter_ids(self, matter_id: int) -> set[int]:
        """Return the set of matter ids that are descendants of matter_id (children, grandchildren, etc.)."""
        with self._session() as session:
            child_rows = (
                session.query(Matter.id).filter(Matter.parent_id == matter_id).all()
            )
        child_ids = {r[0] for r in child_rows}
        ids = set(child_ids)
        for cid in child_ids:
            ids |= self.get_descendant_matter_ids(cid)
        return ids

    def get_time_entries_for_export(
        self, matter_ids: set[int], only_not_invoiced: bool
    ) -> list[dict]:
        """
        Return time entries whose matter_id is in matter_ids, optionally only not-invoiced.
        Each item is a dict: id, matter_id, matter_path, description, start_time, end_time, duration_seconds, invoiced.
        Times as ISO strings.
        """
        if not matter_ids:
            return []
        with self._session() as session:
            q = session.query(TimeEntry).filter(TimeEntry.matter_id.in_(matter_ids))
            if only_not_invoiced:
                q = q.filter(TimeEntry.invoiced == False)
            entries = q.order_by(TimeEntry.start_time).all()
            result = []
            for e in entries:
                matter = session.query(Matter).get(e.matter_id)
                path = matter.get_full_path(session) if matter else ""
                result.append({
                    "id": e.id,
                    "matter_id": e.matter_id,
                    "matter_path": path,
                    "description": e.description or "",
                    "start_time": e.start_time.isoformat() if e.start_time else "",
                    "end_time": e.end_time.isoformat() if e.end_time else "",
                    "duration_seconds": e.duration_seconds or 0.0,
                    "invoiced": bool(e.invoiced),
                })
            return result

    def mark_entries_invoiced(self, entry_ids: list[int]) -> None:
        """Set invoiced=True for all TimeEntry rows with id in entry_ids."""
        if not entry_ids:
            return
        with self._session() as session:
            session.query(TimeEntry).filter(TimeEntry.id.in_(entry_ids)).update(
                {TimeEntry.invoiced: True}, synchronize_session=False
            )
            session.commit()

    def _resolve_time_trio(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
        duration_seconds: float | None,
    ) -> tuple[datetime, datetime | None, float]:
        """Given any two of start/end/duration, compute the third."""
        provided = sum(
            x is not None for x in (start_time, end_time, duration_seconds)
        )
        if provided != 2:
            raise ValueError(
                "Provide exactly two of start_time, end_time, duration_seconds."
            )
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
        self,
        entry_id: int,
        description: str | None = None,
        matter_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Update a time entry. Optionally set matter_id (must exist and not be root). Provide time trio or two of start/end/duration."""
        with self._session() as session:
            entry = session.query(TimeEntry).get(entry_id)
            if entry is None:
                raise ValueError("Time entry not found.")
            if description is not None:
                entry.description = description
            if matter_id is not None:
                matter = session.query(Matter).get(matter_id)
                if matter is None:
                    raise ValueError("Matter not found.")
                if matter.parent_id is None:
                    raise ValueError("Time cannot be logged to a client.")
                entry.matter_id = matter_id
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
                    start_t, end_t, dur = self._resolve_time_trio(
                        start_time, end_time, duration_seconds
                    )
                    entry.start_time = start_t
                    entry.end_time = end_t
                    entry.duration_seconds = dur
            session.commit()

    def add_manual_time_entry(
        self,
        matter_id: int,
        description: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        duration_seconds: float | None = None,
    ) -> TimeEntry:
        """Add a completed time entry manually. Provide two or three of start/end/duration."""
        with self._session() as session:
            matter = session.query(Matter).get(matter_id)
            if matter is None:
                raise ValueError("Matter not found.")
            if matter.parent_id is None:
                raise ValueError("Time cannot be logged to a client.")
            provided = sum(
                x is not None for x in (start_time, end_time, duration_seconds)
            )
            if provided == 3:
                if duration_seconds is not None and duration_seconds < 0:
                    raise ValueError("Duration must be non-negative.")
                if start_time and end_time and end_time < start_time:
                    raise ValueError("End time must be after start time.")
                start_t, end_t, dur = (
                    start_time,
                    end_time,
                    duration_seconds or 0.0,
                )
            else:
                start_t, end_t, dur = self._resolve_time_trio(
                    start_time, end_time, duration_seconds
                )
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

    def _get_root_matter_name(self, session: Session, matter: Matter) -> str:
        """Resolve root matter (parent_id is None) and return its name."""
        current = matter
        while current.parent_id is not None:
            current = session.query(Matter).get(current.parent_id)
            if current is None:
                return matter.name
        return current.name

    def _is_descendant_of(
        self, session: Session, matter_id: int, ancestor_id: int
    ) -> bool:
        """Walk from matter_id upward; return True if ancestor_id is reached."""
        current = session.query(Matter).get(matter_id)
        while current is not None and current.parent_id is not None:
            if current.parent_id == ancestor_id:
                return True
            current = session.query(Matter).get(current.parent_id)
        return False

    def get_matters_with_full_paths_excluding(
        self,
        exclude_matter_id: int,
        for_timer: bool = False,
        include_root_option: bool = True,
    ) -> list[tuple[int | None, str]]:
        """Like get_matters_with_full_paths but excludes exclude_matter_id and its descendants."""
        with self._session() as session:
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
                if self._is_descendant_of(session, m.id, exclude_matter_id):
                    continue
                result.append((m.id, m.get_full_path(session)))
            return result

    def move_matter(self, matter_id: int, new_parent_id: int | None) -> None:
        """Move a matter to another client or under another matter."""
        with self._session() as session:
            matter = session.query(Matter).get(matter_id)
            if matter is None:
                raise ValueError("Matter not found.")
            if new_parent_id is not None:
                if new_parent_id == matter_id:
                    raise ValueError("Cannot move a matter to itself.")
                parent = session.query(Matter).get(new_parent_id)
                if parent is None:
                    raise ValueError("New parent matter not found.")
                if self._is_descendant_of(session, new_parent_id, matter_id):
                    raise ValueError(
                        "Cannot move a matter under one of its descendants."
                    )
            matter.parent_id = new_parent_id
            session.commit()

    def merge_matter_into(
        self, source_matter_id: int, target_matter_id: int
    ) -> None:
        """Merge source matter into target: reassign time entries and children, delete source."""
        with self._session() as session:
            source = session.query(Matter).get(source_matter_id)
            target = session.query(Matter).get(target_matter_id)
            if source is None:
                raise ValueError("Source matter not found.")
            if target is None:
                raise ValueError("Target matter not found.")
            if source_matter_id == target_matter_id:
                raise ValueError("Cannot merge a matter into itself.")
            if self._is_descendant_of(
                session, target_matter_id, source_matter_id
            ):
                raise ValueError(
                    "Cannot merge into a descendant of the source matter."
                )
            session.query(TimeEntry).filter(
                TimeEntry.matter_id == source_matter_id
            ).update({"matter_id": target_matter_id})
            session.query(Matter).filter(
                Matter.parent_id == source_matter_id
            ).update({"parent_id": target_matter_id})
            session.delete(source)
            session.commit()

    def get_time_by_client_and_matter(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[tuple[str, str, float]]:
        """Return aggregated time by client and matter (full path). Sorted by client then matter."""
        with self._session() as session:
            q = session.query(TimeEntry).filter(
                TimeEntry.end_time.isnot(None)
            )
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
                client_name = self._get_root_matter_name(session, matter)
                full_path = matter.get_full_path(session)
                key = (client_name, full_path)
                agg[key] = agg.get(key, 0.0) + (entry.duration_seconds or 0.0)
            result = [(client, path, total) for (client, path), total in agg.items()]
            result.sort(key=lambda r: (r[0], r[1]))
            return result


# Default instance for use by the app
db = DatabaseManager()
