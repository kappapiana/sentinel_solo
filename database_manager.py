"""
Database manager for Sentinel Solo: matters and time entries.
Supports local SQLite (default) or remote PostgreSQL via DATABASE_URL.
Multi-user: owner_id on matters/time_entries; Postgres RLS or SQLite filtering.
"""
import os
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import inspect, event

from models import Base, Matter, TimeEntry, User


class DatabaseManager:
    """Database as an object: owns engine and sessions, exposes operations as methods."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        database_url: str | None = None,
        current_user_id: int | None = None,
    ) -> None:
        self._current_user_id = current_user_id
        url = database_url or os.environ.get("DATABASE_URL")
        if url:
            self._engine = create_engine(url, echo=False)
        else:
            if db_path is None:
                db_path = Path(__file__).resolve().parent / "sentinel.db"
            path_str = str(db_path)
            self._engine = create_engine(f"sqlite:///{path_str}", echo=False)
        self._session_factory = sessionmaker(
            bind=self._engine, autocommit=False, autoflush=False
        )
        self._setup_postgres_pool_checkout()

    @property
    def current_user_id(self) -> int | None:
        """Current user id for this manager (read-only)."""
        return self._current_user_id

    def _setup_postgres_pool_checkout(self) -> None:
        """Register pool checkout to set app.current_user_id (called from __init__ when Postgres)."""
        if self._engine.dialect.name != "postgresql" or self._current_user_id is None:
            return
        uid = str(self._current_user_id)

        @event.listens_for(self._engine.pool, "checkout")
        def _pool_checkout(dbapi_connection, connection_record, connection_proxy):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(
                    "SELECT set_config('app.current_user_id', %s, true)", (uid,)
                )
            finally:
                cursor.close()
            try:
                dbapi_connection.commit()
            except Exception:
                pass

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        """Yield a new session (context manager)."""
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def _require_user(self) -> None:
        """Raise if current_user_id is not set (required for matters/time_entries)."""
        if self._current_user_id is None:
            raise ValueError("Current user is not set.")

    def _matter_query(self, session: Session):
        """Query Matter with owner filter on SQLite."""
        q = session.query(Matter)
        if self._engine.dialect.name == "sqlite" and self._current_user_id is not None:
            q = q.filter(Matter.owner_id == self._current_user_id)
        return q

    def _time_entry_query(self, session: Session):
        """Query TimeEntry with owner filter on SQLite."""
        q = session.query(TimeEntry)
        if self._engine.dialect.name == "sqlite" and self._current_user_id is not None:
            q = q.filter(TimeEntry.owner_id == self._current_user_id)
        return q

    def _is_admin(self, session: Session) -> bool:
        """Return True if the current user is an admin."""
        if self._current_user_id is None:
            return False
        user = session.query(User).filter(User.id == self._current_user_id).first()
        return user is not None and bool(user.is_admin)

    def current_user_is_admin(self) -> bool:
        """Return True if the current user is an admin (for UI)."""
        if self._current_user_id is None:
            return False
        with self._session() as session:
            return self._is_admin(session)

    def init_db(self) -> None:
        """Create tables if they do not exist. For Postgres, enable RLS and create SECURITY DEFINER functions."""
        Base.metadata.create_all(self._engine)
        with self._engine.connect() as conn:
            insp = inspect(conn)
            if "time_entries" in insp.get_table_names():
                columns = [c["name"] for c in insp.get_columns("time_entries")]
                if "invoiced" not in columns:
                    default = "0" if self._engine.dialect.name == "sqlite" else "FALSE"
                    conn.execute(
                        text(f"ALTER TABLE time_entries ADD COLUMN invoiced BOOLEAN NOT NULL DEFAULT {default}")
                    )
                    conn.commit()
        if self._engine.dialect.name == "postgresql":
            self._init_postgres_rls()

    def _init_postgres_rls(self) -> None:
        """Enable RLS on matters, time_entries, users and create SECURITY DEFINER functions."""
        with self._engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION app.current_user_is_admin()
                    RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
                    AS $$
                    SELECT COALESCE(
                        (SELECT is_admin FROM public.users WHERE id::text = current_setting('app.current_user_id', true)),
                        false
                    )
                    $$
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION app.get_login_credentials(p_username text)
                    RETURNS table(id int, password_hash text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
                    AS $$
                    SELECT u.id, u.password_hash FROM public.users u WHERE u.username = p_username
                    $$
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION app.has_any_user()
                    RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
                    AS $$
                    SELECT (SELECT count(*) FROM public.users) > 0
                    $$
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION app.create_first_admin(p_username text, p_password_hash text)
                    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
                    AS $$
                    DECLARE
                        new_id int;
                    BEGIN
                        IF (SELECT count(*) FROM public.users) > 0 THEN
                            RETURN NULL;
                        END IF;
                        INSERT INTO public.users (username, password_hash, is_admin)
                        VALUES (p_username, p_password_hash, true)
                        RETURNING id INTO new_id;
                        RETURN new_id;
                    END
                    $$
                    """
                )
            )
            for table in ("matters", "time_entries", "users"):
                conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            # matters: owner for write; owner or admin for read (admin can export all)
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS matters_owner ON matters;
                    CREATE POLICY matters_owner ON matters
                    FOR ALL USING (owner_id::text = current_setting('app.current_user_id', true))
                    WITH CHECK (owner_id::text = current_setting('app.current_user_id', true))
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS matters_admin_select ON matters;
                    CREATE POLICY matters_admin_select ON matters FOR SELECT
                    USING (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS time_entries_owner ON time_entries;
                    CREATE POLICY time_entries_owner ON time_entries
                    FOR ALL USING (owner_id::text = current_setting('app.current_user_id', true))
                    WITH CHECK (owner_id::text = current_setting('app.current_user_id', true))
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS time_entries_admin_select ON time_entries;
                    CREATE POLICY time_entries_admin_select ON time_entries FOR SELECT
                    USING (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS time_entries_admin_update ON time_entries;
                    CREATE POLICY time_entries_admin_update ON time_entries FOR UPDATE
                    USING (app.current_user_is_admin())
                    WITH CHECK (true)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS time_entries_admin_delete ON time_entries;
                    CREATE POLICY time_entries_admin_delete ON time_entries FOR DELETE
                    USING (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS time_entries_admin_insert ON time_entries;
                    CREATE POLICY time_entries_admin_insert ON time_entries FOR INSERT
                    WITH CHECK (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS matters_admin_delete ON matters;
                    CREATE POLICY matters_admin_delete ON matters FOR DELETE
                    USING (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS matters_admin_insert ON matters;
                    CREATE POLICY matters_admin_insert ON matters FOR INSERT
                    WITH CHECK (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS users_select ON users;
                    CREATE POLICY users_select ON users FOR SELECT
                    USING (id::text = current_setting('app.current_user_id', true) OR app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS users_insert ON users;
                    CREATE POLICY users_insert ON users FOR INSERT
                    WITH CHECK (app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS users_update ON users;
                    CREATE POLICY users_update ON users FOR UPDATE
                    USING (id::text = current_setting('app.current_user_id', true) OR app.current_user_is_admin())
                    WITH CHECK (id::text = current_setting('app.current_user_id', true) OR app.current_user_is_admin())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP POLICY IF EXISTS users_delete ON users;
                    CREATE POLICY users_delete ON users FOR DELETE
                    USING (app.current_user_is_admin())
                    """
                )
            )
            conn.commit()

    def has_any_user(self) -> bool:
        """Return True if at least one user exists. Works without current_user_id (for first-install check)."""
        with self._session() as session:
            if self._engine.dialect.name == "postgresql":
                row = session.execute(text("SELECT app.has_any_user()")).fetchone()
                return bool(row and row[0])
            return session.query(User).count() > 0

    def create_first_admin(self, username: str, password_hash: str) -> int | None:
        """
        Create the first user as admin, only if no users exist. Returns new user id or None if users already exist.
        Works without current_user_id (for first-install button).
        """
        with self._session() as session:
            if self._engine.dialect.name == "postgresql":
                row = session.execute(
                    text("SELECT app.create_first_admin(:u, :h)"),
                    {"u": username, "h": password_hash},
                ).fetchone()
                if row and row[0] is not None:
                    session.commit()
                    return int(row[0])
                return None
            if session.query(User).count() > 0:
                return None
            user = User(
                username=username,
                password_hash=password_hash,
                is_admin=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    def _slugify(self, name: str) -> str:
        """Lowercase, replace non-alphanumeric with hyphen, strip. Empty -> 'matter'."""
        s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
        return s if s else "matter"

    def suggest_unique_code(self, name: str) -> str:
        """Return a unique matter_code from name: slugify, then slug, slug-2, slug-3, ... as needed (per owner)."""
        self._require_user()
        slug = self._slugify(name)
        with self._session() as session:
            matters = self._matter_query(session).filter(
                (Matter.matter_code == slug) | (Matter.matter_code.like(f"{slug}-%"))
            ).all()
            used = {m.matter_code for m in matters}
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
        self._require_user()
        with self._session() as session:
            matter = Matter(
                owner_id=self._current_user_id,
                name=name,
                matter_code=matter_code,
                parent_id=parent_id,
            )
            session.add(matter)
            session.commit()
            session.refresh(matter)
            return matter

    def get_matters_with_full_paths(
        self,
        for_timer: bool = False,
        *,
        include_all_users: bool = False,
    ) -> list[tuple[int, str]]:
        """Return list of (matter_id, full_path) for dropdown.
        When for_timer=True, only matters with a parent (non-root) are returned.
        When include_all_users=True and current user is admin, returns all users' matters (for Timesheet admin view)."""
        self._require_user()
        with self._session() as session:
            if (
                include_all_users
                and self._is_admin(session)
                and self._engine.dialect.name == "sqlite"
            ):
                q = session.query(Matter).order_by(Matter.matter_code)
            else:
                q = self._matter_query(session).order_by(Matter.matter_code)
            if for_timer:
                q = q.filter(Matter.parent_id.isnot(None))
            matters = q.all()
            return [(m.id, m.get_full_path(session)) for m in matters]

    def get_all_matters(self) -> list[Matter]:
        """Return all matters (for Manage Matters tab)."""
        self._require_user()
        with self._session() as session:
            return list(self._matter_query(session).order_by(Matter.matter_code).all())

    def start_timer(
        self, matter_id: int, description: str | None = None
    ) -> TimeEntry:
        """Start a new time entry for the given matter.
        Raises ValueError if matter is a root (client)."""
        self._require_user()
        with self._session() as session:
            matter = self._matter_query(session).filter(Matter.id == matter_id).first()
            if matter is None:
                raise ValueError("Matter not found.")
            if matter.parent_id is None:
                raise ValueError(
                    "Time cannot be logged to a client; select a matter under a client."
                )
            entry = TimeEntry(
                owner_id=self._current_user_id,
                matter_id=matter_id,
                description=description or "",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def stop_timer(self) -> TimeEntry | None:
        """Stop the current running timer. Returns that TimeEntry or None."""
        self._require_user()
        with self._session() as session:
            entry = (
                self._time_entry_query(session)
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
        self._require_user()
        with self._session() as session:
            return (
                self._time_entry_query(session)
                .filter(TimeEntry.end_time.is_(None))
                .order_by(TimeEntry.start_time.desc())
                .first()
            )

    def update_running_entry_start_time(self, new_start: datetime) -> TimeEntry | None:
        """Update the current running entry's start_time. Returns the entry or None."""
        self._require_user()
        with self._session() as session:
            entry = (
                self._time_entry_query(session)
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
        self._require_user()
        with self._session() as session:
            entry = (
                self._time_entry_query(session)
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
        self._require_user()
        with self._session() as session:
            return list(
                self._time_entry_query(session)
                .filter(TimeEntry.matter_id == matter_id)
                .order_by(TimeEntry.start_time.desc())
                .all()
            )

    def get_time_entries_for_day(self, day: date) -> list[TimeEntry]:
        """Return time entries whose start_time falls on the given day (including running). Chronological order."""
        self._require_user()
        with self._session() as session:
            start_dt = datetime.combine(day, datetime.min.time())
            end_dt = datetime.combine(day, datetime.max.time()) + timedelta(seconds=1)
            return list(
                self._time_entry_query(session)
                .filter(TimeEntry.start_time >= start_dt, TimeEntry.start_time < end_dt)
                .order_by(TimeEntry.start_time.asc())
                .all()
            )

    def get_descendant_matter_ids(
        self, matter_id: int, *, include_all_users: bool = False
    ) -> set[int]:
        """Return the set of matter ids that are descendants of matter_id (children, grandchildren, etc.).
        When include_all_users=True and current user is admin, includes descendants across all users (SQLite unscoped)."""
        self._require_user()
        with self._session() as session:
            if (
                include_all_users
                and self._is_admin(session)
                and self._engine.dialect.name == "sqlite"
            ):
                base_q = session.query(Matter)
            else:
                base_q = self._matter_query(session)
            child_matters = base_q.filter(Matter.parent_id == matter_id).all()
        child_ids = {m.id for m in child_matters}
        ids = set(child_ids)
        for cid in child_ids:
            ids |= self.get_descendant_matter_ids(cid, include_all_users=include_all_users)
        return ids

    def get_time_entries_for_export(
        self,
        matter_ids: set[int],
        only_not_invoiced: bool,
        *,
        export_all_users: bool = False,
    ) -> list[dict]:
        """
        Return time entries for export. By default: entries whose matter_id is in matter_ids (owner-scoped).
        If export_all_users is True and the current user is admin: all time entries (all users), ignoring matter_ids.
        Each item is a dict: id, matter_id, matter_path, description, start_time, end_time, duration_seconds, invoiced[, owner_id].
        Times as ISO strings.
        """
        self._require_user()
        with self._session() as session:
            admin = self._is_admin(session)
            if export_all_users:
                if not admin:
                    return []
                # Admin export: all time entries (SQLite: unscoped; Postgres: RLS allows admin SELECT)
                q = (
                    session.query(TimeEntry)
                    if self._engine.dialect.name == "sqlite"
                    else self._time_entry_query(session)
                )
            else:
                if not matter_ids:
                    return []
                # Admin exporting selected matters: include entries from all users in those matters (SQLite unscoped)
                if admin and self._engine.dialect.name == "sqlite":
                    q = session.query(TimeEntry).filter(
                        TimeEntry.matter_id.in_(matter_ids)
                    )
                else:
                    q = self._time_entry_query(session).filter(
                        TimeEntry.matter_id.in_(matter_ids)
                    )
            if only_not_invoiced:
                q = q.filter(TimeEntry.invoiced == False)
            entries = q.order_by(TimeEntry.start_time).all()
            # Resolve matter path: when admin on SQLite use unscoped matter query (see all users' matters)
            if (
                self._engine.dialect.name == "sqlite"
                and (export_all_users or admin)
            ):
                matter_query = session.query(Matter)
            else:
                matter_query = None  # use _matter_query per entry
            result = []
            for e in entries:
                if matter_query is not None:
                    matter = matter_query.filter(Matter.id == e.matter_id).first()
                else:
                    matter = self._matter_query(session).filter(Matter.id == e.matter_id).first()
                path = matter.get_full_path(session) if matter else ""
                item = {
                    "id": e.id,
                    "matter_id": e.matter_id,
                    "matter_path": path,
                    "description": e.description or "",
                    "start_time": e.start_time.isoformat() if e.start_time else "",
                    "end_time": e.end_time.isoformat() if e.end_time else "",
                    "duration_seconds": e.duration_seconds or 0.0,
                    "invoiced": bool(e.invoiced),
                }
                if export_all_users or admin:
                    item["owner_id"] = e.owner_id
                result.append(item)
            return result

    def mark_entries_invoiced(self, entry_ids: list[int]) -> None:
        """Set invoiced=True for all TimeEntry rows with id in entry_ids. Admin can mark any user's entries."""
        self._require_user()
        if not entry_ids:
            return
        with self._session() as session:
            q = (
                session.query(TimeEntry)
                if (
                    self._engine.dialect.name == "sqlite"
                    and self._is_admin(session)
                )
                else self._time_entry_query(session)
            )
            q.filter(TimeEntry.id.in_(entry_ids)).update(
                {TimeEntry.invoiced: True}, synchronize_session=False
            )
            session.commit()

    BACKUP_VERSION = 1

    def export_full_database(self) -> dict:
        """
        Export full database as a portable JSON-serializable dict. Admin only.
        Returns {"version": 1, "exported_at": "<iso>", "users": [...], "matters": [...], "time_entries": [...]}.
        """
        self._require_user()
        with self._session() as session:
            if not self._is_admin(session):
                raise ValueError("Only admin can export the full database.")
            # Unscoped reads (admin sees all via RLS on Postgres; on SQLite we use raw query)
            if self._engine.dialect.name == "sqlite":
                users = session.query(User).order_by(User.id).all()
                matters = session.query(Matter).order_by(Matter.id).all()
                entries = session.query(TimeEntry).order_by(TimeEntry.id).all()
            else:
                users = session.query(User).order_by(User.id).all()
                matters = session.query(Matter).order_by(Matter.id).all()
                entries = session.query(TimeEntry).order_by(TimeEntry.id).all()
        return {
            "version": self.BACKUP_VERSION,
            "exported_at": datetime.now().isoformat(),
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "password_hash": u.password_hash,
                    "is_admin": bool(u.is_admin),
                }
                for u in users
            ],
            "matters": [
                {
                    "id": m.id,
                    "owner_id": m.owner_id,
                    "matter_code": m.matter_code,
                    "name": m.name,
                    "parent_id": m.parent_id,
                }
                for m in matters
            ],
            "time_entries": [
                {
                    "id": e.id,
                    "owner_id": e.owner_id,
                    "matter_id": e.matter_id,
                    "description": e.description or "",
                    "start_time": e.start_time.isoformat() if e.start_time else None,
                    "end_time": e.end_time.isoformat() if e.end_time else None,
                    "duration_seconds": e.duration_seconds if e.duration_seconds is not None else 0.0,
                    "invoiced": bool(e.invoiced),
                }
                for e in entries
            ],
        }

    def import_full_database(self, data: dict) -> None:
        """
        Replace the current database with the backup data. Admin only.
        data must have "version", "users", "matters", "time_entries".
        """
        self._require_user()
        if not isinstance(data, dict):
            raise ValueError("Invalid backup: not a dict.")
        for key in ("version", "users", "matters", "time_entries"):
            if key not in data:
                raise ValueError(f"Invalid backup: missing '{key}'.")
        if data.get("version") != self.BACKUP_VERSION:
            raise ValueError(f"Unsupported backup version: {data.get('version')}.")
        with self._session() as session:
            if not self._is_admin(session):
                raise ValueError("Only admin can import the full database.")
            # Delete in FK order
            session.query(TimeEntry).delete(synchronize_session=False)
            session.query(Matter).delete(synchronize_session=False)
            session.query(User).delete(synchronize_session=False)
            session.flush()
            # Insert preserving IDs
            for row in data["users"]:
                session.add(
                    User(
                        id=row["id"],
                        username=row["username"],
                        password_hash=row.get("password_hash"),
                        is_admin=bool(row.get("is_admin", False)),
                    )
                )
            session.flush()
            for row in data["matters"]:
                session.add(
                    Matter(
                        id=row["id"],
                        owner_id=row["owner_id"],
                        matter_code=row["matter_code"],
                        name=row["name"],
                        parent_id=row.get("parent_id"),
                    )
                )
            session.flush()
            for row in data["time_entries"]:
                start_time = datetime.fromisoformat(row["start_time"]) if row.get("start_time") else None
                end_time = datetime.fromisoformat(row["end_time"]) if row.get("end_time") else None
                session.add(
                    TimeEntry(
                        id=row["id"],
                        owner_id=row["owner_id"],
                        matter_id=row["matter_id"],
                        description=row.get("description") or "",
                        start_time=start_time,
                        end_time=end_time,
                        duration_seconds=float(row.get("duration_seconds", 0) or 0),
                        invoiced=bool(row.get("invoiced", False)),
                    )
                )
            session.commit()
        # Reset Postgres sequences so next auto-insert gets a valid id
        if self._engine.dialect.name == "postgresql":
            with self._session() as session:
                for table, col in (("users", "id"), ("matters", "id"), ("time_entries", "id")):
                    session.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence(:t, :c), COALESCE((SELECT MAX({col}) FROM {table}), 1))"
                        ),
                        {"t": table, "c": col},
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
        self._require_user()
        with self._session() as session:
            entry = self._time_entry_query(session).filter(TimeEntry.id == entry_id).first()
            if entry is None:
                raise ValueError("Time entry not found.")
            if description is not None:
                entry.description = description
            if matter_id is not None:
                matter = self._matter_query(session).filter(Matter.id == matter_id).first()
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
        self._require_user()
        with self._session() as session:
            matter = self._matter_query(session).filter(Matter.id == matter_id).first()
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
                owner_id=self._current_user_id,
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
            current = self._matter_query(session).filter(
                Matter.id == current.parent_id
            ).first()
            if current is None:
                return matter.name
        return current.name

    def _is_descendant_of(
        self, session: Session, matter_id: int, ancestor_id: int
    ) -> bool:
        """Walk from matter_id upward; return True if ancestor_id is reached."""
        current = self._matter_query(session).filter(Matter.id == matter_id).first()
        while current is not None and current.parent_id is not None:
            if current.parent_id == ancestor_id:
                return True
            current = self._matter_query(session).filter(
                Matter.id == current.parent_id
            ).first()
        return False

    def get_matters_with_full_paths_excluding(
        self,
        exclude_matter_id: int,
        for_timer: bool = False,
        include_root_option: bool = True,
    ) -> list[tuple[int | None, str]]:
        """Like get_matters_with_full_paths but excludes exclude_matter_id and its descendants."""
        self._require_user()
        with self._session() as session:
            q = self._matter_query(session).order_by(Matter.matter_code)
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
        self._require_user()
        with self._session() as session:
            matter = self._matter_query(session).filter(Matter.id == matter_id).first()
            if matter is None:
                raise ValueError("Matter not found.")
            if new_parent_id is not None:
                if new_parent_id == matter_id:
                    raise ValueError("Cannot move a matter to itself.")
                parent = self._matter_query(session).filter(
                    Matter.id == new_parent_id
                ).first()
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
        self._require_user()
        with self._session() as session:
            source = self._matter_query(session).filter(
                Matter.id == source_matter_id
            ).first()
            target = self._matter_query(session).filter(
                Matter.id == target_matter_id
            ).first()
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
            self._time_entry_query(session).filter(
                TimeEntry.matter_id == source_matter_id
            ).update({"matter_id": target_matter_id})
            self._matter_query(session).filter(
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
        self._require_user()
        with self._session() as session:
            q = self._time_entry_query(session).filter(
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
                matter = self._matter_query(session).filter(
                    Matter.id == entry.matter_id
                ).first()
                if matter is None:
                    continue
                client_name = self._get_root_matter_name(session, matter)
                full_path = matter.get_full_path(session)
                key = (client_name, full_path)
                agg[key] = agg.get(key, 0.0) + (entry.duration_seconds or 0.0)
            result = [(client, path, total) for (client, path), total in agg.items()]
            result.sort(key=lambda r: (r[0], r[1]))
            return result

    def get_time_by_client_and_matter_detailed(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[tuple[str, str, float, float]]:
        """Like get_time_by_client_and_matter but returns (client, matter_path, total_seconds, not_invoiced_seconds)."""
        self._require_user()
        with self._session() as session:
            q = self._time_entry_query(session).filter(
                TimeEntry.end_time.isnot(None)
            )
            if date_from is not None:
                start_dt = datetime.combine(date_from, datetime.min.time())
                q = q.filter(TimeEntry.start_time >= start_dt)
            if date_to is not None:
                end_dt = datetime.combine(date_to, datetime.max.time())
                q = q.filter(TimeEntry.start_time <= end_dt)
            entries = q.all()
            agg_total: dict[tuple[str, str], float] = {}
            agg_not_invoiced: dict[tuple[str, str], float] = {}
            for entry in entries:
                matter = self._matter_query(session).filter(
                    Matter.id == entry.matter_id
                ).first()
                if matter is None:
                    continue
                client_name = self._get_root_matter_name(session, matter)
                full_path = matter.get_full_path(session)
                key = (client_name, full_path)
                sec = entry.duration_seconds or 0.0
                agg_total[key] = agg_total.get(key, 0.0) + sec
                if not entry.invoiced:
                    agg_not_invoiced[key] = agg_not_invoiced.get(key, 0.0) + sec
            result = [
                (client, path, agg_total.get((client, path), 0.0), agg_not_invoiced.get((client, path), 0.0))
                for (client, path) in agg_total
            ]
            result.sort(key=lambda r: (r[0], r[1]))
            return result

    # --- Auth and user management ---

    def get_login_credentials(self, username: str) -> tuple[int, str] | None:
        """
        Return (user_id, password_hash) for the given username, or None if not found.
        Used for login: app hashes password and verifies with bcrypt.verify(password, password_hash).
        Works without current_user_id. Postgres: app.get_login_credentials(); SQLite: read users.
        """
        with self._session() as session:
            if self._engine.dialect.name == "postgresql":
                row = session.execute(
                    text("SELECT * FROM app.get_login_credentials(:u)"),
                    {"u": username},
                ).fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return (int(row[0]), str(row[1]))
                return None
            user = session.query(User).filter(User.username == username).first()
            if user and user.password_hash:
                return (user.id, user.password_hash)
            return None

    def get_user(self, user_id: int) -> User | None:
        """Return User by id (current user can read self; admin can read any)."""
        self._require_user()
        with self._session() as session:
            return session.query(User).filter(User.id == user_id).first()

    def list_users(self) -> list[User]:
        """List all users (admin only on Postgres via RLS; SQLite: check is_admin in app)."""
        self._require_user()
        with self._session() as session:
            return list(session.query(User).order_by(User.username).all())

    def create_user(
        self,
        username: str,
        password_hash: str,
        *,
        is_admin: bool = False,
    ) -> User:
        """Create a new user (admin only)."""
        self._require_user()
        with self._session() as session:
            if self._engine.dialect.name == "sqlite":
                admin = (
                    session.query(User)
                    .filter(User.id == self._current_user_id, User.is_admin == True)
                    .first()
                )
                if not admin:
                    raise ValueError("Only admin can create users.")
            user = User(
                username=username,
                password_hash=password_hash,
                is_admin=is_admin,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def update_user(
        self,
        user_id: int,
        *,
        username: str | None = None,
        password_hash: str | None = None,
        is_admin: bool | None = None,
    ) -> None:
        """Update user (own row for non-admin; any row for admin)."""
        self._require_user()
        with self._session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                raise ValueError("User not found.")
            if self._engine.dialect.name == "sqlite":
                is_self = user_id == self._current_user_id
                admin = (
                    session.query(User)
                    .filter(User.id == self._current_user_id)
                    .first()
                )
                if not is_self and (not admin or not admin.is_admin):
                    raise ValueError("Only admin can update other users.")
                if not is_self and is_admin is not None:
                    if not admin or not admin.is_admin:
                        raise ValueError("Only admin can change is_admin.")
            if username is not None:
                user.username = username
            if password_hash is not None:
                user.password_hash = password_hash
            if is_admin is not None:
                user.is_admin = is_admin
            session.commit()

    def delete_user(self, user_id: int) -> None:
        """Delete a user (admin only)."""
        self._require_user()
        with self._session() as session:
            if self._engine.dialect.name == "sqlite":
                admin = (
                    session.query(User)
                    .filter(User.id == self._current_user_id, User.is_admin == True)
                    .first()
                )
                if not admin:
                    raise ValueError("Only admin can delete users.")
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                raise ValueError("User not found.")
            session.delete(user)
            session.commit()


# Default instance for use by the app (no user; for login only)
db = DatabaseManager()
