#!/usr/bin/env bash
# Install Sentinel Solo: copy app, create venv, install deps, add launcher and desktop entry.
# Default: user install under ~/.local (no sudo). Use --prefix for system-wide.
# Database: SQLite by default (file in app dir or cwd). Use --database-url to use PostgreSQL.
# Requires Python 3.10+ (3.12 recommended). Dependencies: flet, sqlalchemy, bcrypt; psycopg2 for PostgreSQL.

set -e

APP_NAME="sentinel-solo"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Default: user-local install
PREFIX="${PREFIX:-$HOME/.local}"
DEST_DIR="$PREFIX/share/$APP_NAME"
BIN_DIR="$PREFIX/bin"
APPS_DIR="$PREFIX/share/applications"

# Optional: install from a different source dir (e.g. when packaging)
SRC_DIR="${SRC_DIR:-$SCRIPT_DIR}"
PYTHON="${PYTHON3:-python3}"

# PostgreSQL: set by --postgres (interactive) or --database-url-file FILE. Written to DEST_DIR/config.env.
DATABASE_URL=""
DATABASE_URL_FILE=""
USE_POSTGRES_INTERACTIVE=""

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "  Install Sentinel Solo under \$PREFIX (default: \$HOME/.local)."
    echo ""
    echo "Options:"
    echo "  --prefix DIR           Install to DIR (e.g. /usr/local for system-wide; may need sudo)."
    echo "  --postgres             Configure PostgreSQL interactively (prompts for host, user, db, password; no secret on CLI)."
    echo "  --database-url-file F  Read PostgreSQL URL from file F (e.g. a chmod 600 file); no secret on CLI."
    echo "  --help                 Show this help."
    echo ""
    echo "Examples:"
    echo "  $0                         # install to ~/.local, SQLite backend"
    echo "  $0 --postgres              # prompt for PostgreSQL connection (password not shown)"
    echo "  $0 --database-url-file ~/.config/sentinel-db.url   # PostgreSQL URL from file"
    echo "  PREFIX=/opt/sentinel $0    # install to /opt/sentinel"
    echo "  $0 --prefix /usr/local     # system-wide (run with sudo if needed)"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            DEST_DIR="$PREFIX/share/$APP_NAME"
            BIN_DIR="$PREFIX/bin"
            APPS_DIR="$PREFIX/share/applications"
            shift 2
            ;;
        --postgres)
            USE_POSTGRES_INTERACTIVE=1
            shift
            ;;
        --database-url-file)
            DATABASE_URL_FILE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# Resolve PostgreSQL URL without putting secrets on the CLI
if [[ -n "$USE_POSTGRES_INTERACTIVE" ]]; then
    echo "PostgreSQL connection (password will not be echoed):"
    read -r -p "  Host [localhost]: " pg_host
    pg_host="${pg_host:-localhost}"
    read -r -p "  Port [5432]: " pg_port
    pg_port="${pg_port:-5432}"
    read -r -p "  User: " pg_user
    read -r -p "  Database name: " pg_db
    read -r -s -p "  Password: " pg_pass
    echo ""
    if [[ -z "$pg_user" ]] || [[ -z "$pg_db" ]]; then
        echo "Error: User and database name are required." >&2
        exit 1
    fi
    # URL-encode password so special characters don't break the URL (pass via stdin to avoid exposure in process list)
    pg_pass_encoded="$(printf '%s' "$pg_pass" | "$PYTHON" -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=''))" 2>/dev/null)" || pg_pass_encoded="$pg_pass"
    DATABASE_URL="postgresql+psycopg2://${pg_user}:${pg_pass_encoded}@${pg_host}:${pg_port}/${pg_db}"
elif [[ -n "$DATABASE_URL_FILE" ]]; then
    if [[ ! -r "$DATABASE_URL_FILE" ]]; then
        echo "Error: Cannot read --database-url-file $DATABASE_URL_FILE" >&2
        exit 1
    fi
    DATABASE_URL=$(cat "$DATABASE_URL_FILE")
    DATABASE_URL="${DATABASE_URL%"${DATABASE_URL##*[![:space:]]}"}"
    if [[ -z "$DATABASE_URL" ]]; then
        echo "Error: Empty URL in $DATABASE_URL_FILE" >&2
        exit 1
    fi
fi

# Create directories
mkdir -p "$DEST_DIR" "$BIN_DIR" "$APPS_DIR"

echo "Installing Sentinel Solo to $DEST_DIR ..."

# Copy app files (no venv, no __pycache__, no .git, no sentinel.db)
# Prefer rsync; fallback: copy essential files only.
rsync -a --exclude='venv' --exclude='.venv' --exclude='__pycache__' \
      --exclude='.git' --exclude='sentinel.db' --exclude='*.pyc' --exclude='.cursor' \
      "$SRC_DIR/" "$DEST_DIR/" 2>/dev/null || {
    for f in main.py database_manager.py models.py requirements.txt run.sh README.md install.sh uninstall.sh; do
        [[ -f "$SRC_DIR/$f" ]] && cp "$SRC_DIR/$f" "$DEST_DIR/"
    done
    [[ -d "$SRC_DIR/tests" ]] && cp -r "$SRC_DIR/tests" "$DEST_DIR/"
}

# Create venv and install dependencies
echo "Creating virtual environment and installing dependencies..."
if ! command -v "$PYTHON" &>/dev/null; then
    echo "Error: $PYTHON not found. Install Python 3.10+ (3.12 recommended)." >&2
    exit 1
fi
"$PYTHON" -m venv "$DEST_DIR/venv"
"$DEST_DIR/venv/bin/pip" install -q --upgrade pip
"$DEST_DIR/venv/bin/pip" install -q -r "$DEST_DIR/requirements.txt"

# Optional: write PostgreSQL config so launcher can export DATABASE_URL (shell-quoted so special chars are safe)
if [[ -n "$DATABASE_URL" ]]; then
    echo "Configuring PostgreSQL backend..."
    printf 'DATABASE_URL=%q\n' "$DATABASE_URL" > "$DEST_DIR/config.env"
    chmod 600 "$DEST_DIR/config.env"
    echo "  Wrote $DEST_DIR/config.env (DATABASE_URL). Ensure the database and user exist; first run will create tables."
fi

# Launcher script (DEST_DIR is expanded). Sources config.env if present so DATABASE_URL is set for the app.
LAUNCHER="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER" << LAUNCHER_END
#!/usr/bin/env bash
# Launcher for Sentinel Solo (installed)
export XCURSOR_THEME="\${XCURSOR_THEME:-Adwaita}"
export XCURSOR_SIZE="\${XCURSOR_SIZE:-24}"
CONFIG_ENV="$DEST_DIR/config.env"
if [[ -r "\$CONFIG_ENV" ]]; then
    set -a
    . "\$CONFIG_ENV"
    set +a
    [[ -n "\$DATABASE_URL" ]] && export DATABASE_URL
fi
exec "$DEST_DIR/venv/bin/python" "$DEST_DIR/main.py" "\$@"
LAUNCHER_END
chmod +x "$LAUNCHER"

# Desktop entry (menu integration)
DESKTOP_FILE="$APPS_DIR/sentinel-solo.desktop"
cat > "$DESKTOP_FILE" << DESKTOP_END
[Desktop Entry]
Version=1.0
Type=Application
Name=Sentinel Solo
Comment=Time tracking with clients and matters
Exec=$LAUNCHER
Icon=clock
Categories=Office;Utility;
Terminal=false
StartupNotify=true
DESKTOP_END

# Ensure ~/.local/bin is in PATH hint (optional)
if [[ "$PREFIX" == "$HOME/.local" ]] && [[ -d "$HOME/.local/bin" ]]; then
    echo ""
    echo "Installation complete. Run: $APP_NAME"
    echo "If '$APP_NAME' is not found, add to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
else
    echo ""
    echo "Installation complete. Launcher: $LAUNCHER"
fi
echo "Desktop entry: $DESKTOP_FILE (Sentinel Solo will appear in your application menu if supported)."
if [[ -n "$DATABASE_URL" ]]; then
    echo "Backend: PostgreSQL (DATABASE_URL from $DEST_DIR/config.env)."
fi
