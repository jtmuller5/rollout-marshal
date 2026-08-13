#!/usr/bin/env bash
# Record one of the still shots — 2, 3 or 6 — to an mp4, the same way shot 4 is recorded:
# a real browser on a real page, on a virtual X display, with ffmpeg reading that display.
# No camera, no desktop, nothing composited afterwards.
#
#   bash demo/record_shots.sh 3
#   bash demo/record_shots.sh 2      # reads the policy out of whatever store is selected
#
# Shot 2 should be recorded against Firestore, so the policy on screen is the real one
# with the real created_at:
#
#   GOOGLE_APPLICATION_CREDENTIALS=<key> GOOGLE_CLOUD_PROJECT=gen-lang-client-0325469250 \
#   MARSHAL_STORE=firestore bash demo/record_shots.sh 2
#
# The length is not a choice made here: it is the shot's window in notes/demo-script.md,
# read through the parser the narration uses, plus SLACK seconds so demo/assemble.py trims
# the tail rather than refusing a short clip. Shots 1 and 5 are Joe's and are not here.
#
# What it produces:
#   takes/shot<N>-<utc>.mp4      the recording
#   takes/shot<N>-<utc>-at*.png  frames pulled out of it, so the picture can be checked
#
# Written by an autonomous agent working for Joe Muller.
set -euo pipefail

cd "$(dirname "$0")/.."

SHOT="${1:-}"
case "$SHOT" in
  2|3|6) ;;
  *) echo "usage: bash demo/record_shots.sh <2|3|6>   (1 and 5 are Joe's)" >&2; exit 2 ;;
esac

APP="${MARSHAL_APP:-bakedown}"
PORT="${SHOT_PORT:-8813}"
DISPLAY_NUM="${DISPLAY_NUM:-:78}"
WIDTH="${WIDTH:-1920}"
HEIGHT="${HEIGHT:-1080}"
FPS="${FPS:-15}"
SLACK="${SLACK:-3}"
PY="${PY:-.venv/bin/python}"
STATE="${MARSHAL_STATE_DIR:-.marshal-state}"
CHROME="${CHROME:-$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome 2>/dev/null | tail -1)}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="takes/shot$SHOT-$STAMP"
DATA="$STATE/shot-data-$SHOT.json"
mkdir -p takes "$STATE"

export MARSHAL_STATE_DIR="$STATE"
export MARSHAL_APP="$APP"
export PYTHONUNBUFFERED=1

rule() { printf '\n\033[1m── %s\033[0m\n' "$*"; }

[ -x "$CHROME" ] || { echo "no chromium at '$CHROME' — set CHROME=" >&2; exit 2; }
command -v Xvfb >/dev/null || { echo "Xvfb is not installed" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is not installed" >&2; exit 2; }

# On this machine a port is taken until proved otherwise, and a server that loses the bind
# writes the failure into its own log and exits, which reads as a broken build later on.
if [ "$(ss -tln | grep -c ":$PORT ")" != "0" ]; then
  echo "port $PORT is already in use" >&2; exit 2
fi
if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ]; then
  echo "display $DISPLAY_NUM is already up" >&2; exit 2
fi

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT

rule "what this shot shows"
$PY demo/take/shot_data.py --shot "$SHOT" --app "$APP" --out "$DATA"
WINDOW="$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["window"])' "$DATA")"
LENGTH="$($PY -c 'import sys; print(float(sys.argv[1]) + float(sys.argv[2]))' "$WINDOW" "$SLACK")"

rule "the page on :$PORT"
$PY demo/take/shot_server.py --port "$PORT" --data "$DATA" >"$OUT-page.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$PORT/data.json" >/dev/null && break
  sleep 0.2
done
curl -sf "http://127.0.0.1:$PORT/data.json" >/dev/null || { echo "the page server did not come up" >&2; exit 1; }

rule "the display, $WIDTH x $HEIGHT"
Xvfb "$DISPLAY_NUM" -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp >"$OUT-xvfb.log" 2>&1 &
PIDS+=($!)
sleep 2

rm -rf "$STATE/chrome-profile-shot$SHOT"
DISPLAY="$DISPLAY_NUM" "$CHROME" \
  --no-sandbox --disable-gpu --no-first-run --no-default-browser-check --test-type \
  --disable-infobars --disable-sync --hide-scrollbars \
  --disable-features=Translate,TranslateUI,ChromeWhatsNewUI,PrivacySandboxSettings4 \
  --user-data-dir="$STATE/chrome-profile-shot$SHOT" \
  --window-position=0,0 --window-size="$WIDTH,$HEIGHT" --kiosk \
  "http://127.0.0.1:$PORT/stills.html?shot=$SHOT" >"$OUT-chrome.log" 2>&1 &
PIDS+=($!)
sleep 5

rule "recording ${LENGTH}s to $OUT.mp4  (window ${WINDOW}s + ${SLACK}s slack)"
DISPLAY="$DISPLAY_NUM" ffmpeg -hide_banner -loglevel error -y \
  -f x11grab -draw_mouse 0 -framerate "$FPS" -video_size "${WIDTH}x${HEIGHT}" \
  -i "$DISPLAY_NUM" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
  "$OUT.mp4" &
FFMPEG=$!
sleep 1

# The page holds still until this, so no beat is spent before the recorder is running.
curl -sf -X POST "http://127.0.0.1:$PORT/go" >/dev/null

sleep "$LENGTH"
kill -INT "$FFMPEG" 2>/dev/null || true
wait "$FFMPEG" 2>/dev/null || true

rule "what came out"
[ -s "$OUT.mp4" ] || { echo "no recording was produced" >&2; exit 1; }
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height \
  -of default=noprint_wrappers=1 "$OUT.mp4"

# An exit code says a file exists, never that the picture is right. Pull frames out and
# look at them: a blank page and a rendered one weigh about the same.
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT.mp4" | cut -d. -f1)
for pct in 10 40 70 95; do
  at=$(( DUR * pct / 100 ))
  ffmpeg -hide_banner -loglevel error -y -ss "$at" -i "$OUT.mp4" -frames:v 1 \
    "$OUT-at${at}s.png"
done
ls -la "$OUT".mp4 "$OUT"-*.png

echo
echo "shot $SHOT: $OUT.mp4"
echo "frames:  $OUT-at*.png"
echo "put it in the cut:  \"$SHOT\": {\"kind\": \"clip\", \"path\": \"$OUT.mp4\"}"
