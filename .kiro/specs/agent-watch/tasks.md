# Implementation Plan: Agent Watch

## Overview

Build order follows the demo path: backend core logic, then the ingest and config API, then the SDK with the path blocklist, then the `.env` block + SNS email running end to end on AWS. After that come the dashboard, the spend cap, and infra/docs polish.

Every leaf task is sized for under an hour and carries its own tests. Where a design Property applies, its Hypothesis test is part of that task and is required. Each property test uses `@settings(max_examples=100)` (filesystem properties add `deadline=None`) and the tag comment `# Feature: agent-watch, Property N: <title>`. Backend tests live in `backend/tests/`, SDK tests in `sdk/tests/`, dashboard tests next to the code under `dashboard/` (vitest). Tests never need AWS credentials or network (Req 17.5).

Commit after each leaf task using `feat(scope)`, `test(scope)`, or `fix(scope)`. Scopes: `backend`, `sdk`, `demo`, `dashboard`, `infra`, `docs`.

## Tasks

- [x] 1. Backend foundations
  - [x] 1.1 Scaffold the backend package and test tooling
    - Write the failing tests first. Add `backend/tests/test_smoke.py` that imports `agentwatch_api` and `agentwatch_api.handlers` and checks the Hypothesis profile is loaded; it fails until the package exists.
    - Create `backend/src/agentwatch_api/__init__.py`, `backend/src/agentwatch_api/handlers/__init__.py`, `backend/requirements.txt` (runtime: none beyond the Lambda-provided `boto3`), `backend/requirements-dev.txt` (pinned `pytest`, `hypothesis`, `pyyaml`, `boto3`).
    - Add `backend/pyproject.toml` with `[tool.pytest.ini_options]` `pythonpath = ["src", "../sdk", ".."]` and `testpaths = ["tests"]`.
    - Add `backend/tests/conftest.py` registering a Hypothesis `ci` profile (`max_examples=100`) and loading it by default.
    - _Requirements: 17.2, 17.5_
    - Commit: `feat(backend): scaffold package and pytest/hypothesis config`

  - [x] 1.2 Implement the backend Pricing_Table and cost math
    - Write the failing tests first. In `backend/tests/test_pricing.py`, assert `pricing_table()["models"]` contains at least one Bedrock Claude ID (`anthropic.claude-...`), one cross-region `us.anthropic.claude-...` ID, and one Anthropic API ID (`claude-...`); unknown models cost 0.0; a hand-computed example matches `estimate_cost`; zero tokens cost 0.0. Add `backend/tests/test_properties_pricing.py` with Property 2.
    - Create `backend/src/agentwatch_api/pricing.py`: `ModelPrice`, `PRICING` (exact IDs incl. the `us.anthropic.*` profile ID and the Anthropic fallback ID that `demo/models.py` will use; check prices on the Bedrock and Anthropic pricing pages), `pricing_table()`, `cost_from_table()`, `estimate_cost()`, `format_cost()`, `parse_cost()`.
    - Property test: **Property 2: Cost format round trip** (required). Also assert non-negative cost for all generated inputs (Req 17.4).
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.11, 17.4_
    - Commit: `feat(backend): pricing table and cost estimator`

  - [x] 1.3 Add demo model constants and the pricing coverage test
    - Write the failing tests first. Add `backend/tests/test_demo_models.py` that loads `demo/models.py` by file path (`importlib.util.spec_from_file_location`) and asserts `BEDROCK_MODEL_ID` starts with `us.anthropic.` and both `BEDROCK_MODEL_ID` and `ANTHROPIC_MODEL_ID` are keys in `pricing_table()["models"]`.
    - Create `demo/models.py` with only those two constants. Fix `PRICING` if a key is missing.
    - _Requirements: 3.11, 16.6_
    - Commit: `feat(demo): model ID constants checked against pricing table`

  - [x] 1.4 Implement common event validation
    - Write the failing tests first. In `backend/tests/test_validation.py`, cover: missing each of `agentId`, `ownerId`, `ts`, `eventId`, `type` returns a `ValidationError` naming the field; bad `ts` format (not 24-char `YYYY-MM-DDTHH:MM:SS.mmmZ`); bad `eventId` (not 32 lowercase hex); `agentId` pattern/length; unknown `type`; unknown top-level field; `meta` over 4 KB.
    - Create `backend/src/agentwatch_api/validation.py` with `ValidationError`, `Event` dataclass, `validate_agent_id(s)`, and the common part of `validate_event(body, now)`.
    - _Requirements: 13.1, 13.4, 20.1_
    - Commit: `feat(backend): common event validation`

  - [x] 1.5 Implement type-specific event validation
    - Write the failing tests first. Extend `backend/tests/test_validation.py`: `llm_call` needs `model`, integer `inputTokens`/`outputTokens` >= 0; `tool_call` needs `tool`, `target`; `blocked` needs `violationType` in {`spend_cap`, `blocked_path`}, `attemptedCostUsd` >= 0 (bools rejected) for spend_cap, non-empty `attemptedPath` for blocked_path; string fields capped at 1024 chars; client `costUsd` is ignored/dropped.
    - Extend `validate_event` in `backend/src/agentwatch_api/validation.py`.
    - _Requirements: 13.2, 13.3, 13.4, 13.6, 13.7, 13.8_
    - Commit: `feat(backend): type-specific event validation`

  - [x] 1.6 Implement Guardrail_Config parsing
    - Write the failing tests first. In `backend/tests/test_rules.py`, cover: valid config parses; `EMPTY_CONFIG` is `{"dailySpendCapUsd": null, "blockedPaths": []}`; cap as bool/string/negative/NaN/inf rejected; `blockedPaths` not a list, containing empty or non-string, over 100 entries, or entry over 1024 chars rejected; unknown key and missing key rejected; error messages name the field. Add `backend/tests/test_properties_rules.py` with Property 3.
    - Create `backend/src/agentwatch_api/rules.py`: `GuardrailConfig` (frozen dataclass, paths as tuple), `parse_config(obj)`, `to_json(cfg)`, `EMPTY_CONFIG`.
    - Property test: **Property 3: Guardrail_Config JSON round trip** (required).
    - _Requirements: 21.6, 22.4_
    - Commit: `feat(backend): guardrail config parsing`

  - [x] 1.7 Implement credential parsing and matching
    - Write the failing tests first. In `backend/tests/test_auth.py`, cover: headers are read case-insensitively; missing or malformed `x-agentwatch-owner` (1 to 64 of `[A-Za-z0-9._-]`) or `x-agentwatch-key-hash` (64 lowercase hex) returns `None`; `key_verifier` equals `sha256(key_hash.encode("ascii")).hexdigest()` on a known vector; `matches` uses `hmac.compare_digest` (patch and assert called). Add a Hypothesis test in `backend/tests/test_properties_auth.py` for the `auth.matches` clause of Property 14: true exactly when ownerId and verifier both equal.
    - Create `backend/src/agentwatch_api/auth.py`: `Credentials`, `parse_credentials(headers)`, `key_verifier(key_hash)`, `matches(record, creds)`. `Credentials.__repr__` hides the Key_Hash.
    - Property test: **Property 14: Authorization gate** (`auth.matches` clause, required; route clauses are added in 2.7).
    - _Requirements: 14.8, 14.9, 25.1_
    - Commit: `feat(backend): credential parsing and constant-time matching`

  - [x] 1.8 Define the Store protocol and InMemoryStore agent records
    - Write the failing tests first. In `backend/tests/test_store_memory.py`, cover: `event_sk(ts, eventId) == f"{ts}#{eventId}"`; `META_SK == "META"`; `create_agent_if_absent` returns True once then False for the same agentId; `get_agent` returns None for unknown ids; `put_config` with a wrong verifier returns False and changes nothing; new records have null `firstSeen`/`lastSeen`/`model` and `totalSpendUsd == 0.0`.
    - Create `backend/src/agentwatch_api/store.py`: `AgentRecord` dataclass, `Store` Protocol (`get_agent`, `create_agent_if_absent`, `put_config`, `record_event`, `bump_last_seen`, `query_events`, `list_by_owner`, `sum_spend`), key helpers, and `InMemoryStore` methods for agent records.
    - _Requirements: 4.2, 4.3, 4.7, 23.1_
    - Commit: `feat(backend): store protocol and in-memory agent records`

  - [x] 1.9 Implement InMemoryStore event writes
    - Write the failing tests first. Extend `backend/tests/test_store_memory.py`: `record_event` returns `"stored"` and adds cost to `totalSpendUsd`, sets `firstSeen` if absent, sets `model` for `llm_call`; same SK again returns `"duplicate"` with no cost change; wrong verifier returns `"forbidden"` even when the SK also exists; event items carry no `keyVerifier`/`gsiOwnerId`; `bump_last_seen` keeps the later ts.
    - Implement `InMemoryStore.record_event(event, cost, key_verifier)` (verifier check first, then SK check, then both writes together) and `bump_last_seen(agent_id, ts)`.
    - _Requirements: 4.5, 4.6, 4.8, 23.2, 23.3_
    - Commit: `feat(backend): in-memory event writes with duplicate/forbidden results`

  - [x] 1.10 Implement InMemoryStore event and owner queries
    - Write the failing tests first. Extend `backend/tests/test_store_memory.py`: `query_events` returns events by SK in asc/desc, respects `limit`, applies a type filter after the page is read (pages can be short), and returns a `last_sk` for pagination; `list_by_owner` returns only META records with that ownerId; `sum_spend(agent_id, start_sk, end_sk)` sums `costUsd` over the SK range.
    - Implement `query_events`, `list_by_owner`, `sum_spend` in `InMemoryStore`.
    - _Requirements: 4.4, 6.1, 24.1_
    - Commit: `feat(backend): in-memory event and owner queries`

  - [x] 1.11 Implement classify_cancellation
    - Write the failing tests first. In `backend/tests/test_store_classify.py`, one example per row of the design's cancellation table. Add `backend/tests/test_properties_store.py` with the classification clause of Property 28 over 2-item reason lists drawn from `{None, "ConditionalCheckFailed", "TransactionConflict", "ThrottlingError", "ValidationError"}`.
    - Add `classify_cancellation(reasons)` to `backend/src/agentwatch_api/store.py` (forbidden if item 1 failed, duplicate if only item 0 failed, else raise).
    - Property test: **Property 28: Transaction outcomes are classified correctly** (classification clause, required; service clause in 2.3).
    - _Requirements: 4.8, 23.4_
    - Commit: `feat(backend): classify transaction cancellation reasons`

  - [x] 1.12 Implement DynamoStore agent-record and event writes
    - Write the failing tests first. In `backend/tests/test_store_dynamo.py`, use a hand-written fake low-level client that records calls and can raise a `TransactionCanceledException`-shaped `botocore.exceptions.ClientError` with `CancellationReasons`. Assert: `create_agent_if_absent` sends `attribute_not_exists(sk)` and writes `gsiOwnerId`; `record_event` sends two TransactItems in order (event Put with `attribute_not_exists(sk)`, META Update with `ADD totalSpendUsd`, `if_not_exists(firstSeen)`, `keyVerifier = :kv`); each cancellation row maps to the right result; numbers are written as `Decimal(str(round(x, 6)))`; `bump_last_seen` swallows `ConditionalCheckFailedException`.
    - Implement `DynamoStore.__init__(table_name, client=None)`, `get_agent` (consistent read), `create_agent_if_absent`, `put_config`, `record_event`, `bump_last_seen` in `backend/src/agentwatch_api/store.py`.
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7, 4.8, 14.3, 23.5_
    - Commit: `feat(backend): DynamoStore writes with transactional event recording`

  - [x] 1.13 Implement DynamoStore queries
    - Write the failing tests first. Extend `backend/tests/test_store_dynamo.py` with the fake client: `query_events` builds `KeyConditionExpression` on `sk` between event bounds (excluding `META`), sets `ScanIndexForward`, `Limit`, `ExclusiveStartKey`, and a `FilterExpression` on `type`; `list_by_owner` queries `ownerIndex` on `gsiOwnerId`; `sum_spend` pages through and converts `Decimal` to `float`.
    - Implement `query_events`, `list_by_owner`, `sum_spend` in `DynamoStore`.
    - _Requirements: 4.4, 5.3, 6.1, 24.1_
    - Commit: `feat(backend): DynamoStore queries`

  - [x] 1.14 Checkpoint: backend foundations
    - Write the failing tests first. Run `pytest` in `backend/` and fix anything red; ensure all tests pass, ask the user if questions arise.

- [x] 2. Service layer and API for ingest and config
  - [x] 2.1 Add the service Result type and the authorize helper
    - Write the failing tests first. In `backend/tests/test_service_auth.py`, cover: `authorize` returns `None` for a missing record, the record for Matching_Credentials, and `"forbidden"` for an ownerId or verifier mismatch; `Result(status, body)` equality.
    - Create `backend/src/agentwatch_api/service.py` with `Result`, `authorize(store, agent_id, creds)`, `new_record(creds, cfg)`, and a `Publisher` protocol with a `NullPublisher` default (no-op until task 4.2).
    - _Requirements: 25.2, 25.3, 14.8_
    - Commit: `feat(backend): service result type and authorize helper`

  - [x] 2.2 Implement ingest_event validation, registration, and cost
    - Write the failing tests first. In `backend/tests/test_service_ingest.py`, cover: invalid body returns 400 and stores nothing; body `ownerId` differing from Credentials returns 400; first event creates a META record with empty config and `firstSeen == lastSeen == ts`; `llm_call` cost equals `estimate_cost`, `tool_call` and `blocked` cost 0.0 even if the client sent `costUsd`; response is `{"eventId","costUsd","duplicate": false}`. Add `backend/tests/test_properties_ingest.py` with Property 7.
    - Implement `ingest_event(store, creds, body, now, publisher=NullPublisher())` steps 1 to 4 and 8 from the design.
    - Property test: **Property 7: Invalid events are rejected and nothing is stored** (required).
    - _Requirements: 4.1, 4.5, 13.4, 13.5, 13.9, 13.10, 23.1_
    - Commit: `feat(backend): ingest_event with validation, registration, server-side cost`

  - [x] 2.3 Handle races, duplicates, forbidden, and lastSeen in ingest_event
    - Write the failing tests first. Extend `backend/tests/test_service_ingest.py`: a store whose `create_agent_if_absent` loses the race (another record appears) is re-read and authorized; a mismatched existing record returns 403 `{"error":"forbidden"}` and stores nothing; a resubmitted eventId returns 200 `duplicate: true` with no spend change; an Unreported_Agent keeps its config and gets `firstSeen`/`lastSeen`; `lastSeen` keeps the later ts on out-of-order events. Extend `backend/tests/test_properties_ingest.py` with Properties 10 and 12, and add the service clause of Property 28 (verifier replaced mid-flight via `InMemoryStore`) to `backend/tests/test_properties_store.py`.
    - Implement steps 2 (race re-read), 5, and 6 of `ingest_event` in `backend/src/agentwatch_api/service.py`.
    - Property tests (required): **Property 10: Total spend equals the sum of distinct stored events** (check `totalSpendUsd` on the record and distinct stored event items; the timeline clause is added in 5.2), **Property 12: Registration invariants** (events-only interleavings here; PUTs join in 2.5), **Property 28: Transaction outcomes are classified correctly** (service clause).
    - _Requirements: 4.7, 4.8, 5.6, 23.2, 23.3, 23.4, 23.5_
    - Commit: `feat(backend): ingest race handling, duplicates, lastSeen`

  - [x] 2.4 Implement get_config
    - Write the failing tests first. In `backend/tests/test_service_config.py`, cover: authorized GET returns `{"guardrails": <stored>, "pricing": pricing_table()}`; missing record returns the empty config plus Pricing_Table and creates nothing; mismatch returns 403. Add `backend/tests/test_properties_config.py` with the `get_config` clause of Property 6.
    - Implement `get_config(store, creds, agent_id)` in `backend/src/agentwatch_api/service.py`.
    - Property test: **Property 6: Read routes never create records** (`get_config` clause, required; spend and timeline clauses are added in 6.1 and 5.2).
    - _Requirements: 3.7, 22.1, 22.2, 25.2_
    - Commit: `feat(backend): get_config service`

  - [x] 2.5 Implement put_config
    - Write the failing tests first. Extend `backend/tests/test_service_config.py`: valid PUT on an existing record replaces config and returns `{"guardrails": cfg}`; PUT on a missing record creates it with null `firstSeen`/`lastSeen`; a lost create race re-reads and authorizes; mismatch returns 403 and changes nothing. Extend `backend/tests/test_properties_config.py` with Properties 4 and 5, and extend Property 12 in `backend/tests/test_properties_ingest.py` to interleave PUTs.
    - Implement `put_config(store, creds, agent_id, body)` in `backend/src/agentwatch_api/service.py`.
    - Property tests (required): **Property 4: Invalid guardrail configs are rejected without side effects**, **Property 5: Config PUT then GET round trip** (PUT/GET clause; the inventory clause is added in 5.1), **Property 12: Registration invariants** (with PUTs).
    - _Requirements: 9.3, 22.3, 22.4, 22.5, 22.6, 23.5_
    - Commit: `feat(backend): put_config service with registration`

  - [x] 2.6 Implement the Lambda router for POST /events and the config routes
    - Write the failing tests first. In `backend/tests/test_handler.py`, build API Gateway HTTP API v2 events and assert: `POST /events`, `GET /agents/{agentId}/config`, `PUT /agents/{agentId}/config` reach the right service call; invalid JSON returns 400; unknown routeKey returns 404 `{"error":"not found"}`; an unexpected exception returns 500 `{"error":"internal"}`; responses have `content-type: application/json`.
    - Create `backend/src/agentwatch_api/handlers/api.py` with `lambda_handler(event, context)`, a route table, and lazy per-container deps (`DynamoStore(os.environ["TABLE_NAME"])`, `NullPublisher` for now) overridable in tests. Use `datetime.now(timezone.utc)` for `now`.
    - _Requirements: 2.4, 15.2, 22.1, 22.3_
    - Commit: `feat(backend): lambda router for events and config routes`

  - [x] 2.7 Enforce the authorization gate and secret hygiene at the handler
    - Write the failing tests first. Extend `backend/tests/test_handler.py`; extend the Property 14 test in `backend/tests/test_properties_auth.py` with the route clauses (driven through `lambda_handler`); add `backend/tests/test_properties_api.py` with Property 15 (use `caplog` to capture logs; scan responses, logs, and every store item).
    - In `handlers/api.py`, return 401 `{"error":"unauthorized"}` before any route work when Credentials are missing or malformed; log only route, agentId, status, and request id; never log headers.
    - Property tests (required): **Property 14: Authorization gate** (route clauses), **Property 15: Secret hygiene in the API**.
    - _Requirements: 4.6, 14.3, 14.5, 14.10, 25.1, 25.2, 25.4_
    - Commit: `feat(backend): 401 gate and secret-safe logging`

  - [x] 2.8 Checkpoint: service and API
    - Write the failing tests first. Run `pytest` in `backend/` and fix anything red; ensure all tests pass, ask the user if questions arise.

- [x] 3. SDK with path blocklist
  - [x] 3.1 Scaffold the SDK package
    - Write the failing tests first. Add `sdk/tests/test_packaging.py`: `import agentwatch` works and exposes `__version__`; `pyproject.toml` lists exactly one runtime dependency, `requests`, with a version range; no file under `sdk/agentwatch/` imports `boto3`, `botocore`, `numpy`, `pandas`, or `torch` (AST scan).
    - Create `sdk/pyproject.toml` (runtime `requests>=2.31,<3`; dev extras pinned `pytest`, `hypothesis`), `sdk/agentwatch/__init__.py`, empty `client.py`, `guardrails.py`, `pricing.py`, and `sdk/tests/conftest.py` with the Hypothesis profile.
    - _Requirements: 10.7, 19.1, 19.2, 19.3_
    - Commit: `feat(sdk): scaffold package with requests-only dependency`

  - [x] 3.2 Add Key_Hash, exceptions, and safe repr
    - Write the failing tests first. In `sdk/tests/test_credentials.py`, cover: `key_hash("abc")` equals the known SHA-256 hex vector; `GuardrailBlocked` has `violation_type` and `detail`, and `SpendCapExceeded`/`PathBlocked` subclass it; a credentials holder's `repr` contains neither the API_Key nor the Key_Hash.
    - Implement `key_hash(api_key)` and the exception classes in `sdk/agentwatch/client.py`; export the exceptions from `__init__.py`.
    - _Requirements: 14.1, 14.4_
    - Commit: `feat(sdk): key hash and guardrail exceptions`

  - [x] 3.3 Implement ApiClient with credential headers
    - Write the failing tests first. In `sdk/tests/test_api_client.py`, with a `FakeTransport`, cover: `post_event` sends JSON to `<endpoint>/events`; `get_config` and `get_spend` hit `/agents/{agentId}/config` and `/spend`; every request has `X-Agentwatch-Owner` and `X-Agentwatch-Key-Hash`; timeout is 2 s. Add `sdk/tests/test_properties_transport.py` with Property 19 (scan URL, headers, body, and `caplog` for the plaintext key, including on 401 and network errors).
    - Implement `ApiClient(endpoint, owner_id, key_hash, transport=None)` in `sdk/agentwatch/client.py` using a `requests.Session` by default.
    - Property test: **Property 19: Credentials sent, secrets never leaked by the SDK** (required).
    - _Requirements: 2.4, 2.5, 14.2, 14.4_
    - Commit: `feat(sdk): api client with credential headers`

  - [x] 3.4 Implement the send-with-retries policy
    - Write the failing tests first. In `sdk/tests/test_sender.py`, cover: 5xx then 200 succeeds on attempt 2; 401/403 logs `agentwatch: authorization failed (check owner_id/api_key)` once and does not retry; 400 logs the server message and does not retry; four failures log a warning with the eventId. Use a fake sleep. Extend `sdk/tests/test_properties_transport.py` with Property 20.
    - Implement `send_with_retries(api, event, sleep)` in `sdk/agentwatch/client.py` (backoff 0.5, 1, 2 s; retry on connection error, timeout, 429, 5xx; never raises).
    - Property test: **Property 20: Retry policy** (required).
    - _Requirements: 2.2, 2.3, 2.6_
    - Commit: `feat(sdk): event send retry policy`

  - [x] 3.5 Implement the background Sender
    - Write the failing tests first. In `sdk/tests/test_sender.py`, cover: `enqueue` delivers via the daemon thread in order; `send_sync` sends immediately on the caller thread; `flush(timeout=5)` drains the queue; `atexit` registration happens once.
    - Implement `Sender` (queue, daemon thread, `enqueue`, `send_sync`, `flush`, `atexit` hook) in `sdk/agentwatch/client.py`.
    - _Requirements: 2.1, 2.3_
    - Commit: `feat(sdk): background sender with sync path and flush`

  - [x] 3.6 Implement SDK cost math over the Pricing_Table
    - Write the failing tests first. In `sdk/tests/test_pricing.py`, cover: known model cost from a sample table; unknown model and empty table give 0.0; `sdk/agentwatch/pricing.py` has no numeric price literals (AST scan for float constants in a dict). Add `backend/tests/test_properties_sdk_parity.py` with Property 1 (imports both packages).
    - Implement `cost_from_table(table, model, in_tok, out_tok)` in `sdk/agentwatch/pricing.py` (same formula as the backend).
    - Property test: **Property 1: SDK cost matches backend cost** (required).
    - _Requirements: 3.8, 3.9, 17.4_
    - Commit: `feat(sdk): cost math over fetched pricing table`

  - [x] 3.7 Implement Watcher init and config fetch/cache/sync
    - Write the failing tests first. In `sdk/tests/test_config_sync.py`, with a fake clock and `FakeTransport`, cover: `init` without `endpoint` and without `AGENTWATCH_ENDPOINT` raises `ValueError`; `init` fetches config once; a failing first fetch leaves `EMPTY` (no cap, no paths, empty pricing); a failure after a success keeps the last good config and logs a warning; refresh is attempted only when 60 s have passed since the last attempt. Add `sdk/tests/test_properties_sync.py` with the config clauses of Property 23.
    - Implement `agentwatch.init(agent_id, owner_id, api_key, endpoint=None, *, transport=None, clock=None, sleep=None)`, `Watcher`, `EMPTY`, and `_maybe_refresh_config` in `sdk/agentwatch/client.py` and `__init__.py`.
    - Property test: **Property 23: Sync timing and last-good cache** (config clauses, required; spend clause is added in 6.2).
    - _Requirements: 8.8, 21.1, 21.2, 21.3, 21.4, 21.5_
    - Commit: `feat(sdk): watcher init and config cache with 60s sync`

  - [x] 3.8 Implement path forms and entry classification
    - Write the failing tests first. In `sdk/tests/test_guardrails_paths.py`, cover: `absolute_path` resolves `./x` and `a/../x` lexically and keeps symlinks; `normalize_path` resolves symlinks (skip if `os.symlink` is not permitted); `path_forms` returns casefolded values; `~` expands; `is_directory_entry` is true for `"~/.ssh"` and `"/a/b"` and false for `".env"`.
    - Implement `_seps`, `absolute_path`, `normalize_path`, `path_forms`, `is_directory_entry` in `sdk/agentwatch/guardrails.py`.
    - _Requirements: 8.4_
    - Commit: `feat(sdk): path forms for blocklist matching`

  - [x] 3.9 Implement path_matches and blocked_entry_for
    - Write the failing tests first. Extend `sdk/tests/test_guardrails_paths.py`: blocking `/a/b` blocks `/a/b`, `/A/B`, `/a/b/c`, not `/a/bc`; `.env` blocks `x/.env` and `.ENV` anywhere; root `/` blocks everything; `blocked_entry_for` returns the first matching entry or `None`. Add `sdk/tests/test_properties_paths.py` with Properties 26 and 27 (symlink-free `tmp_path` trees, `deadline=None`, non-ASCII case forms like `ß`, `É`).
    - Implement `_under`, `path_matches`, `blocked_entry_for` in `sdk/agentwatch/guardrails.py`.
    - Property tests (required): **Property 26: Sibling prefixes are not blocked**, **Property 27: Case changes do not change the decision**.
    - _Requirements: 8.5, 8.6, 8.10, 8.12_
    - Commit: `feat(sdk): directory and name entry matching`

  - [x] 3.10 Cover symlink and spelling cases
    - Write the failing tests first. In `sdk/tests/test_guardrails_symlinks.py`, add the example: a symlink named `.env` pointing to `secrets.txt` is blocked by `.env`; an innocent alias pointing into a blocked directory is blocked. Add Property 25 to `sdk/tests/test_properties_paths.py` (generated trees with symlinks to files and directories; skip if symlinks are not permitted).
    - Fix `sdk/agentwatch/guardrails.py` if any case fails.
    - Property test: **Property 25: Equivalent spellings keep the decision; symlink aliases keep blocks** (required).
    - _Requirements: 8.4, 8.9, 8.11_
    - Commit: `test(sdk): symlink and equivalent-spelling blocklist cases`

  - [x] 3.11 Implement the tool wrapper and tool_call events
    - Write the failing tests first. In `sdk/tests/test_tool_wrapper.py`, cover: `aw.tools({...})` keeps keys and wraps each function; `@aw.tool(name=..., path_arg=...)` works; path argument found from `path_arg` or the first of `path, file_path, filepath, filename, file`; `target` is the path else `repr` of the first argument truncated to 200; `meta.args` holds at most 10 reprs truncated to 200; a raising tool still queues an event with `meta.error` and re-raises; `ts` is 24-char UTC and `eventId` is 32 hex.
    - Implement event building (`_new_event`), `Watcher.tool`, `Watcher.tools` in `sdk/agentwatch/client.py` (blocklist check is added in 3.12).
    - _Requirements: 1.2, 1.3, 1.4, 20.3_
    - Commit: `feat(sdk): tool wrapper with tool_call events`

  - [x] 3.12 Enforce the blocklist in the tool wrapper
    - Write the failing tests first. Extend `sdk/tests/test_tool_wrapper.py`: with `.env` blocked, `read_file(".env")` raises `PathBlocked`, the tool is never called, and one `blocked` event with `violationType="blocked_path"` and `attemptedPath=".env"` was sent via `send_sync` before the raise; a tool without a path argument skips the check; a stale config is refreshed first; the block still raises when reporting fails. Add Property 24 to `sdk/tests/test_properties_paths.py` with the independent reference rule.
    - Wire `_maybe_refresh_config` and `blocked_entry_for(os.fsdecode(os.fspath(value)), ...)` into the tool wrapper in `sdk/agentwatch/client.py`.
    - Property test: **Property 24: Blocklist decision matches the reference rule** (required).
    - _Requirements: 8.1, 8.2, 8.3, 8.7, 8.8, 10.2, 16.3, 20.4_
    - Commit: `feat(sdk): enforce path blocklist with synchronous blocked event`

  - [x] 3.13 Implement the LLM wrapper event capture
    - Write the failing tests first. In `sdk/tests/test_llm_wrapper.py`, with fake Bedrock (`converse` returning `usage.inputTokens/outputTokens`) and fake Anthropic (`messages.create` returning `usage.input_tokens/output_tokens`) clients, cover: `aw.wrap` detects each client; other attributes pass through; an `llm_call` event has model, tokens, and `meta = {provider, messageCount, promptChars, maxTokens, stopReason, latencyMs}` and no prompt text; a provider exception propagates with no event. Add `sdk/tests/test_properties_capture.py` with Property 18 (mixed LLM and tool calls).
    - Implement `Watcher.wrap` and the Bedrock/Anthropic wrappers in `sdk/agentwatch/client.py` (no spend check yet).
    - Property test: **Property 18: Every wrapped call yields one well-formed event** (required).
    - _Requirements: 1.1, 1.3, 1.4, 20.2_
    - Commit: `feat(sdk): LLM wrapper for Bedrock and Anthropic clients`

  - [x] 3.14 Add the unknown-model warn-once
    - Write the failing tests first. In `sdk/tests/test_pricing.py`, add a fixture clearing `pricing._warned`; cover a single warning naming the model after two calls with a fetched table, and none with `EMPTY`. Add `sdk/tests/test_properties_pricing.py` with Property 29 using `caplog`.
    - Implement `_warned` and `warn_unknown_model` in `sdk/agentwatch/pricing.py`; call it from the LLM wrapper only when the config came from a successful fetch.
    - Property test: **Property 29: Unknown models warn once per process** (required).
    - _Requirements: 3.4, 3.10_
    - Commit: `feat(sdk): warn once per unknown model`

  - [x] 3.15 Verify the 3-line integration
    - Write the failing tests first. Add `sdk/tests/test_integration_snippet.py` that runs the exact 3-line snippet from the design against a fake transport and fake Anthropic client, makes one LLM call and one tool call, flushes, and sees two events.
    - Fix any gaps in `sdk/agentwatch/__init__.py` or `client.py`.
    - _Requirements: 1.5_
    - Commit: `test(sdk): 3-line integration snippet`

  - [x] 3.16 Checkpoint: SDK
    - Write the failing tests first. Run `pytest` in `sdk/` and `backend/` and fix anything red; ensure all tests pass, ask the user if questions arise.

  - [ ] 3.17 Check every path-like tool argument (group 3 review)
    - Write the failing tests first. Extend `sdk/tests/test_tool_wrapper.py`: `copy(src="ok.txt", dst=".env")` is blocked; a blocked path in the 2nd positional arg, in `**kwargs`, or inside a list/tuple value is blocked; `path_arg=["a", "b"]` checks both; a path with a NUL byte sends a blocked event and raises `PathBlocked`; the tool is never called. Extend Property 24 so the attempted path can sit in any argument position.
    - In `sdk/agentwatch/client.py`, replace `_find_path` with `_candidate_paths`: named args (`PATH_ARG_NAMES` + `src, dst, source, destination, target_path`, or `path_arg` / each name if a list), plus every str/PathLike in `*args`/`**kwargs` and one level of list/tuple values. Block if any one matches; a path that raises in normalization is blocked.
    - _Requirements: 8.1, 8.2, 8.7, 8.13, 8.14_
    - Commit: `fix(sdk): check every path-like tool argument`

  - [ ] 3.18 NFC normalization, any-component names, and inode matching (group 3 review)
    - Write the failing tests first. Extend `sdk/tests/test_guardrails_paths.py`: NFD `é` path vs NFC entry (and the reverse) match; `.git` blocks `.git/config` and `a/.git/hooks/x`; `.git` does not block `a/.github/x`; a directory entry blocks an attempted path whose string forms differ but whose parent has the same `(st_dev, st_ino)` (firmlink/bind mount simulated by monkeypatching `normalize_path` so it does not resolve a symlinked alias); a non-existent entry falls back to string matching. Update the Property 24 reference rule.
    - In `sdk/agentwatch/guardrails.py`: `_fold(s) = unicodedata.normalize("NFC", s).casefold()`; Name_Entry matches any component of either form; Directory_Entry also matches when `(st_dev, st_ino)` of the existing entry equals that of the attempted path or any of its existing parents.
    - _Requirements: 8.5, 8.6, 8.12, 8.15_
    - Commit: `fix(sdk): NFC folding, any-component name entries, inode directory match`

  - [ ] 3.19 Harden transport: no redirects, HTTPS only (group 3 review)
    - Write the failing tests first. In `sdk/tests/test_api_client.py`: `RequestsTransport` passes `allow_redirects=False` on every request (fake session); a 3xx is returned as-is and is not followed; `init`/`ApiClient` reject `http://example.com`, `ftp://…`, and a bare host with `ValueError`, and accept `https://…`, `http://localhost[:port]`, and `http://127.0.0.1[:port]`.
    - Implement in `sdk/agentwatch/client.py`.
    - _Requirements: 14.11, 14.12_
    - Commit: `fix(sdk): no redirects and https-only endpoint`

  - [ ] 3.20 Warn loudly when guardrails are not active (group 3 review)
    - Write the failing tests first. In `sdk/tests/test_config_sync.py`: a failing first fetch logs `agentwatch: guardrails NOT active (config fetch failed)` once at init and once per failed refresh while no fetch has succeeded; after a success, failures log only the "keeping last good config" warning.
    - Implement in `Watcher._fetch_config` in `sdk/agentwatch/client.py`.
    - _Requirements: 21.7_
    - Commit: `fix(sdk): warn when guardrails are not active`

- [ ] 4. The `.env` block and SNS alert, end to end
  - [ ] 4.1 Implement format_alert and publish_alert
    - Write the failing tests first. In `backend/tests/test_alerts.py`, cover: subject names the agentId and violation; body for spend_cap includes `attemptedCostUsd`, for blocked_path includes `attemptedPath`; `publish_alert` calls `publisher.publish(subject, body)` and returns True; a raising publisher returns False and logs `alert_publish_failed` with agentId and eventId. Add `backend/tests/test_properties_alerts.py` with Property 17.
    - Create `backend/src/agentwatch_api/alerts.py` with `format_alert(event)`, `publish_alert(publisher, event)`, and `SnsPublisher(topic_arn, client=None)`.
    - Property test: **Property 17: Alert content** (required).
    - _Requirements: 10.5, 10.6, 10.8_
    - Commit: `feat(backend): alert formatting and safe SNS publish`

  - [ ] 4.2 Wire alerts into ingest_event and the handler
    - Write the failing tests first. Extend `backend/tests/test_service_ingest.py`: a stored blocked event calls a `FakePublisher` once; a duplicate blocked event and non-blocked events do not; a raising publisher still returns 200 and the event stays stored. Add Property 16 to `backend/tests/test_properties_alerts.py`.
    - Implement step 7 of `ingest_event` in `backend/src/agentwatch_api/service.py`; in `handlers/api.py`, build `SnsPublisher(os.environ["TOPIC_ARN"])`.
    - Property test: **Property 16: Alert publish rules** (required).
    - _Requirements: 4.8, 10.3, 10.8_
    - Commit: `feat(backend): publish alert for newly stored blocked events`

  - [ ] 4.3 Write the minimal SAM template for the demo
    - Write the failing tests first. Add `backend/tests/test_template.py` that parses `backend/template.yaml` with a CloudFormation-tag-aware YAML loader and asserts: `ApiFunction` has `python3.11`, `arm64`, handler `agentwatch_api.handlers.api.lambda_handler`, env `TABLE_NAME` and `TOPIC_ARN`, `LoggingConfig: {LogFormat: JSON, ApplicationLogLevel: INFO}`; routes `POST /events`, `GET /agents/{agentId}/config`, `PUT /agents/{agentId}/config` exist; `EventTable` is `PAY_PER_REQUEST` with keys `agentId`/`sk` and GSI `ownerIndex` on `gsiOwnerId`; `AlertTopic` has an `email` subscription from the `AlertEmail` parameter.
    - Create `backend/template.yaml` and `backend/samconfig.toml` (`region = "us-west-2"`). Full routes, CORS, throttling, and Budget come in 7.1.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.6, 18.1, 18.2, 18.4_
    - Commit: `feat(infra): minimal SAM template for ingest, config, table, topic`

  - [ ] 4.4 Write demo/bad_agent.py
    - Write the failing tests first. Add `sdk/tests/test_bad_agent.py` that imports `demo/bad_agent.py` by path, runs its `main()` with a fake transport returning `.env` in Blocked_Paths and a fake LLM client, and asserts `PathBlocked` is caught and printed and one `blocked_path` event with `attemptedPath=".env"` was sent.
    - Create `demo/bad_agent.py` (models from `demo/models.py`, scripted `read_file(".env")`, injectable client and transport for tests) and `demo/requirements.txt` (pinned `boto3`, `anthropic`, plus `-e ../sdk`).
    - _Requirements: 16.2, 16.3, 16.6_
    - Commit: `feat(demo): bad agent that gets blocked reading .env`

  - [ ] 4.5 Write demo/demo_agent.py with Bedrock to Anthropic fallback
    - Write the failing tests first. Add `sdk/tests/test_demo_agent.py`: when the Bedrock factory raises (missing `boto3`, `AccessDeniedException`, or a `converse` failure), `make_client()` returns a wrapped Anthropic client using `ANTHROPIC_MODEL_ID`; when Bedrock works, it uses `BEDROCK_MODEL_ID`; the agent's harmless `read_file` tool runs.
    - Create `demo/demo_agent.py` with `make_client()` and `main()`, using only constants from `demo/models.py`. Share setup with `bad_agent.py` via a small `demo/common.py` if it avoids duplication.
    - _Requirements: 16.1, 16.5, 16.6_
    - Commit: `feat(demo): well-behaved demo agent with Bedrock fallback`

  - [ ] 4.6 Checkpoint: deploy and see the `.env` block and email
    - Write the failing tests first. Before deploying, run `pytest` in `backend/` and `sdk/` (all green), and confirm `test_template.py` passes.
    - Run `sam build && sam deploy --guided --region us-west-2` from `backend/` with `AlertEmail`; confirm the SNS subscription email.
    - `curl` a `PUT /agents/bad-bot/config` with `{"dailySpendCapUsd": null, "blockedPaths": [".env"]}`, then run `python demo/bad_agent.py` with `AGENTWATCH_ENDPOINT` set. Expect `PathBlocked` in the terminal and the alert email within about 10 s.
    - Verify against real DynamoDB that a wrong-key write to an existing sort key returns 403, not duplicate.
    - Run `python demo/demo_agent.py` and see a 200 for its events. Record the endpoint URL in `PROGRESS.md`; if AWS access blocks this, log it under "Blocked" and continue with group 5.
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 10.4, 14.6, 16.3, 16.4_

- [ ] 5. Dashboard
  - [ ] 5.1 Implement list_inventory and GET /agents
    - Write the failing tests first. In `backend/tests/test_service_inventory.py`, cover: no matching records returns 200 `{"agents": []}`; two owners sharing an ownerId with different keys see only their own agents; an Unreported_Agent shows nulls and `totalSpendUsd: 0.0`; items have all InventoryItem fields and no `keyVerifier`. Add Property 13 to `backend/tests/test_properties_inventory.py`, and extend Property 5 in `backend/tests/test_properties_config.py` with the inventory clause.
    - Implement `list_inventory(store, creds)` in `backend/src/agentwatch_api/service.py`; add the `GET /agents` route in `handlers/api.py` and `backend/template.yaml` (update `test_template.py`).
    - Property tests (required): **Property 13: Inventory returns exactly the matching records**, **Property 5: Config PUT then GET round trip** (inventory clause).
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7_
    - Commit: `feat(backend): inventory endpoint`

  - [ ] 5.2 Implement get_timeline and GET /agents/{agentId}/events
    - Write the failing tests first. In `backend/tests/test_service_timeline.py`, cover: default `order=asc`, `limit=50`; `limit` outside 1..100, bad `order`, bad `type`, an undecodable cursor, or a cursor `sk` that is not an event SK returns 400; missing agent returns `{"events": [], "nextCursor": null}`; mismatch returns 403; absent TimelineItem fields are `null`. Add Properties 8 and 9 to `backend/tests/test_properties_timeline.py`; extend Property 10 with the timeline clause and Property 6 with the `get_timeline` clause.
    - Implement `get_timeline(store, creds, agent_id, query)` and base64url cursor encode/decode in `backend/src/agentwatch_api/service.py`; add the route in `handlers/api.py` and `backend/template.yaml` (update `test_template.py`).
    - Property tests (required): **Property 8: Ingest then timeline round trip with server-side cost**, **Property 9: Timeline order, filter, and pagination**, **Property 10** (timeline clause), **Property 6** (`get_timeline` clause).
    - _Requirements: 6.1, 6.3, 12.2, 13.9, 20.5, 22.2_
    - Commit: `feat(backend): timeline endpoint with cursor and type filter`

  - [ ] 5.3 Add CORS for the dashboard and redeploy
    - Write the failing tests first. Extend `backend/tests/test_template.py` to assert `CorsConfiguration` allows `http://localhost:3000` and the `DashboardOrigin` parameter, methods `GET` and `PUT`, and headers `content-type`, `x-agentwatch-owner`, `x-agentwatch-key-hash`.
    - Update `backend/template.yaml`; run `sam deploy`.
    - _Requirements: 15.8_
    - Commit: `feat(infra): CORS for dashboard origin`

  - [ ] 5.4 Scaffold the Next.js dashboard
    - Write the failing tests first. Add `dashboard/lib/smoke.test.ts` asserting `next.config.mjs` sets `output: "export"` and that vitest runs in jsdom.
    - Create the Next.js 14 App Router app in `dashboard/` with TypeScript, Tailwind, shadcn/ui (`Table`, `Input`, `Button`, `Select`, `Alert`), vitest + Testing Library + jsdom, and `NEXT_PUBLIC_API_URL`. Add `dashboard/lib/types.ts` mirroring InventoryItem, TimelineItem, Guardrail_Config, Config_Response.
    - _Requirements: 17.3_
    - Commit: `feat(dashboard): scaffold Next.js static export with vitest`

  - [ ] 5.5 Implement lib/credentials.ts
    - Write the failing tests first. In `dashboard/lib/credentials.test.ts`, cover: `hashKey("abc")` equals the known SHA-256 lowercase hex vector; `saveCredentials` writes only `{ownerId, keyHash}` under `agentwatch.credentials` and no plaintext key; `loadCredentials` returns null when empty or corrupt; `clearCredentials` removes the key.
    - Implement `dashboard/lib/credentials.ts` using `crypto.subtle.digest`.
    - _Requirements: 11.6, 11.9, 14.7_
    - Commit: `feat(dashboard): browser key hashing and credential storage`

  - [ ] 5.6 Implement lib/api.ts
    - Write the failing tests first. In `dashboard/lib/api.test.ts` with a mocked `fetch`, cover: `apiFetch` adds `x-agentwatch-owner` and `x-agentwatch-key-hash`; 401/403 throw `AuthError`; other non-2xx throw `ApiError` with the server `error` message; `getInventory`, `getTimeline({order, type, cursor, limit})`, `getConfig`, `putConfig` build the right URLs and bodies.
    - Implement `dashboard/lib/api.ts`.
    - _Requirements: 9.2, 9.3, 11.7, 11.8_
    - Commit: `feat(dashboard): API client with credential headers`

  - [ ] 5.7 Implement CredentialsForm
    - Write the failing tests first. In `dashboard/components/CredentialsForm.test.tsx`, cover: labelled ownerId and API key (`type="password"`) inputs; submit hashes and saves, calls `onSaved`, and clears the key field; an optional error message renders in `role="alert"`.
    - Implement `dashboard/components/CredentialsForm.tsx`.
    - _Requirements: 11.5, 11.6, 14.7_
    - Commit: `feat(dashboard): credentials form`

  - [ ] 5.8 Implement InventoryTable and AddAgentForm
    - Write the failing tests first. In `dashboard/components/InventoryTable.test.tsx`, cover: rows show agentId, model, last activity, total spend; rows link to `/agent?id=<agentId>`; Unreported_Agents show "not yet reported" and an empty model cell. In `dashboard/components/AddAgentForm.test.tsx`, cover: invalid agentId shows an error; valid agentId navigates to `/agent?id=<agentId>` (mock the router).
    - Implement `dashboard/components/InventoryTable.tsx` and `dashboard/components/AddAgentForm.tsx`.
    - _Requirements: 11.2, 11.3, 11.10, 11.11, 11.12_
    - Commit: `feat(dashboard): inventory table and add-agent form`

  - [ ] 5.9 Build the inventory page with polling
    - Write the failing tests first. In `dashboard/app/page.test.tsx`, cover: no stored credentials shows `CredentialsForm`; with credentials, the table renders from a mocked `getInventory`; `AuthError` shows "Credentials not accepted" and the form; "Clear credentials" clears storage and shows the form; with fake timers, inventory refetches every 30 s and the interval is cleared on unmount; other errors keep the last data and show an inline alert.
    - Implement `dashboard/app/page.tsx`.
    - _Requirements: 11.1, 11.4, 11.5, 11.8, 11.9_
    - Commit: `feat(dashboard): inventory page with 30s polling`

  - [ ] 5.10 Implement the Timeline component
    - Write the failing tests first. In `dashboard/components/Timeline.test.tsx`, cover: mixed `llm_call`, `tool_call`, and `blocked` events render in one list in the order returned (`order=desc`); the type filter resets the list and passes `type`; a mocked `IntersectionObserver` firing loads `nextCursor` and appends; no more loads when `nextCursor` is null.
    - Implement `dashboard/components/Timeline.tsx`.
    - _Requirements: 6.4, 12.2, 20.5_
    - Commit: `feat(dashboard): timeline with infinite scroll and type filter`

  - [ ] 5.11 Implement the RulesEditor component
    - Write the failing tests first. In `dashboard/components/RulesEditor.test.tsx`, cover: loads and shows the config from `getConfig`; saving a cap, adding a path, and removing a path each send the full Guardrail_Config via `putConfig`; success shows the returned config; failure shows an error in `role="alert"` and keeps the draft; an empty cap input sends `null`.
    - Implement `dashboard/components/RulesEditor.tsx`.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 12.3, 12.4_
    - Commit: `feat(dashboard): rules editor`

  - [ ] 5.12 Build the agent detail page
    - Write the failing tests first. In `dashboard/app/agent/page.test.tsx`, cover: reads `?id=` and renders `Timeline` and `RulesEditor` for it; missing `id` shows a message with a link back; `AuthError` shows the credentials form.
    - Implement `dashboard/app/agent/page.tsx` (wrap `useSearchParams` in `Suspense` for static export).
    - _Requirements: 12.1, 12.3, 12.4_
    - Commit: `feat(dashboard): agent detail page`

  - [ ] 5.13 Deploy the dashboard to Amplify Hosting
    - Write the failing tests first. Add `dashboard/lib/build.test.ts` asserting `amplify.yml` exists with `baseDirectory: out` and runs `npm ci` and `npm run build`; run `npm run build` locally and confirm `out/` is produced.
    - Create `dashboard/amplify.yml`; connect the repo in Amplify with `NEXT_PUBLIC_API_URL`; set the deployed origin as the `DashboardOrigin` parameter and `sam deploy` again.
    - _Requirements: 11.1, 15.8, 18.3_
    - Commit: `feat(dashboard): Amplify build config`

  - [ ] 5.14 Checkpoint: dashboard
    - Write the failing tests first. Run `npx vitest --run` in `dashboard/` and `pytest` in `backend/` and `sdk/`; ensure all tests pass, ask the user if questions arise.
    - On the deployed dashboard, enter credentials, see `bad-bot` in the inventory, open it, and see the blocked event in the timeline.

- [ ] 6. Spend cap
  - [ ] 6.1 Implement get_spend and GET /agents/{agentId}/spend
    - Write the failing tests first. In `backend/tests/test_service_spend.py`, cover: response `{"agentId","rollingSpendUsd","windowStart","windowEnd"}`; events exactly at `now - 24h` are excluded and at `now` are included; missing agent returns 0.0 and creates nothing; mismatch returns 403. Add Property 11 to `backend/tests/test_properties_spend.py` and extend Property 6 with the `get_spend` clause.
    - Implement `get_spend(store, creds, agent_id, now)` in `backend/src/agentwatch_api/service.py`; add the route in `handlers/api.py` and `backend/template.yaml` (update `test_template.py`).
    - Property tests (required): **Property 11: Rolling 24h spend matches the window sum**, **Property 6: Read routes never create records** (`get_spend` clause).
    - _Requirements: 24.1, 24.2, 24.4_
    - Commit: `feat(backend): rolling 24h spend endpoint`

  - [ ] 6.2 Implement SDK spend sync and Local_Spend_Total
    - Write the failing tests first. In `sdk/tests/test_spend_sync.py`, cover: `init` fetches spend and sets Local_Spend_Total; a failing first fetch starts at 0.0; each completed LLM call adds `cost_from_table` of actual usage under the lock; a failing or slow (>2 s) sync keeps the value and warns; a successful sync replaces it. Add Property 22 to `sdk/tests/test_properties_spend.py` and extend Property 23 in `sdk/tests/test_properties_sync.py` with the spend clause.
    - Implement `_maybe_sync_spend` and the post-call accumulation in `sdk/agentwatch/client.py`.
    - Property tests (required): **Property 22: Local spend accounting**, **Property 23: Sync timing and last-good cache** (spend clause).
    - _Requirements: 7.2, 7.3, 7.4, 7.9, 7.10_
    - Commit: `feat(sdk): local spend total with 60s server sync`

  - [ ] 6.3 Implement estimate_pending_cost and spend_decision
    - Write the failing tests first. In `sdk/tests/test_pricing.py`, cover: `estimate_input_tokens` is `ceil(len(json.dumps(messages + system, default=str)) / 4)`; max tokens from Anthropic `max_tokens` and Bedrock `inferenceConfig.maxTokens`, defaulting to 4096 for Bedrock; `estimate_pending_cost` uses `cost_from_table`. In `sdk/tests/test_guardrails_spend.py`, `spend_decision(t, e, c)` is `"block"` iff `t + e > c` (exactly equal allows).
    - Implement `estimate_input_tokens`, `estimate_pending_cost` in `sdk/agentwatch/pricing.py` and `spend_decision` in `sdk/agentwatch/guardrails.py`.
    - _Requirements: 7.5, 7.6, 7.7_
    - Commit: `feat(sdk): pending cost estimate and spend decision`

  - [ ] 6.4 Enforce the spend cap in the LLM wrapper
    - Write the failing tests first. In `sdk/tests/test_llm_wrapper.py`, cover: over the cap raises `SpendCapExceeded`, the fake client is never called, and one `blocked` event with `violationType="spend_cap"` and `attemptedCostUsd == e` is sent synchronously; at or under the cap the call proceeds; no cap always proceeds; the check runs before every call for both providers. Add Property 21 to `sdk/tests/test_properties_spend.py`.
    - Implement `check_spend` and call it at the top of both LLM wrappers in `sdk/agentwatch/client.py`.
    - Property test: **Property 21: Spend cap decision** (required).
    - _Requirements: 7.1, 7.6, 7.7, 7.8, 10.1, 20.4_
    - Commit: `feat(sdk): enforce daily spend cap before LLM calls`

  - [ ] 6.5 Add the demo spend-cap run
    - Write the failing tests first. Extend `sdk/tests/test_demo_agent.py`: running `demo_agent.main(loop=3)` against a fake transport whose config has a tiny cap raises and catches `SpendCapExceeded` and prints the block.
    - Add a `--loop N` option to `demo/demo_agent.py` that repeats the question so a small cap trips. Redeploy the backend (spend route), set a `0.001` cap in the dashboard, run it, and see the `spend_cap` email.
    - _Requirements: 7.6, 10.1, 10.4_
    - Commit: `feat(demo): spend cap demo loop`

  - [ ] 6.6 Checkpoint: spend cap
    - Write the failing tests first. Run `pytest` in `backend/` and `sdk/`; ensure all tests pass, ask the user if questions arise.

- [ ] 7. Infra polish, docs, and rehearsal
  - [ ] 7.1 Complete the SAM template
    - Write the failing tests first. Extend `backend/tests/test_template.py`: all six routes map to `ApiFunction`; default route throttling is rate 10, burst 20; `CostBudget` is `AWS::Budgets::Budget` at 10 USD monthly with an actual > 100% email notification to `AlertEmail`; `ApiFunction` policies are exactly `DynamoDBCrudPolicy` on `EventTable` and `SNSPublishMessagePolicy` on `AlertTopic`.
    - Update `backend/template.yaml`; `sam validate` and `sam deploy`.
    - _Requirements: 15.5, 15.7, 18.5_
    - Commit: `feat(infra): throttling, budget, least-privilege policies`

  - [ ] 7.2 Write README.md with Known limitations
    - Write the failing tests first. Add `backend/tests/test_readme.py` checking `README.md` has a "Known limitations" heading that mentions `open()`, shell commands, the recognized path arguments, and the spend under-count while events are queued.
    - Write `README.md`: what Agent Watch is, the 3-line integration, deploy steps (`sam deploy`, Amplify), running the demos and tests, and the Known limitations section (incl. case-insensitive over-blocking).
    - Known limitations: agent IDs are global and first-come; GET /config reveals whether a name is taken.
    - Known limitations: a hardlink to a blocked file under a different name is not caught by a Name_Entry (it is a different name, and a directory entry catches it only if the link lives inside the blocked directory); the check-then-use window (TOCTOU) means a symlink swapped between the check and the tool's `open()` is not caught. Both are out of the threat model: the SDK guards a careless agent, not a malicious one.
    - _Requirements: 26.1, 26.2, 26.3_
    - Commit: `feat(docs): README with known limitations`

  - [ ] 7.3 Write ARCHITECTURE.md, DEMO_SCRIPT.md, and SUBMISSION.md
    - Write the failing tests first. Extend `backend/tests/test_readme.py` to assert `docs/ARCHITECTURE.md`, `docs/DEMO_SCRIPT.md`, and `docs/SUBMISSION.md` exist and each has a top-level heading; `DEMO_SCRIPT.md` mentions `bad_agent.py` and `.env`.
    - Write the three docs (architecture diagram and decisions from the design, the demo click-path, submission text with the "next steps" list).
    - _Requirements: 16.1, 16.2_
    - Commit: `feat(docs): architecture, demo script, submission`

  - [ ]* 7.4 Add moto-based DynamoStore tests
    - Write the failing tests first. In `backend/tests/test_store_moto.py` (pinned `moto` in dev deps), create the table with the GSI and check create/record/duplicate/forbidden/query/sum_spend against moto. Skip if moto is missing.
    - _Requirements: 4.1, 4.4, 4.8_
    - Commit: `test(backend): moto DynamoStore checks`

  - [ ] 7.5 Final checkpoint: end-to-end rehearsal
    - Write the failing tests first. Run `pytest` in `backend/` and `sdk/` and `npx vitest --run` in `dashboard/`; ensure all tests pass, ask the user if questions arise.
    - Follow `docs/DEMO_SCRIPT.md` on the deployed stack: add `.env` in the dashboard, run `bad_agent.py`, see `PathBlocked` and the email within 10 s; set a tiny cap and run `demo_agent.py --loop 5`, see the `spend_cap` block; confirm inventory and timeline update. Note timings and any issue in `PROGRESS.md`.
    - _Requirements: 5.4, 6.2, 10.4, 16.3, 16.4, 24.3_

## Notes

- Property tests are required and live inside the task that adds the logic. Only 7.4 is optional (`*`).
- Properties split across tasks (5, 6, 10, 12, 14, 23, 28) get one test each; later tasks extend that same test with the new clause instead of adding a second one.
- If AWS access blocks 4.6, 5.3, 5.13, or 7.1, log it under "Blocked" in `PROGRESS.md` and continue with the next local task.
- Not automated by design: latency targets, email delivery time, HTTPS-only, and constant-time comparison (single `hmac.compare_digest` call site). They are checked in 4.6 and 7.5.
