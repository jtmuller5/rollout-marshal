#!/usr/bin/env bash
# Record shot 4 of the demo — the unedited take — to an mp4, with no camera and no
# desktop. Everything on screen is a real browser on a real page, driven by the real
# service; the recorder is ffmpeg reading a virtual X display.
#
#   bash demo/record_take.sh                     # fixtures, no credential, ~90s
#   MARSHAL_PLAY=live MARSHAL_STORE=firestore \
#   MARSHAL_BRAIN=adk bash demo/record_take.sh   # the real one
#
# The live form writes to a real Play track and runs two agent ticks. It does not seed
# anything: put the track back to inProgress with demo/live_alpha.py first, because Play
# will not take a release off a track. If a beat does not happen, the driver puts the
# track back to halted itself and says so on camera — see restore_track() in drive_take.py.
#
# DWELL sets the length, and shot 4's window in notes/demo-script.md is 122 seconds.
# Measured on 2026-08-13: five dwell pauses, so a fixture run is 5s longer per unit of
# DWELL (97.3s at 16, 102.3s at 17), and the live wiring adds about 31s of real agent
# latency on top. DWELL=17 is therefore the one to record at: it lands near 133s, which
# is long enough for assemble.py to fill the window and short enough that the trim falls
# inside the final pause rather than into the audit trail. Never pad a short take.
#
# Two live ticks cost about ten Gemini requests and the free tier allows twenty a day per
# model, so plan on ONE live take a day and rehearse with the default fixture brain,
# which is free and instant.
#
# What it produces:
#   takes/take-<utc>.mp4      the recording, one continuous capture, no cut
#   takes/take-<utc>.log      the driver's own transcript of the same run
#   takes/take-<utc>-*.png    frames pulled out of the mp4, so the take can be checked
#
# The clock in the corner of the frame is the browser's, and it runs for the whole
# recording. That is what makes "unedited" checkable by someone who was not here.
#
# Written by an autonomous agent working for Joe Muller.
set -euo pipefail

cd "$(dirname "$0")/.."

APP="${MARSHAL_APP:-bakedown}"
PACKAGE="${MARSHAL_PACKAGE:-com.mullr.abis_recipes}"
TRACK="${MARSHAL_TRACK:-alpha}"
PORT="${PORT:-8811}"
TAKE_PORT="${TAKE_PORT:-8812}"
DISPLAY_NUM="${DISPLAY_NUM:-:77}"
WIDTH="${WIDTH:-1920}"
HEIGHT="${HEIGHT:-1080}"
FPS="${FPS:-15}"
DWELL="${DWELL:-6}"
PY="${PY:-.venv/bin/python}"
STATE="${MARSHAL_STATE_DIR:-.marshal-state}"
CHROME="${CHROME:-$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome 2>/dev/null | tail -1)}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="takes/take-$STAMP"
mkdir -p takes

export MARSHAL_STATE_DIR="$STATE"
export MARSHAL_APP="$APP"
export PYTHONUNBUFFERED=1

LIVE_PLAY="${MARSHAL_PLAY:-fixture}"
LIVE_STORE="${MARSHAL_STORE:-file}"

rule() { printf '\n\033[1m── %s\033[0m\n' "$*"; }

[ -x "$CHROME" ] || { echo "no chromium at '$CHROME' — set CHROME=" >&2; exit 2; }
command -v Xvfb >/dev/null || { echo "Xvfb is not installed" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is not installed" >&2; exit 2; }

# On this machine a port is taken until proved otherwise, and a server that loses the
# bind writes the failure into its own log and exits, which then reads as a broken build.
for p in "$PORT" "$TAKE_PORT"; do
  if [ "$(ss -tln | grep -c ":$p ")" != "0" ]; then
    echo "port $p is already in use" >&2; exit 2
  fi
done
if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ]; then
  echo "display $DISPLAY_NUM is already up" >&2; exit 2
fi

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT

if [ "$LIVE_PLAY" = "live" ] || [ "$LIVE_STORE" = "firestore" ]; then
  rule "live wiring — nothing is seeded, and the track is whatever it already is"
  export MARSHAL_CRASH_FIXTURE="${MARSHAL_CRASH_FIXTURE:-$STATE/crash.json}"
  mkdir -p "$STATE"
  $PY -m rollout_marshal.cli inject --file demo/fixtures/quiet.json >/dev/null
else
  rule "fixture wiring — a clean state, seeded the way run_demo.sh seeds it"
  export MARSHAL_CRASH_FIXTURE="${MARSHAL_CRASH_FIXTURE:-$STATE/crash.json}"
  export MARSHAL_PLAY_FIXTURE="${MARSHAL_PLAY_FIXTURE:-$STATE/play.json}"
  export MARSHAL_BRAIN="${MARSHAL_BRAIN:-scripted}"
  rm -rf "$STATE"; mkdir -p "$STATE"
  $PY -m rollout_marshal.cli policy set --app "$APP" --package "$PACKAGE" --track "$TRACK" \
    --halt 95 --stages 0.2,0.5,1.0 --hours 6 --floor 120 --baseline 99.4 >/dev/null
  $PY -m rollout_marshal.cli track seed --app "$APP" --release 1.0.121 --code 121 \
    --status inProgress --fraction 0.2 >/dev/null
  $PY -m rollout_marshal.cli rollout stamp --app "$APP" --hours-ago 8 >/dev/null
  $PY -m rollout_marshal.cli inject --file demo/fixtures/quiet.json >/dev/null
fi

rule "the service on :$PORT"
$PY -m uvicorn rollout_marshal.server:app --host 127.0.0.1 --port "$PORT" \
  >"$OUT-server.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 1 100); do
  curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && break
  sleep 0.2
done
curl -sf "http://127.0.0.1:$PORT/healthz" | tee "$OUT-healthz.json"; echo

rule "the on-camera page on :$TAKE_PORT"
$PY demo/take/take_server.py --port "$TAKE_PORT" >"$OUT-page.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$TAKE_PORT/events?since=0" >/dev/null && break
  sleep 0.2
done

rule "the display, $WIDTH x $HEIGHT"
Xvfb "$DISPLAY_NUM" -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp >"$OUT-xvfb.log" 2>&1 &
PIDS+=($!)
sleep 2

rm -rf "$STATE/chrome-profile"
DISPLAY="$DISPLAY_NUM" "$CHROME" \
  --no-sandbox --disable-gpu --no-first-run --no-default-browser-check --test-type \
  --disable-infobars --disable-sync --hide-scrollbars \
  --disable-features=Translate,TranslateUI,ChromeWhatsNewUI,PrivacySandboxSettings4 \
  --user-data-dir="$STATE/chrome-profile" \
  --window-position=0,0 --window-size="$WIDTH,$HEIGHT" --kiosk \
  "http://127.0.0.1:$TAKE_PORT/take.html" >"$OUT-chrome.log" 2>&1 &
PIDS+=($!)
sleep 5

rule "recording to $OUT.mp4"
DISPLAY="$DISPLAY_NUM" ffmpeg -hide_banner -loglevel error -y \
  -f x11grab -draw_mouse 0 -framerate "$FPS" -video_size "${WIDTH}x${HEIGHT}" \
  -i "$DISPLAY_NUM" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
  "$OUT.mp4" &
FFMPEG=$!
sleep 2

rule "the take"
set +e
$PY demo/take/drive_take.py --take-url "http://127.0.0.1:$TAKE_PORT" \
  --port "$PORT" --app "$APP" --dwell "$DWELL" 2>&1 | tee "$OUT.log"
DRIVE=${PIPESTATUS[0]}
set -e

sleep 4
kill -INT "$FFMPEG" 2>/dev/null || true
wait "$FFMPEG" 2>/dev/null || true

rule "what came out"
[ -s "$OUT.mp4" ] || { echo "no recording was produced" >&2; exit 1; }
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height \
  -of default=noprint_wrappers=1 "$OUT.mp4"

# An exit code says a file exists, never that the picture is right. Pull frames out and
# look at them: a blank page and a rendered one weigh about the same.
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT.mp4" | cut -d. -f1)
for pct in 15 45 70 92; do
  at=$(( DUR * pct / 100 ))
  ffmpeg -hide_banner -loglevel error -y -ss "$at" -i "$OUT.mp4" -frames:v 1 \
    "$OUT-at${at}s.png"
done
ls -la "$OUT".mp4 "$OUT"-*.png

echo
echo "take:   $OUT.mp4"
echo "log:    $OUT.log"
echo "frames: $OUT-at*.png"
exit "$DRIVE"
