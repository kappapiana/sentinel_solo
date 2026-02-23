# Sentinel Solo — Architecture

This document describes how the application is structured and how its main functional areas (Auth, Timer, Matters, Reporting, Timesheet, Users) interact with the core **Matter hierarchy** and the database layer.

## Overview

- **models.py** — SQLAlchemy models: `User`, `Matter` (hierarchy), `TimeEntry`. The Matter tree is the core domain (clients as roots, matters as children with unlimited nesting).
- **database_manager.py** — Single entry point for all persistence. `DatabaseManager` is created with a `current_user_id`; all matter and time-entry operations are **owner-scoped** (RLS-style). Exposes APIs used by the UI.
- **main.py** — Flet UI: one `SentinelApp` instance per logged-in user, tab-based layout. Auth (login / create first admin) runs before the app; after login, a `DatabaseManager(current_user_id=user_id)` is created and passed into `SentinelApp`.

There are no separate Python packages for “Auth” or “Reporting”; these are **logical modules** implemented as methods and helpers inside `main.py` and `database_manager.py`. The sections below describe how each area interacts with the Matter hierarchy and the DB.

---

## Core: Matter hierarchy

- **Matter** has `parent_id` (self-FK). Roots (`parent_id is None`) are **clients**; non-roots are **matters** (projects, subprojects, etc.). Paths are built recursively via `Matter.get_full_path(session)` → e.g. `"Client A > Project X > Sub"`.
- **TimeEntry** belongs to a **Matter** and an **User** (`owner_id`). Time can only be logged on non-root matters.
- **User** has an optional `default_hourly_rate_euro`. Matter (and client) can have `hourly_rate_euro`; effective rate for a matter is resolved as matter → client → user (see database_manager rate APIs).

All lists of matters (timer dropdown, matters tab, move/merge targets, timesheet) use **full paths** from `DatabaseManager.get_matters_with_full_paths(for_timer=...)`, grouped by client (first path segment). The hierarchy is therefore central to every feature that displays or selects matters.

---

## Logical modules and interaction with the Matter hierarchy

### Auth (pre-app flow in main.py)

- **Role:** Decide whether to show “Create first admin” or login; validate credentials; create a `DatabaseManager(current_user_id=...)` and pass it into `SentinelApp`.
- **Interaction with Matter hierarchy:** None directly. Auth only touches `User` and (for create first admin) `DatabaseManager.init_db()`. The Matter hierarchy is only accessed after login, via the per-user `DatabaseManager` instance.

### Timer (SentinelApp._build_timer_tab)

- **Role:** Start/stop timer, today’s activities (edit start/end/duration/description, delete zero-duration entries), manual entry, matter selection, Continue task.
- **Interaction with Matter hierarchy:**
  - Matter list: `get_matters_with_full_paths(for_timer=True)` (non-roots only), grouped by client; selection is a single matter id + path.
  - All time is logged to the selected matter; start/stop and manual entry call `start_timer(matter_id)`, `stop_timer()`, `add_manual_time_entry(matter_id, ...)`.
  - Today’s activities: `get_time_entries_for_day(today)`; edits use `update_time_entry` / `delete_time_entry`. Continue uses `continue_time_entry(entry_id)` (same matter, description, new segment linked by `activity_group_id`).

### Matters (SentinelApp._build_matters_tab)

- **Role:** Add/edit clients and matters (with optional hourly rate), move, merge, time entries list per matter.
- **Interaction with Matter hierarchy:**
  - Add: `add_matter(name, code, parent_id=..., hourly_rate_euro=...)` — parent_id defines place in tree.
  - Lists: `get_all_matters()` and `get_matters_with_full_paths()` for dropdowns and move/merge targets; move/merge use `move_matter`, `merge_matter` (hierarchy and time entries updated).
  - Time entries: `get_time_entries_by_matter(matter_id)`, `update_time_entry`, `add_manual_time_entry`, `continue_time_entry`; UI shows full path via matter and paths.

### Reporting (SentinelApp._build_reporting_tab)

- **Role:** Show time and chargeable amounts by client and matter; sort by “most not invoiced” or “most accrued” time; optional search.
- **Interaction with Matter hierarchy:**
  - Data: `get_time_by_client_and_matter_detailed()` returns rows `(client_name, matter_path, total_seconds, not_invoiced_seconds, total_amount_eur, not_inv_amount_eur, rate_source)`. Client is derived from the **full path** (first segment). No direct Matter tree traversal in the UI — everything is driven by this aggregated API keyed by path.
  - Sort preference `reporting_sort` (e.g. most_uninvoiced / most_accrued) is stored in `page.data` and reused by Timesheet for client order.

### Timesheet (SentinelApp._build_timesheet_tab)

- **Role:** Select matters (by client; client checkbox selects all matters for that client), preview, export to JSON, optional mark as invoiced.
- **Interaction with Matter hierarchy:**
  - Matter list: same `get_matters_with_full_paths()` (and same client grouping). Client order uses the **same** `reporting_sort` and `get_time_by_client_and_matter_detailed()` so clients are sorted by not-invoiced or total time, consistent with Reporting.
  - Export: `get_time_entries_for_export(matter_ids, ...)`; matter_ids are the selected non-root matter IDs. Chargeable amounts and rate source come from the same resolution as Reporting.

### Users (SentinelApp._build_users_tab, admin only)

- **Role:** List/add/edit/delete users; edit default hourly rate; database backup/restore.
- **Interaction with Matter hierarchy:** Indirect. User’s `default_hourly_rate_euro` is used when a matter (and its ancestors) have no rate. Backup/restore serializes users, matters, and time_entries (hierarchy is preserved by `parent_id` and FKs).

---

## Data flow summary

1. **Auth** → creates `DatabaseManager(current_user_id)` → passed to `SentinelApp(page, user_db)`.
2. **SentinelApp** holds `self.db` and builds tabs that call `self.db.*` for all reads/writes. Matter hierarchy is never traversed in the UI; paths and aggregates come from `database_manager` (e.g. `get_matters_with_full_paths`, `get_time_by_client_and_matter_detailed`).
3. **Shared state:** `page.data` holds UI preferences (e.g. `reporting_sort`, refresh callbacks). Reporting and Timesheet both read `reporting_sort` so client ordering is consistent.

---

## Regression tests and this setup

Regression tests live under **tests/** and do not depend on a “modular” split of Auth/Reporting into separate packages:

- **tests/test_database_manager.py** — Exercises `DatabaseManager` (matters, paths, owner filtering, reporting aggregation, rates, continue/delete time entry, backup/restore). Uses a temporary DB and two users; no UI.
- **tests/test_regression.py** — User/matter creation, path recursion, RLS (one user cannot see another’s matters), timer duration.

Because Auth and Reporting are implemented inside `main.py` and `database_manager.py` (not as separate installable modules), the same test command continues to apply: run the full test suite with **`pytest tests/`** (or **`pytest`** from the project root). There is no `tests/test_logic.py`; the correct invocation is **`pytest tests/`** so that both `test_database_manager.py` and `test_regression.py` are executed. The regression-testing rule should reference this command so it remains valid for the current layout.
