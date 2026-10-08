# PROGRESS

Last updated: 2026-10-08 by Kiro session

## Done
- Group 1 (1.1–1.14) Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries, review hardening.
- Group 2 (2.1–2.8) Service layer and API: `service.py` (`Result`, `authorize`, `authorize_or_register`, `ingest_event`, `get_config`, `put_config`, `NullPublisher`) and `handlers/api.py` (route table, 401 gate, 400/404/500 mapping, structured secret-free logs). Properties 4, 5, 6 (config clause), 7, 10, 12, 14 (route clauses), 15, 28 (service clause) added. Backend suite: 370 passed.

- Task 3.1 SDK scaffold: `sdk/pyproject.toml` (requests-only), `agentwatch/__init__.py` with `__version__`, stub `client.py`/`guardrails.py`/`pricing.py`, `tests/conftest.py`, `tests/test_packaging.py` (3 passed).

## In progress
- (none)

## Next step
- Task 3.2: write failing `sdk/tests/test_credentials.py` (known SHA-256 vector for `key_hash`, `GuardrailBlocked` with `violation_type`/`detail`, `SpendCapExceeded`/`PathBlocked` subclasses, credentials `repr` hides key and hash). Then implement `key_hash` and the exceptions in `sdk/agentwatch/client.py` and export the exceptions from `__init__.py`.

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

## Open bugs
- (none known)
