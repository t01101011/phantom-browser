# Notion task workflow

Notion is the human-facing source of truth for Phantom Browser work. Repo files and GitHub are evidence/projections, not a second editable task database.

Project page: `399539c8-7ba9-811c-9b07-d0f19fb583ce`

## State model

Status and execution mode are separate axes.

Status:
- `Pending`: accepted backlog, not started.
- `In Progress`: actively being worked.
- `Review`: implementation is complete and evidence is attached; tk decides accept/reopen.
- `Blocked`: cannot proceed; `Review Notes` must identify the dependency or required human action.
- `Done`: accepted by tk, or explicitly approved for auto-close.
- `Archived`: retained historical item.
- `Not Started`: legacy inbox; migrate accepted work to `Pending`.

Execution Mode:
- `Autonomous`: Trang may implement, test, document, and submit for review without intermediate approval.
- `Manual`: tk/human must perform the work.
- `Collaborative`: Trang can prepare or automate part of it, but needs human input/action.

Autonomous does not mean auto-Done. Default transition:

`Pending -> In Progress -> Review -> Done`

Failures or missing dependencies move to `Blocked`, never silently back to `Pending`.

## Sync identity and evidence

- `Task Key`: immutable machine key, recommended `phantom:<slug>`; never derive identity from the mutable title.
- `Repo Ref`: canonical GitHub issue/PR, plan section, artifact URL, or other review target.
- `Review Notes`: concise acceptance evidence (tests, CI URL, artifact checksum) or blocker/handoff.
- `Last Synced`: reconciler watermark only, not task completion time.

## Ownership and write rules

1. Notion owns title, priority, status, execution mode, due date, and project relation.
2. GitHub/repo owns code, commits, tests, CI logs, releases, and artifacts.
3. A task starts when Notion is changed to `In Progress` before implementation.
4. When autonomous work passes its stated acceptance checks, set `Review`, attach `Repo Ref`, and write evidence to `Review Notes`.
5. Only tk's acceptance moves `Review` to `Done`, unless a task explicitly opts into auto-close.
6. Human changes in Notion win for workflow fields. Automation must not overwrite a newer human edit.
7. Reconciliation is idempotent by `Task Key`; never match by title and never create duplicates.

## Reconciler design

Recommended implementation:
- Pull Notion tasks for the Phantom project.
- Validate unique/non-empty `Task Key` for managed tasks.
- Read GitHub/CI/artifact state using `Repo Ref`.
- Propose or apply only monotonic transitions (`In Progress -> Review` after verified acceptance evidence).
- Store the Notion `last_edited_time` observed at sync start; skip writes if it changed before PATCH.
- Record `Last Synced` after a successful reconciliation.
- Never infer `Done` from a merged commit alone.

This keeps one workflow truth while letting code automation produce grounded evidence. Two writable masters would eventually fight each other, because apparently distributed systems were not annoying enough already.
