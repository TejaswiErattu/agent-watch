# Agent Watch: submission

## One line

Agent Watch gives students one place to see, control, and cap what their AI agents do. It takes three lines of Python, runs serverless on AWS, and was built entirely in Kiro.

## Problem

Students build agents for class projects and hackathons on personal API keys. Nothing shows them what the agent called, what files it touched, or what it cost. One runaway loop can drain a month's budget overnight, and one careless tool can read a `.env` file full of secrets. There's no security team and no budget for mistakes.

## What it does

- **3-line SDK.** `agentwatch.init`, `aw.wrap(client)`, `aw.tools(TOOLS)`. Every Bedrock or Anthropic call and every tool call becomes an event with tokens and cost. Prompt text is never sent.
- **Guardrails before the action runs.** A blocked-path list (stops `.env`, `~/.ssh`, and symlink aliases of them) and a daily spend cap (stops the LLM call before it's paid for). Both are enforced in the SDK, and a block still happens even if reporting it to the server fails.
- **Alert email.** When a guardrail fires, the owner gets an SNS email within seconds.
- **Dashboard.** Inventory of every agent (owner, model, first/last seen, total spend), a per-agent timeline with type filter, and a rules editor. Rule changes reach a running agent within 60 s.

## Demo

`bad_agent.py` tries to read `.env`. The SDK raises `PathBlocked` before the file is opened, the blocked event shows in the timeline, and the alert email arrives on screen. Then `demo_agent.py --loop 5` runs into a small daily cap and stops with `SpendCapExceeded`. See `docs/DEMO_SCRIPT.md`.

## How it's built

- **AWS, serverless, us-west-2.** API Gateway HTTP API (throttled 10 rps / burst 20), one Python 3.11 arm64 Lambda, a DynamoDB single table with a sparse owner GSI, an SNS email topic, Amplify Hosting for the static Next.js dashboard, and a $10 monthly AWS Budget. All of it is defined in one SAM template.
- **Security choices.** API keys never leave the agent's process. The server stores only a hash of the key's hash and compares in constant time. Cost is computed server-side. A wrong key writes nothing (the transaction is conditioned on the key). Logs and responses never contain key material. CORS allows only the dashboard origin.
- **Correctness.** Event writes are transactional and idempotent, so SDK retries never double-count spend. Path checks use both the absolute and the symlink-resolved path, case-folded.
- **Tests.** pytest + Hypothesis with 29 correctness properties from the design, plus vitest for the dashboard. No AWS or network needed. The live stack is checked by hand.

## Built with Kiro

- **Specs.** `.kiro/specs/agent-watch/` holds requirements (EARS acceptance criteria), the design (decisions, interfaces, 29 properties), and `tasks.md`. Each task was written test-first and committed on its own.
- **Steering.** `product.md`, `tech.md`, `structure.md`, and `workflow.md` kept every session on the same stack, naming, and handoff routine.
- **Hooks.** `.kiro/hooks/` defines tests-on-save for `sdk/` and `backend/src/`, a secrets guard on save, and a session handoff on stop.
- **MCP.** The GitHub server opened the infra PRs (#1 SAM template, #2 throttling and budget), and they were merged only after Tejaswi approved. The AWS docs server, along with the SAM translator source fetched through GitHub, was used to check SAM `Globals` behavior before the live template changed.
- **Memory.** `PROGRESS.md` carried state, decisions, and blockers across sessions.

## Known limitations

These are listed in `README.md`. In short, the SDK guards a careless agent, not a malicious one. Direct `open()` calls and shell commands aren't covered, the spend total can briefly under-count while events are queued, and agent ids are first-come.

## Next steps

- Multi-framework support: JavaScript/TypeScript SDK, plus LangChain and OpenAI client wrappers
- Full auth: user accounts (Cognito) instead of per-agent key binding, and team sharing
- Mobile-friendly dashboard
- Anomaly detection: alert on unusual call rates or new tools/paths, not just fixed rules
- Risk scoring for agent actions
- Reliable alerts via DynamoDB Streams (at-least-once, deduplicated)
- Kernel-level or sandboxed file enforcement to cover `open()` and shell commands
