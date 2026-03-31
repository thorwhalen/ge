---
name: ge-context
description: "Use when you need to prepare, read, or refresh full context for a GitHub issue, PR, or discussion — fetching data, downloading media, and writing structured context documents."
---

# ge-context: Prepare Full Context Documents

Use this skill when you need to prepare or refresh a structured context document for a GitHub issue, PR, or discussion. This is the data-preparation layer — for the full "work on an issue" workflow, use the main `ge` skill instead.

## Prerequisites

- `ge` package installed
- `gh` CLI authenticated
- `ffmpeg` (optional, for video frame extraction)
- `anthropic` package + `ANTHROPIC_API_KEY` (optional, for AI image descriptions)
- ImageMagick (optional, for clipboard montage via `copy_images_to_clipboard`)

## Preparing Context

### Auto-detect from URL

```python
import ge

ctx = ge.prepare('https://github.com/owner/repo/issues/42')
# Also works with PR and discussion URLs
```

### Explicit type

```python
ctx = ge.prepare_issue('owner/repo', 42)
ctx = ge.prepare_pr('owner/repo', 7, include_diff=True)
ctx = ge.prepare_discussion('owner/repo', 5)
```

### Parameters

All `prepare_*` functions accept:
- `output_dir` (str, default `None`) — Where to write context files. Defaults to `~/.cache/ge/<owner>/<repo>/<kind>_<number>/`
- `download_media_flag` (bool, default `True`) — Whether to download images/videos
- `describe_media` (bool, default `True`) — Whether to describe images via Claude API. Requires `anthropic` package and `ANTHROPIC_API_KEY`. Fails silently if unavailable.

`prepare_pr` additionally accepts:
- `include_diff` (bool, default `True`) — Whether to include the full diff

## Output Files

After calling `prepare_*`, two files are written to the output directory (returned in `ctx['output_dir']`):

| File | Format | Contents |
|------|--------|----------|
| `issue_42_context.md` | Markdown | Human/agent-readable context document |
| `issue_42_context.json` | JSON | Structured data for programmatic access |

The naming pattern is `{kind}_{number}_context.{ext}` where kind is `issue`, `pr`, or `discussion`.

Media files are saved to a `media/` subdirectory. File types are auto-detected from content (magic bytes), and correct extensions are added (`.png`, `.jpg`, `.mp4`, etc.). Videos get a directory named after their UUID for extracted frames:

```
media/
├── <uuid>.png              ← image (with correct extension)
├── <uuid>.mp4              ← video source
└── <uuid>/                 ← video frames directory
    ├── scene_001.jpg
    └── scene_002.jpg
```

## Context Document Structure

The markdown context document contains these sections:

1. **Header** — Title, state, author, dates
2. **Body** — Issue/PR description with media paths rewritten to local files
3. **Comments** — All comments in chronological order
4. **Reviews** (PRs only) — Review comments and verdicts
5. **Diff** (PRs only) — Full diff if `include_diff=True`
6. **Analysis** — Freshness assessment, signals, recommendation
7. **Media Files** — Manifest of downloaded images and extracted video frames
8. **Image Descriptions** — AI-generated descriptions of all visual files (when available)

## Return Value

The `prepare_*` functions return a dict containing:

```python
{
    'kind': 'issue',           # or 'pr', 'discussion'
    'number': 42,
    'title': 'Bug in auth flow',
    'body': '...',             # With local media paths
    'comments': [...],
    'analysis': {
        'recommendation': 'proceed',
        'signals': [...],
        ...
    },
    'media': {
        'images': [...],
        'video_frames': {...},
        'all_visual_files': [...],
        'manifest': [...],
        'image_descriptions': '...',  # AI-generated (or None)
    },
    'context_md': '...',       # The rendered markdown
}
```

## Image Analysis Tools

Beyond automatic descriptions during `prepare_*`, two standalone tools are available:

### Describe images (Claude API)

```python
from ge.media import describe_images

# Describe one or more images
text = describe_images('screenshot.png', 'error.jpg')
text = describe_images('frame1.jpg', 'frame2.jpg',
                       prompt="What changed between these frames?")
```

### Copy images to clipboard (montage)

```python
from ge.media import copy_images_to_clipboard

# Create montage and copy to clipboard for pasting into Claude Code
path = copy_images_to_clipboard('img1.png', 'img2.png', 'img3.png')
# Then Cmd+V in Claude Code
```

## Refreshing Context

To refresh context (e.g., after new comments), simply call `prepare_*` again — it overwrites the existing files.

## Standalone Media Processing

To download media from any markdown text (not just GitHub context):

```python
from ge.media import process_all_media

result = process_all_media(markdown_text, output_dir='/tmp/my_media')
# Returns: {'images': [...], 'video_frames': {...}, 'manifest': [...], 'rewritten_markdown': '...'}
```
