---
inclusion: always
---
# Product: Agent Watch

Agent Watch gives students one place to see, control, and cap what their AI agents do.

## Problem
Students build agents for class projects and hackathons on personal API keys. Nothing shows them what the agent called, what files or data it touched, or what it cost. One runaway loop can drain a month's budget overnight and a careless tool can read a `.env` file.

## Who it is for
UW students and first-time agent builders. No security team, no enterprise tooling, no budget for mistakes.

## What it does (MVP, due Oct 23 2026)
1. `agentwatch` Python SDK: wrap an agent in 3 lines, every LLM call and tool call becomes an event
2. Ingestion API: receives events, estimates cost, stores them
3. Inventory: every agent that has reported in, with owner, model, first/last seen, total spend
4. Timeline: per-agent ordered feed of actions
5. Guardrails: per-agent daily spend cap and blocked-path list, enforced in the SDK before the action runs
6. Alert: email when a cap or rule fires
7. Dashboard: inventory page, agent detail page, rules editor

## Not in scope
Multi-framework support, full auth, mobile, anomaly detection, risk scoring. These are "next steps" in the submission.

## Judging story
Built entirely in Kiro with specs, hooks, steering, and MCP. Serverless on AWS. The demo moment: a misbehaving agent tries to read `.env`, gets blocked live, the alert email arrives on screen.
