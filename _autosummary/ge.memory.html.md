# ge.memory

GitHub-backed durable memory for autonomous agent execution.

Three stores exposed as `collections.abc` facades. GitHub is the single
source of truth; a thin per-store local snapshot under `.ge/cache/` is a
hydrate-only cache (disposable, never authoritative).

- [`RoadmapStore`](#ge.memory.RoadmapStore) — `MutableMapping[task_id, TaskRecord]` over a
  *roadmap issue* whose body holds a markdown task list between
  `<!-- ge:roadmap:begin -->` / `<!-- ge:roadmap:end -->` markers.
- [`DecisionLog`](#ge.memory.DecisionLog) — append-only `Iterable[Decision]` backed by
  decision-tagged comments on an issue or PR.
- [`TriageBacklog`](#ge.memory.TriageBacklog) — `MutableMapping[issue_ref, TriageVerdict]`
  spanning multiple repos. Backed by a tracking issue containing a fenced
  JSON block (`<!-- ge:triage:begin -->` / `end`). Cross-repo refs use
  `"owner/repo#N"`.

The [`github_memory()`](#ge.memory.github_memory) factory bundles these into a mall.

## Design notes

- Writes go to GitHub *first*; the local cache is updated as a side-effect on
  successful round-trip. A failed write does **not** poison the cache.
- `check_requirements` verifies `gh` is installed, authenticated, and
  carries the `project` scope (needed if the user later switches the
  triage backend to a GitHub Project).

### Functions

| [`github_memory`](#ge.memory.github_memory)(repo, \*[, roadmap_issue, ...])   | Bundle the three stores into a "mall" dict keyed by name.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`check_requirements`](#ge.memory.check_requirements)(\*[, require_project_scope]) | Verify external prerequisites for the memory layer.         |

### Classes

| [`TaskState`](#ge.memory.TaskState)(\*values)                               | Roadmap task lifecycle state.                                                              |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`TaskRecord`](#ge.memory.TaskRecord)(id, title[, state, metadata])          | A single roadmap task.                                                                     |
| [`TriageVerdict`](#ge.memory.TriageVerdict)(\*values)                           | Triage classification for an issue.                                                        |
| [`TriageEntry`](#ge.memory.TriageEntry)(ref, verdict[, order, ...])           | A cross-repo triage backlog entry.                                                         |
| [`Decision`](#ge.memory.Decision)(summary[, rationale, metadata, ...])     | A logged decision (rendered as a tagged comment on an issue/PR).                           |
| [`RoadmapStore`](#ge.memory.RoadmapStore)(repo, issue_number, \*[, cache_dir]) | A `MutableMapping[task_id, TaskRecord]` over a roadmap issue.                              |
| [`DecisionLog`](#ge.memory.DecisionLog)(repo, target_number, \*[, cache_dir]) | Append-only iterable of [`Decision`](#ge.memory.Decision) records. |
| [`TriageBacklog`](#ge.memory.TriageBacklog)(repo, tracking_issue, \*[, ...])    | Cross-repo triage backlog.                                                                 |

### *class* ge.memory.Decision(summary, rationale='', metadata=<factory>, created_at=None, url=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A logged decision (rendered as a tagged comment on an issue/PR).

### *class* ge.memory.DecisionLog(repo, target_number, , cache_dir=None)

Bases: [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)

Append-only iterable of [`Decision`](#ge.memory.Decision) records.

Backed by issue/PR comments tagged with `<!-- ge:decision -->` on a
single target (issue or PR). Iteration fetches all comments from
GitHub, filters by tag, and yields parsed decisions in chronological
order.

Significant choices and course-corrections should be appended here so
they survive into future sessions. Micro-decisions belong in local
scratch and should be summarised at handover.

#### append(summary, , rationale='', metadata=None)

Post a tagged comment recording this decision.

Returns the [`Decision`](#ge.memory.Decision) (with `url` and `created_at`
populated from the GitHub response on success).

* **Return type:**
  [`Decision`](#ge.memory.Decision)

### *class* ge.memory.RoadmapStore(repo, issue_number, , cache_dir=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A `MutableMapping[task_id, TaskRecord]` over a roadmap issue.

Iteration yields task ids in roadmap order. Mutations rewrite the
roadmap issue body in place; the local cache is updated on success.

Initialise via [`github_memory()`](#ge.memory.github_memory) or directly with `(repo, issue)`.
The roadmap issue body should contain (or will be augmented with) a
block:

```default
<!-- ge:roadmap:begin -->
- [ ] Task one
- [x] Task two
<!-- ge:roadmap:end -->
```

Tasks outside the block are ignored.

#### append(title, , state=TaskState.todo)

Add a new task to the end of the roadmap.

* **Return type:**
  [`TaskRecord`](#ge.memory.TaskRecord)

#### hydrate()

Refresh the local cache from GitHub and return the current task list.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TaskRecord`](#ge.memory.TaskRecord)]

#### next_todo()

Return the first `todo` task in roadmap order, or None.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`TaskRecord`](#ge.memory.TaskRecord)]

### *class* ge.memory.TaskRecord(id, title, state=TaskState.todo, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single roadmap task.

`id` is a stable slug derived from the title. `metadata` holds any
extra agent-attached fields (e.g. links to PRs).

### *class* ge.memory.TaskState(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

Roadmap task lifecycle state.

### *class* ge.memory.TriageBacklog(repo, tracking_issue, , cache_dir=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

Cross-repo triage backlog.

Keys are issue refs of the form `"owner/repo#N"`; values are
[`TriageEntry`](#ge.memory.TriageEntry). Iteration order is the agent-chosen resolution
order (the `order` field).

Backed by a *tracking issue* whose body holds a JSON block between
`<!-- ge:triage:begin -->` / `end`. This keeps the implementation
free of GraphQL/Project dependencies while preserving full cross-repo
semantics — fully-qualified refs do the heavy lifting.

Switching to a GitHub Project backend later is a swap of this class’s
I/O methods; the public interface stays the same.

### *class* ge.memory.TriageEntry(ref, verdict, order=0, rationale='', metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A cross-repo triage backlog entry.

### *class* ge.memory.TriageVerdict(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

Triage classification for an issue.

### ge.memory.check_requirements(, require_project_scope=False)

Verify external prerequisites for the memory layer.

Returns a dict `{"ok": bool, "gh": ..., "auth": ..., "scopes": [...],
"missing": [...]}`. Raises `EnvironmentError` with actionable
install instructions if a hard requirement is missing.

Set `require_project_scope=True` if you plan to swap the triage
backend to a GitHub Project.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### ge.memory.github_memory(repo, , roadmap_issue=None, decisions_target=None, triage_issue=None, cache_dir=None)

Bundle the three stores into a “mall” dict keyed by name.

Each store is only constructed if its target was provided. `roadmap`
requires `roadmap_issue`; `decisions` requires `decisions_target`
(the issue or PR number where decisions are logged); `triage`
requires `triage_issue` (the tracking issue holding the JSON block).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`object`](https://docs.python.org/3/builtins/functions.html#object)]

```pycon
>>> # mall = github_memory('owner/repo', roadmap_issue=1, decisions_target=1)
```
