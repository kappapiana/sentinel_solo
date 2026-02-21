# Sentinel Solo (v.0.0.2)

A desktop time-tracking app with a hierarchy of **clients** and **matters** (projects/subprojects). Log time with a timer or by manual entry; view and edit time entries per matter; move or merge matters with time ported correctly.

**Tech stack:** Python 3.12, [Flet](https://flet.dev/) (GUI), SQLAlchemy, SQLite.

## Features

- **Timer** – Select a matter (searchable, folded by client), add an optional task description, then Start/Stop. Elapsed time is stored on the selected matter.
- **Manual entry** – Same matter selection; enter two of Start time, End time, or Duration; the third is derived. Add the entry to the selected matter.
- **Manage Matters** – Add clients (roots) and matters (under a client or another matter). Per matter: **Move** (to another client or subproject), **Merge** (into another matter; time and children follow), **Time entries** (list, edit, add manual).
- **Reporting** – View time aggregated by client and matter (expandable list).

Matters support unlimited nesting (Client → Project → Subproject…). Time can only be logged on non-root matters (i.e. under a client).

## Setup

1. **Clone and enter the project**
   ```bash
   git clone https://github.com/kappapiana/sentinel_solo.git
   cd sentinel_solo
   ```

2. **Create and use a virtual environment**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate   # Linux/macOS
   # or: venv\Scripts\activate  on Windows
   ```

3. **Install dependencies**
   ```bash
   pip install flet sqlalchemy
   ```

4. **Run the app**
   ```bash
   python main.py
   ```

The first run creates a SQLite database (`sentinel.db`) in the project directory.

## Project layout

- **main.py** – Flet UI: Timer tab, Manage Matters tab, Reporting tab; dialogs for move/merge and time entries.
- **database_manager.py** – DB access: matters, time entries, move/merge, get/update/add time entries.
- **models.py** – SQLAlchemy models: `Matter` (tree via `parent_id`), `TimeEntry` (linked to matter).

## Usage notes

- **Matter selection (Timer tab):** Search by name or path; expand/collapse clients to pick a matter. All time (timer and manual) is logged to the matter selected there.
- **Time entries (Manage Matters):** Open “Time entries” from a matter’s menu to see, edit, or add entries. When editing or adding, fill two of Start, End, and Duration; the third is computed.
- **Move/Merge:** Use the matter menu (⋮) for “Move…” or “Merge…”. Target selection uses the same searchable, folded list as the Timer.

## License

Use and modify as you like.
