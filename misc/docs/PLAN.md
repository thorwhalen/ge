# ge — Development Plan

This document is for Claude Code (or any AI agent) to understand the project goals, current state, and next steps.

## Project Goal

`ge` (GitHub Engineering) reduces boilerplate when AI coding agents work on GitHub issues and PRs. Instead of the agent manually fetching issue text, it runs `ge prepare` and gets a structured context document with full text, comments, media, cross-references, and freshness analysis.

## Architecture

```
ge/
├── __init__.py      # Facade: prepare(), prepare_issue(), prepare_pr()
├── __main__.py      # CLI via argh (SSOT: _cli_commands list)
├── github.py        # GitHub API via `gh` CLI subprocess
├── media.py         # Image download + video frame extraction (ffmpeg)
├── analysis.py      # Staleness/freshness/relevance analysis
├── context.py       # Assembles everything into context docs
└── util.py          # Internal helpers: gh wrapper, URL parsing, media extraction
tests/
├── test_util.py     # URL parsing, media extraction, rewriting
├── test_analysis.py # Analysis logic with mocked GitHub data
└── test_media.py    # Filename sanitization, download mocking
SKILL.md             # Claude Code skill instructions
pyproject.toml
README.md
misc/docs/
├── PLAN.md          # This file
└── SURVEY_OF_TOOLS_FOR_GE.md  # Survey of related tools & integrations
```

**Design principles:**
- All GitHub access via `gh` CLI (handles auth, works with private repos)
- Functional style with small focused functions
- Progressive disclosure: `ge.prepare(url)` is the simple entry point; individual functions available for advanced use
- CLI mirrors Python API via argh dispatch

## Current State: Working core

The core workflow works:
1. `ge prepare owner/repo --number 42` → fetches issue, comments, downloads media, runs analysis, writes context doc
2. `ge analyze-issue` / `ge analyze-pr` → quick freshness check without media download
3. SKILL.md teaches Claude Code the workflow

## Implementation Plan

The following items should all be implemented now. They are informed by the
[tool survey](./SURVEY_OF_TOOLS_FOR_GE.md) and focus on making ge robust,
tested, and more useful.

### 1. Package setup: restore pyproject.toml

The pyproject.toml was deleted. Restore it with proper `[project.scripts]`
entry point (`ge = "ge.__main__:main"`) and `argh` as a dependency.

### 2. Tests

- **test_util.py**: Unit tests for `parse_repo_spec`, `parse_issue_url`,
  `extract_media_urls`, `rewrite_media_refs`, `_sanitize_filename` (move to
  testable location if needed). These functions have doctests — convert to
  proper pytest cases with edge cases.
- **test_analysis.py**: Test `_extract_file_refs`, `_days_ago` and the
  recommendation logic in `analyze_issue`/`analyze_pr` by mocking the GitHub
  fetchers.
- **test_media.py**: Test `_sanitize_filename` and `download_media` with
  mocked HTTP calls.

### 3. Smarter video frame extraction (from survey §5.2)

Replace evenly-spaced frame extraction with ffmpeg's built-in scene detection
filter (`-vf "select=gt(scene\,0.3)"`). This extracts frames only where the
visual content actually changes — much better for bug reproduction videos.
Zero additional Python dependency; only requires ffmpeg which is already a
prerequisite.

Keep the current evenly-spaced approach as a fallback (`mode='uniform'`) and
make scene detection the default (`mode='scene'`).

### 4. Robustness improvements

- Cache `_check_gh()` result so it's only called once per session (not per API call).
- Handle edge cases: issues with no body, PRs with enormous diffs (>100k chars),
  paginated responses that return mixed types.
- Better error when `gh api` returns HTML instead of JSON (rate limiting / auth issues).

### 5. Analysis enhancements

- **Label-based signals**: Recognize common labels (`good first issue`,
  `help wanted`, `priority:high`, `bug`, `enhancement`) and include them in
  the analysis signals.
- **CI status for PRs**: Use `gh api repos/{owner}/{repo}/commits/{sha}/status`
  to check CI pass/fail and include in PR analysis.

### 6. Discussion support

Wire `get_discussion` into prepare/analyze. Add `prepare_discussion` and
`analyze_discussion` functions, and a `ge prepare` path for discussion URLs.

## Future Work (not implemented now)

These are noted for future reference, informed by the survey.

- **ghapi as optional backend** (survey §1): Replace subprocess+json.loads
  with native Python objects when `ghapi` is installed. Keep `gh` CLI as
  default fallback.
- **Image descriptions** (survey §6): Use a local vision model (moondream,
  ollama+llava) or Anthropic API to auto-describe screenshots and embed
  descriptions in the context document.
- **MCP server interface** (survey §2): Expose `ge` tools via FastMCP for
  agents that support MCP natively.
- **`ge work <url>`**: Higher-level command that prepares context, checks out
  a branch, and opens the context doc.
- **`ge triage <repo>`**: List open issues with freshness scores.
- **Claude Agent SDK orchestration** (survey §3.2): Use the Agent SDK to
  spawn Claude with full context to actually work on issues.
- **Context window awareness**: If context doc exceeds ~50k tokens, produce
  a summary version.

## Notes for Claude Code

When working on this codebase:
- Run `python -m ge prepare <some-public-repo> <issue-number>` to test changes end-to-end
- The `gh` CLI must be authenticated on your system
- All functions have docstrings with `>>>` examples; keep this convention
- Helper functions used only within one function should be inner functions; module-level helpers start with `_`
- Keep the `_cli_commands` list in `__main__.py` as the SSOT for CLI commands
