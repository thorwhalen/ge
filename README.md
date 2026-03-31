# ge — GitHub Engineering for AI Agents

Tools and skills that let AI coding agents work on GitHub issues, PRs, and discussions intelligently.

```bash
pip install ge
ge install-skills   # register skills with Claude Code
```

Now, from any project, tell your AI agent "work on issue #42" — it will prepare full context, check freshness, download media, and proceed with informed decisions.

## Install skills for Claude Code

`ge` ships Claude Code skills that teach the agent how to work on GitHub issues. After installing the package, register the skills globally:

```bash
ge install-skills
```

This creates symlinks in `~/.claude/skills/` pointing to the skills bundled with `ge`. From then on, when you ask Claude Code to work on a GitHub issue in any project, it will automatically:

1. Verify the issue belongs to the current project
2. Fetch the full issue context (body, comments, media, cross-references)
3. Analyze freshness — is it stale? already fixed? has related merged PRs?
4. Ask you before working on ambiguous or likely-resolved issues
5. Request you paste images when visual context matters

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
```
