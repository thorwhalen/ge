# ge — GitHub Engineering for AI Agents

Prepare rich context from GitHub issues and PRs so AI coding agents can work on them intelligently.

```bash
pip install ge
ge prepare owner/repo 42
# → .ge/issue_42_context.md  (full context document)
# → .ge/media/               (downloaded screenshots & video frames)
```

## What it does

`ge` fetches an issue or PR and assembles **everything** an agent needs:

- **Issue/PR body and all comments** — with media URLs rewritten to local paths
- **Images downloaded** — screenshots, mockups, error captures
- **Video frames extracted** — via ffmpeg scene detection, capturing actual visual changes
- **Freshness analysis** — is this issue stale? already fixed? has related merged PRs?
- **Cross-references** — commits and PRs that mention this issue
- **Code file checks** — do the files mentioned in the issue still exist?

All via `gh` CLI, so private repos just work.

## Quick start

```bash
# Install
pip install ge

# Prepare context for an issue
ge prepare owner/repo 42

# Or from a URL
ge prepare https://github.com/owner/repo/pull/7

# Just check freshness (no download)
ge analyze-issue owner/repo 42
```

## For Claude Code users

Copy `SKILL.md` into your project's `.claude/skills/` directory (or point Claude Code to it). The skill teaches the agent to:

1. Run `ge prepare` before working on any issue
2. Check the freshness analysis and ask you before working on stale/resolved issues
3. Request you paste images when visual context matters
4. Use the full context document as its working knowledge

## Requirements

- **`gh` CLI** — installed and authenticated (`gh auth login`)
- **`ffmpeg`** — optional, for video frame extraction
- **Python 3.10+**

## Commands

```
ge prepare <repo> <N>              Full context (auto-detects issue/PR/discussion)
ge prepare-discussion <repo> <N>   Full context for a GitHub Discussion
ge analyze-issue <repo> <N>        Freshness analysis (JSON, no download)
ge analyze-pr <repo> <N>           PR review analysis with CI status (JSON)
ge fetch-issue <repo> <N>          Raw issue JSON
ge fetch-pr <repo> <N>             Raw PR JSON
ge fetch-discussion <repo> <N>     GitHub Discussion JSON
ge media <file.md>                 Download media from markdown
ge video-frames <video>            Extract frames (scene detection by default)
```

## Project structure

```
ge/
├── __init__.py      # Facade: prepare(), prepare_issue(), prepare_pr()
├── __main__.py      # CLI via argh (SSOT: _cli_commands list)
├── github.py        # GitHub API via `gh` CLI subprocess
├── media.py         # Image download + video frame extraction (ffmpeg)
├── analysis.py      # Staleness/freshness/relevance analysis
├── context.py       # Assembles everything into context docs
└── util.py          # Internal helpers: gh wrapper, URL parsing, media extraction
SKILL.md             # Claude Code skill instructions
pyproject.toml
README.md
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
```
