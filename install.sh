#!/usr/bin/env bash
# Install Sentinel Solo: copy app, create venv, install deps, add launcher and desktop entry.
# Default: user install under ~/.local (no sudo). Use --prefix for system-wide.
# Requires Python 3.10+ (3.12 recommended). Dependencies: flet, sqlalchemy, bcrypt; optional psycopg2 for PostgreSQL.

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

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "  Install Sentinel Solo under \$PREFIX (default: \$HOME/.local)."
    echo ""
    echo "Options:"
    echo "  --prefix DIR   Install to DIR (e.g. /usr/local for system-wide; may need sudo)."
    echo "  --help         Show this help."
    echo ""
    echo "Examples:"
    echo "  $0                                    # install to ~/.local"
    echo "  PREFIX=/opt/sentinel $0                # install to /opt/sentinel"
    echo "  $0 --prefix /usr/local                # system-wide (run with sudo if needed)"
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
PYTHON="${PYTHON3:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "Error: $PYTHON not found. Install Python 3.10+ (3.12 recommended)." >&2
    exit 1
fi
"$PYTHON" -m venv "$DEST_DIR/venv"
"$DEST_DIR/venv/bin/pip" install -q --upgrade pip
"$DEST_DIR/venv/bin/pip" install -q -r "$DEST_DIR/requirements.txt"

# Launcher script (DEST_DIR is expanded)
LAUNCHER="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER" << LAUNCHER_END
#!/usr/bin/env bash
# Launcher for Sentinel Solo (installed)
export XCURSOR_THEME="\${XCURSOR_THEME:-Adwaita}"
export XCURSOR_SIZE="\${XCURSOR_SIZE:-24}"
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
