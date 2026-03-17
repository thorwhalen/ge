# ge Skills

Skills have moved to `ge/data/skills/`. To install them globally so Claude Code can discover them in any project:

```bash
ge install-skills
# or:
python -m ge install-skills
```

This creates symlinks in `~/.claude/skills/` pointing to the skill files in this package.

## Available Skills

| Skill | Description |
|-------|-------------|
| `ge` | Full workflow: verify project, prepare context, analyze, work on an issue/PR |
| `ge-analyze` | Quick triage: check staleness, find related PRs, assess relevance |
| `ge-context` | Prepare/refresh structured context documents for issues/PRs/discussions |

For the main workflow skill, see [`ge/data/skills/ge/SKILL.md`](ge/data/skills/ge/SKILL.md).
