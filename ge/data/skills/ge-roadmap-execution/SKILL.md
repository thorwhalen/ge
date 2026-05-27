---
name: ge-roadmap-execution
description: "Execute a roadmap of tasks end-to-end using GitHub as durable memory. Use when launched against a roadmap issue (typically by `ge run-roadmap`) — take the next todo task, do it, verify it, mark it done, log decisions, and repeat. Survives context exhaustion because each work unit rehydrates from GitHub."
---

# Roadmap execution

You drive a roadmap of tasks to completion. The roadmap lives in a single
GitHub issue, its body containing a markdown task list bracketed by
`<!-- ge:roadmap:begin -->` / `<!-- ge:roadmap:end -->`. Each entry is one
of `- [ ]` (todo), `- [ ] … <!-- ge:doing -->` (in progress), or `- [x]`
(done).

Memory model: **GitHub is the single source of truth.** The local
`.ge/cache/` snapshot is hydrate-only — never the authority.

If you are running unattended, the `ge-autonomous-execution` skill applies
in parallel: decide-and-log instead of asking.

## Inputs you receive

The runner gives you `REPO` (e.g. `owner/repo`) and `ROADMAP_ISSUE` (the
issue number). Optionally a `DECISIONS_TARGET` issue/PR for the decision
log; if absent, log decisions on the roadmap issue itself.

## The loop (one iteration = one work unit)

```python
import ge

mall = ge.github_memory(
    REPO,
    roadmap_issue=ROADMAP_ISSUE,
    decisions_target=DECISIONS_TARGET or ROADMAP_ISSUE,
)
roadmap = mall["roadmap"]
decisions = mall["decisions"]

task = roadmap.next_todo()
if task is None:
    # No work left — exit cleanly.
    raise SystemExit(0)

# 1. Claim the task.
task.state = ge.TaskState.doing
roadmap[task.id] = task

# 2. Do the work in the codebase (edits, tests, commits — your normal
#    engineering loop). Run/verify before claiming success.

# 3. Mark done — and log only if you made a non-obvious decision.
task.state = ge.TaskState.done
roadmap[task.id] = task
# decisions.append("Used X over Y", rationale="...")  # only if surprising
```

## Modifying the roadmap mid-flight

The roadmap is **agent-modifiable**. If discovery proves a task wrong,
or you uncover a prerequisite, edit it:

- `roadmap.append("New prerequisite I discovered")` — adds a todo at the
  end (you can re-order via repeated `__setitem__`).
- `roadmap[task_id] = new_record` — rename / change state.
- `del roadmap[task_id]` — drop a task that no longer makes sense.

Any non-trivial roadmap edit is a course-correction. **Log it** with the
*why* — that is exactly the case `DecisionLog` exists for.

## CLI equivalents (for shell-driven steps)

```bash
ge roadmap-show owner/repo 1            # JSON dump of all tasks
ge roadmap-next owner/repo 1            # task id of next todo, or empty
ge roadmap-set  owner/repo 1 <id> doing
ge roadmap-set  owner/repo 1 <id> done
ge roadmap-append owner/repo 1 "new task title"
ge decision-log owner/repo 1 "short summary" --rationale "why"
```

## Definition of done for an iteration

- The task is verified (tests run, change exercised, output checked —
  whatever applies to the task type). Compiling is not verifying.
- The task is marked `done` in the roadmap. Marking done is the last
  step, *after* verification, never before.
- If you made a decision that another session would not infer from the
  code, it is in `DecisionLog`.
- If the work produced a PR, the PR body summarises the *why* — that is
  the handover to a human reviewer.

## What to skip

- Do not write a play-by-play decision for every edit. Curate.
- Do not "wrap up early" because the session feels long. Token exhaustion
  is not a failure — the runner relaunches with a clean context and the
  next iteration rehydrates from GitHub.
- Do not commit local cache files; `.ge/` is gitignored.
