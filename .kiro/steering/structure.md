---
inclusion: always
---
# Repo structure

```
agent-watch/
  .kiro/              steering, hooks, specs, mcp settings (judges read this)
  sdk/                Python package `agentwatch`
    agentwatch/       __init__.py, client.py, guardrails.py, pricing.py
    tests/
    pyproject.toml
  backend/            SAM app
    template.yaml
    src/agentwatch_api/   handlers/, store.py, pricing.py, rules.py, alerts.py
    tests/
  dashboard/          Next.js app
    app/, components/, lib/
  demo/               demo_agent.py, bad_agent.py (the one that gets blocked)
  docs/               ARCHITECTURE.md, DEMO_SCRIPT.md, SUBMISSION.md
  PROGRESS.md         living status file, updated at the end of every session
  README.md
```

## Naming
- Python: snake_case files and functions, PascalCase classes
- TypeScript: camelCase, components PascalCase in `components/`
- Events: `{agentId, ownerId, ts, eventId, type: "llm_call"|"tool_call"|"blocked", tool, target, inputTokens, outputTokens, costUsd, meta}`
