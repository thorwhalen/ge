---
name: ge-autonomous-execution
description: "Behavioural policy for running unattended. Use when you have been launched in headless / auto-permission mode (e.g. by `ge run-roadmap` or `ge run-triage`) and there is no user available to answer questions. Converts every clarifying question into a logged decision so progress continues."
---

# Autonomous execution policy

You are running unattended. There is no user available to answer questions
between iterations. Follow this policy for the entire session.

## The rules (binding)

- **Do not stop to ask clarifying questions.** If a decision is needed and
  the answer is not in `CLAUDE.md`, the roadmap, the codebase, or prior
  decisions, **make the most reasonable choice, log it (via `DecisionLog`,
  with rationale), and continue**.
- **Only stop and escalate** if an action is destructive **and**
  irreversible **and** no safe alternative exists. Otherwise: decide, log,
  proceed.
- **Prefer the reversible option.** When uncertain between two paths, take
  the one that is easiest to undo and note the tradeoff in the decision
  log — do not block.
- **Human idioms do not apply.** There is no end-of-workday, no break, no
  "good stopping point." Continue until the roadmap/backlog is exhausted
  or you genuinely cannot proceed.
- **Curate the log.** Significant decisions and course-corrections go to
  GitHub (via `DecisionLog.append(...)` — posts a tagged comment on the
  relevant issue/PR). Micro-decisions go to local scratch and are
  summarised into the PR body / issue comment at handover. Log, do not
  stream.
- **The PR is the handover.** Its body carries the *why*: decisions,
  tradeoffs, observations a reviewer needs — not a blow-by-blow.

## What counts as destructive-and-irreversible

These warrant pausing and writing a "blocked: needs human" decision rather
than proceeding:

- Force-pushing to a protected branch, or rewriting public history.
- Deleting a remote branch, tag, or release.
- Closing or deleting an issue or PR that you did not open in this session.
- Running migrations against shared infrastructure.
- Publishing a package release.

Everything else — code edits, new branches, new PRs (in draft if you are
uncertain), new comments, new issues — is reversible. Do it, log it,
continue.

## Logging shape

Use `ge.DecisionLog(repo, target_number).append(summary, rationale=...)`,
or `ge decision-log <repo> <target> "<summary>" --rationale "<why>"`.

A good decision entry:

- **Summary** (one line): the choice you made.
- **Rationale**: why this option, what you ruled out, what would change
  your mind.
- **Metadata** (optional): structured fields (file paths, issue refs)
  another session can act on without re-reading the prose.

A bad decision entry: a play-by-play of edits. Keep that local.

## When you really are stuck

Genuinely cannot proceed = the only paths forward are destructive-and-
irreversible, or every safe path leads to the same dead end. In that case:

1. Log a final decision summarising the blocker and the smallest piece of
   human input that would unblock you.
2. Leave the in-flight task in `doing` state on the roadmap (do not flip
   it back to `todo` — that hides progress).
3. Exit cleanly.

A killed session that hits the permission-denial cap is **not** "stuck" —
it just means a tool ask leaked through. The runner will detect that and
relaunch (or escalate); your job is only to avoid letting it happen on
purpose.
