# ge — GitHub Engineering for AI Agents

Tools and skills that let AI coding agents work on GitHub issues, PRs, and discussions intelligently.

Most GitHub engineering *can* be done from an AI agent console with `gh` and Python. But some tasks — fetching an issue with all its comments, downloading screenshots, extracting video frames, checking if the issue is stale or already fixed — burn tokens every time, with a different improvised solution each time. `ge` crystallizes these into deterministic tools with CLI and Python interfaces. More importantly, it wraps them into **AI skills** that agents can use directly, so you just say "work on issue #42" and the agent knows exactly what to do.

So that's the order here: skills first (the intended interface), then the tools underneath (for when you want direct control).

```bash
pip install ge
ge install-skills   # register skills with Claude Code
```

## Skills — the main interface

`ge` ships Claude Code skills that teach the agent how to work on GitHub issues. After installing the package, register them globally:

```bash
ge install-skills
```

This creates symlinks in `~/.claude/skills/` pointing to the skills bundled with `ge`. From then on, tell your agent "work on THIS" — where THIS can be:

- **A GitHub URL:** `work on https://github.com/owner/repo/issues/42`
- **A bare number:** `work on issue #42` (assumes the current repo)
- **A repo+number:** `work on owner/repo#42`
- **A pre-prepared context folder:** `work on ~/.cache/ge/owner/repo/issue_42`

The agent resolves whatever you give it, **confirms** what it understood before proceeding, then:

1. **Loads or prepares** full context (body, comments, media, cross-references)
2. **Analyzes freshness** — is it stale? already fixed? has related merged PRs?
3. **Describes images** via the Claude API (or asks you to paste them as fallback)
4. **Asks you** before working on ambiguous or likely-resolved issues
5. **Works on the issue** — creates a branch, makes changes, submits a PR

Three skills are installed:

| Skill | Purpose |
|-------|---------|
| `ge` | Full workflow — resolve target, confirm, prepare context, analyze, work |
| `ge-analyze` | Quick triage — check if an issue is worth working on |
| `ge-context` | Context preparation — fetch and assemble structured documents |

To remove the skills: `ge uninstall-skills`

## Tools — what the skills use under the hood

Everything below is what the skills orchestrate automatically. You can use any of it directly via CLI or Python.

### What `ge prepare` does

Fetches an issue or PR and assembles **everything** an agent needs:

- **Issue/PR body and all comments** — with media URLs rewritten to local paths
- **Images downloaded** — screenshots, mockups, error captures (auto-detected from content)
- **Video frames extracted** — via ffmpeg scene detection
- **AI image descriptions** — images described via Claude API, embedded in the context document
- **Freshness analysis** — staleness, related merged PRs, resolution signals
- **Cross-references** — commits and PRs that mention this issue

All via `gh` CLI, so private repos just work.

### Quick start

```bash
ge prepare owner/repo --number 42
ge prepare https://github.com/owner/repo/pull/7
ge analyze-issue owner/repo 42
```

### Requirements

- **`gh` CLI** — installed and authenticated (`gh auth login`)
- **Python 3.10+**
- **`ffmpeg`** — optional, for video frame extraction
- **`anthropic`** — optional, for AI-powered image descriptions (`pip install anthropic` + set `ANTHROPIC_API_KEY`)
- **ImageMagick** — optional, for clipboard montage (`brew install imagemagick` on macOS)

### CLI commands

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

### Python API

```python
import ge

# Prepare full context
ctx = ge.prepare('https://github.com/owner/repo/issues/42')
ctx = ge.prepare_issue('owner/repo', 42)
ctx = ge.prepare_pr('owner/repo', 7)
ctx = ge.prepare_discussion('owner/repo', 5)

# Just analysis (no download)
analysis = ge.analyze_issue('owner/repo', 42)

# Resolve flexible input
target = ge.resolve_target('#42', current_repo='owner/repo')

# Image tools
from ge.media import describe_images, copy_images_to_clipboard
text = describe_images('screenshot.png', 'error.jpg')
path = copy_images_to_clipboard('img1.png', 'img2.png')
```

### Image analysis

When `ge prepare` runs, it downloads images and — if `anthropic` is installed — automatically sends them to the Claude API for visual analysis. The descriptions are embedded in the context document under "Image Descriptions (AI-generated)".

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

To disable: `ge prepare owner/repo --number 42 -d`

Standalone:

```bash
ge describe-images screenshot.png error.jpg
ge describe-images frame1.jpg frame2.jpg --prompt "What changed between these frames?"
ge copy-images screenshot1.png screenshot2.png   # montage + clipboard (macOS)
```

## Project structure

```
ge/
├── __init__.py      # Facade: prepare(), resolve_target(), install_skills(), etc.
├── __main__.py      # CLI via argh (SSOT: _cli_commands list)
├── github.py        # GitHub API via `gh` CLI subprocess
├── media.py         # Image download, video frames, describe_images, clipboard montage
├── analysis.py      # Staleness/freshness/relevance analysis
├── context.py       # Assembles everything into context docs
├── util.py          # Internal helpers: gh wrapper, URL parsing, resolve_target
└── data/skills/     # Claude Code skills (symlinked by install-skills)
    ├── ge/          # Full workflow skill
    ├── ge-analyze/  # Triage/staleness skill
    └── ge-context/  # Context preparation skill
```
