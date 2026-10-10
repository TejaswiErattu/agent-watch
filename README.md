# Agent Watch

Agent Watch gives students one place to see, control, and cap what their AI agents do. Wrap an agent in three lines, and every LLM call and tool call shows up on a dashboard with its cost. Guardrails (a daily spend cap and a blocked-path list) are enforced in the SDK before the action runs, and an email goes out when one fires.

- `sdk/`: the `agentwatch` Python package (Python 3.11, `requests` only)
- `backend/`: AWS SAM app. API Gateway HTTP API, one Lambda, DynamoDB single table, SNS email topic, and a $10 monthly AWS Budget
- `dashboard/`: Next.js 14 static export on Amplify Hosting (inventory, agent timeline, rules editor)
- `demo/`: `demo_agent.py` (well-behaved, Claude on Bedrock with an Anthropic API fallback) and `bad_agent.py` (tries to read `.env` and gets blocked)
- `.kiro/`: the specs, steering, hooks, and MCP settings this was built with

## 3-line integration

```python
import agentwatch
aw = agentwatch.init(agent_id="study-bot", owner_id="tejaswi", api_key=os.environ["AGENTWATCH_KEY"])
client, TOOLS = aw.wrap(client), aw.tools(TOOLS)
```

`aw.wrap(client)` accepts a Bedrock runtime client (`converse`) or an Anthropic client (`messages.create`). `aw.tools(TOOLS)` wraps a dict of tool functions. The endpoint comes from `AGENTWATCH_ENDPOINT`, or from `endpoint=` on `init`. The API key never leaves the process. Only its SHA-256 is sent, and the server stores a hash of that.

Wrapped calls can raise `agentwatch.PathBlocked` or `agentwatch.SpendCapExceeded`. Both subclass `GuardrailBlocked`.

## Deploy

Prerequisites: AWS CLI credentials for us-west-2, SAM CLI, Python 3.11, and Node.js with npm.

1. Backend (from `backend/`):
   ```bash
   sam build
   sam deploy --parameter-overrides AlertEmail=[email] DashboardOrigin=https://main.<app-id>.amplifyapp.com
   ```
   `samconfig.toml` sets stack `agent-watch`, region `us-west-2`, and `confirm_changeset = true`. Review the change set before you accept it. Confirm the SNS subscription email once. The stack output `ApiUrl` is your `AGENTWATCH_ENDPOINT`.
2. Dashboard: connect the repo in AWS Amplify Hosting (platform `WEB`). The root `amplify.yml` is a monorepo spec with `appRoot: dashboard`. Set the env var `NEXT_PUBLIC_API_URL` to the `ApiUrl`. Amplify runs `npm ci` and `npm run build` and serves `out/`.
3. CORS allows only `DashboardOrigin`. For local dashboard development against the deployed API, redeploy with `DashboardOrigin=http://localhost:3000`.

## Run the demos

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r demo/requirements.txt
export AGENTWATCH_ENDPOINT=<ApiUrl> AGENTWATCH_OWNER=<owner-id> AGENTWATCH_KEY=<your-key>
python demo/bad_agent.py              # add ".env" to bad-bot's blocked paths first; prints PathBlocked, alert email arrives
python demo/demo_agent.py --loop 5    # set a small daily cap on demo-bot first; stops on SpendCapExceeded
```

Keep `AGENTWATCH_KEY` out of the repo. In the dashboard you enter the same owner id and key. The browser stores only the key's hash.

## Run the tests

No AWS credentials or network needed.

```bash
pip install -e "sdk[dev]" -r backend/requirements-dev.txt
(cd backend && pytest)
(cd sdk && pytest)
(cd dashboard && npm ci && npx vitest --run)
```

## Known limitations

The SDK guards a careless agent, not a malicious one. Agent code that wants to bypass it can.

Path blocklist coverage:
- It covers only tools wrapped with `aw.tools` / `aw.tool` that receive the path as an argument. A recognized path argument is one named `path`, `file_path`, `filepath`, `filename`, `file`, `src`, `dst`, `source`, `destination`, or `target_path`, or one set with `path_arg=`. Any other str/bytes/PathLike argument is also checked.
- It does not cover direct `open()` calls in agent code, shell commands run by a tool (`subprocess`, `os.system`), or tools that build the path internally, for example from a config value or by joining strings inside the tool.
- Matching is case-insensitive, so it over-blocks on case-sensitive filesystems: blocking `.env` also blocks `.ENV`. Every string argument is checked, so `search(".env")` is blocked even though it isn't a file read. Both errors fall on the safe side.
- A hardlink to a blocked file under a different name is not caught by a name entry, since it really is a different name. A directory entry catches it only if the link lives inside the blocked directory.
- Check-then-use (TOCTOU): if a symlink is swapped between the SDK's check and the tool's own `open()`, the swap is not caught.

Spend cap:
- The cap is enforced in the SDK process, from a local total resynced from the server at most every 60 s. During a sync, the local total can briefly under-count while completed LLM call events are still queued for sending. The server hasn't counted them yet.
- The pending-call estimate is worst-case (`max_tokens` output), so the block can come one call early. Concurrent threads can each overshoot the cap by about one call, because check and accumulate are not atomic.
- If no config fetch has ever succeeded, no guardrails are active. The SDK logs `agentwatch: guardrails NOT active (config fetch failed)`.

Identity and alerts:
- There is no user auth. Agent ids are global and first-come: the first owner id plus key to report an agent id owns it. `GET /agents/{agentId}/config` reveals whether a name is taken (403 if it belongs to someone else, an empty config if it is free).
- Alerts are at-most-once. A Lambda crash between storing a blocked event and publishing to SNS loses that email. It never sends duplicates.
- API throttling (10 rps, burst 20) is stage-wide, not per client.
