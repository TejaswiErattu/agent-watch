# PROGRESS

Last updated: 2026-10-08 by Kiro session

## Done
- 1.1–1.13 Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries.
- 1.14 Checkpoint: fixed review findings (commit `fix(backend): harden event validation and align store number handling`). Backend suite: 270 passed.
  - `ts` regex uses `[0-9]` (non-ASCII digits rejected).
  - NaN/Infinity rejected anywhere in an event (400); `allow_nan=False`; `meta` max depth 32 (iterative walk, no RecursionError).
  - Fields belonging to another event type are dropped before type checks.
  - `_num` writes ints exactly; only costs are rounded (`round_cost`); `from_av` parses big ints exactly.
  - InMemoryStore adds the rounded cost to `totalSpendUsd` and returns `last_sk` on an exactly-full page, matching DynamoStore.
  - Added the missing 1.12 tests (no secrets on event Put, model only for llm_call, RuntimeError / ClientError re-raise, AttributeValue round trip incl. null cap).

## In progress
- (none)

## Next step
- Task 2.1: create `backend/tests/test_service_auth.py` (failing), then `backend/src/agentwatch_api/service.py` with `Result`, `authorize`, `new_record`, `Publisher`/`NullPublisher`.

## Blocked
- (none)

## Decisions
- 2026-10-08 firstSeen is the ts of the first event to arrive, not the earliest ts. It matches Property 12 and is a single `if_not_exists` in the transaction (no read-compare-write).
- 2026-10-08 Fields from another event type are dropped silently instead of rejected. Old or sloppy SDKs keep working, and junk never reaches storage. Non-finite numbers are still rejected even in dropped fields, because they signal a broken client.
- 2026-10-08 Only costs are rounded to 6 dp. Other numbers (token counts, meta values) are stored exactly, so ints stay ints.
- 2026-10-08 InMemoryStore `last_sk` follows DynamoDB `LastEvaluatedKey`: it's set whenever `limit` items were read. Callers may get one empty final page.

## Open bugs
- (none known)
