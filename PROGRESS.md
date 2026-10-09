# PROGRESS

Last updated: 2026-10-08 by Kiro session (group 4)

## Done
- Group 1 (1.1–1.14) Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries, review hardening.
- Group 2 (2.1–2.8) Service layer and API: `service.py` (`Result`, `authorize`, `authorize_or_register`, `ingest_event`, `get_config`, `put_config`, `NullPublisher`) and `handlers/api.py` (route table, 401 gate, 400/404/500 mapping, structured secret-free logs). Properties 4, 5, 6 (config clause), 7, 10, 12, 14 (route clauses), 15, 28 (service clause) added. Backend suite: 370 passed.

- Group 3 (3.1–3.16) SDK: key hash and exceptions, `ApiClient`, retrying background `Sender`, cost math, `Watcher` config cache with 60 s sync, path blocklist (forms, matching, symlinks, enforcement with a synchronous blocked event), tool wrapper, LLM wrapper for Bedrock `converse` and Anthropic `messages.create` (metadata only, no prompt text), unknown-model warn-once, and a test that runs the 3-line snippet verbatim. Properties 1, 18–20, 23 (config), 24–27, 29 added. Checkpoint: SDK 136 passed, backend 381 passed.

- Group 3 review fixes (3.17–3.20), each pushed as its own `fix(sdk)` commit. The tool wrapper now checks every path-like argument and fails closed when a path can't be normalized. Matching uses NFC before casefold, name entries match any path component, and existing directory entries also match by inode. Transport sends with `allow_redirects=False` and accepts only https endpoints (loopback http allowed). A "guardrails NOT active" warning fires while no config fetch has succeeded. Req 8.6, 8.13–8.15, 14.11–14.12, 21.7, and Property 24 updated. Checkpoint: SDK 184 passed, backend 381 passed.

- 3.17 regression fix (pushed as `fix(sdk)`): fail-closed on unnormalizable values now applies only to named path args. Binary `bytes` with a NUL in another arg is skipped. Req 8.14 and design updated.
- Group 4 (4.1–4.5): `alerts.py` (`format_alert`, `publish_alert`, `SnsPublisher`) and Properties 16 and 17; step 7 of `ingest_event` publishes only for newly stored blocked events; the handler builds `SnsPublisher(TOPIC_ARN)`. `demo/bad_agent.py`, `demo/demo_agent.py` (Bedrock probe, Anthropic fallback), `demo/common.py`, `demo/notes.txt`, `demo/requirements.txt`. Checkpoint: SDK 195 passed, backend 397 on main (404 with `test_template.py` on the PR branch).

## In progress
- 4.3 SAM template (`backend/template.yaml`, `samconfig.toml`, `tests/test_template.py`) is on branch `feat/sam-template`, pushed with `main` merged in. `sam validate --lint` passes. Waiting for Tejaswi's approval before merging. The PR isn't open yet (see Blocked).
- 4.6 deploy: waiting on Tejaswi to run `sam deploy` (commands are in the session summary). Run it after the 4.3 merge.

## Next step
- Open the 4.3 PR, get approval, merge `feat/sam-template` into main. Tejaswi runs the 4.6 deploy and demo commands, then records `ApiUrl` here. After that: task 5.1 (`list_inventory` and `GET /agents`).

## Blocked
- Opening the 4.3 PR through the GitHub MCP server. `.kiro/settings/mcp.json` defines `github`, but its tools weren't exposed to the agent this session (needs `GITHUB_TOKEN` set and the server connected in the MCP panel). Fallback, if Tejaswi okays it: `gh pr create`.

## Decisions
- 2026-10-08 firstSeen is the ts of the first event to arrive, not the earliest ts. It matches Property 12 and is a single `if_not_exists` in the transaction (no read-compare-write).
- 2026-10-08 Fields from another event type are dropped silently instead of rejected. Non-finite numbers are still rejected even in dropped fields.
- 2026-10-08 Only costs are rounded to 6 dp. Other numbers are stored exactly, so ints stay ints.
- 2026-10-08 InMemoryStore `last_sk` follows DynamoDB `LastEvaluatedKey`: it's set whenever `limit` items were read.
- 2026-10-08 `new_record(agent_id, creds, cfg)` takes agentId (tasks.md listed `new_record(creds, cfg)`, but a record needs its key).
- 2026-10-08 `authorize_or_register` is shared by ingest and put_config. It returns "created" so put_config skips a redundant update after creating the record with the submitted config.
- 2026-10-08 A duplicate event's response reports the stored costUsd (one consistent `get_item`, only on the duplicate path). Recomputing from the resubmitted body could disagree with what was stored. (Replaces the earlier "recompute, no extra read" decision, per group 2 review.)
- 2026-10-08 The handler sets the `agentwatch_api` logger to INFO; the SAM template must also set `LoggingConfig.ApplicationLogLevel: INFO` (task 4.3).
- 2026-10-08 On 401 the handler reads no body and no path; the log agentId is set by the route after the gate, and the POST body is parsed once.
- 2026-10-08 get_config and put_config validate the path agentId (400) before touching the store.
- 2026-10-08 The handler's 500 path logs only the exception type, never its message, since messages can echo inputs or secrets.

- 2026-10-08 SDK tool events trim trailing `meta.args` to fit a 3 KB UTF-8 budget. 10 args × 200 chars of wide Unicode could exceed the server's 4 KB meta cap, and the event would be lost to a 400.
- 2026-10-08 SDK config refresh is timed from the last attempt, not the last success (design), so an outage gets at most one request per 60 s.

- 2026-10-08 Blocked events carry the tool name and matching entry in `meta` (`{tool, entry}`), because backend validation drops `tool` on `blocked` events.

- 2026-10-08 The LLM wrapper doesn't add to Local_Spend_Total yet. Task 6.2 owns spend accounting, so 3.13 records events only, which matches "no spend check yet".
- 2026-10-08 `aw.wrap` raises `TypeError` for a client that has neither `converse` nor `messages.create`. Wrapping it silently would record nothing and hide the mistake.
- 2026-10-08 Unknown-model warnings run only after a successful config fetch (`_last_config_ok` is set). With EMPTY, every model is unknown, so warnings would just be noise (Req 21.4).

- 2026-10-08 (3.17) Every str/bytes/PathLike tool argument is a candidate path, so `search(".env")` is blocked too. Over-blocking is the safe direction, and the SDK can't know which strings a tool treats as paths.
- 2026-10-08 (3.17) A path whose normalization raises (e.g. a NUL byte) is blocked and reported with `meta.entry = "<unnormalizable path>"`. Fail closed.
- 2026-10-08 (3.17 regression fix) Fail-closed applies only to named path args (`PATH_ARG_NAMES` / `path_arg`). Other candidates that fail normalization are skipped, so `write_file("out.zip", data)` with NUL bytes in `data` isn't blocked. A NUL can't name a real file, so skipping it only lets non-path data through.
- 2026-10-08 (3.18) The inode match only adds blocks and runs only for directory entries that exist. Ancestor ids are computed lazily, once per attempted path.
- 2026-10-08 (3.19) The endpoint check parses with `urlsplit` instead of matching a prefix, so `http://localhost.evil.com` and `http://localhost@evil.com` are rejected.
- 2026-10-08 (3.20) While no fetch has succeeded, the "NOT active" line replaces the "keeping last good config" warning and the failure reason drops to DEBUG, so the warning text stays exact.
- 2026-10-08 Not fixed, documented instead (README in 7.2, INTERVIEW_PREP): a hardlink to a blocked file under another name, and the TOCTOU window for a swapped symlink. Both fall outside the threat model (careless agent, not a malicious one).

- 2026-10-08 (4.1) Alert email fields escape non-printable chars, so an attempted path can't forge email lines. The subject is capped at 100 chars (SNS limit). Publish failures log only the exception type.
- 2026-10-08 (4.2) Alerts are at-most-once. Publishing happens synchronously after a "stored" write, so a crash between write and publish loses the email but never duplicates it. DynamoDB Streams would make it reliable, and that's a next step.
- 2026-10-08 (4.4/4.5) Demo setup comes from env vars `AGENTWATCH_ENDPOINT`, `AGENTWATCH_OWNER`, `AGENTWATCH_KEY`. `make_client` sends a 1-token Bedrock probe so a fallback happens at startup, not mid-demo.

## Open bugs
- (none known)
