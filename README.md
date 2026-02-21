# Sentinel Solo (v.0.0.3)

A desktop time-tracking app with a hierarchy of **clients** and **matters** (projects/subprojects). Log time with a timer or by manual entry; view and edit time entries per matter; move or merge matters with time ported correctly.

**Tech stack:** Python 3.12, [Flet](https://flet.dev/) (GUI), SQLAlchemy. Database: SQLite (default) or PostgreSQL (remote).

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

   **Linux installer (optional):** run `./install.sh` to install under `~/.local` (venv, launcher `sentinel-solo`, and a desktop menu entry). Use `./install.sh --prefix /usr/local` for a system-wide install (may require sudo for directory creation). To remove: `./uninstall.sh` (or `./uninstall.sh --prefix /usr/local` if you installed system-wide).

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

The first run creates a SQLite database (`sentinel.db`) in the project directory. If no users exist, the app shows a **Create first admin** form so you can choose username and password for the initial admin (see below).

**Optional: remote PostgreSQL**  
To use a shared remote database (e.g. for multiple devices or Android), set the **`DATABASE_URL`** environment variable to a PostgreSQL connection string before starting the app:

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/dbname"
python main.py
```

Create the database and tables on the server first (run the app once with that URL, or run `Base.metadata.create_all` against the engine). Use SSL and strong credentials in production; ensure the host allows connections from your clients (e.g. firewall, VPN).

**Cross-platform and Android**  
Flet runs on Windows, macOS, Linux, web, and mobile. To build an Android APK, use Flet’s build tools (see [Flet docs](https://flet.dev/docs/)); install Android SDK/NDK as required and run the APK build command. The same codebase runs on desktop and mobile.

## Project layout

- **main.py** – Flet UI: Timer tab (today’s activities list + matter selector + timer/manual), Manage Matters tab, Reporting tab, Timesheet tab; dialogs for move/merge and time entries.
- **database_manager.py** – DB access: matters, time entries, move/merge, get/update/add time entries, get time for day, suggest unique code, timesheet export.
- **models.py** – SQLAlchemy models: `Matter` (tree via `parent_id`), `TimeEntry` (linked to matter).
- **run.sh** – Linux launcher: runs the app with the project venv and optional cursor theme env vars.
- **install.sh** – Linux installer: installs app under `~/.local` (or `--prefix`), creates venv, adds `sentinel-solo` launcher and desktop menu entry.
- **uninstall.sh** – Linux uninstaller: removes the installed app dir, launcher, and desktop entry (use same `--prefix` as for install).

## User administration and admin user

- **What it is:** The app is multi-user. Each user sees only their own matters and time entries. At least one user can be **admin**: they can create, edit, and delete other users; normal users can only change their own login data (username/password). There is no in-app “User administration” screen yet—the backend supports it (`list_users`, `create_user`, `update_user`, `delete_user`), so a future version could add a settings or admin tab.

- **How to get the admin user:** On first install, when there are no users in the database, the app shows a **“Create first admin”** screen: enter username and password and click **Create admin**. That user is created with admin rights and you are logged in. This works for both **SQLite** and **PostgreSQL** (no manual INSERT needed).

## Usage notes

- **Today’s activities (Timer tab):** Edit Matter, Description, Start, End, or Duration in place. Changes are saved on blur; end/duration/start are linked as above. Duration is shown as H:MM (no seconds).
- **Matter selection (Timer tab):** Search by name or path; all clients are listed (expand to see matters). All time (timer and manual) is logged to the matter selected there.
- **Time entries (Manage Matters):** Open “Time entries” from a matter’s menu to see, edit, or add entries. When editing or adding, fill two of Start, End, and Duration; the third is computed.
- **Move/Merge:** Use the matter menu (⋮) for “Move…” or “Merge…”. Target selection uses the same searchable, folded list as the Timer.
- **Timesheet:** Check the matters whose time you want to export, then “Export timesheet” to save a JSON file (e.g. under `exports/`). You can optionally mark those entries as invoiced after export.

## License

Use and modify as you like.
