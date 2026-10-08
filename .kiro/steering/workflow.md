---
inclusion: always
---
# Session workflow (read this first, every session)

You are the build agent for Agent Watch. Tejaswi is a UW Informatics student working solo, deadline Oct 23 2026 11:59 PM PST. Protect her time.

## At the start of every session
1. Read `PROGRESS.md`. It says what is done, what is in progress, what is next, and open bugs.
2. Read `.kiro/specs/agent-watch/tasks.md` and find the next unchecked task.
3. Say in 3 lines: what you understand the current state to be, what you will do now, and what "done" looks like.

## While working
- One task at a time. Finish it, run its tests, commit, then move on.
- Run shell commands one at a time. Never run tests, edits, git add, or git commit in parallel; wait for each to finish.
- After writing code, explain it in two layers: **conceptual** (what problem this solves and why this shape) and **technical** (how it works, one tradeoff you made). Keep each under 120 words. Tejaswi will use these for interviews.
- If a task is bigger than expected, split it in `tasks.md` instead of pushing through.
- If something is blocked (missing AWS access, failing deploy), write it under "Blocked" in `PROGRESS.md` and move to the next unblocked task.

## Before the session ends or the context is getting long
Run the handoff:
1. Update `PROGRESS.md`: move finished tasks to Done, write the exact next step, list open bugs, note any decision you made and why.
2. Tick completed tasks in `tasks.md`.
3. Commit everything: `chore: session handoff <date>`.
4. Print a 5-line summary Tejaswi can paste into a fresh session.

## Git
- Work on `main` for the hackathon (solo project, speed over ceremony). Commit small and often.
- For anything risky (schema change, infra change), branch `feat/<name>`, open a PR through the GitHub MCP server, and ask Tejaswi to approve before merging. Never merge without her saying yes.

## Interview prep
When a task is done, add 2 to 3 interview questions with short answers to `docs/INTERVIEW_PREP.md` under that task's heading. Questions should sound like what an AWS or security interviewer would ask.
