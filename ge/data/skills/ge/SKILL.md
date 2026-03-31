---
name: ge
description: "Use when asked to work on a GitHub issue, PR, or discussion. Resolves flexible input (URL, folder, number), confirms with the user, prepares context, and guides the workflow."
---

# ge: Work on a GitHub Issue, PR, or Discussion

Use this skill when asked to work on a GitHub issue, PR, or discussion. It handles the full workflow: resolve what the user means, confirm, prepare or load context, check freshness, handle media, and guide implementation.

## Prerequisites

- `ge` package installed (`pip install ge` or `pip install -e /path/to/ge`)
- `gh` CLI installed and authenticated (`gh auth login`)
- `ffmpeg` (optional, for video frame extraction)
- `anthropic` package + `ANTHROPIC_API_KEY` (optional, for AI image descriptions)
- ImageMagick (optional, for clipboard montage via `copy_images_to_clipboard`)

## Workflow

### Step 0: Resolve what the user means

The user can say "work on THIS" where THIS can be any of:

- A GitHub URL: `https://github.com/owner/repo/issues/42`
- A folder with pre-prepared context: `~/.cache/ge/owner/repo/issue_42`
- A bare number: `42` or `#42` (assumes current repo)
- `owner/repo#42` or `owner/repo/42`

Use `ge.resolve_target()` to parse any of these:

```python
import ge
import subprocess

# Get current repo for bare-number resolution
result = subprocess.run(
    ['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'],
    capture_output=True, text=True
)
current_repo = result.stdout.strip()  # e.g. "owner/repo"

# Resolve the user's input
target = ge.resolve_target(USER_INPUT, current_repo=current_repo)
```

The returned dict contains:
- `repo`: `"owner/repo"` (or None)
- `number`: int
- `kind`: `"issue"` | `"pr"` | `"discussion"` | None
- `context_dir`: path to pre-prepared context folder (or None)
- `context_md`: path to the context markdown file (or None)
- `has_prepared_context`: bool
- `source`: how input was resolved (`"url"`, `"folder"`, `"number"`, `"repo_number"`)

### Step 1: Confirm with the user (MANDATORY)

**Before doing any work**, confirm what you resolved. This is not optional.

**If the repo differs from the current working directory's repo**, flag it:

> I resolved your request as **issue #42** in **other/repo**.
> You're currently in **owner/repo** — this is a different repository.
> Should I proceed?

**If resolved normally**, confirm concisely:

> I'll work on **issue #520** in **cosmograph-org/cosmograph**.
> Pre-prepared context found at `~/.cache/ge/.../issue_520/`.
> Shall I proceed?

Or if no pre-prepared context:

> I'll work on **issue #42** in **owner/repo**.
> No pre-prepared context found — I'll fetch and prepare it now.
> Shall I proceed?

**Wait for the user to confirm before continuing.**

### Step 2: Load or prepare context

**If `target['has_prepared_context']` is True:**

Read the existing context markdown file directly:

```python
# target['context_md'] is the path to the markdown file
# Read it with the Read tool
```

Check how fresh it is — the file's `prepared_at` timestamp is in the JSON. If it's more than a day old, mention it: "Context was prepared on DATE. Want me to refresh it?"

**If `target['has_prepared_context']` is False:**

Prepare fresh context:

```python
ctx = ge.prepare(target['repo'], target['number'])
# ctx['output_dir'] has the path to the context files
```

This auto-detects type (issue/PR/discussion), fetches everything, downloads media, runs analysis, and generates image descriptions if `anthropic` is available.

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

The context document includes downloaded images and — when `anthropic` is installed and `ANTHROPIC_API_KEY` is set — **AI-generated image descriptions** under the "Image Descriptions (AI-generated)" section.

**If image descriptions are present** (check the "Image Descriptions" section in the markdown):
- Read and incorporate the descriptions into your understanding.
- No manual image pasting needed.

**If image descriptions are NOT present** but images were downloaded:

1. **Describe images programmatically** (preferred — if `anthropic` is available):
   ```python
   from ge.media import describe_images
   import glob
   imgs = sorted(glob.glob(target['context_dir'] + '/media/*.png'))
   imgs += sorted(glob.glob(target['context_dir'] + '/media/*/*.jpg'))
   if imgs:
       description = describe_images(*imgs)
       print(description)
   ```
   **Tell the user if this fails** — they need to know you couldn't analyze the visual content.

2. **Create a montage and ask the user to paste** (if ImageMagick is available):
   ```python
   from ge.media import copy_images_to_clipboard
   path = copy_images_to_clipboard(*imgs)
   ```
   Then tell the user: "A montage of N images has been copied to your clipboard. Please paste it here with Cmd+V so I can see the visual context."

3. **Ask the user to paste individual images** (last resort):
   List the specific files and explain why they matter.

**Always tell the user if you had problems accessing or analyzing media files.**

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
| `ge.resolve_target(input, current_repo=...)` | Resolve flexible input to a target dict |
| `ge.prepare(url_or_spec, number)` | Full context preparation (auto-detects type) |
| `ge.prepare_issue(repo, number)` | Prepare issue context |
| `ge.prepare_pr(repo, number)` | Prepare PR context |
| `ge.prepare_discussion(repo, number)` | Prepare discussion context |
| `ge.analyze_issue(repo, number)` | Staleness analysis (JSON, no media) |
| `ge.analyze_pr(repo, number)` | PR review analysis (JSON, no media) |
| `ge.describe_images(*paths)` | Describe images via Claude API (vision) |
| `ge.copy_images_to_clipboard(*paths)` | Create montage + copy to clipboard |
| `ge.process_all_media(markdown, output_dir)` | Download images + extract video frames |

## Key Principles

1. **Always confirm with the user before working.** Show what you resolved and wait for approval.
2. **Use pre-prepared context when available.** Don't re-fetch if `has_prepared_context` is True (unless stale).
3. **Check freshness before coding.** Issues may be stale, already fixed, or deprioritized.
4. **Use image descriptions when available.** Read the "Image Descriptions" section. If missing, generate them with `describe_images()`. Tell the user if you can't analyze images.
5. **Ask the user about ambiguity.** If the analysis shows conflicting signals, discuss with the user.
6. **Use `gh` for all GitHub access.** This ensures private repo access works via the user's existing auth.
