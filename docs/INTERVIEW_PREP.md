# Interview prep (auto-filled by Kiro as tasks complete)

Format per task:
## Task name
**Conceptual:** ...
**Technical:** ...
**Q:** ... **A:** ...

## 1.1 Scaffold the backend package and test tooling
**Conceptual:** Before any logic exists, the repo needs a test harness that runs with zero AWS access. That keeps every later task fast to verify and safe to run on a laptop or in CI without credentials.
**Technical:** `pyproject.toml` puts `src`, `../sdk`, and the repo root on `pythonpath`, so tests import the backend, the SDK, and `demo/` without installing anything. `conftest.py` registers and loads a Hypothesis `ci` profile (100 examples). Tradeoff: path injection instead of an editable install. It's less "proper" packaging but has no setup step.

**Q:** Why keep Lambda handlers thin? **A:** Business logic in plain modules can be unit-tested with fakes and no AWS. The handler only translates the API Gateway event, so there's very little Lambda-specific code to get wrong.
**Q:** Why does `requirements.txt` list no runtime deps? **A:** The Lambda Python runtime already ships boto3. Bundling nothing keeps the deployment package small and cold starts short.

## 1.2 Pricing_Table and cost math
**Conceptual:** Cost is computed on the server from one price table so a buggy or malicious client can't under-report spend. The SDK gets the same table in the config response, so local cap checks use identical numbers.
**Technical:** `PRICING` maps exact model IDs (Bedrock base, `us.` inference profile, Anthropic API) to per-million-token prices. `cost_from_table` rounds to 6 dp, and unknown models cost 0.0. Tradeoff: exact-match lookup means a new model ID silently costs 0 until it's added, which the demo-model test (1.3) guards against.

**Q:** Why not trust the client's cost? **A:** The client is untrusted. Server-side cost from a single table keeps totals consistent and tamper-resistant.
**Q:** Why do Bedrock models need an inference profile ID? **A:** Newer Claude models on Bedrock only support on-demand calls through geo or global cross-Region profiles (`us.anthropic...`), which route across Regions for capacity.

## 1.3 Demo model constants and pricing coverage test
**Conceptual:** A typo in a model ID would make every call cost $0, so the spend-cap demo would never trip. One file of constants plus a test that cross-checks them against the price table turns that silent failure into a red test.
**Technical:** The backend test loads `demo/models.py` by file path with `importlib.util`, so `demo/` doesn't need to be a package. Tradeoff: it couples the backend test suite to a demo file, but that coupling is exactly the invariant we want enforced.

**Q:** How do you stop configuration drift between two components? **A:** Make one the source of truth and add a test that fails when the other disagrees.
**Q:** Why use a `us.` inference profile? **A:** It routes within US Regions for capacity and it's the on-demand ID Bedrock requires for this model.

## 1.4 Common event validation
**Conceptual:** The API is public, so every event body is untrusted input. Strict validation at the edge means corrupt or oversized data never reaches DynamoDB, and the sort key stays well-formed. That matters because the timeline and spend queries depend on lexicographic `ts` ordering.
**Technical:** `validate_event` returns either an `Event` or a `ValidationError(field, reason)` instead of raising, so the service maps it straight to a 400. It uses fixed-width `ts` regex plus `strptime` (rejects Feb 30), lowercase-hex `eventId`, an allowlist of top-level fields, and a 4 KB cap on serialized `meta`. Client `costUsd` is dropped from the stored item. Tradeoff: it reports only the first error, not all of them. That's simpler, and enough for a machine client.

**Q:** Why an allowlist of fields instead of a denylist? **A:** Unknown fields get rejected by default, so nobody can smuggle attributes like `keyVerifier` or `gsiOwnerId` into stored items.
**Q:** Why cap `meta` size? **A:** DynamoDB items max out at 400 KB and every byte costs write units. A cap bounds cost and blocks abuse.
**Q:** Why a fixed-width timestamp? **A:** Sort keys compare as strings. A fixed width makes string order equal time order, so range queries for "last 24h" are exact.

## 1.5 Type-specific event validation
**Conceptual:** Each event type has its own contract. An `llm_call` needs token counts to be priced, a `tool_call` needs to say what it touched, and a `blocked` event needs to say why. Checking these at ingest keeps the timeline, cost math, and alert emails from ever seeing half-formed data.
**Technical:** `_validate_type_specific` runs after the common checks and returns the first failing field. Token counts must be real ints (bools rejected explicitly, since `True` is an `int` in Python). `attemptedCostUsd` must be finite and >= 0, which rules out NaN and inf. Strings are capped at 1024 chars. Tradeoff: `target` may be empty for no-arg tools, which is looser but matches what the SDK sends.

**Q:** What is a subtle Python validation bug with JSON numbers? **A:** `isinstance(True, int)` is true, so `true` would pass as a token count unless bools are rejected explicitly.
**Q:** Why reject NaN and infinity? **A:** They poison sums (NaN + x = NaN) and can't be stored as DynamoDB numbers, so one bad event could break spend totals.

## 1.6 Guardrail_Config parsing
**Conceptual:** The guardrail config is the contract between the dashboard (writer), the API (store), and the SDK (enforcer). One strict parser means a bad value like a negative cap or an empty path can never reach the SDK and silently weaken a guardrail.
**Technical:** `parse_config` requires both keys, rejects unknown ones, and checks that the cap is null or finite >= 0 (bools rejected) and that paths are 1 to 100 non-empty strings of at most 1024 chars. `GuardrailConfig` is a frozen dataclass with paths as a tuple, so it's hashable and safe to share across threads. A Hypothesis property checks `parse(to_json(c)) == c`. Tradeoff: PUT always sends the full config (no partial patch), which is simpler and avoids lost-update merges.

**Q:** Why would an empty string in a blocklist be dangerous? **A:** Depending on the matcher, `""` could match nothing (a silent no-op) or everything. Rejecting it removes the ambiguity.
**Q:** What does a round-trip property test buy you? **A:** It proves serialize and parse are inverses over thousands of generated configs, which catches type drift such as tuple vs list or int vs float.

## 1.7 Credential parsing and constant-time matching
**Conceptual:** There's no full auth in the MVP, so each agent is bound to the ownerId plus key that first registered it. The server never stores anything that could be replayed as a credential. A database leak exposes only verifiers, not usable keys.
**Technical:** Clients send `sha256(api_key)` as the Key_Hash. The server stores `sha256(key_hash)` as the Key_Verifier and compares with `hmac.compare_digest`, at a single call site. Headers are read case-insensitively because HTTP API lowercases them. `Credentials.key_hash` is `repr=False`, so it can't leak into logs through an f-string. Tradeoff: the Key_Hash is a bearer token, which is acceptable over HTTPS for an MVP. Real auth (Cognito) is a next step.

**Q:** Why hash twice? **A:** If the DB stored the Key_Hash, anyone who read the DB could replay it. Storing a hash of it means a leaked value is useless as a credential.
**Q:** Why constant-time comparison? **A:** `==` can return early on the first differing byte. Timing then leaks how much of a guess is right, and `compare_digest` removes that signal.
**Q:** Is unsalted SHA-256 OK here? **A:** Yes for high-entropy random API keys, where brute force isn't feasible. For human passwords you'd use a slow salted KDF like Argon2 or bcrypt.

## 1.8 Store protocol and InMemoryStore agent records
**Conceptual:** The service layer talks to a `Store` interface, not to DynamoDB. One fake that mirrors DynamoDB's conditional semantics lets every business rule be tested in milliseconds without AWS, while the real `DynamoStore` stays a thin adapter.
**Technical:** It's a single table. The Agent_Record lives at `sk="META"` and events at `sk="{ts}#{eventId}"`. Event SKs start with a digit, so `META` sorts after all of them and never collides. `create_agent_if_absent` mimics `attribute_not_exists(sk)`, and `put_config` mimics `keyVerifier = :kv`. `gsiOwnerId` is written only on META items, which makes the owner GSI sparse. Tradeoff: the fake can drift from real DynamoDB behavior, so 1.12 tests the adapter's exact request shapes and 7.4 adds optional moto tests.

**Q:** What is a sparse GSI and why use one? **A:** DynamoDB indexes only items that have the GSI key attribute. Putting `gsiOwnerId` only on agent records means the inventory query reads agents, never millions of events.
**Q:** Why a Protocol instead of a base class? **A:** Structural typing. Any object with the right methods works, so test fakes don't need inheritance, and `runtime_checkable` still lets a test assert conformance.

## 1.9 InMemoryStore event writes
**Conceptual:** An SDK retry must never double-count spend, and a request with the wrong key must never write anything. The fake store enforces both the same way DynamoDB will: through conditions checked before any write, with all-or-nothing effects.
**Technical:** `record_event` mirrors a two-item `TransactWriteItems`. Item 1 (the META update) carries `keyVerifier = :kv`, and item 0 (the event put) carries `attribute_not_exists(sk)`. Auth is checked first, so a wrong key on a duplicate still returns `forbidden`. Only after both pass does it write the event, add to `totalSpendUsd`, and set `firstSeen` if absent. Tradeoff: `lastSeen` is a separate, non-transactional conditional update, because "keep the later ts" can fail harmlessly on out-of-order events.

**Q:** How do you make ingestion idempotent? **A:** Use a client-generated eventId in the sort key and a conditional put on `attribute_not_exists(sk)`. A retry hits the condition and changes nothing.
**Q:** Why a transaction instead of two writes? **A:** Without one, a crash between "store event" and "add cost" leaves the total wrong forever. A transaction makes them succeed or fail together.

## 1.10 InMemoryStore event and owner queries
**Conceptual:** Three read patterns cover the product. The timeline is one agent's events in time order, the inventory is every agent for one owner, and the spend window is one agent's events in a time range. Each maps to a single DynamoDB Query, with no scans.
**Technical:** `query_events` reads `limit` items past the cursor, then applies the type filter. That matches DynamoDB, where `Limit` caps items read before the `FilterExpression`, so pages can come back short and the client keeps following the cursor. `sum_spend` uses an inclusive SK range, like `BETWEEN`. Tradeoff: filtering after the read wastes some read capacity versus a per-type index, but it avoids a second GSI at MVP scale.

**Q:** Why can a DynamoDB page with a filter return fewer items than `Limit`? **A:** `Limit` counts items evaluated, not items returned. The filter runs afterward, so you paginate on `LastEvaluatedKey`, not on page size.
**Q:** Why avoid Scan? **A:** A Scan reads the whole table and costs capacity in proportion to table size. A Query on a partition key reads only the matching items.

## 1.11 Classify transaction cancellation reasons
**Conceptual:** A transactional event write can fail two ways we care about: the event already exists (duplicate) or the caller's key doesn't match (forbidden). DynamoDB reports failures per item in a `CancellationReasons` list, so we need one function that turns that raw list into a clean result the service layer can act on.
**Technical:** The 2-item transaction orders the event Put first and the META Update second. If item 1 (the `keyVerifier` condition) failed we return "forbidden"; forbidden wins even if item 0 also failed, so a wrong key never looks like a duplicate. If only item 0 failed we return "duplicate". Any other combination (throttling, conflict, no failure) raises so the caller retries or 500s. Tradeoff: matching exact `Code` strings is brittle if AWS renames them, but it keeps the mapping explicit and testable without AWS.

**Q:** Why check the verifier failure before the duplicate failure? **A:** Security first. A caller with the wrong key must always get "forbidden", never leak that an eventId exists via a "duplicate" response.
**Q:** How does DynamoDB signal which item in a transaction failed? **A:** `TransactionCanceledException` carries a `CancellationReasons` list positionally aligned with the `TransactItems`; non-failing items show `{"Code": "None"}`.
**Q:** Why raise on unexpected codes instead of defaulting? **A:** Throttling and conflicts are retryable and distinct from business outcomes. Collapsing them into a result would hide real failures and corrupt the retry logic.

## 1.12 DynamoStore agent-record and event writes
**Conceptual:** This is the real AWS-backed store. It must guarantee exactly one agent record per agentId, never double-count spend on SDK retries, and reject a caller whose key no longer matches, all without locks. DynamoDB conditional writes and a two-item transaction give those guarantees in a single round trip each.
**Technical:** `create_agent_if_absent` uses `attribute_not_exists(sk)` so a lost race returns False instead of overwriting. `record_event` runs one `TransactWriteItems`: a conditional event Put plus a META Update that does `ADD totalSpendUsd` and `if_not_exists(firstSeen)` under `keyVerifier = :kv`. On cancellation it maps `CancellationReasons` to duplicate/forbidden/raise. Numbers go in as `Decimal(str(round(x,6)))`. Tradeoff: I hand-wrote low-level AttributeValue (de)serialization instead of using the resource API, which is more code but lets tests use a tiny fake client with no moto dependency.

**Q:** How do you prevent a retried request from charging twice? **A:** The event Put is conditional on `attribute_not_exists(sk)`, and the cost ADD lives in the same transaction. If the event already exists, the whole transaction cancels and no cost is added.
**Q:** Why wrap the event write and the spend increment in a transaction? **A:** They must be atomic. Separately, a crash between them leaves `totalSpendUsd` permanently wrong. A transaction makes both apply or neither.
**Q:** Why `Decimal(str(round(x,6)))` instead of passing a float? **A:** DynamoDB rejects native floats and stores numbers as decimals. Converting through a rounded string avoids binary-float artifacts like 0.1+0.2 and caps precision at 6 places.
**Q:** How does the write guard against a record whose key was replaced mid-flight? **A:** The META Update carries `ConditionExpression keyVerifier = :kv`. If the stored verifier changed, item 1 fails with ConditionalCheckFailed and we return "forbidden".

## 1.13 DynamoStore queries
**Conceptual:** Three reads back the product: a timeline (one agent's events in order), an inventory (all agents for one owner), and a rolling spend sum (one agent's events in a time window). All three are single-partition or single-GSI Queries, never Scans, so cost scales with the data returned, not the table size.
**Technical:** `query_events` uses `KeyConditionExpression sk BETWEEN :lo AND :hi` where `:hi` sorts below the reserved `META` sort key, so events come back but the agent record never does. Type filtering uses a server-side `FilterExpression` with a `#t` alias because `type` is reserved. `list_by_owner` queries the sparse `ownerIndex`, and `sum_spend` pages via `ExclusiveStartKey`, converting `Decimal` to `float`. Tradeoff: filtering by type after the read can return short pages, so callers follow the cursor instead of trusting page size, which matches how DynamoDB counts `Limit`.

**Q:** Why does the SK high bound sort below "META"? **A:** Event SKs start with a digit and META starts with 'M'. A `BETWEEN` ending below "META" returns only events, so the agent record is never mixed into a timeline.
**Q:** Why page with `ExclusiveStartKey` for the spend sum? **A:** A single Query returns at most 1 MB. For a correct total you must follow `LastEvaluatedKey` until it's absent, otherwise you'd undercount a busy day.
**Q:** Why alias `type` as `#t`? **A:** `type` is a DynamoDB reserved word. Using an `ExpressionAttributeNames` placeholder is the supported way to reference it in a FilterExpression.
**Q:** Why a sparse GSI for inventory instead of filtering the base table? **A:** Only agent records carry `gsiOwnerId`, so the index holds one item per agent. The owner query reads exactly those, with no event noise and no Scan.

## 1.14 Checkpoint: backend foundations (review fixes)
**Conceptual:** A review found inputs that passed validation but would break storage or ordering: non-ASCII digits in `ts`, NaN/Infinity, very deep `meta`, and unvalidated fields from other event types. It also found the in-memory fake drifting from DynamoDB. Each fix closes a gap between "passes validation" and "safe to store".
**Technical:** `ts` uses `[0-9]`, because `\d` matches Unicode digits. An iterative walk rejects non-finite floats in any field and `meta` deeper than 32 levels, with no recursion risk. Foreign-type fields are dropped before type checks. Only costs are rounded, so ints stay ints. Tradeoff: dropping foreign fields silently is lenient to clients, but it means typos in field names go unreported.

**Q:** Why is `\d` a security bug in a validator? **A:** In Python 3, `\d` matches any Unicode decimal digit. A `ts` like `٢٠٢٦-...` passes the check but sorts above `META` as a string, which breaks range queries and record separation.
**Q:** How can a JSON body crash a Python service? **A:** `json.loads` accepts `NaN`/`Infinity` and deep nesting. NaN can't be a DynamoDB number (500 on write), and recursive validators can hit RecursionError. Reject both at the edge with an iterative walk.
**Q:** Why keep a test fake behaviorally identical to DynamoDB? **A:** Service tests trust the fake. If its rounding or pagination differs, a test can pass while production totals drift or pagination stops early.

## 2.1 Service Result type and authorize helper
**Conceptual:** Every route needs the same answer to one question: is there a record for this agent, and do these credentials own it? One helper with three outcomes (missing, match, forbidden) keeps that decision in one place, so no route can get it subtly wrong.
**Technical:** `authorize` does a consistent read, then `auth.matches`. `new_record` stores `sha256(key_hash)`, never the Key_Hash. `Result(status, body)` is a frozen dataclass, so service tests compare whole responses with `==`. `Publisher` is a Protocol with a `NullPublisher` default, which lets ingest run before SNS exists. Tradeoff: returning a sentinel string `"forbidden"` instead of raising is less Pythonic, but it keeps control flow explicit and easy to test.

**Q:** Why separate "missing" from "forbidden"? **A:** A missing record means first contact, so ingest registers it and reads return empty. Forbidden means someone else owns the agentId, which must never create or change anything.
**Q:** Why a consistent read for authorization? **A:** An eventually consistent read could miss a just-created record and treat the agent as new, opening a window for a second owner to race in.

## 2.2 ingest_event: validation, registration, server-side cost
**Conceptual:** Ingest is the one write path from untrusted agents. It validates, binds a new agentId to the caller's credentials on first contact, and computes cost on the server so a client can't under-report spend.
**Technical:** `validate_event` runs first (400, nothing stored). The body `ownerId` must equal the header ownerId. A missing record is created with an empty config, then `record_event` writes the event and cost in one transaction, then `bump_last_seen`. Only `llm_call` costs money, via `estimate_cost`, rounded with the shared `round_cost`, so the response matches what's stored. Tradeoff: race handling, forbidden, and duplicates are deferred to 2.3 so each task stays under an hour.

**Q:** Why check that body ownerId equals the header ownerId? **A:** Otherwise a caller could write events claiming another owner. The authenticated identity has to win over anything in the payload.
**Q:** Why return the server's cost in the response? **A:** The SDK can reconcile its local spend estimate with the authoritative number instead of trusting its own math.

## 2.3 Ingest races, duplicates, forbidden, lastSeen
**Conceptual:** Two first events for a new agent can arrive at once, an SDK retry can resubmit an event, and a record's key can change between the read and the write. Each case has to resolve without locks, without double-charging, and without letting the wrong caller write.
**Technical:** `authorize_or_register` creates the record with `attribute_not_exists`. If the create loses, it re-reads and authorizes against the winner's record. `record_event`'s outcome drives the response: `forbidden` returns 403 and skips `lastSeen`, `duplicate` returns 200 with `duplicate: true` and no spend change. Tradeoff: a duplicate's response reports the recomputed cost rather than reading the stored item, which saves a read and is identical as long as prices don't change between retries.

**Q:** How do you handle two concurrent "first" requests for the same new resource? **A:** Conditional create. The loser gets a condition failure, re-reads the winner's record, and authorizes against it, so the outcome is the same as if the requests had been serial.
**Q:** What's a TOCTOU bug and where could one appear here? **A:** Time-of-check to time-of-use. Authorization reads the record, then the write happens later. The `keyVerifier = :kv` condition on the write re-checks ownership atomically, closing the gap.
**Q:** Why should a retried request return 200 instead of an error? **A:** Idempotency. The client can't tell whether its first attempt landed, so "already stored" has to look like success or it will retry forever.

## 2.4 get_config
**Conceptual:** The SDK fetches its guardrails and the price table on startup and every 60 s. A brand-new agent has no record yet, so it gets the empty config instead of an error. Reads never create records, so a typo'd agentId can't squat on a name.
**Technical:** It validates the agentId (400), then `authorize`. A missing record returns `EMPTY_CONFIG` plus `pricing_table()`, a match returns the stored config, and a mismatch returns 403. A Hypothesis property checks that a read on any agentId leaves the store empty. Tradeoff: missing and empty look identical to the caller, which leaks nothing about which agentIds exist, but the SDK can't tell "not registered yet" apart.

**Q:** Why should a GET never create state? **A:** GETs are safe and idempotent by HTTP semantics. Caches, retries, and crawlers can repeat them, and a side effect would let anyone register agentIds just by reading.
**Q:** Why return 200 with an empty config instead of 404 for an unknown agent? **A:** A 404 vs 403 split tells an attacker which agentIds exist. The empty config also lets a new agent start with safe defaults.

## 2.5 put_config
**Conceptual:** A student sets guardrails before the agent has ever run, which is exactly when the `.env` rule matters most. So a PUT on an unknown agentId registers it, bound to the caller's key, and every later write must come from that same key.
**Technical:** It validates the agentId and parses the full config (400, no side effects). Then `authorize_or_register` either creates the record with the submitted config or returns the existing one. Existing records are updated with `SET guardrails` under `keyVerifier = :kv`, so a key swapped mid-flight returns 403. Properties cover invalid bodies (store unchanged), PUT-then-GET round trips, and one META item across interleaved events and PUTs. Tradeoff: full replace, not patch. Simpler, and no lost-update merge logic.

**Q:** Why full replace instead of PATCH? **A:** With a single writer (the dashboard), full replace is idempotent and needs no merge rules. Concurrent PATCHes would need versioning to avoid lost updates.
**Q:** What stops someone from overwriting another student's guardrails? **A:** The update is conditional on the stored keyVerifier matching sha256 of the caller's Key_Hash, checked atomically in DynamoDB, not just in application code.

## 2.6 Lambda router for events and config
**Conceptual:** One Lambda serves every route. The handler only translates API Gateway's event into service calls and back, so all business rules stay in plain, fast-to-test Python, and the Lambda-specific surface is tiny.
**Technical:** It routes on `routeKey` through a dict table. The JSON body is decoded (including base64 bodies), and malformed JSON, bad base64, or pathological nesting all return 400. Unknown routes return 404 `{"error":"not found"}`. Any unexpected exception is logged and becomes 500 `{"error":"internal"}`, so stack traces never leak. Deps (`DynamoStore`, publisher) are built lazily once per container and are overridable in tests. Tradeoff: a single function means a shared cold start and one IAM role for all routes, which is fine at this size.

**Q:** Why build the boto3 client outside the handler call? **A:** Lambda reuses containers, so module-level state survives across invocations. Creating the client once saves connection setup on every warm request.
**Q:** Why return a generic 500 body? **A:** Internal error details such as exception text and table names help attackers map the system. Log them server-side and return a fixed message.

## 2.7 401 gate and secret-safe logging
**Conceptual:** Unauthenticated requests should cost almost nothing and learn nothing, so the credential check runs before any body parsing or database read. Logs are useful for debugging, but they're also a common leak path, so they carry only what an operator needs: route, agentId, status, and request id.
**Technical:** `lambda_handler` calls `parse_credentials` right after route lookup and returns a fixed 401 body on failure. Mismatches surface as 403 from the service layer. Logging uses `extra=` fields, never headers. The 500 path logs the exception type, not its message, since messages can echo input. Properties drive random operation sequences through the handler and assert no Key_Hash or verifier appears in responses, logs, or stored items. Tradeoff: no stack traces in logs makes 500s harder to debug.

**Q:** Why check auth before validating the body? **A:** It denies unauthenticated callers a free validation oracle and avoids spending CPU parsing attacker-supplied payloads.
**Q:** How can secrets leak through logs even if you never log them directly? **A:** Through exception messages, request dumps, or header logging. Log structured, allowlisted fields and only the exception type.
**Q:** What's the difference between 401 and 403 here? **A:** 401 means no usable credentials were presented. 403 means valid-looking credentials that don't own this agent.

## 3.1 Scaffold the SDK package
**Conceptual:** The SDK runs inside a student's own project, so every dependency we add is one more thing that can break their install or bloat their environment. Tests that lock the dependency list to `requests` alone make "lightweight SDK" an enforced rule, not a promise.
**Technical:** `test_packaging.py` parses `pyproject.toml` with `tomllib` and asserts exactly one runtime dependency with a bounded range (`requests>=2.31,<3`). It also walks every file under `sdk/agentwatch/` with `ast` and fails on imports of `boto3`, `botocore`, `numpy`, `pandas`, or `torch`. Tradeoff: an AST scan is static, so it misses dynamic imports via `importlib`. It's cheap and catches the common accident of a stray import.
**Q:** Why keep boto3 out of the SDK? **A:** It's a heavy dependency, and it would need AWS credentials on the student's machine. The SDK only talks HTTPS to our API with an owner id and a key hash, so the AWS surface stays server-side.
**Q:** Why an upper bound like `<3` on requests? **A:** It allows minor and patch updates but blocks a future major release with breaking changes from silently entering a user's environment.

## 3.2 Key_Hash, exceptions, and safe repr
**Conceptual:** The student's API key shouldn't leave their machine, and it shouldn't sit in memory where a traceback or debug print could expose it. The SDK hashes the key as soon as it gets it and sends only the hash. Guardrail blocks are typed exceptions, so an agent can catch `PathBlocked` specifically and keep running.

**Technical:** `key_hash` is the SHA-256 hex digest of the UTF-8 key, checked against the FIPS "abc" vector. `Credentials` is a frozen dataclass with `key_hash` marked `repr=False`, and `from_api_key` drops the plaintext. `SpendCapExceeded` and `PathBlocked` subclass `GuardrailBlocked` and fix `violation_type`. Tradeoff: an unsalted fast hash of a high-entropy key is fine, but it would be weak for human-chosen passwords.

**Q:** Why is unsalted SHA-256 acceptable here when it's wrong for passwords? **A:** API keys are long random strings, so there's nothing to brute-force or look up in a rainbow table. Passwords are low-entropy and need a slow, salted KDF like Argon2 or bcrypt.

**Q:** Isn't the hash itself now a bearer credential? **A:** Yes. Anyone with the hash can call the API, so it's treated as a secret too: hidden from repr and logs, and sent only over HTTPS. The server stores only a hash of the hash, so a table leak doesn't expose it.

**Q:** Why a typed exception hierarchy? **A:** Callers can catch every guardrail block or just one kind. Exceptions also stop execution before the risky action, which a return value can't guarantee.

## 3.3 ApiClient with credential headers
**Conceptual:** Every request the SDK sends has to prove who it's from, and none of them may carry the raw key. Putting all HTTP behind one small client means the credential rule lives in one place, and tests can swap the network for a recording fake.

**Technical:** `ApiClient` builds `/events`, `/agents/{id}/config`, and `/agents/{id}/spend` URLs and adds `X-Agentwatch-Owner` and `X-Agentwatch-Key-Hash` to every call, with a 2 s timeout. The `Transport` protocol returns `Response(status, body)`. `RequestsTransport` turns connection errors and timeouts into `TransportError` that carries only the exception type name. Property 19 runs random keys and outcomes and scans URLs, headers, bodies, logs, and repr. Tradeoff: dropping requests' error message loses some debugging detail.

**Q:** Why a transport seam instead of mocking `requests`? **A:** A two-method fake is simpler and safer than patching a library's internals. Tests also never touch the network.

**Q:** Why strip the exception message from network errors? **A:** Library errors often embed the URL or request details. Keeping only the type means a logged error can't leak a credential.

**Q:** Why a short 2 s timeout? **A:** The SDK runs inside someone else's agent. A slow monitoring backend must never stall the agent, so we fail fast and retry in the background.

## 3.4 Send-with-retries policy
**Conceptual:** Networks fail, and a monitoring SDK must never take the agent down with it. Some failures are temporary and worth retrying, like timeouts, 429s, and 5xx. Others won't change on retry, like a bad request or a wrong key, so retrying them only wastes time and hammers the server.

**Technical:** `send_with_retries` makes up to 4 attempts with 0.5, 1, and 2 s sleeps through an injected `sleep`, so tests run instantly. It stops on 2xx, 400, 401, 403, or any other 4xx. A 401 or 403 logs one fixed message per process. Every failure path returns False, and nothing raises. Property 20 checks attempt counts and sleeps against random outcome sequences. Tradeoff: there's no jitter, which is fine for one client but would cause synchronized retries at scale.

**Q:** Which HTTP statuses are safe to retry? **A:** Timeouts, connection errors, 429, and 5xx. Here POST is also safe to retry because eventId makes the write idempotent, so a duplicate is detected and not double-counted.

**Q:** Why log the auth failure only once? **A:** A wrong key fails every event. Logging each one floods the user's console and hides real problems.

**Q:** What would you add for many clients? **A:** Exponential backoff with full jitter, plus honoring `Retry-After` on 429, so clients don't retry in lockstep.

## 3.5 Background Sender
**Conceptual:** Reporting must not slow the agent down, so normal events go into a queue and a background thread sends them. Blocked events are different. They're the evidence for the alert email, and the agent is about to raise, so they're sent synchronously before the exception. That way even a crashing bad agent reports what it tried.

**Technical:** `Sender` owns a `queue.Queue` and one daemon thread named `agentwatch-sender` that calls `send_with_retries` for each item, in FIFO order. `flush(timeout)` waits on the queue's `all_tasks_done` condition with a deadline. An `atexit` hook flushes for up to 5 s. The sleep and `atexit` hooks are injected for tests. Tradeoff: a daemon thread dies with the process, so events queued after the 5 s flush window are lost.

**Q:** Why a daemon thread? **A:** A non-daemon thread would keep the interpreter alive and hang the student's script on exit. The `atexit` flush gives queued events a bounded chance to go out.

**Q:** Why send blocked events synchronously? **A:** The exception may end the process. A queued event could be lost, and the block event is what triggers the alert.

**Q:** What are the limits of an in-memory queue? **A:** It's unbounded and lost on a crash. For production, use a bounded queue with drop-oldest, or spool to disk.

## 3.6 SDK cost math over the Pricing_Table
**Conceptual:** Prices change, and a student won't upgrade their SDK just because Anthropic cut a price. So the SDK holds no prices. It uses the table the server sends with each config fetch. The backend stays the single source of truth, and the SDK's spend-cap estimate matches what the server will bill.

**Technical:** `cost_from_table(table, model, in, out)` is `(in*inputPerMTok + out*outputPerMTok) / 1e6`, rounded to 6 dp, and returns 0.0 for an unknown model or an empty table. An AST test fails on any non-zero float literal in the file. Property 1 runs random models and token counts through both the SDK and the backend and requires agreement within $0.0001. Tradeoff: the formula is duplicated in two packages, and a parity test guards it instead of a shared library.

**Q:** Why not ship prices in the SDK? **A:** Clients drift. Server-provided data updates every user immediately and avoids two sources disagreeing.

**Q:** Why duplicate the formula instead of sharing a package? **A:** The SDK must stay requests-only and installable on its own. Four lines plus a property test is cheaper than a third package.

**Q:** What happens before the first config fetch? **A:** The table is empty, so estimates are 0.0 and a cap can't block. That's the fail-open choice for availability, and it's documented.

## 3.7 Watcher init and config sync
**Conceptual:** When a student adds `.env` to the blocklist in the dashboard, the running agent should pick it up within a minute, without a restart. When the API is down, the agent should keep working with the last rules it saw, not crash and not silently drop its guardrails.

**Technical:** `init` resolves the endpoint (argument, else `AGENTWATCH_ENDPOINT`), hashes the key, starts the `Sender`, and fetches config once. `_maybe_refresh_config` refetches when 60 s have passed since the last attempt, not the last success, so a failing API sees at most one request per minute. Any non-2xx, network error, or malformed body counts as a failure and keeps the last good `ConfigResponse`. Before any success it's `EMPTY`. Tradeoff: up to 60 s of staleness after a rule change.

**Q:** Why time refreshes from the last attempt and not the last success? **A:** Timing from success would retry on every guardrail check during an outage, hammering a struggling API. Timing from the attempt caps it at once per interval.

**Q:** Is starting with no rules (fail-open) safe? **A:** It's a deliberate availability tradeoff for a student tool and it's documented. A stricter product could refuse to start, or cache the last config on disk.

**Q:** Why validate the config response on the client? **A:** It's input from the network. A malformed payload must not crash the agent or install a broken rule set, so it's treated like a failed fetch.

## 3.8 Path forms for blocklist matching
**Conceptual:** The same file has many spellings: `./.env`, `a/../.env`, `~/proj/.env`, a symlink, or `.ENV` on a case-insensitive Mac. A blocklist that compares raw strings is trivially bypassed. So every path is turned into a small set of canonical forms before any comparison happens.

**Technical:** `absolute_path` expands `~`, makes the path absolute, and removes `.` and `..` lexically, keeping symlinks. `normalize_path` uses `realpath`, which resolves symlinks. `path_forms` returns both, casefolded. Casefolding goes beyond lowercasing: `ß` becomes `ss`. An entry is a directory entry if it contains a separator, otherwise a file name that matches anywhere. Tradeoff: casefolding can over-block on case-sensitive Linux, which is the safe direction.

**Q:** Why keep both the lexical and the resolved path? **A:** A symlink named `.env` pointing at `secrets.txt` is only caught by the lexical name. A harmless-looking alias pointing into `~/.ssh` is only caught by the resolved path. Checking both closes both gaps.

**Q:** Why `casefold()` instead of `lower()`? **A:** It's Unicode-aware caseless matching. `lower()` misses cases like `ß` vs `SS`, which an attacker could use to slip past a blocklist.

**Q:** Is this a TOCTOU risk? **A:** Yes. A symlink can be swapped between the check and the open. The SDK is a guardrail against accidents, not a sandbox, and the README says so.

## 3.9 Directory and name entry matching
**Conceptual:** Students think about blocked paths in two ways: a place (`~/.ssh`, everything under it) and a kind of file (`.env`, wherever it lives). The matcher supports both, and it has to get the boundary right. Blocking `/a/b` must not block `/a/bc`, or people will stop trusting it.

**Technical:** A directory entry matches when any attempted form equals any entry form, or starts with it plus `os.sep`. That separator boundary is what keeps sibling prefixes out, and `/` correctly blocks everything. A name entry matches when the casefolded basename of any form equals the casefolded entry. `blocked_entry_for` returns the first matching entry, which goes in the alert. Properties 26 (siblings) and 27 (case changes, including `ß`/`É`) run against real temp trees. Tradeoff: matching is O(entries × 4 forms), fine for at most 100 entries.

**Q:** What's the classic bug in prefix-based path checks? **A:** Using `startswith` without a separator, so `/home/al` blocks `/home/alice`. The fix is to compare against `entry + sep` or exact equality.

**Q:** Why test against real temp directories instead of strings? **A:** `realpath` touches the filesystem, and platforms like macOS add their own symlinks (`/var` → `/private/var`). Real trees catch what string tests miss.

**Q:** Why return the matching entry and not just a bool? **A:** The alert and the dashboard can show which rule fired, so the student can tell why the agent was stopped.

## 3.10 Symlink and equivalent-spelling cases
**Conceptual:** Symlinks are the obvious way around a path blocklist: make `notes.txt` point at `~/.ssh/id_rsa` and read that instead. The rule we promise is that an alias can add a block but never remove one. This task proves that rule against real symlinks on disk.

**Technical:** Example tests cover a symlink named `.env` pointing at `secrets.txt`, a file alias and a directory alias into a blocked folder, an alias to a real `.env`, and a blocked entry that is itself a symlink. Property 25 builds a tree with random symlinks and checks two things: the same decision for `p`, `./p`, and `d/../p`, and that every alias resolving to a blocked file is also blocked. No code changes were needed. Tradeoff: there's a check-then-open race, as with any userspace check.

**Q:** How would an attacker bypass a path blocklist? **A:** With `..` segments, symlinks, case changes, `~` expansion, or relative paths. Canonicalizing before comparing, and checking both the link and its target, closes these.

**Q:** What is a metamorphic test? **A:** It checks that a transformation that shouldn't matter, like `./p` vs `p`, gives the same output. It doesn't need to know the right answer for each input.

**Q:** Why is the converse ("alias blocked implies target blocked") not required? **A:** A symlink named `.env` is blocked by its name even when its target isn't. Blocking more is the safe direction.

## 3.11 Tool wrapper with tool_call events
**Conceptual:** Students already have their tools as plain functions in a dict. Wrapping that dict in one line makes every tool call visible on the timeline, including the ones that crash, without changing how the agent calls its tools. The wrapper also finds which argument is a file path, which is the hook the blocklist uses in the next task.

**Technical:** `_wrap_tool` binds arguments with `inspect.signature` and picks the path from `path_arg` or the first of `path`, `file_path`, `filepath`, `filename`, `file`. `target` is that path, else `repr` of the first argument, capped at 200 chars. `meta.args` holds at most 10 reprs and is trimmed to a 3 KB UTF-8 budget so the server's 4 KB limit never rejects it. A `finally` block queues the event even when the tool raises, with `meta.error` set to the exception type. Tradeoff: argument `repr`s can contain user data.

**Q:** Could logging tool arguments leak sensitive data? **A:** Yes. `repr` of arguments can include file contents or tokens. That's why they're truncated, kept in `meta`, and why prompts are never sent. Production would add an allowlist or redaction.

**Q:** Why record the exception type and not the message? **A:** Messages often echo inputs. The type is enough to see that a tool failed and how.

**Q:** Why trim on the client to match a server limit? **A:** A 400 from the server is a lost event. Enforcing the limit before sending keeps the record and avoids wasted retries.

## 3.12 Enforce the path blocklist
**Conceptual:** This is the demo moment. When the agent calls `read_file(".env")`, the file is never opened, the server hears about it before the agent does, and the agent gets a clear `PathBlocked` it can catch. Enforcement sits in the SDK, in front of the action, because once a secret has been read, alerting about it is too late.

**Technical:** Before a tool runs, the wrapper refreshes a stale config and calls `blocked_entry_for` on the decoded path (str, bytes, or PathLike). On a match it sends a `blocked` event synchronously on the caller's thread, with `violationType`, `attemptedPath`, and `meta.{tool, entry}`, then raises. No `tool_call` event is queued. Reporting failures are swallowed, so the block always holds. Property 24 compares against a separately written reference rule. Tradeoff: tools without a recognized path argument aren't checked.

**Q:** Why enforce on the client and not the server? **A:** The server never sees the file read. Only code in the agent's process can stop it. The server is the record and the alert path.

**Q:** What if the report fails? **A:** The block still happens. Failing closed on the action matters more than the telemetry, and retries cover brief outages.

**Q:** Why test against an independently written reference? **A:** Comparing code to itself proves nothing. A second implementation from the spec catches shared misunderstandings.
## 3.13 LLM wrapper event capture
**Conceptual:** One line, `client = aw.wrap(client)`, makes every model call show up on the timeline with model, tokens, and latency. Students keep using the Bedrock or Anthropic client exactly as before. The prompt itself is never sent, only its shape (message count, character count), so watching an agent doesn't create a new data leak.

**Technical:** `wrap` duck-types: a callable `converse` means Bedrock, a `messages.create` means Anthropic. A small proxy overrides only that method and forwards everything else through `__getattr__`. After a successful call it reads `usage` and queues an `llm_call` event with `meta = {provider, messageCount, promptChars, maxTokens, stopReason, latencyMs}`. Provider exceptions propagate and record nothing. Property 18 checks one well-formed event per call across mixed LLM and tool sequences. Tradeoff: streaming APIs aren't wrapped yet.
**Q:** Why duck typing instead of `isinstance` checks on SDK classes? **A:** It avoids importing `boto3` or `anthropic` into the SDK, keeps the dependency footprint to `requests`, and works with fakes in tests.
**Q:** How do you observe LLM usage without logging prompts? **A:** Record metadata only: token counts from the provider's usage block, message count, and character length. That's enough for cost and behavior, with no content to protect.
**Q:** Why no event when the provider call fails? **A:** No tokens were billed and there's no usage to report. The exception still reaches the agent unchanged, so error handling isn't altered.
## 3.14 Unknown-model warn-once
**Conceptual:** If a student uses a model the price table doesn't know, its cost is recorded as $0. That's silent under-reporting, so the SDK warns. But a warning on every call would bury the logs in a loop, so each unknown model warns once per process. Before the first config fetch the table is empty by design, so warnings are skipped then; they'd flag every model.

**Technical:** `pricing.py` keeps a module-level `_warned` set and `warn_unknown_model(table, model)` logs on the `agentwatch` logger the first time. The LLM wrapper calls it only when `_last_config_ok` is set, meaning a fetch succeeded. `cost_from_table` stays pure. Property 29 checks each unknown model warns exactly once, known ones never, and nothing with EMPTY. Tradeoff: module-level state is shared across Watchers, which matches "per process" but needs a test fixture to reset.
**Q:** Why not raise on an unknown model? **A:** Observability shouldn't break the agent. A missing price is a reporting gap, not a safety failure, so warn and keep going.
**Q:** How do you avoid log flooding from a hot loop? **A:** Deduplicate on a key (the model name) and warn once. In production you might rate-limit or emit a metric instead.
**Q:** What's the risk of a $0 cost for unknown models with a spend cap? **A:** The cap could under-count. The warning makes it visible, and the fix is adding the model to the server-side price table, which every SDK picks up on the next sync.
