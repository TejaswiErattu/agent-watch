# Paste this at the start of every new Kiro chat session (v2, from 2026-10-12)

Read PROGRESS.md, then .kiro/specs/agent-watch-v2/requirements.md, design.md, and tasks.md. The v1 spec in .kiro/specs/agent-watch/ is complete and is the reference for the glossary, the existing code shape, and Properties 1 to 29; read its design.md sections only when a task points at them. Tell me in 3 lines: the current state, the next unchecked v2 task you will do, and what done looks like. Then start. One task at a time, tests first, commit after each.

# Paste this in a brand-new session for a v2 group review

#fresh-review Review `git diff <checkpoint-commit>..HEAD` against .kiro/specs/agent-watch-v2/tasks.md group <N>. Check backward compatibility first: every v1 test still passes, stored v1 records still parse, scripts/e2e.sh is unchanged.

---

# Paste this at the start of every new Kiro chat session

Read PROGRESS.md and .kiro/specs/agent-watch/tasks.md. Tell me in 3 lines: the current state, the next task you will do, and what done looks like. Then start.

# Paste this when the context feels long or before you close Kiro

Run the session handoff from workflow.md now. Update PROGRESS.md and tasks.md, commit, and print the 5-line summary.

# Paste this in a brand-new session for a fresh review

#fresh-review Review the diff of the last 3 commits (use git diff HEAD~3) against the current task in tasks.md.
