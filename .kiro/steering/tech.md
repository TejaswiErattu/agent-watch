---
inclusion: always
---
# Tech stack and constraints

| Layer | Choice |
| --- | --- |
| SDK | Python 3.11, package `agentwatch`, zero heavy deps (requests only) |
| API | Amazon API Gateway (HTTP API) + AWS Lambda (Python 3.11) |
| Storage | DynamoDB, single table: PK `agentId`, SK `ts#eventId`; GSI on `ownerId` |
| Alerts | Amazon SNS email topic |
| Dashboard | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui, deployed on AWS Amplify Hosting |
| Demo agent | Python calling Amazon Bedrock (Claude). Fallback: Anthropic API |
| Infra | AWS SAM (`template.yaml`), region us-west-2 |
| Tests | pytest for Python, vitest for dashboard |

## Rules
- Every feature starts as a spec in `.kiro/specs/agent-watch/`. No code without a task in `tasks.md`.
- Keep Lambda handlers thin. Logic lives in `backend/src/agentwatch_api/` and is unit-tested without AWS.
- Cost estimation uses `backend/src/agentwatch_api/pricing.py`. Never hardcode prices elsewhere.
- Never commit secrets. `.env` is gitignored. API keys are hashed (SHA-256) before storage.
- Prefer boring choices. If a library decision takes more than 5 minutes, pick the first option that works.
- Commit after every completed task with message `feat(scope): what` / `fix(scope): what` / `test(scope): what`.
- Stay inside AWS free tier. A billing alarm at $10 is set.
