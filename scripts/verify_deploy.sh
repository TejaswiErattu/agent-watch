#!/usr/bin/env bash
# Post-deploy check: GET /agents/demo-bot/config on the live API.
# Prints only the HTTP status and the guardrail key names (never the key, hash, or values).
# Exits 0 iff the status is 200 and "blockedCommands" is one of the keys.
#
#   scripts/verify_deploy.sh

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

[[ -r "$HOME/.agentwatch_key" ]] || { echo "key file ~/.agentwatch_key missing"; exit 1; }
AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"
export AGENTWATCH_KEY
[[ -n "$AGENTWATCH_KEY" ]] || { echo "key file ~/.agentwatch_key is empty"; exit 1; }

AGENTWATCH_ENDPOINT="https://ypdid9bish.execute-api.us-west-2.amazonaws.com" \
AGENTWATCH_OWNER="tejaswi" \
.venv/bin/python - <<'PY'
import hashlib, os, sys
import requests
key_hash = hashlib.sha256(os.environ["AGENTWATCH_KEY"].encode("utf-8")).hexdigest()
r = requests.get(os.environ["AGENTWATCH_ENDPOINT"] + "/agents/demo-bot/config", timeout=10,
                 allow_redirects=False,
                 headers={"X-Agentwatch-Owner": os.environ["AGENTWATCH_OWNER"],
                          "X-Agentwatch-Key-Hash": key_hash})
print("status:", r.status_code)
keys = sorted(r.json().get("guardrails", {})) if r.ok else []
print("guardrail keys:", keys)
ok = r.status_code == 200 and "blockedCommands" in keys
print("VERIFY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
PY
