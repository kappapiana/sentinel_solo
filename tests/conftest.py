"""
Pytest fixtures for database_manager tests.
Uses a temporary SQLite database and creates two users (admin and normal) so tests
can exercise owner-scoped (RLS-style) filtering.

Optimized with session-scoped caching for faster test execution.
"""
import json
import shutil
from pathlib import Path

import bcrypt
import pytest

from database_manager import DatabaseManager


# Session-scoped: Create a base database template once per test session
@pytest.fixture(scope="session")
def db_template_path(tmp_path_factory: pytest.TempPathFactory):
    """Create a base database with schema and first admin (created once per session)."""
    template_dir = tmp_path_factory.mktemp("db_templates")
    path = template_dir / "base.db"
    
    # Only create if it doesn't exist (for parallel test safety)
    if not path.exists():
        dm = DatabaseManager(db_path=str(path))
        dm.init_db()
        pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
        user1_id = dm.create_first_admin("admin", pw_hash)
        assert user1_id is not None
        
        # Create second user on the template
        db_admin = DatabaseManager(db_path=str(path), current_user_id=user1_id)
        pw2 = bcrypt.hashpw(b"user2", bcrypt.gensalt()).decode("utf-8")
        user2 = db_admin.create_user("user2", pw2, is_admin=False)
        
        # Store both user IDs in a sidecar file for retrieval
        with open(template_dir / "user_ids.json", "w") as f:
            json.dump({"admin_id": user1_id, "user2_id": user2.id}, f)
    
    # Read back the user IDs
    with open(template_dir / "user_ids.json", "r") as f:
        user_ids = json.load(f)
    
    return str(path), user_ids["admin_id"], user_ids["user2_id"]


# Per-test: Temporary database path (for tests that need direct control)
@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A temporary SQLite database path."""
    return tmp_path / "test_sentinel.db"


@pytest.fixture
def db_user1(db_template_path, tmp_path: Path) -> DatabaseManager:
    """Fresh DB copy with admin user for each test (isolated)."""
    base_path, admin_id, _ = db_template_path
    test_db = tmp_path / "test.db"
    shutil.copy(str(base_path), str(test_db))
    return DatabaseManager(db_path=str(test_db), current_user_id=admin_id)


@pytest.fixture
def db_user2(db_template_path, tmp_path: Path) -> DatabaseManager:
    """Fresh DB copy with normal user for each test (isolated)."""
    base_path, _, user2_id = db_template_path
    test_db = tmp_path / "test.db"
    shutil.copy(str(base_path), str(test_db))
    return DatabaseManager(db_path=str(test_db), current_user_id=user2_id)


@pytest.fixture
def db_no_user(db_template_path, tmp_path: Path) -> DatabaseManager:
    """Fresh DB copy with no user context (for init operations)."""
    base_path, _, _ = db_template_path
    test_db = tmp_path / "test.db"
    shutil.copy(str(base_path), str(test_db))
    return DatabaseManager(db_path=str(test_db))


@pytest.fixture
def db_with_two_users(db_template_path):
    """Returns the template path and user IDs for tests needing direct access."""
    return db_template_path
