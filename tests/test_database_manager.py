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

    def test_admin_sees_all_matters_with_include_all_users(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Admin (user1) with include_all_users=True sees both users' matters; default remains owner-scoped."""
        db_user1.add_matter("Admin Client", "admin-c", parent_id=None)
        db_user2.add_matter("Other Client", "other-c", parent_id=None)
        paths_default = db_user1.get_matters_with_full_paths()
        paths_all = db_user1.get_matters_with_full_paths(include_all_users=True)
        assert len(paths_default) == 1
        assert any(p == "Admin Client" for _, p in paths_default)
        assert len(paths_all) == 2
        path_names = {p for _, p in paths_all}
        assert path_names == {"Admin Client", "Other Client"}

    def test_non_admin_include_all_users_still_owner_scoped(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Non-admin (user2) with include_all_users=True still sees only their own matters."""
        db_user1.add_matter("Admin Client", "admin-c", parent_id=None)
        db_user2.add_matter("Other Client", "other-c", parent_id=None)
        paths = db_user2.get_matters_with_full_paths(include_all_users=True)
        assert len(paths) == 1
        assert paths[0][1] == "Other Client"

    def test_admin_export_all_users_includes_everyone_entries(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Admin get_time_entries_for_export(export_all_users=True) returns entries from all users."""
        c1 = db_user1.add_matter("C1", "c1", parent_id=None)
        p1 = db_user1.add_matter("P1", "p1", parent_id=c1.id)
        c2 = db_user2.add_matter("C2", "c2", parent_id=None)
        p2 = db_user2.add_matter("P2", "p2", parent_id=c2.id)
        db_user1.start_timer(p1.id, "Admin work")
        db_user1.stop_timer()
        db_user2.start_timer(p2.id, "User2 work")
        db_user2.stop_timer()
        entries = db_user1.get_time_entries_for_export(set(), only_not_invoiced=False, export_all_users=True)
        assert len(entries) >= 2
        owner_ids = {e["owner_id"] for e in entries}
        assert db_user1.current_user_id in owner_ids
        assert db_user2.current_user_id in owner_ids

    def test_admin_export_selected_matters_includes_all_entries_in_matters(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Admin exporting selected matter_ids gets all users' entries in those matters."""
        c2 = db_user2.add_matter("User2 Client", "u2c", parent_id=None)
        p2 = db_user2.add_matter("User2 Project", "u2p", parent_id=c2.id)
        db_user2.start_timer(p2.id, "User2 entry")
        db_user2.stop_timer()
        # Admin selects user2's project and exports (admin sees it via include_all_users in UI)
        entries = db_user1.get_time_entries_for_export(
            {p2.id}, only_not_invoiced=False
        )
        assert len(entries) == 1
        assert entries[0]["owner_id"] == db_user2.current_user_id
        assert "User2" in entries[0]["matter_path"]


# --- reporting aggregation (time by client/matter, total vs not invoiced) ---


class TestReportingAggregation:
    """get_time_by_client_and_matter and get_time_by_client_and_matter_detailed."""

    def test_get_time_by_client_and_matter_detailed_returns_total_and_not_invoiced(
        self, db_user1: DatabaseManager
    ):
        """Detailed returns (client, matter_path, total_seconds, not_invoiced_seconds)."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        db_user1.start_timer(project.id, "Work")
        db_user1.stop_timer()
        rows = db_user1.get_time_by_client_and_matter_detailed()
        assert len(rows) >= 1
        for client_name, matter_path, total, not_invoiced in rows:
            assert total >= 0
            assert not_invoiced >= 0
            assert not_invoiced <= total

    def test_get_time_by_client_and_matter_detailed_invoiced_excluded_from_not_invoiced(
        self, db_user1: DatabaseManager
    ):
        """When entries are marked invoiced, not_invoiced is less than total."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        project = db_user1.add_matter("Project", "project", parent_id=client.id)
        db_user1.start_timer(project.id, "A")
        db_user1.stop_timer()
        db_user1.start_timer(project.id, "B")
        db_user1.stop_timer()
        rows_before = db_user1.get_time_by_client_and_matter_detailed()
        assert len(rows_before) == 1
        _, _, total_before, not_inv_before = rows_before[0]
        assert not_inv_before == total_before
        # Mark one entry as invoiced
        entries = db_user1.get_time_entries_for_day(date.today())
        if len(entries) >= 1:
            db_user1.mark_entries_invoiced([entries[0].id])
            rows_after = db_user1.get_time_by_client_and_matter_detailed()
            assert len(rows_after) == 1
            _, _, total_after, not_inv_after = rows_after[0]
            assert total_after == total_before
            assert not_inv_after < total_after

    def test_get_time_by_client_and_matter_matches_detailed_totals(self, db_user1: DatabaseManager):
        """Original get_time_by_client_and_matter total equals detailed total."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        db_user1.start_timer(project.id)
        db_user1.stop_timer()
        simple = db_user1.get_time_by_client_and_matter()
        detailed = db_user1.get_time_by_client_and_matter_detailed()
        simple_by_key = {(c, p): sec for c, p, sec in simple}
        for c, p, total, _ in detailed:
            assert (c, p) in simple_by_key
            assert simple_by_key[(c, p)] == total


# --- backup / restore ---


class TestBackupRestore:
    """Full database export and import (admin only)."""

    def test_export_full_database_admin_returns_dict(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Admin export returns dict with version, exported_at, users, matters, time_entries."""
        db_user1.add_matter("C", "c", parent_id=None)
        db_user2.add_matter("X", "x", parent_id=None)
        data = db_user1.export_full_database()
        assert data["version"] == DatabaseManager.BACKUP_VERSION
        assert "exported_at" in data
        assert len(data["users"]) == 2
        assert len(data["matters"]) == 2
        assert data["time_entries"] == []

    def test_export_full_database_non_admin_raises(self, db_user2: DatabaseManager):
        """Non-admin export raises ValueError."""
        db_user2.add_matter("X", "x", parent_id=None)
        with pytest.raises(ValueError, match="Only admin can export"):
            db_user2.export_full_database()

    def test_import_full_database_round_trip(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Export then import preserves users, matters, and time entries."""
        c = db_user1.add_matter("Client", "client", parent_id=None)
        p = db_user1.add_matter("Project", "project", parent_id=c.id)
        db_user1.start_timer(p.id, "Work")
        db_user1.stop_timer()
        data = db_user1.export_full_database()
        assert len(data["users"]) >= 2
        assert len(data["matters"]) >= 2
        assert len(data["time_entries"]) >= 1
        db_user1.import_full_database(data)
        data2 = db_user1.export_full_database()
        assert len(data2["users"]) == len(data["users"])
        assert len(data2["matters"]) == len(data["matters"])
        assert len(data2["time_entries"]) == len(data["time_entries"])
        assert data2["users"][0]["username"] == data["users"][0]["username"]
        assert data2["matters"][0]["name"] == data["matters"][0]["name"]

    def test_import_full_database_invalid_data_raises(self, db_user1: DatabaseManager):
        """Import with missing keys or bad version raises."""
        with pytest.raises(ValueError, match="not a dict"):
            db_user1.import_full_database([])
        with pytest.raises(ValueError, match="missing"):
            db_user1.import_full_database({"version": 1})
        with pytest.raises(ValueError, match="Unsupported backup version"):
            db_user1.import_full_database(
                {"version": 99, "users": [], "matters": [], "time_entries": []}
            )

    def test_import_full_database_non_admin_raises(self, db_user2: DatabaseManager, db_user1: DatabaseManager):
        """Non-admin cannot import."""
        data = db_user1.export_full_database()
        with pytest.raises(ValueError, match="Only admin can import"):
            db_user2.import_full_database(data)


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
