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
