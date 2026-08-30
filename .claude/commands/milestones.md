---
description: Commit the current milestone and update the worklog
argument-hint: [milestone-id] [short summary]
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git commit:*)
---
We just finished milestone $1: "$2".

1. Run the test suite. If anything fails, stop and show me the failure instead of committing.
2. Show me git diff --stat so I can see what changed.
3. Stage everything and commit with the message "$1: $2".
4. Append a dated entry to PROGRESS.md (create it if missing): date, milestone $1, the summary "$2", key files touched, and anything left open.
5. Remind me I can sync PROGRESS.md to the Notion page.
