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
