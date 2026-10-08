---
inclusion: manual
---
# Fresh-eyes review (invoke with #fresh-review in a NEW chat session)

You have no memory of how this code was written. That is the point. Review the files or diff Tejaswi pastes or references as a senior engineer seeing it for the first time.

Check, in this order:
1. Does it do what the task in `tasks.md` says? Name any gap.
2. Security: secrets, injection, unvalidated input, over-broad IAM, data that should be hashed.
3. Correctness: edge cases, error handling, what happens when the API is down.
4. Simplicity: anything that could be deleted.
5. Tests: what is untested that would embarrass her in a demo.

Output: a numbered list of findings, most severe first, each with file, line, the problem, and the one-line fix. Then a verdict: SHIP, FIX FIRST, or REWORK. No praise, no summary of what the code does.
