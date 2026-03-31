# ge — Development Guide

## What this is

`ge` (GitHub Engineering) provides tools and Claude Code skills for working on GitHub issues, PRs, and discussions. The tools have both CLI and Python interfaces. The skills wrap those tools for use by AI agents.

## Architecture

- **`ge/util.py`** — Internal helpers: `gh` CLI wrapper, URL parsing, media extraction, `resolve_target()`
- **`ge/github.py`** — All GitHub API access via `gh` subprocess (never direct HTTP)
- **`ge/media.py`** — Image download, video frame extraction (ffmpeg), `describe_images()` (Claude API), `copy_images_to_clipboard()` (ImageMagick)
- **`ge/analysis.py`** — Freshness/staleness heuristics, recommendations
- **`ge/context.py`** — Orchestrates everything into structured context documents (markdown + JSON)
- **`ge/__init__.py`** — Public facade (`prepare()`, `resolve_target()`, etc.)
- **`ge/__main__.py`** — CLI via argh. SSOT: `_cli_commands` list
- **`ge/data/skills/`** — Claude Code skills (symlinked into `.claude/skills/`)

## Conventions

- All GitHub access goes through the `gh` CLI — never raw HTTP. This gives us auth for free.
- Media types are detected from magic bytes, not file extensions.
- `ffmpeg` and `anthropic` are optional — features degrade gracefully.
- CLI uses `argh` for dispatch. Add new commands to `_cli_commands` in `__main__.py`.
- Tests use `@patch` for subprocess calls. Run with `pytest tests/`.

## Testing

```bash
python -m pytest tests/ -v
```

## Skills

Skills live in `ge/data/skills/` and are symlinked from `.claude/skills/`. Editing them in `ge/data/skills/` updates both locations (repo-local and globally installed via `ge install-skills`).
