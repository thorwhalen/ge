# GitHub as Agent Memory — a light report

*Author: Thor Whalen*
*Status: light report (a deeper research report has been commissioned separately)*

## What this space is called

The umbrella discipline is **context engineering** — Anthropic's preferred term for managing what goes into, and persists across, an agent's context window. The specific sub-problem of persisting decisions, rationale, problems, and future ideas across sessions is called the **memory layer** or **agent memory**. The community shorthand for the failure mode it solves is Steve Yegge's **"50 First Dates" problem**: agents wake up each session with no memory of yesterday's work [1].

## The core finding

The industry consensus in 2026 is that the defining limitation of AI coding tools is that the context window lives for exactly one session — when it ends, the slate is wiped [2]. Every serious approach now externalizes memory to **structured, addressable, version-controlled** state rather than freeform markdown notes. Your instinct (issues + discussions + `docs/` markdown, backed by your `ge` package) is aligned with where the field is heading.

## Beads: external validation of your architecture

The dominant reference point is **Steve Yegge's Beads** (`bd`), a git-backed issue tracker built specifically for AI coding agents [1]. Its architecture mirrors your `ge` / `dacc` design almost exactly:

- Issues stored as JSONL in git (`.beads/beads.jsonl`), cached locally in SQLite for fast queries, with hash-based IDs (e.g. `bd-a1b2`) designed to prevent merge conflicts in multi-agent workflows [3].
- Git is the source of truth; SQLite is the disposable cache — your exact SSOT-with-cache pattern.
- Notably, when Yegge asked Claude what it wanted for memory, the AI designed the git-backed architecture itself [4].

### Best practices crystallized from the Beads community (all ≤ 6 months old)

1. **"Land the plane" pattern.** Agents clean up state at session end and generate ready-to-paste prompts for the next session [3]. This is precisely your handoff protocol, now a named convention.
2. **Addressable work items over markdown piles.** Agents can't distinguish "we decided this yesterday" from "this was a brainstorm three weeks ago" — everything on disk looks equally valid. The fix is addressable work items: every task gets an ID, priority, dependencies, and an audit trail [5]. This is the strongest argument for *structured issues* over loose `docs/*.md`.
3. **Typed dependencies.** Four dependency types — `blocks`, `related`, `parent-child`, and `discovered-from` [3]. The `discovered-from` type is the clever one: it captures work the agent *finds* mid-task, which is exactly the context normally lost on a `/clear`.
4. **Thin client, thick logic.** The "what blocks what" logic lives in the tool binary, not in the agent's system prompt — saving context and money [6]. Relevant to scoping `ge`: keep dependency resolution in your Python facade, not in prose instructions.
5. **Structured output for agents, not humans.** Beads' CLI is "rough" for a human but perfect for an LLM: precise parameters, structured JSON output [6]. Design `ge`'s CLI the same way.
6. **Kill sessions early.** If an agent forgets the memory store mid-session as context fills, one option is simply to kill sessions earlier [3]. Short, disciplined sessions beat long ones that drift.

The companion idea is **MCP Agent Mail** (Jeffrey Emanuel): "Beads gives the agents shared memory, and Agent Mail gives them messaging — that's all they need" [3]. Memory + messaging as the two primitives for multi-agent coordination.

## Controlling GitHub Projects via `gh`

Yes. The `gh project` command is GA and mature. Project subcommands include `create`, `copy`, `list`, `view`; field subcommands include `field-create`, `field-list`, `field-delete`; item subcommands include `item-add`, `item-edit`, `item-archive`, `item-list` [7]. The token needs the `project` scope — verify with `gh auth status` and add it with `gh auth refresh -s project` [8]. For richer manipulation (custom field *values*, status transitions) most people drop to `gh api graphql`, since the CLI surface for field values is thinner than for issues.

Projects is **additive**, not a replacement: items are usually issues, and Projects layers board/table/roadmap views and structured fields (status, priority, iteration) on top. The honest tradeoff is that the `gh project` / GraphQL ergonomics for agents are noticeably rougher than plain `gh issue`, so Projects earns its place mainly when you want queryable cross-repo roadmap views that labels approximate clumsily.

## Broader context-management approaches (≤ 1 year)

Three families have emerged:

- **Dedicated memory frameworks (managed APIs).** Mem0 offers a three-tier memory system (user, session, agent scopes) backed by a hybrid vector + graph + key-value store; when facts conflict it self-edits rather than appending duplicates [9]. That contradiction-resolution behavior is the thing loose markdown can't do. Supermemory positions specifically for coding agents with an MCP server and Claude Code / OpenCode plugins, though its benchmark-leadership claims are self-reported and not independently verified as of late 2025 [9].
- **Git-native / repo-resident memory (your camp + Beads).** The thesis: for teams and agents working asynchronously, git can be a better database than SQL — it lets you branch not only code but the *state of work*, and reverting commits can revert task-state changes too [6]. Best fit for your values (SSOT, no external service, agents already know git).
- **Self-hosted curated memory with lifecycle hooks.** The newest pattern — e.g. Mori — captures sessions via lifecycle hooks with zero instrumentation and runs a "dream pipeline" that distills sessions into curated, governed memories, supporting Claude Code, Cursor, Codex [10]. The "distill sessions into curated memories" step is the automated version of your manual handoff-writing.

## My read for your situation

You are already building the right thing (`ge`), and Beads is strong external validation that your architecture is correct — same git-as-SSOT / SQLite-cache split, same handoff pattern. Two ideas worth stealing:

1. **Typed dependencies including `discovered-from`**, to capture mid-task discoveries you currently lose at `/clear`.
2. **Structured, addressable items over markdown**, for the staleness problem.

Adopt Projects only if you want queryable status/iteration fields for cross-repo roadmap views; otherwise issues + discussions plus `ge`'s facade may already give you Beads-equivalent structure without the rougher `gh project` ergonomics.

---

## REFERENCES

[1] [Beads — Memory for your Agent and The Best Damn Issue Tracker You're Not Using (Ian Bull)](https://ianbull.com/posts/beads/)
[2] [Why Every AI Coding Agent Will Need Persistent Memory by 2027 (DEV Community)](https://dev.to/varun_pratapbhardwaj_b13/why-every-ai-coding-agent-will-need-persistent-memory-by-2027-10h6)
[3] [AI Coding Agents in 2026: Coherence Through Orchestration, Not Autonomy (Mike Mason)](https://mikemason.ca/writing/ai-coding-agents-jan-2026/)
[4] [Beads: Git-Backed Memory for AI Agents That Actually Remembers (YUV.AI)](https://yuv.ai/blog/beads-git-backed-memory-for-ai-agents-that-actually-remembers)
[5] [Beads: Memory for Your Coding Agents (paddo.dev)](https://paddo.dev/blog/beads-memory-for-coding-agents/)
[6] [GitHub All-Stars #12: Beads (VirtusLab)](https://virtuslab.com/blog/ai/beads-give-ai-memory)
[7] [GitHub CLI project command is now generally available (GitHub Blog)](https://github.blog/developer-skills/github/github-cli-project-command-is-now-generally-available/)
[8] [gh project — GitHub CLI manual](https://cli.github.com/manual/gh_project)
[9] [Best AI Agent Memory Frameworks in 2026: Compared and Ranked (Atlan)](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
[10] [Awesome AI Agents 2026 (Mori entry)](https://github.com/ARUNAGIRINATHAN-K/awesome-ai-agents-2026)
[11] [steveyegge/beads (GitHub)](https://github.com/steveyegge/beads)
