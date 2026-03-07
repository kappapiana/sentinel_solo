# Sentinel Solo (v0.4.0)

A desktop time-tracking app with a hierarchy of **clients** and **matters** (projects/subprojects). Log time with a timer or by manual entry; view and edit time entries per matter; set **hourly rates** (EUR) for invoicing (including **per-user rates per matter**); move or merge matters with time ported correctly; and **share matters between users**.

**Tech stack:** Python 3.12, [Flet](https://flet.dev/) (GUI), SQLAlchemy. Database: SQLite (default) or PostgreSQL (remote).

## Features

- **Timer** – **Start timing first:** at the top, a matter chip shows the current selection; below it a compact searchable matter list (clients folded by default). **Start** / **Stop** and **Manual entry** are right there so you can start or stop the timer without scrolling. **Today’s activities** (list of today’s time entries with editable Matter, Description, Start, End, Duration, **Amount (€)**) sit below in a **collapsible** section. Amounts are color-coded by rate source (see **Hourly rates** below; a tooltip on the column header explains the colors in-app).
- **Manual entry** – Click **Manual entry** on the Timer tab to open a **dialog**: the current matter is shown (read-only); enter two of Start time, End time, or Duration and the third is derived. Add the entry and close the dialog; the timer and matter selection stay visible (no mode switch).
- **Manage Matters** – Add clients (roots) and matters (under a client or another matter). **Add form:** choose Client or Matter; for matters, pick the **parent** from a **searchable list** (by client, same pattern as Move). Then name and optional **Client hourly rate (€)** or **Matter hourly rate (€)**. Per matter menu: **Log time** (jump to Timer with this matter selected), **Edit rate…**, **Move**, **Merge**, **Time entries**, and for owners **Share…**. New clients and matters appear in the parent list and Timer immediately.
- **Reporting** – Time by client and matter with **chargeable amounts (€)**; the **first client** is expanded by default so matters are visible at a glance; click to expand/collapse others. Amounts colored by rate source; a short legend is shown under “By client”.
- **Timesheet** – **Matter selection** (search, Unselect all, Sort; then checkboxes by client/matter). **Export** section: save-to folder (last used folder is remembered), “Only not invoiced” checkbox, **Preview** and **Export timesheet** to JSON (includes `amount_eur` and `rate_source` per entry); optionally mark exported entries as invoiced.

Matters support unlimited nesting (Client → Project → Subproject…). Time can only be logged on non-root matters (i.e. under a client). A matter is owned by one user but can be **shared** with others; all shared users see each other’s entries on that matter.

### Hourly rates (EUR)

Every matter and submatter has an **effective hourly rate** used to compute chargeable amounts. Precedence (all amounts in euro):

1. **Per-user rate for this matter** – Optional **“My rate for this matter (€)”** override that can be set per user per matter (owners can also set per-user rates for users who have access). When present, this wins over everything else.
2. **Matter rate** – For a non-root matter, set when adding (Matter hourly rate €) or via **Edit rate…**. Submatters without a rate inherit the nearest ancestor’s rate.
3. **Client rate** – For a root matter (client), set when adding (Client hourly rate €) or via **Manage Matters** → **Edit rate…**. Used for all matters under that client when they have no own rate.
4. **User default** – Set in **Users** → Edit (your user) → **Default hourly rate (€)**. Used when no client or matter rate is set for that user.

**Color convention** (wherever chargeable amounts are shown; also explained in the UI via tooltips and the Reporting legend):

- **Teal** – Per-user rate for this matter (user–matter override).
- **Green** – Rate specific to the matter at hand.
- **Orange** – Rate from an upper-level matter (client or parent matter).
- **Red** – User default rate.

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

   **Linux installer (optional):** run `./install.sh` to install under `~/.local` (venv, launcher `sentinel-solo`, and a desktop menu entry). Use `./install.sh --prefix /usr/local` for a system-wide install (may require sudo for directory creation). To use PostgreSQL as the backend:

   - `./install.sh --postgres` – interactive prompt (host, port, user, db, password; password not echoed and never appears on the command line).
   - `./install.sh --postgres-params-file /path/to/pg.conf` – read host/port/user/db (no password) from a simple env-style file, still prompting for the password:

     ```bash
     # /path/to/pg.conf (NO secrets)
     PGHOST=my-host
     PGPORT=5432
     PGUSER=db_user
     PGDATABASE=timesheets
     ```

   - `./install.sh --database-url-file /path/to/url.txt` – read a full PostgreSQL URL (including password) from a file (e.g. `chmod 600` that file).

   In all cases the installer writes a `config.env` with `DATABASE_URL` into the install dir, and the launcher sets `DATABASE_URL` from there. To remove: `./uninstall.sh` (or `./uninstall.sh --prefix /usr/local` if you installed system-wide).

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

**Optional: PostgreSQL backend**
To use a shared PostgreSQL database (e.g. for multiple devices or Android), either configure it at install time with `./install.sh --postgres` (interactive; no password on the command line) or `./install.sh --database-url-file /path/to/file` (see above), or set the **`DATABASE_URL`** environment variable to a PostgreSQL connection string before starting the app:

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/dbname"
python main.py
```

Create the database and tables on the server first (run the app once with that URL, or run `Base.metadata.create_all` against the engine). Use SSL and strong credentials in production; ensure the host allows connections from your clients (e.g. firewall, VPN).

**PostgreSQL: bootstrap script (required)**  
With RLS enabled, the app uses SECURITY DEFINER functions in the `app` schema so that login, first-admin creation, the Users tab, and add/edit/delete user all work. Run this **once** as a PostgreSQL superuser (e.g. `postgres`) on your database:

```bash
psql -U postgres -d YOUR_DATABASE -f scripts/postgres_bootstrap_login.sql
```

Replace `YOUR_DATABASE` with your DB name (e.g. `timesheets`). You can run it from the server (e.g. `sudo -u postgres psql -d timesheets -f /path/to/scripts/postgres_bootstrap_login.sql`) or from another host if the superuser can connect. The script creates: login helpers (`has_any_user`, `get_login_credentials`, `create_first_admin`), admin check (`get_user_is_admin`), and user admin helpers (`list_users`, `get_user`, `create_user`, `update_user`, `delete_user`). After that:

- “Log out” shows the normal login form and you can sign in as another user.
- The **Users** tab shows for admin and lists all users.
- Add user, Edit user, and Delete user work for admins.

**Cross-platform and Android**  
Flet runs on Windows, macOS, Linux, web, and mobile. To build an Android APK, use Flet’s build tools (see [Flet docs](https://flet.dev/docs/)); install Android SDK/NDK as required and run the APK build command. The same codebase runs on desktop and mobile.

## Tests

From the project root (with venv activated):

```bash
pytest tests/ -v
```

- **tests/test_database_manager.py** – Hierarchical matter creation, `get_full_path` accuracy, per-owner matter code suggestion, RLS-style filtering (each user sees only their own matters and time entries), admin include-all-users and export, reporting aggregation (time by client/matter with total vs not invoiced, plus chargeable amounts and rate source), hourly rate resolution (matter > client > user, `add_matter` with optional `hourly_rate_euro`, `update_matter` / `update_user` rate fields, `amount_eur_from_seconds`), continue/delete time entry, matter budget, user admin (create/list/get/update/delete user, backup/restore), matter sharing, user-matter rates, same-name conflict (`find_owned_matter_with_same_path`), and require-user checks.
- **tests/test_date_picker.py** – `picker_value_to_local_date` (none, plain date, naive datetime, UTC datetime with astimezone).
- **tests/test_regression.py** – User and matter creation, `get_full_path` recursion (multi-level hierarchy), privacy/RLS (one user cannot see another’s matters), and timer start/stop with correct duration calculation.

Fixtures in `tests/conftest.py` use a temporary SQLite database and two users (admin + normal). The suite does not run against PostgreSQL; PostgreSQL-specific behaviour (RLS and the bootstrap script) is covered by the same logic paths but must be verified with a real Postgres database after running the bootstrap script.

## Project layout

- **main.py** – Flet UI: Timer tab (matter chip + Start/Stop first, collapsible today’s activities, manual entry dialog), Manage Matters tab (add client/matter with searchable parent list; Log time, edit rate, move/merge, time entries, share), Reporting tab (first client expanded by default, chargeable €), Timesheet tab (Matter selection + Export sections, remembered folder); Log out in top bar; dialogs for move/merge, edit rate, time entries, manual entry.
- **database_manager.py** – DB access: matters (incl. `hourly_rate_euro`), time entries, rate resolution, move/merge, get/update/add time entries and matters, get time for day, timesheet export (with amount_eur and rate_source), reporting with amounts.
- **models.py** – SQLAlchemy models: `User` (incl. `default_hourly_rate_euro`), `Matter` (tree via `parent_id`, `hourly_rate_euro`), `TimeEntry` (linked to matter).
- **run.sh** – Linux launcher: runs the app with the project venv and optional cursor theme env vars.
- **install.sh** – Linux installer: installs app under `~/.local` (or `--prefix`), creates venv, adds `sentinel-solo` launcher and desktop menu entry. Options `--postgres` (interactive prompt; password not on CLI) or `--database-url-file FILE` configure PostgreSQL (writes `config.env`; launcher exports `DATABASE_URL`).
- **uninstall.sh** – Linux uninstaller: removes the installed app dir, launcher, and desktop entry (use same `--prefix` as for install).
- **scripts/postgres_bootstrap_login.sql** – Run once as a PostgreSQL superuser so login, first admin, Users tab, and add/edit/delete user work with RLS (see **PostgreSQL: bootstrap script** above).
- **tests/** – Pytest suite: `test_database_manager.py` (hierarchy, full paths, owner filtering, reporting, hourly rates, continue/delete time entry, matter budget, user admin, backup/restore, matter sharing, same-name conflict), `test_date_picker.py` (picker_value_to_local_date), `test_regression.py` (user/matter creation, path recursion, RLS, timer duration); see **Tests** above.

## User administration and admin user

- **What it is:** The app is multi-user. Each user sees only their own matters and time entries. At least one user can be **admin**: they can create, edit, and delete other users; normal users can only change their own login data (username/password and **Default hourly rate (€)**). Admins get a **Users** tab in the navigation (people icon) where they can add users (username, password, optional Admin flag), edit any user (username, password, Default hourly rate, and Admin flag for others), and delete other users (you cannot delete yourself).

- **How to get the admin user:** On first install, when there are no users in the database, the app shows a **“Create first admin”** screen: enter username and password and click **Create admin**. That user is created with admin rights and you are logged in. This works for both **SQLite** and **PostgreSQL** (no manual INSERT needed).

## Backup and restore

Admins can export and import the full database from the **Users** tab (Database backup section at the bottom).

- **Export full database:** Set “Save to folder” (default: Downloads or `exports/`), then click **Export full database**. A file `sentinel_backup_YYYYMMDD_HHMMSS.json` is written with all users, matters, and time entries. Use this for backups or before a reinstall.
- **Import full database:** Enter the full path to a backup JSON file, then click **Import full database**. Confirm the dialog: this **replaces** all current users, matters, and time entries with the backup. After a successful import you are logged out and must log in again. The same backup format works for both SQLite and PostgreSQL.

Recommend closing other sessions before restoring and re-logging in after.

## Usage notes

- **Timer tab:** The matter chip and list at the top show the current matter; Start/Stop and Manual entry are immediately below. Today’s activities are in a collapsible section; edit Matter, Description, Start, End, or Duration in place (saved on blur); duration is H:MM. **Manual entry** opens a dialog with the current matter (read-only); fill two of Start, End, Duration—the third is computed.
- **Matter selection (Timer tab):** Search by name or path; clients are listed (expand to see matters). All time (timer and manual) is logged to the matter selected there.
- **Manage Matters:** When adding a matter, choose the parent from the searchable list (search and expand by client). Use **Log time** in a matter’s menu (⋮) to switch to the Timer tab with that matter already selected. **Time entries** opens a dialog to see, edit, or add entries (Amount € with rate-source colors; fill two of Start/End/Duration).
- **Hourly rates:** Set your **Default hourly rate (€)** in Users → Edit (yourself). When adding a client or matter, set **Client hourly rate (€)** or **Matter hourly rate (€)** in the Add form (optional). Change later via **Edit rate…** on each client or matter. Submatters without a rate use the nearest ancestor’s rate; if none, the user default.
- **Move/Merge:** Use the matter menu (⋮) for “Move…” or “Merge…”. Target selection uses a searchable, folded-by-client list.
- **Timesheet:** Under **Matter selection**, search and check the matters to export. Under **Export**, set **Save to folder** (the last used folder is remembered). Click **Export timesheet** to save `timesheet_YYYYMMDD_HHMMSS.json`; you can optionally mark exported entries as invoiced.
- **Log out:** Use the **Log out** button in the top bar (next to “Logged in as …”). The left rail contains only the main tabs (Timer, Manage Matters, Reporting, Timesheet, and Users for admins).

## License

Use and modify as you like.
