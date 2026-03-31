# ge — GitHub Engineering for AI Agents

Tools and skills that let AI coding agents work on GitHub issues, PRs, and discussions intelligently.

```bash
pip install ge
ge install-skills   # register skills with Claude Code
```

Now, from any project, tell your AI agent "work on THIS" — where THIS can be:

- **A GitHub URL:** `work on https://github.com/owner/repo/issues/42`
- **A bare number:** `work on issue #42` (assumes the current repo)
- **A repo+number:** `work on owner/repo#42`
- **A pre-prepared context folder:** `work on ~/.cache/ge/owner/repo/issue_42`

The agent resolves whatever you give it, **confirms** what it understood before proceeding, loads or prepares full context (body, comments, media, freshness analysis, AI image descriptions), and works on the issue.

## Install skills for Claude Code

`ge` ships Claude Code skills that teach the agent how to work on GitHub issues. After installing the package, register the skills globally:

```bash
ge install-skills
```

This creates symlinks in `~/.claude/skills/` pointing to the skills bundled with `ge`. From then on, when you ask Claude Code to work on a GitHub issue in any project, it will automatically:

1. **Resolve** your input — URL, number, folder path, `owner/repo#N` — into a target
2. **Confirm** with you what it resolved before doing any work
3. **Load or prepare** full context (body, comments, media, cross-references)
4. **Analyze freshness** — is it stale? already fixed? has related merged PRs?
5. **Describe images** via the Claude API (or ask you to paste them as fallback)
6. **Ask you** before working on ambiguous or likely-resolved issues

Three skills are installed:

| Skill | Purpose |
|-------|---------|
| `ge` | Full workflow — verify, prepare, analyze, work |
| `ge-analyze` | Quick triage — check if an issue is worth working on |
| `ge-context` | Context preparation — fetch and assemble structured documents |

To remove the skills: `ge uninstall-skills`

## What it does

`ge` fetches an issue or PR and assembles **everything** an agent needs:

- **Issue/PR body and all comments** — with media URLs rewritten to local paths
- **Images downloaded** — screenshots, mockups, error captures (with auto-detected extensions)
- **Video frames extracted** — via ffmpeg scene detection; bare GitHub asset URLs are auto-detected as video/image from content
- **Freshness analysis** — is this issue stale? already fixed? has related merged PRs?
- **Cross-references** — commits and PRs that mention this issue
- **Code file checks** — do the files mentioned in the issue still exist?
- **AI image descriptions** — images are automatically described via the Claude API, so the agent understands visual bugs and UI screenshots without manual pasting

All via `gh` CLI, so private repos just work.

## Quick start

```bash
# Install
pip install ge

# Prepare context for an issue
ge prepare owner/repo --number 42

# Or from a URL
ge prepare https://github.com/owner/repo/pull/7

# Just check freshness (no download)
ge analyze-issue owner/repo 42
```

## Requirements

- **`gh` CLI** — installed and authenticated (`gh auth login`)
- **`ffmpeg`** — optional, for video frame extraction
- **`anthropic`** — optional, for AI-powered image descriptions (`pip install anthropic` + set `ANTHROPIC_API_KEY`)
- **ImageMagick** — optional, for clipboard montage (`brew install imagemagick` on macOS)
- **Python 3.10+**

## Commands

```
ge prepare <repo> --number <N>              Full context (auto-detects issue/PR/discussion)
ge prepare <url>                           Full context from a GitHub URL
ge prepare-discussion <repo> --number <N>  Full context for a GitHub Discussion
ge analyze-issue <repo> <N>                Freshness analysis (JSON, no download)
ge analyze-pr <repo> <N>                   PR review analysis with CI status (JSON)
ge fetch-issue <repo> <N>                  Raw issue JSON
ge fetch-pr <repo> <N>                     Raw PR JSON
ge fetch-discussion <repo> <N>             GitHub Discussion JSON
ge media <file.md>                 Download media from markdown
ge video-frames <video>            Extract frames (scene detection by default)
ge describe-images <img>...        Describe images via Claude API (vision)
ge copy-images <img>...            Create montage + copy to clipboard (macOS)
ge resolve <target>                Resolve a URL, folder, or number to structured target
ge install-skills                  Register skills with Claude Code (~/.claude/skills/)
ge uninstall-skills                Remove ge skill symlinks
```

## Project structure

```
ge/
├── __init__.py      # Facade: prepare(), install_skills(), etc.
├── __main__.py      # CLI via argh (SSOT: _cli_commands list)
├── github.py        # GitHub API via `gh` CLI subprocess
├── media.py         # Image download + video frame extraction (ffmpeg)
├── analysis.py      # Staleness/freshness/relevance analysis
├── context.py       # Assembles everything into context docs
├── util.py          # Internal helpers: gh wrapper, URL parsing, media extraction
└── data/skills/     # Claude Code skills (symlinked by install-skills)
    ├── ge/          # Full workflow skill
    ├── ge-analyze/  # Triage/staleness skill
    └── ge-context/  # Context preparation skill
```

## Python API

```python
import ge

ctx = ge.prepare_issue('owner/repo', 42)
ctx = ge.prepare_pr('owner/repo', 7)
ctx = ge.prepare_discussion('owner/repo', 5)

# Or from any GitHub URL (auto-detects type)
ctx = ge.prepare('https://github.com/owner/repo/issues/42')
ctx = ge.prepare('https://github.com/owner/repo/discussions/5')

# Just analysis
analysis = ge.analyze_issue('owner/repo', 42)

# Resolve flexible input (URL, folder, number, owner/repo#N)
target = ge.resolve_target('#42', current_repo='owner/repo')
# Returns: {repo, number, kind, context_dir, context_md, has_prepared_context, source}
```

## Image analysis

When `ge prepare` runs, it downloads images and — if `anthropic` is installed — automatically sends them to the Claude API for visual analysis. The resulting descriptions are embedded in the context document under "Image Descriptions (AI-generated)", so the agent understands screenshots and visual bugs without manual image pasting.

To set up:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

Image descriptions are generated automatically during `ge prepare`. To disable them:

```bash
ge prepare owner/repo --number 42 -d
```

### Standalone image tools

```bash
# Describe images via Claude API
ge describe-images screenshot.png error.jpg

# Describe with a custom prompt
ge describe-images frame1.jpg frame2.jpg --prompt "What changed between these frames?"

# Create montage + copy to clipboard for pasting into Claude Code (macOS, requires ImageMagick)
ge copy-images screenshot1.png screenshot2.png
# Then Cmd+V in Claude Code
```

Python API:

```python
from ge.media import describe_images, copy_images_to_clipboard

# Get text description of images
text = describe_images('screenshot.png', 'error.jpg')

# Create montage, copy to clipboard
path = copy_images_to_clipboard('img1.png', 'img2.png')
```
