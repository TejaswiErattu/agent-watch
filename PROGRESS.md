# PROGRESS

Last updated: 2026-10-08 by Kiro session

## Done
- Group 1 (1.1–1.14) Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries, review hardening.
- Group 2 (2.1–2.8) Service layer and API: `service.py` (`Result`, `authorize`, `authorize_or_register`, `ingest_event`, `get_config`, `put_config`, `NullPublisher`) and `handlers/api.py` (route table, 401 gate, 400/404/500 mapping, structured secret-free logs). Properties 4, 5, 6 (config clause), 7, 10, 12, 14 (route clauses), 15, 28 (service clause) added. Backend suite: 370 passed.

- Group 3 (3.1–3.16) SDK: key hash and exceptions, `ApiClient`, retrying background `Sender`, cost math, `Watcher` config cache with 60 s sync, path blocklist (forms, matching, symlinks, enforcement with a synchronous blocked event), tool wrapper, LLM wrapper for Bedrock `converse` and Anthropic `messages.create` (metadata only, no prompt text), unknown-model warn-once, and a test that runs the 3-line snippet verbatim. Properties 1, 18–20, 23 (config), 24–27, 29 added. Checkpoint: SDK 136 passed, backend 381 passed.

## In progress
- (none)

## Next step
- Task 4.1: write failing `backend/tests/test_alerts.py` (subject names agentId and violation; spend_cap body has `attemptedCostUsd`, blocked_path body has `attemptedPath`; `publish_alert` returns True on success; a raising publisher returns False and logs `alert_publish_failed` with agentId and eventId) and `backend/tests/test_properties_alerts.py` (Property 17). Then create `backend/src/agentwatch_api/alerts.py` with `format_alert`, `publish_alert`, `SnsPublisher(topic_arn, client=None)`.

## Blocked
- (none)

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

## Open bugs
- (none known)
