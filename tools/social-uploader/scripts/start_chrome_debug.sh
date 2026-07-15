#!/bin/bash

# Launch a separate instance of Google Chrome in debug mode (completely isolated from the Chrome you use every day)
#
# Key points:
# - Bypass macOS `open -a` in Chrome using Chrome binary + nohup & background launch
# Hijacking problem of swallowing parameters when already running
# - Use an independent user-data-dir, which is completely separated from the daily Chrome profile and does not affect each other.
# - Even if you already have regular Chrome open, this script will open a separate window

PORT=9222
DATA_DIR="$HOME/.social_uploader/chrome_profiles/default"
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ ! -x "$CHROME_BIN" ]; then
    echo "Error: Chrome executable not found: $CHROME_BIN"
    echo "Please confirm that Google Chrome is installed in the /Applications/ directory"
    exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Chrome debug mode is already running (port $PORT), no need to start again"
    exit 0
fi

mkdir -p "$DATA_DIR"

echo "Starting Google Chrome in debug mode (port $PORT)..."
echo "Use standalone user-data-dir: $DATA_DIR"
echo "The Chrome you use every day will not be affected"

nohup "$CHROME_BIN" \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$DATA_DIR" \
    --disable-blink-features=AutomationControlled \
    --remote-allow-origins="*" \
    --no-first-run \
    --no-default-browser-check \
    --restore-last-session \
    >/dev/null 2>&1 &

CHROME_PID=$!
disown "$CHROME_PID" 2>/dev/null || true

# Poll to wait for port ready (up to 8 seconds)
for i in 1 2 3 4 5 6 7 8; do
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "✅ Started successfully! Debug port $PORT is ready (Chrome PID=$CHROME_PID)"
        echo ""
        echo "Next step:"
        echo "1. Log in to the target platform (YouTube Studio / TikTok Studio / Instagram) in the newly opened Chrome window"
        echo "2. After logging in, you can run the collection or upload command"
        echo ""
        echo "Data directory: $DATA_DIR (login status is saved here and will be restored automatically next time)"
        exit 0
    fi
    sleep 1
done

echo "⚠️ Chrome has started (PID=$CHROME_PID), but port $PORT has not been ready for 8 seconds"
echo "Please wait a few seconds and recheck using the following command:"
echo "     lsof -nP -iTCP:$PORT -sTCP:LISTEN"
exit 1
