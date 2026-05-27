# Autonomous execution

`ge` can drive Claude Code through a long body of work without
interrupting the user. State lives in GitHub (issues, comments), so each
session can exit and the next one rehydrates — token / context
exhaustion is no longer a failure mode.

## Architecture (three layers, separate concerns)

| Layer | Lives in | What it does |
|-------|----------|--------------|
| **1. Tools** | `ge/memory.py` | `RoadmapStore`, `DecisionLog`, `TriageBacklog` — `MutableMapping`/`Iterable` facades over GitHub. All GraphQL/CLI complexity is contained here. |
| **2. Skills** | `ge/data/skills/{ge-autonomous-execution,ge-roadmap-execution,ge-cross-repo-triage}/SKILL.md` | Behaviour. How and when to use Layer 1. Skills call tools; they don't reimplement GitHub access. |
| **3. Runner** | `ge/run.py` | Launch wrapper. Owns the outer loop and the `--permission-mode` flag (which SKILL.md cannot set). One headless `claude -p` per iteration. |

Layer 1 is independently useful: you can use the stores from Python or
CLI without ever invoking the runner.

## The memory model

GitHub is the single source of truth for durable, coarse-grained state.

- **At the start** of each work unit: hydrate from GitHub.
- **At the end**: reconcile meaningful results back to GitHub.
- **Curate writes**: significant decisions → `DecisionLog`. Micro
  decisions → local scratch, summarised into the PR body at handover.
  Decision *log*, not decision *stream*.

The local `.ge/cache/` directory is a hydrate-only snapshot — disposable
and never authoritative. Multi-machine sync is a non-problem because
there is nothing to sync.

## The store contracts

### `RoadmapStore` — `MutableMapping[task_id, TaskRecord]`

A markdown task list inside a *roadmap issue*, between
`<!-- ge:roadmap:begin -->` / `<!-- ge:roadmap:end -->` markers:

```
<!-- ge:roadmap:begin -->
- [ ] Add tests
- [x] Write docs
- [ ] Ship it <!-- ge:doing -->
<!-- ge:roadmap:end -->
```

- Iteration yields task ids in roadmap order.
- `next_todo()` returns the first `- [ ]` task or `None`.
- `__setitem__` rewrites the issue body in place (via `gh api PATCH`).
- `append(title)` adds a todo at the end (and the agent may add tasks
  as it discovers them — the roadmap is agent-modifiable).

### `DecisionLog` — append-only `Iterable[Decision]`

Backed by comments tagged with `<!-- ge:decision -->` on a chosen issue
or PR. `append(summary, rationale=..., metadata=...)` posts a structured
comment; iteration filters and yields them in chronological order.

### `TriageBacklog` — `MutableMapping[issue_ref, TriageEntry]`

Cross-repo backlog. Keys are `"owner/repo#N"`; values include a
`TriageVerdict` (`stale | closeable | fixable | blocked`), an integer
`order`, and a `rationale`. Backed by a JSON block in a *tracking issue*
body (between `<!-- ge:triage:begin -->` / `end`). Fully-qualified refs
do the cross-repo work.

Why a JSON block instead of a GitHub Project? The Project API adds
GraphQL complexity and an extra OAuth scope (`project`); the JSON-block
backing covers the same semantics with `gh api` only. Swapping in a
Project backend later is a swap of this class's two I/O methods — the
public interface stays the same.

## The runner

```bash
ge run-roadmap owner/repo <ROADMAP_ISSUE> [--mode auto|bypass] [--max-sessions N]
ge run-triage  <TRACKING_REPO> <TRACKING_ISSUE> "owner/a,owner/b" [--phase analyze|execute]
```

The runner:

- Calls `check_requirements()` (`gh` installed, authenticated).
- Builds a self-contained prompt for one work unit, naming the skills
  (`ge-autonomous-execution`, `ge-roadmap-execution` or `ge-cross-repo-triage`)
  and the relevant store coordinates.
- Spawns `claude -p ...` with the chosen `--permission-mode`.
- Inspects the exit:
  - **Clean exit**: continue.
  - **Killed by denial cap** (heuristic on stderr): retry once with a
    fresh context, then escalate.
  - **Other non-zero exit**: escalate immediately, with a decision-log
    entry summarising the failure.
- Repeats until the store reports no more work, or `max_sessions` is
  reached.

## Decision-and-log policy

The `ge-autonomous-execution` skill makes this binding. In short:

- Do not stop to ask questions. Decide, log, proceed.
- Only stop and escalate if an action is destructive **and**
  irreversible **and** no safe alternative exists.
- Prefer the reversible option (draft PR over merged PR; comment over
  close; etc.).
- The PR is the handover — its body carries the *why* for a reviewer.

## When to use which mode

- `--mode auto` (default): Claude Code prompts for destructive tool
  calls. Best for new roadmaps, unfamiliar codebases.
- `--mode bypass` (`--dangerously-skip-permissions`): for trusted,
  well-scoped work where you have explicitly authorised it.
