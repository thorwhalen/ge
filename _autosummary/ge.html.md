# ge

ge: GitHub Engineering tools for AI agents.

Reduces boilerplate when working on GitHub issues and PRs with AI coding agents.
Fetches context, downloads media, checks freshness, and assembles everything
into a structured document the agent can consume.

Usage:

```default
import ge

# Prepare full context for an issue
ctx = ge.prepare_issue('owner/repo', 42)

# Prepare full context for a PR
ctx = ge.prepare_pr('owner/repo', 7)

# Or from a full URL
ctx = ge.prepare('https://github.com/owner/repo/issues/42')
```

### Functions

| [`prepare`](#ge.prepare)(url_or_spec[, number, output_dir, ...])    | Prepare context from a GitHub URL or repo+number.                       |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`prepare_issue`](#ge.prepare_issue)(repo, number, \*[, output_dir, ...]) | Prepare full context for working on a GitHub issue.                     |
| [`prepare_pr`](#ge.prepare_pr)(repo, number, \*[, output_dir, ...])    | Prepare full context for working on or reviewing a GitHub PR.           |
| [`prepare_discussion`](#ge.prepare_discussion)(repo, number, \*[, ...])        | Prepare full context for a GitHub Discussion.                           |
| [`analyze_issue`](#ge.analyze_issue)(repo, number)                        | Analyze an issue for staleness and current relevance.                   |
| [`analyze_pr`](#ge.analyze_pr)(repo, number)                           | Analyze a PR for review context and merge readiness.                    |
| [`get_issue`](#ge.get_issue)(repo, number)                            | Fetch a GitHub issue with body, labels, assignees, state, etc.          |
| [`get_pr`](#ge.get_pr)(repo, number)                               | Fetch a GitHub pull request with body, diff stats, merge state, etc.    |
| [`get_comments`](#ge.get_comments)(repo, number)                         | Fetch all comments on an issue or PR.                                   |
| [`get_pr_diff`](#ge.get_pr_diff)(repo, number)                          | Fetch the raw diff of a PR.                                             |
| [`get_discussion`](#ge.get_discussion)(repo, number)                       | Fetch a GitHub Discussion via GraphQL (discussions aren't in REST API). |
| [`find_related_prs`](#ge.find_related_prs)(repo, issue_number)               | Find PRs that reference or close this issue.                            |
| [`find_related_commits`](#ge.find_related_commits)(repo, issue_number, \*)       | Find recent commits that reference this issue number.                   |
| [`process_all_media`](#ge.process_all_media)(markdown[, output_dir])          | Download all media and extract video frames.                            |
| [`extract_video_frames`](#ge.extract_video_frames)(video_path, \*[, ...])        | Extract representative frames from a video file using ffmpeg.           |
| [`describe_images`](#ge.describe_images)(\*image_paths[, prompt, ...])      | Use the Claude API to describe images, returning a text description.    |
| [`copy_images_to_clipboard`](#ge.copy_images_to_clipboard)(\*image_paths[, ...])     | Create a montage of images and copy it to the macOS clipboard.          |
| [`resolve_target`](#ge.resolve_target)(user_input, \*[, current_repo])     | Resolve flexible user input into a structured target for ge workflows.  |
| [`install_skills`](#ge.install_skills)(\*[, target_dir])                   | Symlink ge skills into ~/.claude/skills/ for global discovery.          |
| [`uninstall_skills`](#ge.uninstall_skills)(\*[, target_dir])                 | Remove ge skill symlinks from ~/.claude/skills/.                        |
| [`github_memory`](#ge.github_memory)(repo, \*[, roadmap_issue, ...])      | Bundle the three stores into a "mall" dict keyed by name.               |
| [`check_requirements`](#ge.check_requirements)(\*[, require_project_scope])    | Verify external prerequisites for the memory layer.                     |

### Classes

| [`RoadmapStore`](#ge.RoadmapStore)(repo, issue_number, \*[, cache_dir])   | A `MutableMapping[task_id, TaskRecord]` over a roadmap issue.                              |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`DecisionLog`](#ge.DecisionLog)(repo, target_number, \*[, cache_dir])   | Append-only iterable of [`Decision`](#ge.Decision) records. |
| [`TriageBacklog`](#ge.TriageBacklog)(repo, tracking_issue, \*[, ...])      | Cross-repo triage backlog.                                                                 |
| [`TaskState`](#ge.TaskState)(\*values)                                 | Roadmap task lifecycle state.                                                              |
| [`TaskRecord`](#ge.TaskRecord)(id, title[, state, metadata])            | A single roadmap task.                                                                     |
| [`TriageVerdict`](#ge.TriageVerdict)(\*values)                             | Triage classification for an issue.                                                        |
| [`TriageEntry`](#ge.TriageEntry)(ref, verdict[, order, ...])             | A cross-repo triage backlog entry.                                                         |
| [`Decision`](#ge.Decision)(summary[, rationale, metadata, ...])       | A logged decision (rendered as a tagged comment on an issue/PR).                           |

### *class* ge.Decision(summary, rationale='', metadata=<factory>, created_at=None, url=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A logged decision (rendered as a tagged comment on an issue/PR).

### *class* ge.DecisionLog(repo, target_number, , cache_dir=None)

Bases: [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)

Append-only iterable of [`Decision`](#ge.Decision) records.

Backed by issue/PR comments tagged with `<!-- ge:decision -->` on a
single target (issue or PR). Iteration fetches all comments from
GitHub, filters by tag, and yields parsed decisions in chronological
order.

Significant choices and course-corrections should be appended here so
they survive into future sessions. Micro-decisions belong in local
scratch and should be summarised at handover.

#### append(summary, , rationale='', metadata=None)

Post a tagged comment recording this decision.

Returns the [`Decision`](#ge.Decision) (with `url` and `created_at`
populated from the GitHub response on success).

* **Return type:**
  [`Decision`](ge.memory.html.md#ge.memory.Decision)

### *class* ge.RoadmapStore(repo, issue_number, , cache_dir=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A `MutableMapping[task_id, TaskRecord]` over a roadmap issue.

Iteration yields task ids in roadmap order. Mutations rewrite the
roadmap issue body in place; the local cache is updated on success.

Initialise via [`github_memory()`](#ge.github_memory) or directly with `(repo, issue)`.
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
  [`TaskRecord`](ge.memory.html.md#ge.memory.TaskRecord)

#### hydrate()

Refresh the local cache from GitHub and return the current task list.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TaskRecord`](ge.memory.html.md#ge.memory.TaskRecord)]

#### next_todo()

Return the first `todo` task in roadmap order, or None.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`TaskRecord`](ge.memory.html.md#ge.memory.TaskRecord)]

### *class* ge.TaskRecord(id, title, state=TaskState.todo, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single roadmap task.

`id` is a stable slug derived from the title. `metadata` holds any
extra agent-attached fields (e.g. links to PRs).

### *class* ge.TaskState(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

Roadmap task lifecycle state.

### *class* ge.TriageBacklog(repo, tracking_issue, , cache_dir=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

Cross-repo triage backlog.

Keys are issue refs of the form `"owner/repo#N"`; values are
[`TriageEntry`](#ge.TriageEntry). Iteration order is the agent-chosen resolution
order (the `order` field).

Backed by a *tracking issue* whose body holds a JSON block between
`<!-- ge:triage:begin -->` / `end`. This keeps the implementation
free of GraphQL/Project dependencies while preserving full cross-repo
semantics — fully-qualified refs do the heavy lifting.

Switching to a GitHub Project backend later is a swap of this class’s
I/O methods; the public interface stays the same.

### *class* ge.TriageEntry(ref, verdict, order=0, rationale='', metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A cross-repo triage backlog entry.

### *class* ge.TriageVerdict(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

Triage classification for an issue.

### ge.analyze_issue(repo, number)

Analyze an issue for staleness and current relevance.

Returns a dict with:

> - state: open/closed
> - age_days: days since creation
> - last_activity_days: days since last comment/event
> - labels: list of label names
> - related_prs: PRs that reference this issue
> - related_commits: commits mentioning this issue
> - referenced_files: files mentioned in the issue body
> - signals: list of human-readable observations about freshness
> - recommendation: ‘proceed’, ‘investigate’, or ‘likely_resolved’
```pycon
>>> # analysis = analyze_issue('owner/repo', 42)
```

### ge.analyze_pr(repo, number)

Analyze a PR for review context and merge readiness.

Returns a dict with state, review status, CI signals, conflicts, etc.

```pycon
>>> # analysis = analyze_pr('owner/repo', 7)
```

### ge.check_requirements(, require_project_scope=False)

Verify external prerequisites for the memory layer.

Returns a dict `{"ok": bool, "gh": ..., "auth": ..., "scopes": [...],
"missing": [...]}`. Raises `EnvironmentError` with actionable
install instructions if a hard requirement is missing.

Set `require_project_scope=True` if you plan to swap the triage
backend to a GitHub Project.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### ge.copy_images_to_clipboard(\*image_paths, tile='3x', geometry='800x600+10+10', montage_path=None)

Create a montage of images and copy it to the macOS clipboard.

Combines multiple images into a single grid image using ImageMagick,
then copies it to the clipboard via `osascript` so the user can
paste it into Claude Code with Cmd+V.

* **Parameters:**
  * **\*image_paths** – Paths to image files to combine.
  * **tile** – Montage tile layout (e.g. ‘3x’ for 3 columns).
  * **geometry** – Tile geometry (size+padding).
  * **montage_path** – Where to save the montage file. Defaults to
    `/tmp/ge_montage.png`.
* **Returns:**
  Path to the montage file.
* **Return type:**
  [*str*](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> # path = copy_images_to_clipboard('img1.png', 'img2.png')
```

### ge.describe_images(\*image_paths, prompt='Describe what you see in these images in detail. If they appear to be screenshots of a bug or UI issue, describe the problem visible.', model='claude-sonnet-4-5-20250514', max_tokens=4096)

Use the Claude API to describe images, returning a text description.

Requires the `anthropic` package and a valid `ANTHROPIC_API_KEY`.

* **Parameters:**
  * **\*image_paths** – One or more paths to image files.
  * **prompt** – The text prompt sent alongside the images.
  * **model** – Claude model to use for vision analysis.
  * **max_tokens** – Maximum tokens in the response.
* **Returns:**
  The model’s textual description of the images.
* **Return type:**
  [*str*](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> # description = describe_images('screenshot.png', 'error.jpg')
```

### ge.extract_video_frames(video_path, , n_frames=5, output_dir=None, mode='scene', scene_threshold=0.3)

Extract representative frames from a video file using ffmpeg.

Two modes are available:

- `mode='scene'` (default): Uses ffmpeg’s scene change detection filter
  to extract frames where visual content actually changes. Better for bug
  reproduction videos where you want one frame per distinct UI state.
  `scene_threshold` controls sensitivity (0.0–1.0, lower = more frames).
  Falls back to ‘uniform’ if scene detection yields no frames.
- `mode='uniform'`: Extracts `n_frames` evenly-spaced frames.

Returns list of paths to extracted frame images (JPEG).

```pycon
>>> # frames = extract_video_frames('demo.mp4')
>>> # frames = extract_video_frames('demo.mp4', mode='uniform', n_frames=5)
```

### ge.find_related_commits(repo, issue_number, , limit=20)

Find recent commits that reference this issue number.

```pycon
>>> # commits = find_related_commits('owner/repo', 42)
```

### ge.find_related_prs(repo, issue_number)

Find PRs that reference or close this issue.

Uses the timeline API to find cross-referenced PRs, and also searches
for PRs mentioning the issue number.

```pycon
>>> # prs = find_related_prs('owner/repo', 42)
```

### ge.get_comments(repo, number)

Fetch all comments on an issue or PR.

```pycon
>>> # comments = get_comments('owner/repo', 42)
```

### ge.get_discussion(repo, number)

Fetch a GitHub Discussion via GraphQL (discussions aren’t in REST API).

```pycon
>>> # disc = get_discussion('owner/repo', 5)
```

### ge.get_issue(repo, number)

Fetch a GitHub issue with body, labels, assignees, state, etc.

```pycon
>>> # issue = get_issue('owner/repo', 42)
```

### ge.get_pr(repo, number)

Fetch a GitHub pull request with body, diff stats, merge state, etc.

```pycon
>>> # pr = get_pr('owner/repo', 7)
```

### ge.get_pr_diff(repo, number)

Fetch the raw diff of a PR.

```pycon
>>> # diff = get_pr_diff('owner/repo', 7)
```

### ge.github_memory(repo, , roadmap_issue=None, decisions_target=None, triage_issue=None, cache_dir=None)

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

### ge.install_skills(, target_dir=None)

Symlink ge skills into ~/.claude/skills/ for global discovery.

Creates symlinks from `target_dir/<skill>` to the skill folders bundled
with the ge package.  Existing correct symlinks are left alone; a warning
is printed if a symlink points elsewhere.

* **Parameters:**
  **target_dir** – Destination directory.  Defaults to `~/.claude/skills/`.

### ge.prepare(url_or_spec, number=None, , output_dir=None, describe_media=True, \*\*kwargs)

Prepare context from a GitHub URL or repo+number.

Automatically detects whether it’s an issue, PR, or discussion.

When `describe_media` is True (default) and the `anthropic` package
is available, downloaded images are described via the Claude API so
the agent gets visual context without manual image pasting.

```pycon
>>> # ctx = ge.prepare('https://github.com/owner/repo/issues/42')
>>> # ctx = ge.prepare('owner/repo', 42)
>>> # ctx = ge.prepare('https://github.com/owner/repo/discussions/5')
```

### ge.prepare_discussion(repo, number, , output_dir=None, download_media_flag=True, describe_media=True)

Prepare full context for a GitHub Discussion.

Fetches the discussion and its comments via GraphQL, downloads media,
and writes a context document.

```pycon
>>> # ctx = prepare_discussion('owner/repo', 5)
```

### ge.prepare_issue(repo, number, , output_dir=None, download_media_flag=True, describe_media=True)

Prepare full context for working on a GitHub issue.

Fetches the issue, comments, media, and performs staleness analysis.
Writes a context document and manifest to output_dir.

When `describe_media` is True (default) and the `anthropic` package
is installed with `ANTHROPIC_API_KEY` set, downloaded images are sent
to the Claude API for automated description.  The description is included
in the context document so the agent has visual context without manual
image pasting.

Returns dict with all assembled context.

```pycon
>>> # ctx = prepare_issue('owner/repo', 42)
```

### ge.prepare_pr(repo, number, , output_dir=None, download_media_flag=True, include_diff=True, describe_media=True)

Prepare full context for working on or reviewing a GitHub PR.

```pycon
>>> # ctx = prepare_pr('owner/repo', 7)
```

### ge.process_all_media(markdown, output_dir=None)

Download all media and extract video frames.

Returns a dict with:

> - url_map, manifest, rewritten_markdown (from download_media)
> - video_frames: {video_local_path: [frame_paths]}
> - images: list of local image paths (for user to paste into agent)
> - all_visual_files: combined list of images + video frames
```pycon
>>> # result = process_all_media(issue_body)
```

### ge.resolve_target(user_input, , current_repo=None)

Resolve flexible user input into a structured target for ge workflows.

Accepts any of these forms:

> - A GitHub URL: `https://github.com/owner/repo/issues/42`
> - A folder path to pre-prepared context: `~/.cache/ge/owner/repo/issue_42`
> - A bare number: `42` or `#42` (uses *current_repo*)
> - `owner/repo#42` or `owner/repo/42`
> - `owner/repo 42`

Returns a dict with:

> - `repo`: `"owner/repo"` (or None if only a folder was given)
> - `number`: int
> - `kind`: `"issue"` | `"pr"` | `"discussion"` | None
> - `context_dir`: path to pre-prepared context (str or None)
> - `context_md`: path to the context markdown file (str or None)
> - `has_prepared_context`: bool — whether context files already exist
> - `source`: how the input was resolved (`"url"`, `"folder"`,
>   `"number"`, `"repo_number"`)
```pycon
>>> r = resolve_target('https://github.com/owner/repo/issues/42')
>>> r['repo'], r['number'], r['kind'], r['source']
('owner/repo', 42, 'issue', 'url')
```

```pycon
>>> r = resolve_target('#42', current_repo='owner/repo')
>>> r['repo'], r['number'], r['source']
('owner/repo', 42, 'number')
```

```pycon
>>> r = resolve_target('owner/repo#42')
>>> r['repo'], r['number'], r['source']
('owner/repo', 42, 'repo_number')
```

### ge.uninstall_skills(, target_dir=None)

Remove ge skill symlinks from ~/.claude/skills/.

Only removes symlinks that point back into the ge package’s skill
directory.  Non-symlinks and symlinks owned by other packages are
left untouched.

* **Parameters:**
  **target_dir** – Directory to remove from.  Defaults to `~/.claude/skills/`.

### Modules

| [`analysis`](ge.analysis.html.md#module-ge.analysis)   | Issue and PR analysis: staleness, relevance, and state assessment.   |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`context`](ge.context.html.md#module-ge.context)     | Context assembly and rendering.                                      |
| [`github`](ge.github.html.md#module-ge.github)       | GitHub data fetching via gh CLI.                                     |
| [`media`](ge.media.html.md#module-ge.media)         | Media download and video frame extraction.                           |
| [`memory`](ge.memory.html.md#module-ge.memory)       | GitHub-backed durable memory for autonomous agent execution.         |
| [`run`](ge.run.html.md#module-ge.run)             | Autonomous-execution runner — Layer 3.                               |
| [`util`](ge.util.html.md#module-ge.util)           | Internal utilities: gh CLI wrapper, subprocess helpers, URL parsing. |
