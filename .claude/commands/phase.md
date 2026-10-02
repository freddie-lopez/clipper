---
description: Build one phase of docs/plan.md end to end
argument-hint: <phase, e.g. 1b>
---
Build phase $ARGUMENTS of Clipper.

1. Read CLAUDE.md and docs/plan.md. Find the row and prompt for phase $ARGUMENTS. If the phase doesn't exist, or it's a "you" step (labeling), stop and tell me.
2. Confirm the latest CI run on main is green. If it isn't, stop and show me why.
3. Follow that phase's prompt. Present your plan and wait for my approval before editing any files.
4. Build until tests, ruff and mypy all pass.
5. Write the devlog entry for this phase in docs/devlog/.
6. Use the reviewer agent to review phase $ARGUMENTS against docs/plan.md. Fix every finding and review again until SIGN-OFF. Never skip the review. If 3 rounds pass without SIGN-OFF, stop and show me what's still open.
7. Commit with the message "Phase $ARGUMENTS: <short summary>". Never push.
8. Finish with a short summary and any reviewer notes for the next phase.
