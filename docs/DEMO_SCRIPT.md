# Agent Watch demo script

Target length is about 3 minutes, and both guardrails fire live. All commands run from the repo root on the deployed stack. The UI labels below are the ones the dashboard actually uses.

## Before recording (about 5 min, off camera)

1. In a terminal, run `source .venv/bin/activate` and export `AGENTWATCH_ENDPOINT=<ApiUrl>`, `AGENTWATCH_OWNER=<owner-id>`, `AGENTWATCH_KEY=<your-key>`. Read the key from your private file. Never show it on screen or paste it into the repo.
2. Check `aws sts get-caller-identity` works (Bedrock), or set `ANTHROPIC_API_KEY` for the fallback.
3. Open the dashboard (https://main.d65rs0iutjwy8.amplifyapp.com). Enter Owner ID and API key, then click **Save credentials**.
4. Open `bad-bot` (inventory link, or type `bad-bot` under **Agent ID** and click **Open**). If `.env` is already under **Blocked paths**, click **Remove** and then **Save rules**, so you can add it live.
5. Open `demo-bot`. Look at its spend in the inventory and pick a **Daily spend cap (USD)** a little above its current 24h spend, about $0.003 more. Leave the cap empty for now.
6. Have the alert inbox open in a second window.
7. Optional: do one full dry run, then reset steps 4 and 5.

## On camera

1. **Problem (20 s).** "Student agents run on personal API keys. Nothing shows what they touched or what they cost. One careless tool reads `.env`, and one loop drains the budget."
2. **3 lines (20 s).** Show the snippet in `README.md`: `agentwatch.init`, `aw.wrap(client)`, `aw.tools(TOOLS)`.
3. **Inventory (15 s).** Show the dashboard inventory: agents, owner, model, first and last seen, total spend.
4. **Path block (60 s).** This is the demo moment.
   - Open `bad-bot`. Under **Add path**, type `.env`, click **Add path**, then **Save rules**.
   - In the terminal: `python demo/bad_agent.py`
   - Expected: the agent answers one question, says it will check the `.env` file, then prints `PathBlocked: ... (Agent Watch stopped the read; an alert email is on its way)`. The file is never opened.
   - Switch to the inbox and show the alert email, subject `Agent Watch: blocked_path blocked for bad-bot`.
   - Back in the dashboard, refresh `bad-bot`. The timeline shows the `blocked` event at the top.
5. **Spend cap (50 s).**
   - Open `demo-bot`. Enter the cap from step 5 of the prep and click **Save rules**.
   - In the terminal: `python demo/demo_agent.py --loop 5`
   - Expected: `run 1/5 agent: ...`, maybe `run 2/5 ...`, then `run N/5: SpendCapExceeded: ... (Agent Watch stopped the call before it ran; ...)`. The blocked call was never sent to the model.
   - Show the alert email (`Agent Watch: spend_cap blocked for demo-bot`), then the `demo-bot` timeline (newest first): the `blocked` event on top, the successful `llm_call` events below it. Use **Filter** to show only `blocked`.
6. **How it's built (20 s).** API Gateway, Lambda, DynamoDB, SNS, and Amplify in us-west-2, throttled, with a $10 budget. Built in Kiro: show `.kiro/specs`, steering, hooks, and MCP.

## If something goes wrong

- `read_file('.env') was NOT blocked`: the rule wasn't saved, or the SDK hasn't fetched it yet. Config is fetched at `init`, so check **Save rules** succeeded and rerun.
- `run 1/5: SpendCapExceeded` immediately: the cap is below the current 24h spend plus about $0.001. Raise it and rerun.
- No block after 5 runs: the cap is too high. Lower it.
- `Bedrock unavailable (...); falling back to Anthropic API`: fine, the demo still works if `ANTHROPIC_API_KEY` is set.
- No email: check spam, and check that the SNS subscription was confirmed. The block itself still happened, so show it in the timeline.
- `agentwatch: authorization failed`: wrong `AGENTWATCH_OWNER` or `AGENTWATCH_KEY` for that agent id.
