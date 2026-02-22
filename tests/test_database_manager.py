"""
Pytest suite for database_manager.py.
Focus: hierarchical matter creation, get_full_path accuracy, RLS-style owner filtering.
"""
from datetime import date

import pytest

from database_manager import DatabaseManager


# --- Hierarchical matter creation ---


class TestHierarchicalMatterCreation:
    """Test creating matters in a tree: root (client), children, grandchildren."""

    def test_add_root_matter(self, db_user1: DatabaseManager):
        """Adding a matter with parent_id=None creates a root (client)."""
        m = db_user1.add_matter("Acme Corp", "acme", parent_id=None)
        assert m.id is not None
        assert m.name == "Acme Corp"
        assert m.matter_code == "acme"
        assert m.parent_id is None
        assert m.owner_id == db_user1.current_user_id

    def test_add_child_and_grandchild(self, db_user1: DatabaseManager):
        """Add client -> project -> subproject and verify parent links."""
        client = db_user1.add_matter("Client A", "client-a", parent_id=None)
        project = db_user1.add_matter("Project X", "project-x", parent_id=client.id)
        sub = db_user1.add_matter("Subtask 1", "subtask-1", parent_id=project.id)
        assert client.parent_id is None
        assert project.parent_id == client.id
        assert sub.parent_id == project.id

    def test_get_all_matters_returns_hierarchy_in_order(self, db_user1: DatabaseManager):
        """get_all_matters returns all matters for current user, ordered by matter_code."""
        db_user1.add_matter("Zebra", "zebra", parent_id=None)
        db_user1.add_matter("Alpha", "alpha", parent_id=None)
        db_user1.add_matter("Beta", "beta", parent_id=None)
        matters = db_user1.get_all_matters()
        codes = [m.matter_code for m in matters]
        assert codes == ["alpha", "beta", "zebra"]


# --- get_full_path accuracy ---


class TestGetFullPath:
    """Test that get_matters_with_full_paths returns correct hierarchical paths."""

    def test_single_root_path_is_name_only(self, db_user1: DatabaseManager):
        """Root matter path is just its name."""
        db_user1.add_matter("Acme", "acme", parent_id=None)
        paths = db_user1.get_matters_with_full_paths()
        assert len(paths) == 1
        mid, path = paths[0]
        assert path == "Acme"

    def test_two_level_path(self, db_user1: DatabaseManager):
        """Client > Project."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        db_user1.add_matter("Project", "project", parent_id=client.id)
        paths = db_user1.get_matters_with_full_paths()
        path_by_id = {mid: p for mid, p in paths}
        assert path_by_id[client.id] == "Client"
        # project id is the other one
        project_id = next(mid for mid, p in paths if p == "Client > Project")
        assert path_by_id[project_id] == "Client > Project"

    def test_three_level_path(self, db_user1: DatabaseManager):
        """Client > Project > Sub."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        project = db_user1.add_matter("Project", "project", parent_id=client.id)
        sub = db_user1.add_matter("Sub", "sub", parent_id=project.id)
        paths = db_user1.get_matters_with_full_paths()
        path_by_id = {mid: p for mid, p in paths}
        assert path_by_id[client.id] == "Client"
        assert path_by_id[project.id] == "Client > Project"
        assert path_by_id[sub.id] == "Client > Project > Sub"

    def test_for_timer_excludes_roots(self, db_user1: DatabaseManager):
        """get_matters_with_full_paths(for_timer=True) excludes root matters."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        db_user1.add_matter("Project", "project", parent_id=client.id)
        all_paths = db_user1.get_matters_with_full_paths(for_timer=False)
        timer_paths = db_user1.get_matters_with_full_paths(for_timer=True)
        assert len(all_paths) == 2
        assert len(timer_paths) == 1
        assert timer_paths[0][1] == "Client > Project"


# --- suggest_unique_code (per-owner) ---


class TestSuggestUniqueCode:
    """Test matter_code suggestion: slugify and per-owner uniqueness."""

    def test_slugify_and_first_suggestion(self, db_user1: DatabaseManager):
        """First suggestion for a name is the slug."""
        code = db_user1.suggest_unique_code("Acme Corp")
        assert code == "acme-corp"

    def test_duplicate_same_owner_gets_suffix(self, db_user1: DatabaseManager):
        """Same owner, same slug -> slug-2, slug-3, ..."""
        db_user1.add_matter("Acme", "acme", parent_id=None)
        assert db_user1.suggest_unique_code("acme") == "acme-2"
        db_user1.add_matter("Acme 2", "acme-2", parent_id=None)
        assert db_user1.suggest_unique_code("acme") == "acme-3"

    def test_different_owners_can_have_same_matter_code(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """User1 and User2 can both have a matter with code 'acme' (unique per owner)."""
        db_user1.add_matter("Acme", "acme", parent_id=None)
        # User2 suggests "acme" -> should get "acme" (not acme-2) because they have no matters yet
        code = db_user2.suggest_unique_code("Acme")
        assert code == "acme"
        db_user2.add_matter("Acme", "acme", parent_id=None)
        # Both have acme
        matters1 = db_user1.get_all_matters()
        matters2 = db_user2.get_all_matters()
        assert [m.matter_code for m in matters1] == ["acme"]
        assert [m.matter_code for m in matters2] == ["acme"]


# --- RLS-style filtering (owner_id) ---


class TestOwnerFiltering:
    """Test that each user only sees and affects their own matters and time entries."""

    def test_user1_sees_only_own_matters(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """User1 adds matters; user2 adds one. Each sees only their own."""
        db_user1.add_matter("Client A", "client-a", parent_id=None)
        db_user1.add_matter("Client B", "client-b", parent_id=None)
        db_user2.add_matter("Solo", "solo", parent_id=None)
        list1 = db_user1.get_all_matters()
        list2 = db_user2.get_all_matters()
        codes1 = {m.matter_code for m in list1}
        codes2 = {m.matter_code for m in list2}
        assert codes1 == {"client-a", "client-b"}
        assert codes2 == {"solo"}

    def test_get_matters_with_full_paths_respects_owner(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Full paths list is owner-scoped."""
        db_user1.add_matter("A", "a", parent_id=None)
        db_user2.add_matter("B", "b", parent_id=None)
        paths1 = db_user1.get_matters_with_full_paths()
        paths2 = db_user2.get_matters_with_full_paths()
        assert len(paths1) == 1 and paths1[0][1] == "A"
        assert len(paths2) == 1 and paths2[0][1] == "B"

    def test_user2_cannot_start_timer_on_user1_matter(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Starting a timer requires the matter to belong to the current user."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        project = db_user1.add_matter("Project", "project", parent_id=client.id)
        # User2 tries to start timer on user1's matter -> Matter not found (filtered out)
        with pytest.raises(ValueError, match="Matter not found"):
            db_user2.start_timer(project.id)

    def test_time_entries_are_owner_scoped(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Each user only sees their own time entries."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        db_user1.start_timer(project.id, "Work")
        db_user1.stop_timer()
        # User2 has no entries
        today = date.today()
        entries1 = db_user1.get_time_entries_for_day(today)
        entries2 = db_user2.get_time_entries_for_day(today)
        assert len(entries1) >= 1
        assert len(entries2) == 0

    def test_get_descendant_matter_ids_only_owner_matters(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Descendants are only within the current user's matters."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        p1 = db_user1.add_matter("P1", "p1", parent_id=client.id)
        p2 = db_user1.add_matter("P2", "p2", parent_id=client.id)
        descendants = db_user1.get_descendant_matter_ids(client.id)
        assert descendants == {p1.id, p2.id}
        # User2 has no matters, so no descendants for any id (or matter not visible)
        # If user2 calls with user1's client id, they get empty (matter not in their query)
        list2 = db_user2.get_all_matters()
        assert len(list2) == 0
        # So get_descendant_matter_ids(client.id) for user2: _matter_query returns no matters,
        # so child_matters is empty, so descendants is empty
        desc2 = db_user2.get_descendant_matter_ids(client.id)
        assert desc2 == set()

    def test_get_descendant_matter_ids_nested(self, db_user1: DatabaseManager):
        """Descendants include grandchildren."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        sub = db_user1.add_matter("S", "s", parent_id=project.id)
        descendants_of_client = db_user1.get_descendant_matter_ids(client.id)
        descendants_of_project = db_user1.get_descendant_matter_ids(project.id)
        assert descendants_of_client == {project.id, sub.id}
        assert descendants_of_project == {sub.id}


# --- require_user ---


class TestRequireUser:
    """Operations that need current_user_id must raise when it is None."""

    def test_add_matter_requires_user(self, db_path):
        """add_matter with no current_user_id raises."""
        dm = DatabaseManager(db_path=db_path)
        dm.init_db()
        # Create at least one user so we can have a db with no user
        import bcrypt
        pw = bcrypt.hashpw(b"x", bcrypt.gensalt()).decode("utf-8")
        dm.create_first_admin("u", pw)
        dm_no_user = DatabaseManager(db_path=db_path, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            dm_no_user.add_matter("X", "x", parent_id=None)

    def test_get_all_matters_requires_user(self, db_path):
        """get_all_matters with no current_user_id raises."""
        dm = DatabaseManager(db_path=db_path)
        dm.init_db()
        with pytest.raises(ValueError, match="Current user is not set"):
            dm.get_all_matters()
