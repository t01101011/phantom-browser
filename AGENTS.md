# Phantom Browser — agent operating rules

## Mandatory Notion workflow

Notion project page: `399539c8-7ba9-811c-9b07-d0f19fb583ce`.
Tasks database: `68737e62-279b-4669-a111-42e912ca9799`.
Detailed contract: `docs/notion-task-workflow.md`.
Helper: `python ~/.hermes/skills/productivity/tk-notion-and-cal-reminders/scripts/notion_cli.py`.

For every coding/work session in this repository:

1. Before implementation, locate the matching Notion task under Phantom Browser.
2. If no matching task exists, create one and assign an `Execution Mode`.
3. Set its status to `In Progress` before modifying code.
4. Keep `Task Key` stable and unique; never identify tasks by mutable title alone.
5. After verified completion, set status to `Review`, not `Done`.
6. Add concise test/CI/artifact evidence to `Review Notes` and the canonical link to `Repo Ref`.
7. If work cannot proceed, set `Blocked` and state the exact dependency in `Review Notes`.
8. Only tk's explicit acceptance moves `Review` to `Done`, unless the task explicitly permits auto-close.

Do not finish a session with implemented Phantom work while its Notion task remains `Pending` or `In Progress` without an accurate note. Human edits in Notion win over automated workflow writes.
