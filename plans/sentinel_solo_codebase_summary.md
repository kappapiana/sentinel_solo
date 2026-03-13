# Sentinel Solo Codebase Summary

**Project**: Sentinel Solo - A multi-user desktop time-tracking application built with Python/Flet that supports PostgreSQL Row Level Security (RLS) for data privacy.

**Version**: v0.4.0

---

## Core Architecture

### Technology Stack
- **GUI Framework**: Flet (Python-based, cross-platform: desktop/mobile/web)
- **ORM**: SQLAlchemy with SQLite (default) or PostgreSQL backend support
- **Authentication**: bcrypt password hashing
- **Database Security**: PostgreSQL RLS via SECURITY DEFINER functions for user-scoped data privacy

### File Structure
| File | Size | Purpose |
|------|------|---------|
| [`main.py`](main.py:1) | ~194K chars | Primary Flet UI implementation (SentinelApp class, tab-based layout) |
| [`database_manager.py`](database_manager.py:1) | ~105K chars | Core persistence layer with dual-backend support |
| [`models.py`](models.py:1) | ~5.7K chars | SQLAlchemy ORM model definitions |
| [`ARCHITECTURE.md`](ARCHITECTURE.md:1) | ~9K chars | Detailed system architecture documentation |
| [`README.md`](README.md:1) | ~15.6K chars | User documentation and usage guide |

---

## Data Models ([`models.py`](models.py:1))

### Entity Relationship Diagram

```mermaid
erDiagram
    USER ||--o{ MATTER : owns
    USER ||--o{ TIME_ENTRY : creates
    USER ||--o{ MATTER_SHARE : shares_with
    USER ||--o{ USER_MATTER_RATE : has_rate_override
    MATTER ||--o{ MATTER : "parent/child"
    MATTER ||--o{ TIME_ENTRY : logged_against
    MATTER ||--o{ MATTER_SHARE : shared_to
    MATTER ||--o{ USER_MATTER_RATE : has_rate_override
    TIME_ENTRY }|--|| USER : owned_by
    TIME_ENTRY }|--|{ MATTER : associated_with
    TIME_ENTRY }o--o{ TIME_ENTRY : "activity_group_id" (self-reference)
```

### Model Definitions

1. **User** - Application user with login credentials, admin flag, and optional default hourly rate
2. **Matter** - Hierarchical tree node (roots = clients, children = projects/subprojects) with hourly_rate_euro and budget_eur
3. **TimeEntry** - Logged work unit with start_time, end_time, duration_seconds, invoiced flag, and activity_group_id for grouping segments
4. **MatterShare** - Link table enabling cross-user matter visibility
5. **UserMatterRate** - Per-user hourly rate override per matter (highest precedence in resolution)

---

## Database Manager ([`database_manager.py`](database_manager.py:1))

### Key Design Patterns

- **Dual Backend Support**: SQLite (application-level filtering) and PostgreSQL (RLS enforcement via SECURITY DEFINER functions)
- **User-Scoped Data Privacy**: Each user sees only their own data plus shared matters
- **Rate Resolution Precedence**: Per-user matter rate → Matter rate → Client rate → User default rate

### Core Method Categories

| Category | Methods |
|----------|---------|
| **Database Initialization** | `init_db()`, `_create_schema_if_not_exists()`, migration logic with version tracking |
| **PostgreSQL RLS Setup** | SECURITY DEFINER functions in `app` schema: `get_login_credentials()`, `create_first_admin()`, `get_user_is_admin()`, `list_users()`, `get_user()`, `create_user()`, `update_user()`, `delete_user()` |
| **User Management** | `get_login_credentials()`, `get_user()`, `get_current_user_is_admin()`, `list_users()`, `create_user()`, `update_user()`, `delete_user()` |
| **Matter Operations** | `add_matter()`, `update_matter()`, `delete_matter()`, `find_owned_matter_with_same_path()`, `move_matter()`, `merge_matter_into()`, `merge_other_user_matter_into_mine()` |
| **Time Entry Management** | `start_timer()`, `stop_timer()`, `get_running_entry()`, `continue_time_entry()`, `update_running_entry_*()`, `get_time_entries_by_matter()`, `get_time_entries_for_day()`, `get_time_entry()`, `update_time_entry()`, `delete_time_entry()`, `add_manual_time_entry()` |
| **Reporting Aggregation** | `get_time_by_client_and_matter()`, `get_time_by_client_and_matter_detailed()` (includes invoiced status and rate source) |
| **Budget Tracking** | `get_matter_budget_usage()`, `get_matter_budget_status()`, `_effective_budget_for_matter_with_map()` (minimum of matter's budget and all ancestor budgets) |
| **Matter Sharing** | `add_matter_share()`, `remove_matter_share()`, `list_matter_shares()`, `get_matter_access_users_with_rates()`, `set_user_matter_rate()` |
| **Backup/Restore** | `export_full_database()`, `import_full_database()` (version 1, preserves IDs across all tables) |

---

## UI Implementation ([`main.py`](main.py:1))

### Application Structure

**SentinelApp Class** - Tab-based layout with five main tabs:
1. **Timer Tab** - Running timer display, manual time entry creation
2. **Manage Matters Tab** - Hierarchical matter tree, add/edit/delete operations, budget tracking
3. **Reporting Tab** - Aggregated time by client/matter with invoiced status and rate source color-coding
4. **Timesheet Tab** - Day-by-day activity view grouped by activity_group_id
5. **Users Tab** - User management (admin only)

### Helper Functions

```python
_rate_source_color(source: str) -> str  # teal/green/orange/red for rate sources
format_eur(amount: float) -> str         # "€ 12.34" format
format_elapsed(seconds: float) -> str    # "HH:MM:SS" format
format_elapsed_hm(seconds: float) -> str # "H:MM" format (no seconds)
format_datetime(dt: datetime | None) -> str  # "%Y-%m-%d %H:%M"
format_time(dt: datetime | None) -> str    # "HH:MM" for day-activity rows
parse_time(s: str) -> time | None          # Parse HH:MM or H:MM
parse_datetime(s: str) -> datetime | None  # Parse "%Y-%m-%d %H:%M"
```

---

## PostgreSQL Bootstrap ([`scripts/postgres_bootstrap_login.sql`](scripts/postgres_bootstrap_login.sql:1))

### SECURITY DEFINER Functions Created

| Function | Purpose |
|----------|---------|
| `app.has_any_user()` | Check if any user exists (for first admin creation) |
| `app.get_login_credentials(username)` | Return (user_id, password_hash) for authentication |
| `app.create_first_admin()` | Create initial admin user with unique constraint |
| `app.get_user_is_admin(user_id)` | Check if user is admin (works regardless of RLS) |
| `app.list_users(caller_id)` | List all users (admin-only via RLS) |
| `app.get_user(caller_id, user_id)` | Get user by ID with caller-based access control |
| `app.create_user(caller_id, username, pw_hash, is_admin)` | Create new user (admin-only) |
| `app.update_user(...)` | Update user fields with partial updates |
| `app.delete_user(caller_id, user_id)` | Delete user (admin-only) |

### Graceful Fallback Logic

The code includes fallback handling for older PostgreSQL versions where newer SQL functions may not exist:
- `list_users_for_share` - Used for listing users who can share a matter
- `get_owned_matter_paths` - Used for finding owned matter paths

---

## Test Coverage ([`tests/`](tests/))

| File | Size | Focus Area |
|------|------|------------|
| [`test_database_manager.py`](tests/test_database_manager.py:1) | ~41K chars | Comprehensive DB layer tests (user ops, matter hierarchy, time entries, budget tracking, sharing, backup/restore) |
| [`test_date_picker.py`](tests/test_date_picker.py:1) | ~1.5K chars | Date/time conversion utility tests |
| [`test_regression.py`](tests/test_regression.py:1) | ~6.6K chars | High-level regression tests for common workflows |
| [`conftest.py`](tests/conftest.py:1) | ~1.9K chars | Test fixtures with temporary SQLite and two-user setup |

---

## Key Technical Features

### 1. Matter Hierarchy Resolution
- Recursive path building for display (e.g., "Client > Project > Subproject")
- Unique matter code generation with slugify-based suffixes (-2, -3, etc.)
- Budget inheritance: effective budget = minimum of matter's budget and all ancestor budgets

### 2. Rate Resolution Logic
```
Per-user matter rate (user_matter) → Matter rate → Client/ancestor rate → User default rate
Color-coded in UI: teal → green → orange → red
```

### 3. Activity Grouping
- `activity_group_id` links time entry segments created via "Continue task"
- First segment has None; continued segments point to first entry id
- Timesheet and reporting treat grouped entries as single logical activities

### 4. Cross-User Matter Merging
- `merge_other_user_matter_into_mine()` - When sharing a matter that already exists under another user, time entries are reassigned to the merged matter
- Preserves all time entry history while consolidating under one owner

### 5. Backup/Restore with ID Preservation
- Full database export as JSON (version 1)
- Import preserves original IDs across all tables
- Sequence reset for PostgreSQL after import
- Version checking on restore

---

## Deployment Scripts

| Script | Purpose |
|--------|---------|
| [`install.sh`](install.sh:1) | ~9.4K chars - Dependency installation and setup |
| [`run.sh`](run.sh:1) | 454 chars - Application launcher |
| [`uninstall.sh`](uninstall.sh:1) | ~1.9K chars - Cleanup script |

---

## Summary

This is a **production-ready, well-documented time-tracking application** with:
- Complete test coverage for database operations
- Dual backend support (SQLite/PostgreSQL) with graceful fallbacks
- Clear separation between UI ([`main.py`](main.py:1)) and persistence ([`database_manager.py`](database_manager.py:1))
- Comprehensive documentation in [`README.md`](README.md:1) and [`ARCHITECTURE.md`](ARCHITECTURE.md:1)
- Schema migration logic with backward compatibility
- Row Level Security for multi-user data privacy
- Budget tracking with hierarchical inheritance
- Flexible rate resolution with per-user overrides
