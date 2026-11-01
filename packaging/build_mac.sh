#!/usr/bin/env bash
# Builds dist/ffpy, dist/ffpy.app, dist/ffpy-<version>-macos-<arch>.zip and dist/ffpy-<version>-macos-<arch>.dmg.
# Usage (from repository root):
#   ./packaging/build_mac.sh [/path/to/conda/env]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolve conda/python environment
ENV_PATH="${1:-${CONDA_PREFIX:-}}"
if [ -z "$ENV_PATH" ]; then
    if [ -n "${CONDA:-}" ] && [ -d "$CONDA/envs/ffpy" ]; then
        ENV_PATH="$CONDA/envs/ffpy"
    elif [ -d "$ROOT/.venv" ] && [ -x "$ROOT/.venv/bin/python" ]; then
        ENV_PATH="$ROOT/.venv"
    elif [ -d "$HOME/miniforge3/envs/ffpy" ]; then
        ENV_PATH="$HOME/miniforge3/envs/ffpy"
    elif [ -d "/opt/homebrew/Caskroom/miniforge/base/envs/ffpy" ]; then
        ENV_PATH="/opt/homebrew/Caskroom/miniforge/base/envs/ffpy"
    fi
fi

if [ -n "$ENV_PATH" ] && [ -d "$ENV_PATH/envs/ffpy" ]; then
    ENV_PATH="$ENV_PATH/envs/ffpy"
fi

if [ -n "$ENV_PATH" ] && [ -x "$ENV_PATH/bin/python" ]; then
    PYTHON_EXE="$ENV_PATH/bin/python"
    export PATH="$ENV_PATH/bin:$PATH"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python)"
else
    echo "Error: conda env or python not found. Specify path as argument: $0 /path/to/conda/env" >&2
    exit 1
fi

echo "Using Python: $PYTHON_EXE"

cd "$ROOT"

VERSION="$("$PYTHON_EXE" -c "import ffpy; print(ffpy.__version__)")"
ARCH="$(uname -m)"
echo "Building ffpy v$VERSION for macOS ($ARCH)..."

"$PYTHON_EXE" -m PyInstaller --noconfirm --clean \
    --distpath "$ROOT/dist" --workpath "$ROOT/build" "$ROOT/packaging/ffpy.spec"

DIST="$ROOT/dist/ffpy"
if [ ! -d "$DIST" ]; then
    echo "Error: PyInstaller output directory $DIST does not exist" >&2
    exit 1
fi

APP="$ROOT/dist/ffpy.app"
if [ ! -d "$APP" ]; then
    echo "Error: PyInstaller output bundle $APP does not exist" >&2
    exit 1
fi

echo "Copying supplementary files..."
rm -rf "$DIST/examples" "$DIST/docs"
cp -R "$ROOT/examples" "$DIST/examples"
cp -R "$ROOT/docs" "$DIST/docs"
cp "$ROOT/README.md" "$DIST/"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$DIST/"

echo "Running smoke tests on frozen build inside ffpy.app..."
TMP_DIR="$(mktemp -d -t ffpy_smoke_XXXXXX)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# Run smoke tests without the conda env on PATH to ensure the bundle is standalone
SAVED_PATH="$PATH"
if [ -n "$ENV_PATH" ]; then
    PATH="$(echo "$PATH" | tr ':' '\n' | grep -v "^$ENV_PATH" | tr '\n' ':' | sed 's/:$//')"
fi

APP_BIN="$APP/Contents/MacOS"

echo "Testing CLI on examples..."
for inp in "$ROOT"/examples/*.inp; do
    base="$(basename "$inp")"
    stem="${base%.inp}"
    "$APP_BIN/ffpy" "$inp" -o "$TMP_DIR" -q
    last_line="$(tail -n 1 "$TMP_DIR/${stem}.out")"
    printf "%-26s %s\n" "$base" "$last_line"
done

echo "Testing GUI smoke test..."
export QT_QPA_PLATFORM=offscreen
"$APP_BIN/ffpy-gui" --smoke-test &
GUI_PID=$!
WAIT_SECS=0
while kill -0 "$GUI_PID" 2>/dev/null; do
    sleep 1
    WAIT_SECS=$((WAIT_SECS + 1))
    if [ "$WAIT_SECS" -ge 60 ]; then
        kill -9 "$GUI_PID" 2>/dev/null
        echo "Error: frozen ffpy-gui did not quit within 60 s" >&2
        exit 1
    fi
done
wait "$GUI_PID"
GUI_EXIT=$?
unset QT_QPA_PLATFORM
if [ $GUI_EXIT -ne 0 ]; then
    echo "Error: frozen ffpy-gui smoke test failed with code $GUI_EXIT" >&2
    exit 1
fi
echo "ffpy-gui starts and quits normally"

PATH="$SAVED_PATH"

ZIP="$ROOT/dist/ffpy-$VERSION-macos-$ARCH.zip"
rm -f "$ZIP"
echo "Creating archive $ZIP..."
(cd "$ROOT/dist" && zip -r -q "$ZIP" ffpy)
echo "Successfully built $ZIP"

DMG="$ROOT/dist/ffpy-$VERSION-macos-$ARCH.dmg"
rm -f "$DMG"
echo "Creating disk image $DMG..."
DMG_SRC="$(mktemp -d -t ffpy_dmg_XXXXXX)"
cp -R "$APP" "$DMG_SRC/"
ln -s /Applications "$DMG_SRC/Applications"
hdiutil create -volname "ffpy" -srcfolder "$DMG_SRC" -ov -format UDZO "$DMG"
rm -rf "$DMG_SRC"

echo "Successfully built $DMG"
