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
