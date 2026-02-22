"""
Regression tests for database_manager.
Covers: User and Matter creation, get_full_path recursion, privacy/RLS (one user cannot see another's matters),
and timer start/stop with correct duration calculation.
"""
from datetime import date

import bcrypt
import pytest

from database_manager import DatabaseManager


class TestUserAndMatterCreation:
    """Creating a User and a Matter."""

    def test_create_first_user_and_matter(self, db_no_user: DatabaseManager, db_path):
        """First user can be created via create_first_admin; then that user can create a matter."""
        pw_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
        user_id = db_no_user.create_first_admin("alice", pw_hash)
        assert user_id is not None
        db_alice = DatabaseManager(db_path=db_path, current_user_id=user_id)
        matter = db_alice.add_matter("My Client", "my-client", parent_id=None)
        assert matter.id is not None
        assert matter.name == "My Client"
        assert matter.owner_id == user_id

    def test_create_second_user_then_matter(self, db_user1: DatabaseManager, db_user2: DatabaseManager, db_path):
        """Second user (created by admin) can create their own matter."""
        matter = db_user2.add_matter("Other Client", "other-client", parent_id=None)
        assert matter.owner_id == db_user2.current_user_id
        matters = db_user2.get_all_matters()
        assert len(matters) == 1
        assert matters[0].matter_code == "other-client"


class TestGetFullPathRecursion:
    """Verifying get_full_path recursion works (multi-level hierarchy)."""

    def test_full_path_one_level(self, db_user1: DatabaseManager):
        """Root matter: path is just the name."""
        m = db_user1.add_matter("Root", "root", parent_id=None)
        paths = db_user1.get_matters_with_full_paths()
        assert (m.id, "Root") in paths

    def test_full_path_recursion_three_levels(self, db_user1: DatabaseManager):
        """Client > Project > Sub: get_full_path recurses correctly."""
        client = db_user1.add_matter("Client", "client", parent_id=None)
        project = db_user1.add_matter("Project", "project", parent_id=client.id)
        sub = db_user1.add_matter("Sub", "sub", parent_id=project.id)
        paths = db_user1.get_matters_with_full_paths()
        path_by_id = {mid: p for mid, p in paths}
        assert path_by_id[client.id] == "Client"
        assert path_by_id[project.id] == "Client > Project"
        assert path_by_id[sub.id] == "Client > Project > Sub"

    def test_full_path_four_levels(self, db_user1: DatabaseManager):
        """Deeper recursion: A > B > C > D."""
        a = db_user1.add_matter("A", "a", parent_id=None)
        b = db_user1.add_matter("B", "b", parent_id=a.id)
        c = db_user1.add_matter("C", "c", parent_id=b.id)
        d = db_user1.add_matter("D", "d", parent_id=c.id)
        paths = db_user1.get_matters_with_full_paths()
        path_by_id = {mid: p for mid, p in paths}
        assert path_by_id[d.id] == "A > B > C > D"


class TestPrivacyRlsCheck:
    """One user cannot see another user's matters (Privacy/RLS check)."""

    def test_user_cannot_see_other_users_matters_list(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """get_all_matters returns only the current user's matters."""
        db_user1.add_matter("User1 Client", "u1-client", parent_id=None)
        db_user2.add_matter("User2 Client", "u2-client", parent_id=None)
        list1 = db_user1.get_all_matters()
        list2 = db_user2.get_all_matters()
        codes1 = {m.matter_code for m in list1}
        codes2 = {m.matter_code for m in list2}
        assert codes1 == {"u1-client"}
        assert codes2 == {"u2-client"}

    def test_user_cannot_see_other_users_matters_in_full_paths(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """get_matters_with_full_paths is owner-scoped."""
        db_user1.add_matter("Only One", "only-one", parent_id=None)
        paths2 = db_user2.get_matters_with_full_paths()
        assert len(paths2) == 0

    def test_user_cannot_start_timer_on_other_users_matter(self, db_user1: DatabaseManager, db_user2: DatabaseManager):
        """Starting a timer on another user's matter raises (matter not found)."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        with pytest.raises(ValueError, match="Matter not found"):
            db_user2.start_timer(project.id)


class TestTimerDurationCalculation:
    """Starting and stopping a timer: duration is calculated correctly."""

    def test_stop_timer_sets_duration_from_start_and_end(self, db_user1: DatabaseManager):
        """After start_timer and stop_timer, duration_seconds equals end_time - start_time."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        entry = db_user1.start_timer(project.id, "Work")
        assert entry.start_time is not None
        assert entry.end_time is None
        assert entry.duration_seconds == 0.0
        stopped = db_user1.stop_timer()
        assert stopped is not None
        assert stopped.end_time is not None
        expected_duration = (stopped.end_time - stopped.start_time).total_seconds()
        assert stopped.duration_seconds == pytest.approx(expected_duration, abs=1.0)

    def test_no_running_timer_returns_none(self, db_user1: DatabaseManager):
        """stop_timer with no running entry returns None."""
        result = db_user1.stop_timer()
        assert result is None

    def test_stopped_entry_appears_in_day_entries_with_duration(self, db_user1: DatabaseManager):
        """Stopped timer entry is in get_time_entries_for_day and has duration set."""
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        db_user1.start_timer(project.id)
        db_user1.stop_timer()
        today = date.today()
        entries = db_user1.get_time_entries_for_day(today)
        assert len(entries) >= 1
        last = entries[-1]
        assert last.end_time is not None
        assert last.duration_seconds is not None
        assert last.duration_seconds >= 0
        assert last.duration_seconds == (last.end_time - last.start_time).total_seconds()
