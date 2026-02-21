# Sentinel Solo (v.0.0.3)

A desktop time-tracking app with a hierarchy of **clients** and **matters** (projects/subprojects). Log time with a timer or by manual entry; view and edit time entries per matter; move or merge matters with time ported correctly.

**Tech stack:** Python 3.12, [Flet](https://flet.dev/) (GUI), SQLAlchemy, SQLite.

## Features

- **Timer** – **Today’s activities** at the top: list of today’s time entries with editable Matter, Description, Start (hh:mm), End (hh:mm), and Duration (H:MM). Changing end recalculates duration; changing start keeps duration and updates end; changing duration updates end. Description is saved when you leave the field. Below: searchable matter list (all clients shown, folded by client), optional task description, then Start/Stop or manual entry.
- **Manual entry** – Same matter selection; enter two of Start time, End time, or Duration; the third is derived. Add the entry to the selected matter.
- **Manage Matters** – Add clients (roots) and matters (under a client or another matter). Per matter: **Move** (to another client or subproject), **Merge** (into another matter; time and children follow), **Time entries** (list, edit, add manual). New clients and matters appear in parent and timer lists immediately.
- **Reporting** – Time by client and matter; clients collapsed by default, click to expand and see matter breakdown; optional search.
- **Timesheet** – Select matters (searchable, folded by client; parent checkbox selects descendants). Export selected time entries to JSON; optionally mark exported entries as invoiced.

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

   On Linux you can use **run.sh**: it runs the app with the project venv (and creates the venv if missing; the script will prompt you to run `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`).

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   or `pip install flet sqlalchemy`.

4. **Run the app**
   ```bash
   python main.py
   ```
   On Linux: `./run.sh` (uses the project venv and sets `XCURSOR_THEME` to avoid cursor theme warnings if needed).

The first run creates a SQLite database (`sentinel.db`) in the project directory.

## Project layout

- **main.py** – Flet UI: Timer tab (today’s activities list + matter selector + timer/manual), Manage Matters tab, Reporting tab, Timesheet tab; dialogs for move/merge and time entries.
- **database_manager.py** – DB access: matters, time entries, move/merge, get/update/add time entries, get time for day, suggest unique code, timesheet export.
- **models.py** – SQLAlchemy models: `Matter` (tree via `parent_id`), `TimeEntry` (linked to matter).
- **run.sh** – Linux launcher: runs the app with the project venv and optional cursor theme env vars.

## Usage notes

- **Today’s activities (Timer tab):** Edit Matter, Description, Start, End, or Duration in place. Changes are saved on blur; end/duration/start are linked as above. Duration is shown as H:MM (no seconds).
- **Matter selection (Timer tab):** Search by name or path; all clients are listed (expand to see matters). All time (timer and manual) is logged to the matter selected there.
- **Time entries (Manage Matters):** Open “Time entries” from a matter’s menu to see, edit, or add entries. When editing or adding, fill two of Start, End, and Duration; the third is computed.
- **Move/Merge:** Use the matter menu (⋮) for “Move…” or “Merge…”. Target selection uses the same searchable, folded list as the Timer.
- **Timesheet:** Check the matters whose time you want to export, then “Export timesheet” to save a JSON file (e.g. under `exports/`). You can optionally mark those entries as invoiced after export.

## License

Use and modify as you like.
