---
name: ge
description: "Use when asked to work on a GitHub issue, PR, or discussion. Prepares context, verifies the issue belongs to the current project, analyzes freshness, and guides the workflow."
---

# ge: Work on a GitHub Issue, PR, or Discussion

Use this skill when asked to work on a GitHub issue, PR, or discussion. It orchestrates the full workflow: verify the target, prepare context, check freshness, and guide you through implementation.

## Prerequisites

- `ge` package installed (`pip install ge` or `pip install -e /path/to/ge`)
- `gh` CLI installed and authenticated (`gh auth login`)
- `ffmpeg` (optional, for video frame extraction)

## Workflow

### Step 0: Verify the issue belongs to this project

Before doing any work, confirm the target matches the current repository.

```python
import subprocess, json

result = subprocess.run(
    ['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'],
    capture_output=True, text=True
)
current_repo = result.stdout.strip()  # e.g. "owner/repo"
```

- If the user gave just a number (e.g. "work on issue #42"), assume the current repo.
- If the user gave a URL or `owner/repo`, parse it and compare with `current_repo`.
- If they don't match, tell the user: "Issue #42 belongs to `other/repo`, but you're in `owner/repo`. Should I proceed anyway?"

### Step 1: Prepare context

```python
import ge

ctx = ge.prepare('owner/repo', 42)
# or from a URL:
ctx = ge.prepare('https://github.com/owner/repo/issues/42')
```

This auto-detects whether it's an issue, PR, or discussion and:
- Fetches the body, comments, reviews, timeline
- Downloads images and extracts video frames
- Runs freshness/staleness analysis
- Writes context files to `~/.cache/ge/<owner>/<repo>/<kind>_<number>/`

The returned dict includes an `output_dir` key with the actual path used.

### Step 2: Read the context document

Read the context markdown file from `ctx['output_dir']` (e.g. `~/.cache/ge/owner/repo/issue_42/issue_42_context.md`). It contains everything assembled: body, comments, analysis, media manifest.

### Step 3: Check the recommendation

The context includes an analysis with a `recommendation` field:

**For issues:**
- `proceed` — Active and unresolved. Go ahead.
- `investigate` — May be partially resolved. Check with the user before working.
- `likely_resolved` — Closed or strong resolution signals. Confirm with the user.

**For PRs:**
- `proceed` — Open and ready for work/review.
- `needs_changes` — Reviewers requested changes. Address their feedback.
- `resolve_conflicts` — Merge conflicts exist. Resolve first.
- `draft_wip` — PR is a draft. May be incomplete.
- `already_merged` / `closed_unmerged` — Confirm with user.

**IMPORTANT:** If recommendation is NOT `proceed`, explain what you found and ask the user before doing work.

### Step 4: Handle media / images

The context lists downloaded images under "Media Files".

If the issue contains important screenshots, error captures, or UI mockups:

1. Tell the user: "This issue has N image(s) that may contain important visual context. They've been downloaded to `<output_dir>/media/`. Please paste them into our conversation so I can analyze them."
2. List the specific files so the user knows which to paste.
3. If the user pastes images, incorporate what you see into your understanding.
4. If the user declines, work from the textual context.

For **videos**: frames are extracted into a directory named after the video's UUID (e.g., `media/<uuid>/scene_001.jpg`). The source video is also saved (e.g., `media/<uuid>.mp4`). Suggest the user paste key frames.

### Step 5: Check referenced code

If the issue mentions specific files, verify they still exist and check recent changes:

```bash
git log --oneline -5 -- <referenced_file>
```

Then read the relevant sections of those files.

### Step 6: Work on the issue

Now you have full context. Create a branch, make changes, and submit a PR. Reference the issue number in your commits.

## Quick analysis shortcut

If you just need to check whether an issue is worth working on (without preparing full context):

```python
import ge
analysis = ge.analyze_issue('owner/repo', 42)
# or for a PR:
analysis = ge.analyze_pr('owner/repo', 7)
```

For more details on interpreting analysis results, see the `ge-analyze` skill.

## Python API Reference

| Function | Description |
|----------|-------------|
| `ge.prepare(url_or_spec, number)` | Full context preparation (auto-detects type) |
| `ge.prepare_issue(repo, number)` | Prepare issue context |
| `ge.prepare_pr(repo, number)` | Prepare PR context |
| `ge.prepare_discussion(repo, number)` | Prepare discussion context |
| `ge.analyze_issue(repo, number)` | Staleness analysis (JSON, no media) |
| `ge.analyze_pr(repo, number)` | PR review analysis (JSON, no media) |
| `ge.get_issue(repo, number)` | Raw issue data |
| `ge.get_pr(repo, number)` | Raw PR data |
| `ge.get_comments(repo, number)` | Issue/PR comments |
| `ge.get_pr_diff(repo, number)` | PR diff text |
| `ge.get_discussion(repo, number)` | Discussion data (GraphQL) |
| `ge.find_related_prs(repo, number)` | PRs that reference this issue |
| `ge.find_related_commits(repo, number)` | Commits that reference this issue |
| `ge.process_all_media(markdown, output_dir)` | Download images + extract video frames |
| `ge.extract_video_frames(path)` | Extract frames from a video file |

## Key Principles

1. **Always prepare context before working.** Don't rely on memory or assumptions about issue state.
2. **Verify the issue belongs to this project.** Don't work on the wrong repo's issues.
3. **Check freshness before coding.** Issues may be stale, already fixed, or deprioritized.
4. **Ask the user about ambiguity.** If the analysis shows conflicting signals, discuss with the user.
5. **Request image paste when visual context matters.** Don't skip visual bugs just because you can't see screenshots directly.
6. **Use `gh` for all GitHub access.** This ensures private repo access works via the user's existing auth.
