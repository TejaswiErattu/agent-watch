#!/usr/bin/env bash
# Pre-recording smoke test for the deployed Agent Watch stack.
#
#   scripts/e2e.sh
#
# Runs all three test suites, then both live guardrail demos (path block on bad-bot,
# spend cap on demo-bot), checks the blocked events were stored, and resets both agents
# so the live demo starts clean. Sends 2 alert emails; LLM cost is under a cent.
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

# cfg_edit AGENT add-path P | remove-path P | cap USD|null  (read-modify-write of the full config)
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

on_exit() {
  local rc=$?
  if [[ $CLEANUP == 1 ]]; then
    if cfg_edit demo-bot cap null; then record "cleanup: demo-bot cap cleared" PASS
    else record "cleanup: demo-bot cap cleared" FAIL; rc=1; fi
    if cfg_edit bad-bot remove-path .env; then record "cleanup: .env removed from bad-bot" PASS
    else record "cleanup: .env removed from bad-bot" FAIL; rc=1; fi
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

# --- 2. path block on bad-bot -----------------------------------------------
cfg_edit bad-bot add-path .env && record "bad-bot: .env added to blockedPaths" PASS \
  || fail_stop "bad-bot: .env added to blockedPaths"
SINCE_BAD=$(now_ts)
run_agent "bad-bot: PathBlocked" "PathBlocked" "$PYBIN" demo/bad_agent.py

# --- 3. spend cap on demo-bot -----------------------------------------------
SPEND_JSON=$(aw_api GET /agents/demo-bot/spend) || fail_stop "demo-bot: read 24h spend"
CAP=$("$PYBIN" -c 'import json, sys; print(round(json.loads(sys.argv[1])["rollingSpendUsd"] + 0.002, 6))' "$SPEND_JSON") \
  || fail_stop "demo-bot: read 24h spend"
record "demo-bot: 24h spend read, cap set to \$$CAP" PASS
cfg_edit demo-bot cap "$CAP" || fail_stop "demo-bot: cap saved"
SINCE_DEMO=$(now_ts)
run_agent "demo-bot: SpendCapExceeded" "SpendCapExceeded" "$PYBIN" demo/demo_agent.py --loop 5

# --- 4. blocked events stored -----------------------------------------------
new_blocked bad-bot blocked_path "$SINCE_BAD" && record "bad-bot: new blocked_path event stored" PASS \
  || fail_stop "bad-bot: new blocked_path event stored"
new_blocked demo-bot spend_cap "$SINCE_DEMO" && record "demo-bot: new spend_cap event stored" PASS \
  || fail_stop "demo-bot: new spend_cap event stored"

# Cleanup and the summary run in on_exit.
