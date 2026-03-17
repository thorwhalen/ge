# ge: GitHub Engineering Skill

Use this skill when asked to work on a GitHub issue, PR, or discussion. It provides CLI tools that fetch full context, download media, and analyze staleness — so you can make informed decisions before writing code.

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth login`)
- `ffmpeg` (optional, for video frame extraction)
- `ge` package installed: `pip install -e /path/to/ge`

## Workflow: Working on an Issue

### Step 1: Prepare the context

```bash
python -m ge prepare <owner/repo> <number>
# or from a URL:
python -m ge prepare https://github.com/owner/repo/issues/42
```

This creates `.ge/issue_<N>_context.md` and `.ge/issue_<N>_context.json`.

### Step 2: Read the context document

```bash
cat .ge/issue_<N>_context.md
```

This contains the issue body (with local media paths), all comments, freshness analysis, related PRs/commits, and a media manifest.

### Step 3: Check the recommendation

The analysis section has a `recommendation` field:
- `proceed` → Issue looks active and unresolved. Go ahead.
- `investigate` → Signals suggest it may be partially or fully resolved. Check with the user before doing work.
- `likely_resolved` → Issue is closed or has strong resolution signals. Confirm with the user.

**IMPORTANT: If recommendation is NOT `proceed`, ask the user before doing work.** Explain what you found (related merged PRs, closing comments, status labels) and ask whether they still want you to work on it.

### Step 4: Handle media / images

The context document lists downloaded images and video frames under "Media Files". 

**Current limitation:** You cannot read image files directly from disk. If the issue contains important screenshots, error captures, or UI mockups:

1. Tell the user: "This issue has N image(s) that may contain important visual context. They've been downloaded to `.ge/media/`. Please paste them into our conversation so I can analyze them."
2. List the specific files so the user knows which to paste.
3. If the user pastes images, analyze them and incorporate what you see into your understanding of the issue.
4. If the user declines, work from the textual context — the alt text and surrounding markdown may still be informative.

For **videos**: frames have been extracted to `_frames/` subdirectories. The same paste workflow applies, but you can suggest the user paste just the key frames (e.g., "frame 0 and frame 4 would show me the before/after states").

### Step 5: Check referenced code

If the issue mentions specific files, check whether they still exist and whether the referenced code has changed:

```bash
# The analysis includes referenced_files — check them on the current branch
git log --oneline -5 -- <referenced_file>
cat <referenced_file>  # or relevant sections
```

### Step 6: Work on the issue

Now you have full context. Create a branch, make changes, and submit a PR as usual. Reference the issue number in your commits.

---

## Workflow: Working on a PR

### Step 1: Prepare the context

```bash
python -m ge prepare <owner/repo> <pr_number>
# or:
python -m ge prepare https://github.com/owner/repo/pull/7
```

### Step 2: Read and understand

The PR context includes: description, review comments, inline code comments, review states, diff, linked issues, merge readiness, and media.

### Step 3: Check the recommendation

- `proceed` → PR is open and ready for work/review.
- `needs_changes` → Reviewers requested changes. Focus on addressing their feedback.
- `resolve_conflicts` → Merge conflicts exist. Resolve them first.
- `draft_wip` → PR is a draft. May be incomplete.
- `already_merged` / `closed_unmerged` → Confirm with user what they want.

### Step 4: If reviewing

Read the diff carefully. Check inline review comments for existing feedback. Look at linked issues for requirements context.

### Step 5: If making changes

Check out the PR branch and make the requested changes. Address review comments specifically.

---

## Workflow: Quick Analysis (no media download)

If you just need to check whether an issue is worth working on:

```bash
python -m ge analyze-issue <owner/repo> <number>
python -m ge analyze-pr <owner/repo> <number>
```

These return JSON with signals, related PRs/commits, and a recommendation — without downloading media.

---

## Available CLI Commands

| Command | Description |
|---------|-------------|
| `ge prepare <repo> <N>` | Full context preparation (auto-detects issue/PR/discussion) |
| `ge prepare-discussion <repo> <N>` | Full context for a GitHub Discussion |
| `ge analyze-issue <repo> <N>` | Staleness analysis only (JSON) |
| `ge analyze-pr <repo> <N>` | PR review analysis with CI status (JSON) |
| `ge fetch-issue <repo> <N>` | Raw issue data (JSON) |
| `ge fetch-pr <repo> <N>` | Raw PR data (JSON) |
| `ge fetch-discussion <repo> <N>` | GitHub Discussion data (JSON) |
| `ge media <file.md>` | Download media from any markdown file |
| `ge video-frames <video>` | Extract frames (scene detection by default) |

## Key Principles

1. **Always prepare context before working.** Don't rely on memory or assumptions about issue state.
2. **Check freshness before coding.** Issues may be stale, already fixed, or deprioritized.
3. **Ask the user about ambiguity.** If the analysis shows conflicting signals, discuss with the user.
4. **Request image paste when visual context matters.** Don't skip visual bugs just because you can't see the screenshots directly.
5. **Use `gh` for all GitHub access.** This ensures private repo access works via the user's existing auth.
