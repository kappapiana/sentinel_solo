# Sentinel Solo (v0.0.7)

A desktop time-tracking app with a hierarchy of **clients** and **matters** (projects/subprojects). Log time with a timer or by manual entry; view and edit time entries per matter; set **hourly rates** (EUR) for invoicing; move or merge matters with time ported correctly.

**Tech stack:** Python 3.12, [Flet](https://flet.dev/) (GUI), SQLAlchemy. Database: SQLite (default) or PostgreSQL (remote).

## Features

- **Timer** – **Today’s activities** at the top: list of today’s time entries with editable Matter, Description, Start (hh:mm), End (hh:mm), Duration (H:MM), and **Amount (€)** (duration × applicable hourly rate, color-coded by rate source). Below: searchable matter list (all clients shown, folded by client), optional task description, then Start/Stop or manual entry.
- **Manual entry** – Same matter selection; enter two of Start time, End time, or Duration; the third is derived. Add the entry to the selected matter.
- **Manage Matters** – Add clients (roots) and matters (under a client or another matter). **Add form** order: parent (for matters), then name, then **Client hourly rate (€)** or **Matter hourly rate (€)** (optional; leave empty to use default or set later). Per matter menu: **Edit rate…**, **Move**, **Merge**, **Time entries** (list with amount € per entry, edit, add manual). New clients and matters appear in parent and timer lists immediately.
- **Reporting** – Time by client and matter with **chargeable amounts (€)**; clients collapsed by default, click to expand; amounts colored by rate source (see **Hourly rates** below).
- **Timesheet** – Select matters (searchable, folded by client; parent checkbox selects descendants). **Preview** shows entries with duration and Amount (€) by rate source. **Save to folder** and **Export timesheet** to JSON (includes `amount_eur` and `rate_source` per entry); optionally mark exported entries as invoiced.

Matters support unlimited nesting (Client → Project → Subproject…). Time can only be logged on non-root matters (i.e. under a client).

### Hourly rates (EUR)

Every matter and submatter has an **effective hourly rate** used to compute chargeable amounts. Precedence (all amounts in euro):

1. **User default** – Set in **Users** → Edit (your user) → **Default hourly rate (€)**. Used when no client or matter rate is set.
2. **Client rate** – For a root matter (client), set when adding (Client hourly rate €) or via **Manage Matters** → **Edit rate…**. Used for all matters under that client when they have no own rate.
3. **Matter rate** – For a non-root matter, set when adding (Matter hourly rate €) or via **Edit rate…**. Submatters without a rate inherit the nearest ancestor’s rate.

**Color convention** (wherever chargeable amounts are shown):

- **Red** – User default rate.
- **Orange** – Rate from an upper-level matter (client or parent matter).
- **Green** – Rate specific to the matter at hand.

## Setup

**Requirements:** Python 3.10+ (3.12 recommended).

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

## Tests

From the project root (with venv activated):

```bash
pytest tests/ -v
```

- **tests/test_database_manager.py** – Hierarchical matter creation, `get_full_path` accuracy, per-owner matter code suggestion, RLS-style filtering (each user sees only their own matters and time entries), admin include-all-users and export, reporting aggregation (time by client/matter with total vs not invoiced, plus chargeable amounts and rate source), **hourly rate resolution** (matter > client > user, `add_matter` with optional `hourly_rate_euro`, `update_matter` / `update_user` rate fields, `amount_eur_from_seconds`), **continue_time_entry** (activity group chaining), **delete_time_entry** (remove entry, owner-scoped), backup/restore (export/import full database), and require-user checks.
- **tests/test_regression.py** – User and matter creation, `get_full_path` recursion (multi-level hierarchy), privacy/RLS (one user cannot see another’s matters), and timer start/stop with correct duration calculation.

Fixtures in `tests/conftest.py` use a temporary SQLite database and two users (admin + normal).

## Project layout

- **main.py** – Flet UI: Timer tab (today’s activities with amount column), Manage Matters tab (add client/matter with optional rate; edit rate per matter), Reporting tab (chargeable €), Timesheet tab (preview + export); dialogs for move/merge, edit matter rate, and time entries.
- **database_manager.py** – DB access: matters (incl. `hourly_rate_euro`), time entries, rate resolution, move/merge, get/update/add time entries and matters, get time for day, timesheet export (with amount_eur and rate_source), reporting with amounts.
- **models.py** – SQLAlchemy models: `User` (incl. `default_hourly_rate_euro`), `Matter` (tree via `parent_id`, `hourly_rate_euro`), `TimeEntry` (linked to matter).
- **run.sh** – Linux launcher: runs the app with the project venv and optional cursor theme env vars.
- **install.sh** – Linux installer: installs app under `~/.local` (or `--prefix`), creates venv, adds `sentinel-solo` launcher and desktop menu entry.
- **uninstall.sh** – Linux uninstaller: removes the installed app dir, launcher, and desktop entry (use same `--prefix` as for install).
- **tests/** – Pytest suite: `test_database_manager.py` (hierarchy, full paths, owner filtering, reporting aggregation, hourly rate resolution, continue_time_entry, delete_time_entry, backup/restore), `test_regression.py` (user/matter creation, path recursion, RLS, timer duration); see **Tests** above.

## User administration and admin user

- **What it is:** The app is multi-user. Each user sees only their own matters and time entries. At least one user can be **admin**: they can create, edit, and delete other users; normal users can only change their own login data (username/password and **Default hourly rate (€)**). Admins get a **Users** tab in the navigation (people icon) where they can add users (username, password, optional Admin flag), edit any user (username, password, Default hourly rate, and Admin flag for others), and delete other users (you cannot delete yourself).

- **How to get the admin user:** On first install, when there are no users in the database, the app shows a **“Create first admin”** screen: enter username and password and click **Create admin**. That user is created with admin rights and you are logged in. This works for both **SQLite** and **PostgreSQL** (no manual INSERT needed).

## Backup and restore

Admins can export and import the full database from the **Users** tab (Database backup section at the bottom).

- **Export full database:** Set “Save to folder” (default: Downloads or `exports/`), then click **Export full database**. A file `sentinel_backup_YYYYMMDD_HHMMSS.json` is written with all users, matters, and time entries. Use this for backups or before a reinstall.
- **Import full database:** Enter the full path to a backup JSON file, then click **Import full database**. Confirm the dialog: this **replaces** all current users, matters, and time entries with the backup. After a successful import you are logged out and must log in again. The same backup format works for both SQLite and PostgreSQL.

Recommend closing other sessions before restoring and re-logging in after.

## Usage notes

- **Today’s activities (Timer tab):** Edit Matter, Description, Start, End, or Duration in place. Changes are saved on blur; end/duration/start are linked as above. Duration is shown as H:MM (no seconds).
- **Matter selection (Timer tab):** Search by name or path; all clients are listed (expand to see matters). All time (timer and manual) is logged to the matter selected there.
- **Time entries (Manage Matters):** Open “Time entries” from a matter’s menu to see, edit, or add entries; each entry shows its chargeable Amount (€) with the usual rate-source color. When editing or adding, fill two of Start, End, and Duration; the third is computed.
- **Hourly rates:** Set your **Default hourly rate (€)** in Users → Edit (yourself). When adding a client or matter, you can set **Client hourly rate (€)** or **Matter hourly rate (€)** in the Add form (field order: parent → name → rate). You can also set or change rates later via Manage Matters → **Edit rate…** on each client or matter. Submatters without a rate use the nearest ancestor’s rate; if none, the user default.
- **Move/Merge:** Use the matter menu (⋮) for “Move…” or “Merge…”. Target selection uses the same searchable, folded list as the Timer.
- **Timesheet:** Set **Save to folder** to the directory where the file should go (default is your Downloads folder or the app’s `exports/` directory). Check the matters whose time you want to export, then click **Export timesheet** to save `timesheet_YYYYMMDD_HHMMSS.json` there. You can optionally mark those entries as invoiced after export.

## License

Use and modify as you like.
