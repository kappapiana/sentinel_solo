#!/usr/bin/env bash
# Uninstall Sentinel Solo: remove app dir, launcher, and desktop entry.
# Use the same --prefix as for install (default: ~/.local).

set -e

APP_NAME="sentinel-solo"
# Default: same as install
PREFIX="${PREFIX:-$HOME/.local}"
DEST_DIR="$PREFIX/share/$APP_NAME"
BIN_DIR="$PREFIX/bin"
APPS_DIR="$PREFIX/share/applications"
LAUNCHER="$BIN_DIR/$APP_NAME"
DESKTOP_FILE="$APPS_DIR/$APP_NAME.desktop"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "  Uninstall Sentinel Solo from \$PREFIX (default: \$HOME/.local)."
    echo ""
    echo "Options:"
    echo "  --prefix DIR   Uninstall from DIR (must match the prefix used for install)."
    echo "  --help         Show this help."
    echo ""
    echo "Examples:"
    echo "  $0                      # uninstall from ~/.local"
    echo "  $0 --prefix /usr/local  # uninstall system-wide install"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            DEST_DIR="$PREFIX/share/$APP_NAME"
            BIN_DIR="$PREFIX/bin"
            APPS_DIR="$PREFIX/share/applications"
            LAUNCHER="$BIN_DIR/$APP_NAME"
            DESKTOP_FILE="$APPS_DIR/$APP_NAME.desktop"
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

removed=0

if [[ -d "$DEST_DIR" ]]; then
    echo "Removing $DEST_DIR"
    rm -rf "$DEST_DIR"
    removed=1
fi

if [[ -f "$LAUNCHER" ]]; then
    echo "Removing launcher $LAUNCHER"
    rm -f "$LAUNCHER"
    removed=1
fi

if [[ -f "$DESKTOP_FILE" ]]; then
    echo "Removing desktop entry $DESKTOP_FILE"
    rm -f "$DESKTOP_FILE"
    removed=1
fi

if [[ $removed -eq 0 ]]; then
    echo "Nothing found to uninstall under $PREFIX (no $DEST_DIR, $LAUNCHER, or $DESKTOP_FILE)."
else
    echo "Uninstall complete."
fi
