#!/usr/bin/env bash
# Pre-recording smoke test for the deployed Agent Watch stack.
#
#   scripts/e2e.sh
#
# Runs all three test suites, then the live guardrail demos (path and command blocks on
# bad-bot; pause/resume and spend cap on demo-bot), checks the blocked events were stored,
# and resets both agents so the live demo starts clean. Sends 4 alerts (each an email and,
# with a webhook set, a Discord message); LLM cost is under a cent.
#
# Rate limit (group 12) is not covered: it was cut on 2026-10-17 for time and never built,
# so there is nothing deployed to test.
#
# The pause runs on demo-bot during `demo_agent.py --loop 20 --sleep 2`, like the demo. The
# printed pause-to-stop time includes the 5 s status poll, the 2 s sleep, and any in-flight call.
#
# The API key is read only from ~/.agentwatch_key and is never printed, logged, or written.
# HTTP calls go through Python (key hashed in-process), so neither the key nor its hash
# appears on a command line.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PYBIN=.venv/bin/python
export AGENTWATCH_ENDPOINT="https://ypdid9bish.execute-api.us-west-2.amazonaws.com"
export AGENTWATCH_OWNER="tejaswi"

RESULTS=()
CLEANUP=0
LOOP_PID=""
LOOP_LOG=""
# Pause deadline: status poll (5 s) + --sleep 2 + one LLM call, with margin.
PAUSE_MAX_S=20

record() { RESULTS+=("$2  $1"); echo "[$2] $1"; }
fail_stop() { record "$1" FAIL; exit 1; }

# aw_api METHOD PATH [JSON_BODY]: prints the response body; non-zero exit on HTTP error.
aw_api() {
  "$PYBIN" - "$@" <<'PY'
import hashlib, json, os, sys
import requests
method, path = sys.argv[1], sys.argv[2]
body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
key_hash = hashlib.sha256(os.environ["AGENTWATCH_KEY"].encode("utf-8")).hexdigest()
r = requests.request(method, os.environ["AGENTWATCH_ENDPOINT"] + path, json=body, timeout=10,
                     allow_redirects=False,
                     headers={"X-Agentwatch-Owner": os.environ["AGENTWATCH_OWNER"],
                              "X-Agentwatch-Key-Hash": key_hash})
if not r.ok:
    sys.exit(f"HTTP {r.status_code} on {method} {path}")
print(r.text)
PY
}

# cfg_edit AGENT add-path P | remove-path P | add-command RE | remove-command RE | cap USD|null
# (read-modify-write of the full config)
cfg_edit() {
  local cur new
  cur=$(aw_api GET "/agents/$1/config") || return 1
  new=$("$PYBIN" -c '
import json, sys
g = json.loads(sys.argv[1])["guardrails"]; op, val = sys.argv[2], sys.argv[3]
if op == "add-path" and val not in g["blockedPaths"]:
    g["blockedPaths"].append(val)
elif op == "remove-path":
    g["blockedPaths"] = [p for p in g["blockedPaths"] if p != val]
elif op == "add-command":
    cmds = g.setdefault("blockedCommands", [])
    if val not in cmds:
        cmds.append(val)
elif op == "remove-command":
    g["blockedCommands"] = [c for c in g.get("blockedCommands", []) if c != val]
elif op == "cap":
    g["dailySpendCapUsd"] = None if val == "null" else float(val)
print(json.dumps(g))' "$cur" "$2" "$3") || return 1
  aw_api PUT "/agents/$1/config" "$new" >/dev/null
}

# new_blocked AGENT VIOLATION_TYPE SINCE_TS: success if a matching blocked event has ts >= SINCE_TS.
new_blocked() {
  local out
  out=$(aw_api GET "/agents/$1/events?type=blocked&order=desc&limit=100") || return 1
  "$PYBIN" -c '
import json, sys
ev = json.loads(sys.argv[1])["events"]
sys.exit(0 if any(e.get("violationType") == sys.argv[2] and e["ts"] >= sys.argv[3] for e in ev) else 1)
' "$out" "$2" "$3"
}

# run_agent NAME EXPECT CMD...: runs a demo agent, indents its output, passes if EXPECT appears.
run_agent() {
  local name=$1 expect=$2 out; shift 2
  out=$("$@" 2>&1)
  sed 's/^/    /' <<<"$out"
  if grep -q "$expect" <<<"$out"; then record "$name" PASS; else fail_stop "$name (no $expect)"; fi
}

# set_paused AGENT true|false
set_paused() {
  aw_api PUT "/agents/$1/status" "{\"paused\": $2}" >/dev/null
}

# wait_for FILE PATTERN [MAX_S]: success once PATTERN appears in FILE, checking every second.
wait_for() {
  local i
  for ((i = 0; i < ${3:-60}; i++)); do
    grep -q "$2" "$1" 2>/dev/null && return 0
    sleep 1
  done
  return 1
}

# expect_in OUTPUT NAME EXPECT: passes if EXPECT appears in OUTPUT.
expect_in() {
  if grep -q "$3" <<<"$1"; then record "$2" PASS; else fail_stop "$2 (no $3)"; fi
}

# The pipe_to_shell pattern comes from the dashboard presets, so it's never retyped here.
PIPE_TO_SHELL=$("$PYBIN" -c '
import json
print(next(p["pattern"] for p in json.load(open("dashboard/lib/commandPresets.json")) if p["id"] == "pipe_to_shell"))')

on_exit() {
  local rc=$?
  if [[ $CLEANUP == 1 ]]; then
    if [[ -n $LOOP_PID ]]; then kill "$LOOP_PID" 2>/dev/null; wait "$LOOP_PID" 2>/dev/null; fi
    [[ -n $LOOP_LOG ]] && rm -f "$LOOP_LOG"
    if set_paused demo-bot false; then record "cleanup: demo-bot resumed" PASS
    else record "cleanup: demo-bot resumed" FAIL; rc=1; fi
    if cfg_edit demo-bot cap null; then record "cleanup: demo-bot cap cleared" PASS
    else record "cleanup: demo-bot cap cleared" FAIL; rc=1; fi
    if cfg_edit bad-bot remove-path .env; then record "cleanup: .env removed from bad-bot" PASS
    else record "cleanup: .env removed from bad-bot" FAIL; rc=1; fi
    if cfg_edit bad-bot remove-command "$PIPE_TO_SHELL"; then record "cleanup: pipe_to_shell removed from bad-bot" PASS
    else record "cleanup: pipe_to_shell removed from bad-bot" FAIL; rc=1; fi
  fi
  echo
  echo "== e2e summary =="
  printf '  %s\n' ${RESULTS[@]+"${RESULTS[@]}"}  # safe on macOS bash 3.2 with set -u
  [[ $rc == 0 ]] && echo "  RESULT: PASS" || echo "  RESULT: FAIL"
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

# --- credentials (never echoed) ---------------------------------------------
[[ -r "$HOME/.agentwatch_key" ]] || fail_stop "key file ~/.agentwatch_key missing"
AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"
export AGENTWATCH_KEY
[[ -n "$AGENTWATCH_KEY" ]] || fail_stop "key file ~/.agentwatch_key is empty"

# --- 1. test suites (stop on first failure) ---------------------------------
(cd backend && ../"$PYBIN" -m pytest -q) && record "backend pytest" PASS || fail_stop "backend pytest"
(cd sdk && ../"$PYBIN" -m pytest -q) && record "sdk pytest" PASS || fail_stop "sdk pytest"
(cd dashboard && npx vitest --run) && record "dashboard vitest" PASS || fail_stop "dashboard vitest"

now_ts() { "$PYBIN" -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z")'; }

# From here on, always reset both agents on exit.
CLEANUP=1

# --- 2. path block and command block on bad-bot -----------------------------
cfg_edit bad-bot add-path .env && record "bad-bot: .env added to blockedPaths" PASS \
  || fail_stop "bad-bot: .env added to blockedPaths"
cfg_edit bad-bot add-command "$PIPE_TO_SHELL" && record "bad-bot: pipe_to_shell added to blockedCommands" PASS \
  || fail_stop "bad-bot: pipe_to_shell added to blockedCommands"
SINCE_BAD=$(now_ts)
BAD_OUT=$("$PYBIN" demo/bad_agent.py 2>&1)
sed 's/^/    /' <<<"$BAD_OUT"
expect_in "$BAD_OUT" "bad-bot: PathBlocked" "PathBlocked"
expect_in "$BAD_OUT" "bad-bot: CommandBlocked" "CommandBlocked"

# --- 3. pause and resume demo-bot mid-run -----------------------------------
cfg_edit demo-bot cap null || fail_stop "demo-bot: cap cleared before pause"
set_paused demo-bot false || fail_stop "demo-bot: active before pause"
LOOP_LOG=$(mktemp)
"$PYBIN" -u demo/demo_agent.py --loop 20 --sleep 2 >"$LOOP_LOG" 2>&1 &
LOOP_PID=$!
wait_for "$LOOP_LOG" "run 2/20 agent:" && record "demo-bot: loop running" PASS \
  || fail_stop "demo-bot: loop running (no run 2/20)"
SINCE_PAUSE=$(now_ts)
set_paused demo-bot true && record "demo-bot: paused via PUT /status" PASS || fail_stop "demo-bot: paused via PUT /status"
PAUSED_AT=$SECONDS
if wait_for "$LOOP_LOG" "AgentPaused" "$PAUSE_MAX_S"; then
  record "demo-bot: AgentPaused after ~$((SECONDS - PAUSED_AT)) s (limit ${PAUSE_MAX_S} s)" PASS
else
  sed 's/^/    /' "$LOOP_LOG"; fail_stop "demo-bot: AgentPaused within ${PAUSE_MAX_S} s"
fi
wait "$LOOP_PID" 2>/dev/null; LOOP_PID=""
sed 's/^/    /' "$LOOP_LOG"
new_blocked demo-bot paused "$SINCE_PAUSE" && record "demo-bot: new paused event stored" PASS \
  || fail_stop "demo-bot: new paused event stored"
set_paused demo-bot false && record "demo-bot: resumed via PUT /status" PASS || fail_stop "demo-bot: resumed via PUT /status"
run_agent "demo-bot: runs again after resume" "^agent:" "$PYBIN" demo/demo_agent.py --loop 1

# --- 4. spend cap on demo-bot -----------------------------------------------
SPEND_JSON=$(aw_api GET /agents/demo-bot/spend) || fail_stop "demo-bot: read 24h spend"
CAP=$("$PYBIN" -c 'import json, sys; print(round(json.loads(sys.argv[1])["rollingSpendUsd"] + 0.002, 6))' "$SPEND_JSON") \
  || fail_stop "demo-bot: read 24h spend"
record "demo-bot: 24h spend read, cap set to \$$CAP" PASS
cfg_edit demo-bot cap "$CAP" || fail_stop "demo-bot: cap saved"
SINCE_DEMO=$(now_ts)
run_agent "demo-bot: SpendCapExceeded" "SpendCapExceeded" "$PYBIN" demo/demo_agent.py --loop 5

# --- 5. blocked events stored -----------------------------------------------
new_blocked bad-bot blocked_path "$SINCE_BAD" && record "bad-bot: new blocked_path event stored" PASS \
  || fail_stop "bad-bot: new blocked_path event stored"
new_blocked bad-bot blocked_command "$SINCE_BAD" && record "bad-bot: new blocked_command event stored" PASS \
  || fail_stop "bad-bot: new blocked_command event stored"
new_blocked demo-bot spend_cap "$SINCE_DEMO" && record "demo-bot: new spend_cap event stored" PASS \
  || fail_stop "demo-bot: new spend_cap event stored"

# Cleanup and the summary run in on_exit.
