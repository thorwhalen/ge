---
name: ge-cross-repo-triage
description: "Triage and resolve a cross-repo issue backlog. Use when launched by `ge run-triage` against multiple repos — Phase A classifies and orders issues into a `TriageBacklog`; Phase B executes them one at a time (failing test → confirm red → fix → confirm green → open PR, then stop). Stops at PR; merging is a separate later phase."
---

# Cross-repo triage

Triage and resolve issues across one or more repositories. The runner
hands you the list of repos and the `TRACKING_REPO` + `TRACKING_ISSUE`
that backs the `TriageBacklog`.

Two phases. **Phase A is read-mostly; Phase B opens PRs but stops short
of merge** — merging is deferred so conflicts and dependencies can be
handled deliberately later.

If you are running unattended, the `ge-autonomous-execution` skill applies
in parallel.

## Phase A — analyse and order

For each repo, fetch open issues (use the existing `ge` tools or
`gh issue list`). Classify each:

| Verdict     | Meaning                                                        |
|-------------|----------------------------------------------------------------|
| `stale`     | Old, no recent activity, likely irrelevant. Recommend close.   |
| `closeable` | Already resolved in the code; PR/commit exists. Recommend close. |
| `fixable`   | Real, actionable, has enough information to attempt a fix.      |
| `blocked`   | Real but needs upstream / a decision / missing info first.     |

Then **order** them — dependencies first, then quickest wins, then the
rest. Record into the backlog with fully-qualified refs:

```python
import ge

backlog = ge.TriageBacklog(TRACKING_REPO, TRACKING_ISSUE)
backlog["owner/repoA#42"] = ge.TriageEntry(
    ref="owner/repoA#42",
    verdict=ge.TriageVerdict.fixable,
    order=1,
    rationale="blocks #43; small change in one file",
)
```

The backlog is durable: it lives as JSON inside the tracking issue body,
between `<!-- ge:triage:begin -->` / `end`. Future sessions read the same
backlog and continue from where you left off.

CLI:

```bash
ge triage-set owner/tracking 9 owner/repoA#42 fixable --order 1 --rationale "..."
ge triage-show owner/tracking 9
```

## Phase B — execute, one entry at a time

Iterate `backlog` in order. For each `fixable` entry:

1. **Write a failing test that reproduces the bug.**
2. **Run it and confirm it fails.** A test that passes before the fix
   is not a valid reproduction. Record that finding in the decision log
   and move on rather than "fixing" nothing.
3. **Fix the bug.**
4. **Run the test and confirm it now passes.** Run the full test suite
   if it is cheap; otherwise at least the affected module.
5. **Open a draft PR.** The PR body carries the *why*: the bug, the
   failing test, the fix approach, observations a reviewer needs.
   Reference the issue with `Refs #N` (not `Closes` — Phase B stops
   before merge so closure happens later).
6. **Stop.** Do not merge. Do not move to the next entry until the PR
   for this one is open (or you have logged a decision explaining why
   you skipped).

For `stale` / `closeable` entries: in Phase B, post a comment on the
issue explaining your conclusion and (if confident) close it. Closing is
reversible — re-opening is one click — so it's not in the
destructive-and-irreversible bucket.

For `blocked` entries: skip. Log a one-line decision describing the
blocker.

## Definition of done

- Every fixable entry has either an open PR or a logged decision
  explaining why no PR was opened.
- Stale/closeable entries are commented and (where appropriate) closed.
- Blocked entries have a recorded blocker.
- The `TriageBacklog` reflects the final state — entries you actioned
  remain (with metadata pointing at the PR), so a later "merge phase"
  knows what to consider.
