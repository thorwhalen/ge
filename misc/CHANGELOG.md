# Changelog

## Unreleased

### Added

- **Autonomous execution capability.** `ge` can now drive Claude Code
  through long bodies of work without interrupting the user, using
  GitHub as durable memory.
  - `ge/memory.py` — GitHub-backed stores as `collections.abc` facades:
    `RoadmapStore` (markdown task list inside a roadmap issue),
    `DecisionLog` (tagged comments on an issue or PR), `TriageBacklog`
    (cross-repo JSON block keyed by `owner/repo#N`). `github_memory()`
    factory bundles them as a mall. Local `.ge/cache/` is hydrate-only;
    GitHub is the single source of truth.
  - `ge/run.py` — Autonomous runner with `run_roadmap()` /
    `run_triage()`. Launches headless `claude -p` one work unit at a
    time; permission mode (`auto` default, `bypass` on request) is set
    here, not in any skill. Detects killed-by-denial-cap sessions and
    retries once before escalating.
  - Three new bundled skills: `ge-autonomous-execution` (the decide-and-log
    behavioural policy), `ge-roadmap-execution` (drive a roadmap issue
    end-to-end), `ge-cross-repo-triage` (Phase A analyse + Phase B
    failing-test → fix → PR, stop at PR).
  - New CLI commands: `ge roadmap-show / -next / -set / -append`,
    `ge decision-log`, `ge decisions-show`, `ge triage-show / -set`,
    `ge check-requirements`, `ge run-roadmap`, `ge run-triage`.
  - `.ge/` added to `.gitignore`.
  - Docs: `misc/docs/AUTONOMOUS_EXECUTION.md`; new sections in README;
    pointers in `.claude/CLAUDE.md`.
