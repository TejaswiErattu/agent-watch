# Agent Watch starter kit

Drop the contents of this folder into the root of your `agent-watch` repo. Then open the folder in Kiro.

What is here:
- `.kiro/steering/` : product, tech, structure, workflow (always on) and fresh-review (manual, `#fresh-review`)
- `.kiro/hooks/` : tests on save, secrets guard, session handoff on stop
- `.kiro/settings/mcp.json` : GitHub and AWS docs MCP servers. Needs `GITHUB_TOKEN` in your shell env.
- `.kiro/specs/agent-watch/` : empty, Kiro fills requirements.md, design.md, tasks.md when you create the spec
- `PROGRESS.md` : the memory that survives every new session
- `docs/HANDOFF_PROMPT.md` : the three prompts you paste
- `docs/CLAUDE_SIDE_PROMPT.md` : how to use Claude chat without breaking the Kiro-only rule
