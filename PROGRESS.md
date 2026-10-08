# PROGRESS

Last updated: 2026-10-08 by Kiro session

## Done
- Group 1 (1.1–1.14) Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries, review hardening.
- Group 2 (2.1–2.8) Service layer and API: `service.py` (`Result`, `authorize`, `authorize_or_register`, `ingest_event`, `get_config`, `put_config`, `NullPublisher`) and `handlers/api.py` (route table, 401 gate, 400/404/500 mapping, structured secret-free logs). Properties 4, 5, 6 (config clause), 7, 10, 12, 14 (route clauses), 15, 28 (service clause) added. Backend suite: 370 passed.

## In progress
- (none)

## Next step
- Task 3.1: create `sdk/tests/test_packaging.py` (failing), then scaffold `sdk/pyproject.toml` (runtime `requests>=2.31,<3`), `sdk/agentwatch/__init__.py` with `__version__`, empty `client.py`/`guardrails.py`/`pricing.py`, and `sdk/tests/conftest.py`.

## Blocked
- (none)

## Decisions
- 2026-10-08 firstSeen is the ts of the first event to arrive, not the earliest ts. It matches Property 12 and is a single `if_not_exists` in the transaction (no read-compare-write).
- 2026-10-08 Fields from another event type are dropped silently instead of rejected. Non-finite numbers are still rejected even in dropped fields.
- 2026-10-08 Only costs are rounded to 6 dp. Other numbers are stored exactly, so ints stay ints.
- 2026-10-08 InMemoryStore `last_sk` follows DynamoDB `LastEvaluatedKey`: it's set whenever `limit` items were read.
- 2026-10-08 `new_record(agent_id, creds, cfg)` takes agentId (tasks.md listed `new_record(creds, cfg)`, but a record needs its key).
- 2026-10-08 `authorize_or_register` is shared by ingest and put_config. It returns "created" so put_config skips a redundant update after creating the record with the submitted config.
- 2026-10-08 A duplicate event's response reports the recomputed server cost (no extra read). It's identical unless prices change between retries.
- 2026-10-08 get_config and put_config validate the path agentId (400) before touching the store.
- 2026-10-08 The handler's 500 path logs only the exception type, never its message, since messages can echo inputs or secrets.

## Open bugs
- (none known)
