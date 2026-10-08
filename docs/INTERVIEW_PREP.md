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
