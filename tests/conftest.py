"""
Pytest fixtures for database_manager tests.
Uses a temporary SQLite database and creates two users (admin and normal) so tests
can exercise owner-scoped (RLS-style) filtering.
"""
import tempfile
from pathlib import Path

import bcrypt
import pytest

from database_manager import DatabaseManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A temporary SQLite database path (same path for all managers in a test)."""
    return tmp_path / "test_sentinel.db"


@pytest.fixture
def db_no_user(db_path: Path) -> DatabaseManager:
    """Database manager with no current_user_id (for init_db and creating first user)."""
    dm = DatabaseManager(db_path=db_path)
    dm.init_db()
    return dm


@pytest.fixture
def db_with_two_users(db_no_user: DatabaseManager, db_path: Path):
    """
    Create two users in the DB and return (db_no_user, user1_id, user2_id).
    user1 is admin (created via create_first_admin), user2 is created by user1.
    """
    # Create first admin
    pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
    user1_id = db_no_user.create_first_admin("admin", pw_hash)
    assert user1_id is not None
    # Create second user as admin
    db_admin = DatabaseManager(db_path=db_path, current_user_id=user1_id)
    pw2 = bcrypt.hashpw(b"user2", bcrypt.gensalt()).decode("utf-8")
    user2 = db_admin.create_user("user2", pw2, is_admin=False)
    user2_id = user2.id
    return db_no_user, user1_id, user2_id


@pytest.fixture
def db_user1(db_path: Path, db_with_two_users) -> DatabaseManager:
    """Database manager scoped to user1 (admin)."""
    _, user1_id, _ = db_with_two_users
    return DatabaseManager(db_path=db_path, current_user_id=user1_id)


@pytest.fixture
def db_user2(db_path: Path, db_with_two_users) -> DatabaseManager:
    """Database manager scoped to user2."""
    _, _, user2_id = db_with_two_users
    return DatabaseManager(db_path=db_path, current_user_id=user2_id)
