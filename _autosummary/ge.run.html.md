# ge.run

Autonomous-execution runner — Layer 3.

Launches `claude` in headless mode in a loop, one invocation per work
unit. State persists between iterations *only* through GitHub-backed
memory ([`ge.memory`](ge.memory.html.md#module-ge.memory)); each session starts with a fresh context
window and rehydrates from the roadmap / triage backlog.

Two entry points:

- [`run_roadmap()`](#ge.run.run_roadmap) — drive a roadmap issue end to end.
- [`run_triage()`](#ge.run.run_triage)  — drive a cross-repo triage backlog (Phase A or B).

The permission-mode choice (`auto` vs `bypass`) lives here because
SKILL.md files cannot set `--permission-mode` — that is a launch-time
flag on `claude`.

What a spawned session can see is decided here too ([`SessionScope`](#ge.run.SessionScope)):
the cwd picks which `CLAUDE.md` files load (the cwd’s and its ancestors’), an
`--add-dir` contributes its skills but never its `CLAUDE.md`, and each one
widens the skill listing toward the budget past which descriptions are dropped
silently. So the runner warns when the cwd is outside every package checkout,
adds directories only when asked, puts any add-dir’s `CLAUDE.md` and the requested routing
documents into the prompt as the first Read, names the skills to load, and
returns the scope with the run so a later diagnosis can see it.

Token / context exhaustion is *not* a failure: it ends the current
session; the loop’s next iteration just rehydrates and continues. A
session terminated by the permission-denial cap *is* a failure: the
runner retries once and then escalates.

### Functions

| [`package_root`](#ge.run.package_root)([path])                              | The git checkout holding *path* (default: the current directory), or `None`.   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`run_roadmap`](#ge.run.run_roadmap)(repo, roadmap_issue, \*[, mode, ...]) | Drive a roadmap issue to completion.                                           |
| [`run_triage`](#ge.run.run_triage)(repos, \*, tracking_repo, ...[, ...])  | Drive a cross-repo triage backlog.                                             |

### Classes

| [`SessionResult`](#ge.run.SessionResult)(iteration, returncode, stdout, ...)   | Outcome of a single `claude` invocation.                          |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`SessionScope`](#ge.run.SessionScope)(cwd[, add_dirs, read_first, ...])      | What one spawned `claude` session can see, decided by the runner. |

### *class* ge.run.SessionResult(iteration, returncode, stdout, stderr, duration_sec)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of a single `claude` invocation.

#### *property* killed_by_denial_cap *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

did Claude Code terminate due to the denial cap?

* **Type:**
  Heuristic

### *class* ge.run.SessionScope(cwd, add_dirs=(), read_first=(), skills=(), model=None, effort=None, warnings=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one spawned `claude` session can see, decided by the runner.

- `cwd`: where the session starts, so whose `CLAUDE.md` loads.
- `add_dirs`: further directories the run must *edit*, passed as
  `--add-dir`. Each one adds its skills to the listing; none adds its
  `CLAUDE.md`, which is why those become first Reads.
- `read_first`: routing documents the prompt tells the session to Read
  before anything else (absolute paths).
- `skills`: skills to load by name, beyond the runner’s own. A skill named
  in the prompt is invocable even when the listing shows it name-only.
- `model` / `effort`: `claude --model` / `--effort`, when set.
- `warnings`: why this scope may not load the work’s instructions.

```pycon
>>> scope = SessionScope(cwd=Path("/w/pkg"), add_dirs=(Path("/w/lib"),), model="opus")
>>> scope.cli_args()
('--add-dir', '/w/lib', '--model', 'opus')
```

#### as_dict()

JSON-ready, for the run’s result and its decision log.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### *classmethod* build(, cwd=None, add_dirs=(), read_first=(), skills=(), model=None, effort=None)

A scope from loose arguments, checked before anything is spawned.

`cwd` defaults to the current directory. Directories must exist; relative
add-dirs resolve against the current directory, relative `read_first`
paths against the scope’s cwd (both become absolute). Every add-dir’s
instruction file is added to `read_first`. A cwd outside every git
checkout is kept, with a warning (`OUTSIDE_A_CHECKOUT`).

* **Return type:**
  [`SessionScope`](#ge.run.SessionScope)

#### cli_args()

The `claude` flags this scope adds (after `-p` and the permission flags).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

#### prompt_preamble()

The lines that open the prompt: the first Reads, then the skills to load.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### ge.run.package_root(path=None)

The git checkout holding *path* (default: the current directory), or `None`.

A session’s `CLAUDE.md` comes from its cwd and the cwd’s ancestors, so any
directory inside a package checkout loads the package’s instructions (and a
subdirectory adds its own). A directory outside every checkout, such as a
projects root or a scratch folder, loads none of the work’s.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### ge.run.run_roadmap(repo, roadmap_issue, , mode='auto', decisions_target=None, max_sessions=50, cwd=None, add_dirs=(), read_first=(), skills=(), model=None, effort=None, on_session=None)

Drive a roadmap issue to completion.

Each iteration is one headless `claude` invocation that performs
exactly one roadmap step. The loop terminates when:

- no todo tasks remain (`status='completed'`),
- two consecutive sessions hit the denial cap (`status='escalated_denial_cap'`),
- a session exits non-zero for another reason (`status='escalated_error'`),
- or `max_sessions` is reached.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"owner/repo"` containing the roadmap issue.
  * **roadmap_issue** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – the roadmap issue number.
  * **mode** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"auto"` (default) or `"bypass"`.
  * **decisions_target** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – issue/PR number to log decisions on. Defaults
    to `roadmap_issue`.
  * **max_sessions** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – safety ceiling on total iterations.
  * **cwd** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – where the spawned `claude` starts, so whose `CLAUDE.md` it
    loads. Defaults to the current directory. A cwd outside every git
    checkout (a projects root, a scratch folder) loads no package’s
    instructions: it is kept, and named in the scope’s `warnings`.
  * **add_dirs** ([`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – directories the run must edit besides `cwd` (`--add-dir`);
    their `CLAUDE.md` files become first Reads, since an add-dir’s
    never loads.
  * **read_first** ([`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – routing documents the session must Read first.
  * **skills** ([`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – skills to load by name, beyond `ge-autonomous-execution` and
    `ge-roadmap-execution`.
  * **model** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – `claude --model` / `--effort`.
  * **effort** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – `claude --model` / `--effort`.
  * **on_session** – optional callable invoked with each [`SessionResult`](#ge.run.SessionResult).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

The result carries `scope` ([`SessionScope.as_dict()`](#ge.run.SessionScope.as_dict)), so a later
diagnosis can see what the sessions could see.

### ge.run.run_triage(repos, , tracking_repo, tracking_issue, phase='analyze', mode='auto', max_sessions=50, cwd=None, add_dirs=(), read_first=(), skills=(), model=None, effort=None, on_session=None)

Drive a cross-repo triage backlog.

`phase='analyze'` runs Phase A (classify + order); a single
iteration is normally enough. `phase='execute'` runs Phase B
(one fix-and-PR per iteration); the loop terminates when no
unactioned `fixable` entries remain.

The triage backlog lives in `tracking_repo#tracking_issue` (see
[`ge.memory.TriageBacklog`](ge.memory.html.md#ge.memory.TriageBacklog)). `cwd`, `add_dirs`, `read_first`,
`skills`, `model` and `effort` scope each spawned session, as for
[`run_roadmap()`](#ge.run.run_roadmap); the result carries `scope`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
