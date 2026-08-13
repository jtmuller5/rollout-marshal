#!/usr/bin/env bash
# Shot 4 of the demo, end to end, on one command.
#
#   bash demo/run_demo.sh
#
# It starts the service, declares a policy, seeds a track, and runs two ticks with a
# crash spike injected between them. The first tick ends in a refusal; the second one
# ends in a halt, a store write and an email.
#
# Defaults are the safe ones: fixture Play client, fixture crash feed, JSON state on
# disk, mail written to a file, and the scripted brain, so this runs on a clean
# checkout with no credentials at all. Every one of those is a single environment
# variable away from the real thing:
#
#   MARSHAL_BRAIN=adk        Gemini 3.5 through ADK (needs Vertex AI or a Gemini key)
#   MARSHAL_PLAY=live        real Play Developer API writes (needs PLAY_SERVICE_ACCOUNT_JSON)
#   MARSHAL_CRASH_FEED=sentry  live release health (needs SENTRY_ORG, SENTRY_AUTH_TOKEN)
#   MARSHAL_STORE=firestore  Firestore instead of JSON files (needs GOOGLE_CLOUD_PROJECT)
#
# Written by an autonomous agent working for Joe Muller.
set -euo pipefail

cd "$(dirname "$0")/.."

APP="${MARSHAL_APP:-bakedown}"
PACKAGE="${MARSHAL_PACKAGE:-com.mullr.abis_recipes}"
TRACK="${MARSHAL_TRACK:-alpha}"
PORT="${PORT:-8811}"
STATE="${MARSHAL_STATE_DIR:-.marshal-state}"
PY="${PY:-.venv/bin/python}"

export MARSHAL_STATE_DIR="$STATE"
export MARSHAL_CRASH_FIXTURE="${MARSHAL_CRASH_FIXTURE:-$STATE/crash.json}"
export MARSHAL_PLAY_FIXTURE="${MARSHAL_PLAY_FIXTURE:-$STATE/play.json}"
export MARSHAL_BRAIN="${MARSHAL_BRAIN:-scripted}"
export PYTHONUNBUFFERED=1

rule() { printf '\n\033[1m── %s\033[0m\n' "$*"; }

rm -rf "$STATE"
mkdir -p "$STATE"

rule "the policy, written down before the release (shot 2)"
$PY -m rollout_marshal.cli policy set --app "$APP" --package "$PACKAGE" --track "$TRACK" \
  --halt 95 --stages 0.2,0.5,1.0 --hours 6 --floor 120 --baseline 99.4

rule "the release, staged at 20% on $TRACK"
$PY -m rollout_marshal.cli track seed --app "$APP" --release 1.0.121 --code 121 \
  --status inProgress --fraction 0.2
$PY -m rollout_marshal.cli rollout stamp --app "$APP" --hours-ago 8 >/dev/null
echo "stage entered 8 hours ago, so the clock is not what refuses the widen"

rule "release health: quiet — 100% crash-free over 41 sessions"
$PY -m rollout_marshal.cli inject --file demo/fixtures/quiet.json >/dev/null
cat demo/fixtures/quiet.json

rule "starting the service on :$PORT"
$PY -m uvicorn rollout_marshal.server:app --host 127.0.0.1 --port "$PORT" \
  >"$STATE/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && break
  sleep 0.2
done
curl -sf "http://127.0.0.1:$PORT/healthz"; echo

# The demo's right-hand pane. Here it is a file; on camera it is a browser on /stream.
curl -sN "http://127.0.0.1:$PORT/stream" >"$STATE/stream.ndjson" 2>/dev/null &
STREAM=$!
trap 'kill $SERVER $STREAM 2>/dev/null || true' EXIT

rule "4a — first tick: the agent wants to widen, and the gate says no"
curl -sf -X POST "http://127.0.0.1:$PORT/tick/$APP" | $PY -m json.tool

rule "4b — injecting the crash spike, out loud: 76.9% over 412 sessions"
$PY -m rollout_marshal.cli inject --file demo/fixtures/spike.json

rule "4c — second tick: the halt"
curl -sf -X POST "http://127.0.0.1:$PORT/tick/$APP" | $PY -m json.tool

rule "the track after the write"
$PY - <<PYEOF
import json, os
from rollout_marshal.play import build_play_client
t = build_play_client().get_track("$PACKAGE", "$TRACK")
print(json.dumps({"status": t.status, "user_fraction": t.user_fraction,
                  "version_code": t.version_code, "release": t.release_name}, indent=2))
PYEOF

rule "4d — the audit trail"
$PY demo/show_decisions.py "$APP"

rule "4d — the email, sent after the fact"
cat "$STATE"/mail/*.eml

rule "the streamed log the right-hand pane reads"
wc -l <"$STATE/stream.ndjson" | tr -d ' ' | xargs -I{} echo "{} events on /stream"
sed -n '1,4p' "$STATE/stream.ndjson"

rule "done"
echo "state:  $STATE/"
echo "log:    $STATE/server.log"
echo "stream: $STATE/stream.ndjson"
