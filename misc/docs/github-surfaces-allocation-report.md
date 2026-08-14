# Issues, Discussions, Projects, and Files: Allocating Work and Knowledge in Agent-Operated Repositories

*A practice report for maintainers who work alongside AI coding agents, and for the agents themselves.*

*Status of evidence: all platform capability claims below were verified against live GraphQL introspection, the published OpenAPI description, and primary GitHub documentation as of mid-August 2026. Claims that did not survive verification have been removed; claims that rest only on inference or on a single anecdote are labelled as such in the text.*

---

## 1. Abstract

**Put everything with an unresolved state in Issues, put every settled conclusion in a committed Markdown file, treat Projects as a view that may hold no information of its own, and default to Discussions being switched off.** This is not a stylistic preference; it follows from capability facts an agent can verify. Only Issues and pull requests implement GitHub's `Assignable` interface, so only an Issue can carry an obligation that notifies a named person and remains queryable afterwards [1][2]. Only Issues and pull requests are members of the `ProjectV2ItemContent` union, so a Discussion can never appear on a board, in a milestone, in a dependency query, or in any cross-repository rollup [3]. Only Issues have typed hierarchy (sub-issues, capped at 100 children and 8 levels of nesting) [4], typed dependencies (`blocked_by`/`blocking`, capped at 50 per relationship type) [5], typed fields [6], and semantic search — the `SearchType` enum offers `ISSUE_SEMANTIC` and `ISSUE_HYBRID` and has no Discussion counterpart [7]. Only files in the working tree are retrievable by a cold agent with no token, no network, no rate-limit budget, and no prior knowledge that the content exists. Discussions retain exactly two properties the others lack: a typed pointer to which comment is the answer (`answer`, `isAnswered`, `answerChosenAt`, `answerChosenBy`) [1], and the ability for a human to subscribe to discussions *only*, which makes a low-volume human channel possible in a repository where agents generate high issue volume [8]. Those two properties are real, and for most agent-operated repositories they do not pay for the retrieval loss, the taxonomy-bootstrap wall, and the preview-grade tooling that come with them. The decision procedure in §9 collapses to two questions an agent answers mechanically, in order: *does something remain undone until someone acts?* → Issue. *Must a future session find this without being told it exists?* → committed Markdown. Everything else is a comment on an Issue.

---

## 2. Scope

**Covered.** Allocation of textual work and knowledge across four surfaces in a Git-hosted repository on GitHub: Issues, Discussions, Projects (v2), and Markdown files under version control. The audience is a maintainer of many repositories who runs AI coding agents against them — sometimes interactively, sometimes unattended — plus a small number of human collaborators. The report covers product semantics, API and CLI operability, observed practice in public projects, a prescriptive workflow for asking a specific human a question that blocks work, architecture decision records, failure modes, and a copy-pasteable allocation rule.

**Not covered.** Pull-request review conventions and branch strategy, except where a pull request functions as a decision surface (§5.5, §7.1). Wikis, which have no content API beyond a Git remote and no query surface at all. External trackers except as comparison points. Enterprise Server version skew. Security-advisory and Dependabot surfaces. Team discussions, which are a different, removed feature (sunset notice February 2023; removed from Enterprise Server 3.12 in February 2024).

**Deliberately out of scope: taste.** This report answers the allocation question with a rule rather than a balance. Where a genuine trade-off exists it is named, quantified where possible, and then resolved with a default and a stated reason. A rule an agent can execute badly-but-consistently beats a judgment an agent re-derives freshly, and differently, every session.

**Currency.** GitHub shipped a great deal to Issues between January 2025 and July 2026 and almost nothing to Discussions in the same window. Any allocation advice written before mid-2025 describes a different platform. Re-check the capability table in §4.1 before reusing this report after roughly mid-2027.

---

## 3. The surfaces and what each is actually for

### 3.1 What GitHub says, and why it does not help

GitHub's routing guidance is scenario-based and file-scoped. Its quickstart routes you to Issues for "I want to keep track of tasks, enhancements and bugs" and "I want to ask a question about files in the repository", and to Discussions for "I have a question that's not necessarily related to specific files in the repository" and "I want to start or participate in an open-ended conversation" [9]. The main "About discussions" page describes Discussions' features — announcements, decisions with community input, Q&A, polls — and never compares them to Issues at all; it mentions issues once, in passing, as something you can convert *into* a discussion [10].

That axis — *is this about specific files?* — is useless to an agent. It says nothing about which surface survives, which is queryable, which is writable by the agent's actual toolchain, or which a future session will find. Note also that GitHub's public Discussions documentation is framed throughout around community engagement with external contributors; there is no vendor guidance for the private-repository-plus-agents case at all. The allocation rule has to be derived from capability, not from prose, and it has to be authored locally.

### 3.2 Issues: the only surface with an obligation primitive

An Issue is the only object (with pull requests) that can be **assigned**. In the GraphQL schema, the `Assignable` interface has exactly two implementing types, `Issue` and `PullRequest`; the `Discussion` type has no `assignees` field, no `assignedActors` field, and no `viewerCanAssign` field, and there is no `assignDiscussion` mutation [1]. Assignment matters for three separate reasons that compound:

- It **notifies**. Being assigned to an issue or pull request is one of GitHub's automatic subscription triggers [11].
- It **persists as a queryable obligation**. `assignee:` is a search qualifier for issues; the discussions qualifier list contains `is:answered`, `is:unanswered`, `answered-by:`, `category:`, `author:`, `commenter:`, `involves:`, `label:` and more — and no `assignee:` [12].
- It **has a state you can close against**. `IssueStateReason` is `REOPENED | NOT_PLANNED | COMPLETED | DUPLICATE`.

Assignment is not universal, however. Eligible assignees are: yourself, anyone who has already commented on the item, anyone with write permission, and organization members with read permission [2]. On a personal-account repository the last path does not exist, so an outside stakeholder cannot be assigned until they have commented — a chicken-and-egg problem with a concrete workaround in §6. Up to 10 assignees are supported, on any repository [13].

Beyond assignment, Issues carry every structural primitive the platform has added recently:

- **Hierarchy.** Sub-issues, generally available since April 2025 [14], capped at 100 sub-issues per parent and 8 levels of nesting [4], addressable in both directions over REST (`GET`/`POST /repos/{owner}/{repo}/issues/{n}/sub_issues`, `DELETE .../sub_issue`, `PATCH .../sub_issues/priority`, and `GET /repos/{owner}/{repo}/issues/{n}/parent`) [15].
- **Dependencies.** `blocked_by`/`blocking` went generally available on 21 August 2025, with up to 50 linked issues per relationship type, full REST, GraphQL and webhook support, and four search filters: `is:blocked`, `is:blocking`, `blocked-by:`, `blocking:` [5][16]. GraphQL exposes `blockedBy`, `blocking`, and an `issueDependenciesSummary` with `totalBlockedBy`/`totalBlocking`.
- **Typed fields.** Issue fields went generally available on 2 July 2026 with Priority, Effort, Start date and Target date preconfigured plus organization-defined custom fields, explicitly readable and writable through GitHub's MCP server [6].
- **Types.** Issue types are an *organization*-level construct: `POST /orgs/{org}/issue-types` creates them while `GET /repos/{owner}/{repo}/issue-types` is read-only [17]; an organization may define up to 25 [18]. On personal-account repositories the GraphQL `Repository.issueTypes` field resolves to `null`, and `Organization` has an `issueTypes` field while `User` does not. **Consequence: issue types do not exist on personal repositories, so labels remain the only portable classification axis across a mixed estate.**
- **Milestones.** `Issue` exposes `milestone` and `viewerCanSetMilestone`; `Discussion` exposes neither [1].
- **Semantic retrieval.** See §4.1(d).

### 3.3 Discussions: two real capabilities and a long list of absences

Discussions **can** be labelled — `Labelable` is implemented by `Discussion`, `Issue` and `PullRequest` [1] — so a cross-surface taxonomy is possible. At the GraphQL layer this is a two-mutation sequence, because `CreateDiscussionInput` accepts only `clientMutationId`, `repositoryId`, `title`, `body` and `categoryId`, with no `labelIds` [19]; the current CLI hides that from you (§4.1).

Discussions **can** be closed, with their own resolution vocabulary: `DiscussionStateReason` is `RESOLVED | OUTDATED | DUPLICATE | REOPENED`, and `CloseDiscussionInput` takes `discussionId` plus `reason` [1]. `OUTDATED` is, semantically, exactly the ADR "superseded" state expressed on the deliberation surface. Note a schema quirk: `Discussion` has no `state` field in GraphQL — only `closed`, `closedAt`, `stateReason`, `viewerCanClose`, `viewerCanReopen`.

The genuinely unique capability is the **typed answer pointer**. Discussion categories carry an `isAnswerable` boolean, and a Discussion exposes `answer`, `isAnswered`, `answerChosenAt` and `answerChosenBy`, driven by `markDiscussionCommentAsAnswer` / `unmarkDiscussionCommentAsAnswer` [1][19]. This is a thing Issues structurally cannot do: a stable, machine-readable pointer to *which* comment in a sixty-comment thread is the conclusion. An agent re-reading a long deliberation can fetch `discussion.answer.body` and skip the stream entirely. That is worth something, and §9 says exactly when.

The absences are long and structural. `Discussion` has no `assignees`, no `milestone`, no `issueType`, no `parent`, no `subIssues`, no `subIssuesSummary`, no `projectItems`, no `projectsV2`, no `timelineItems`, no `linkedBranches`, and no `duplicateOf` [1]. It is addressable by number, category and label only.

Two further constraints bite agents specifically:

- **Categories cannot be created, edited, or deleted through any API.** The GraphQL `Mutation` type has 258 fields and *zero* of them match "category", case-insensitively. Category management is documented exclusively as a web-UI action, and a repository or organization may have at most 25 categories [20]. Categories are to Discussions what labels are to Issues — the primary organising axis — and they require a human to click through the UI once per repository. Across a large estate this is a hard scaling wall: an agent can file only into categories a human pre-provisioned, and "this category does not exist here" is a real error the agent cannot fix.
- **Announcement categories restrict creation to maintain/admin permission, and announcements are the one category type that cannot be transferred to another repository** [20]. So the category an agent would naturally use for release notes or decision broadcasts is both permission-gated and a one-way placement.

### 3.4 Projects: a view, not a store

The `ProjectV2ItemContent` union resolves to exactly `DraftIssue | Issue | PullRequest`, and `AddProjectV2ItemByIdInput.contentId` is documented as "The id of the Issue or Pull Request to add" [3]. There is no mutation to add a Discussion, and the request to allow it has been open since April 2021 [21]. This settles the "is Projects a content surface or a view?" question in the direction of *view*: its addressable universe is Issues and pull requests, with one exception.

That exception is **draft issues**, which exist only inside a project and are invisible to `gh issue list`, to repository search, and to every per-repository query. An agent must never park real work in a draft item.

Projects gained a REST API on 11 September 2025 that is read-oriented on the project resource itself — `GET /orgs/{org}/projectsV2` and `/users/{username}/projectsV2` list and read projects, fields and items; `POST` is available on items, drafts, views and fields; `PATCH`/`DELETE` on items — but there is no REST endpoint that *creates* a project [22]. The same release made sub-issues inherit their parent's Project and Milestone by default and enabled cross-organization parent/child links [22]. That inheritance removes most of the residual reason to touch Projects programmatically at all: an agent that creates a sub-issue no longer needs a follow-up call to place it on the roadmap.

### 3.5 Files: the only surface retrievable without being known about

A Markdown file in the working tree is reachable by `grep` and `glob` with no authentication, no network, no rate-limit budget, no CLI version gate, and — crucially — **no prior knowledge that it exists**. Every other surface requires the agent to know to ask. Measured latency for a local ripgrep over a documentation directory versus an authenticated API round-trip differs by roughly one to two orders of magnitude and is network-dependent; the durable part of the argument is not the multiplier but the absence of preconditions.

Files are also the only surface where provenance is cryptographically anchored. "Who decided this, and when" lives in commit history and survives repository moves. On Discussions it does not: the tooling for migrating discussions between repositories documents that the API cannot set creation date or author, so all migrated content shows as created by the token user, with the original author and timestamp preserved only as prose injected into the body [23].

### 3.6 The capability differences that actually matter

| Capability | Issue | Discussion | Project item | Repo file |
|---|---|---|---|---|
| Assignable (obligation + auto-subscribe) | Yes [1][11] | **No field exists** [1] | Inherits from issue | No |
| Labelable | Yes | Yes [1] | n/a | No |
| Milestone | Yes [1] | No [1] | n/a | No |
| Typed hierarchy (parent/child) | Yes, 100/8 [4] | No | No | Directory tree |
| Typed dependencies | Yes, 50/type [5] | No | No | No |
| Typed custom fields | Org-level [6][18] | No | Yes (view only) | Frontmatter |
| Terminal state + reason | `COMPLETED`/`NOT_PLANNED`/`DUPLICATE` | `RESOLVED`/`OUTDATED`/`DUPLICATE` [1] | Status field | Git status line |
| Typed "which comment is the answer" | **No** | **Yes** [1] | No | n/a |
| Member of a Project | Yes [3] | **Never** [3][21] | — | No |
| Semantic / hybrid search | Yes [7] | No — lexical only [7] | No | Local grep only |
| Taxonomy creatable by API | Labels: yes | Categories: **no** [20] | Fields: yes [22] | Yes |
| Per-event-type human subscription | Yes | Yes [8] | No | Via commits |

---

## 4. The decisive constraint: agent operability

This is the section that should change your mind. The product-semantics differences above are already lopsided; the operability differences are worse, and they compound, because an agent pays them on every call, in every session, in every repository.

### 4.1 The asymmetry table

| Operation | Issues | Discussions |
|---|---|---|
| Documented REST | Yes, in the published OpenAPI description | **Zero paths** matching "discussion" out of 808 [24] |
| Undocumented REST | n/a | `GET` works and returns live data; `POST` returns 404 [25] |
| GraphQL | Full | Full (the only supported write path) [19] |
| CLI contract stability | Stable for years | **Preview**: "the `discussion` command set is in preview and is subject to change without notice" [26] |
| CLI create | `gh issue create` | `gh discussion create` (v2.94.0+, preview) [27][28] |
| CLI outcome verbs | `gh issue close --reason` | **None** — close, reopen and mark-answer are GraphQL-only [27] |
| CLI cross-repo search | `gh search issues --owner ...` | **None** — `gh search` has no discussions subcommand; GraphQL `search(type: DISCUSSION)` with `org:` is the only path [27] |
| Default state filter | `--state open` [29] | `--state open` [30] |
| MCP: create | `issue_write` [31] | **No create tool exists** [31] |
| MCP: default toolset | Yes | Not in the hosted default; reachable at a per-toolset URL or via the `X-MCP-Toolsets` header [32] |
| Agent dispatch target | Yes — assign an issue to a coding agent [33] | No |
| Write cost (GraphQL secondary budget) | REST: 1 request against 5,000/hr | Mutation: 5 points, plus a mandatory category-ID preflight [34] |

Four of these deserve elaboration, because they are the ones that fail silently.

**(a) The undocumented REST trap.** `GET /repos/{owner}/{repo}/discussions`, `.../discussions/{number}` and `.../discussions/{number}/comments` all return live, structured JSON under `X-GitHub-Api-Version: 2022-11-28`. They are also absent from GitHub's published OpenAPI description entirely, absent from every generated SDK, and the documentation URL that GitHub's own 404 body points at does not itself exist [24][25]. `POST` to the same path returns 404, so writes are genuinely GraphQL-only. An agent that *probes* rather than reads specs will conclude Discussions have REST support and build on an endpoint carrying no compatibility guarantee. Any policy touching Discussions must name the supported path explicitly.

**(b) The stale-binary problem, which cuts both ways.** The `gh discussion` command group did not exist for the first five and a half years of Discussions' life; it shipped on 10 June 2026 in CLI v2.94.0 [26][28], closing a long-standing request [35]. The same release added `--type`, `--parent`/`--set-parent`/`--remove-parent`, `--blocked-by`/`--blocking` with add/remove variants, and new `parent`, `subIssues`, `type` and dependency JSON fields on `gh issue view` and `gh issue list` [36][37]. An agent running an installed CLI even a year old has *none* of that, and will silently no-op or error on flags a skill file confidently instructs it to use. The correct discipline is not to assume presence *or* absence: **feature-detect** (`gh discussion --help`; `gh issue create --help | grep -q -- --blocked-by`) and branch. Note also that a preview command set is an unstable contract by declaration — a routine upgrade can change it with no deprecation cycle.

**(c) The MCP gap.** The official GitHub MCP server's discussions toolset contains exactly five tools — `list_discussions`, `get_discussion`, `get_discussion_comments`, `list_discussion_categories`, `discussion_comment_write` — and **none of them creates a discussion** [31]. The issues toolset has `issue_write`, `add_issue_comment`, `issue_read`, `list_issues`, `search_issues`, `sub_issue_write`, `list_issue_fields`, `list_issue_types`. An agent whose only GitHub access is MCP can open an Issue, wire sub-issues, and add it to a Project, but cannot start a Discussion — it can only join one a human began. The discussions toolset *is* reachable on the hosted remote server, at a dedicated per-toolset URL or via a header, but it is not in the default set [32], so an out-of-the-box agent does not know the surface exists. Whatever your policy says, agent-authored rationale will drift toward Issues by default.

**(d) Retrieval, which matters more than writes.** Semantic and hybrid search for Issues went generally available on 2 April 2026 via `search_type=semantic|hybrid` on `/search/issues` and `searchType: SEMANTIC|HYBRID` in GraphQL, rate-limited to 10 requests per minute [7]. The `SearchType` enum is `ISSUE, ISSUE_ADVANCED, ISSUE_SEMANTIC, ISSUE_HYBRID, REPOSITORY, USER, DISCUSSION` — there is a plain `DISCUSSION` type and no semantic or hybrid counterpart, and the OpenAPI parameter description states the search-type parameter applies only to issue searches. An agent asking *"have we decided this before?"* can pose that question in natural language against Issues and get meaning-matched hits. Against Discussions it can only match keywords, and only if it guesses the words a human used a year ago. Discussion search *does* work — a falsification test on a large public repository confirmed the qualifiers genuinely filter rather than being silently ignored (bare repository query: 688 results; `+category:general`: 184; `+category:` a nonexistent name: 0; `+is:answered`: 283) — but it is lexical, un-CLI'd, and repository-scoped from the CLI.

### 4.2 Rate limits are an allocation input, not a footnote

REST core and GraphQL each allow 5,000 units per hour; search allows 30 requests per minute; semantic and hybrid issue search allow 10 per minute [7][34]. GraphQL adds secondary limits of 2,000 points per minute and 100 concurrent requests, with **mutations costing 5 points** [34]. Separately, content-generating requests are capped at 80 per minute and 500 per hour.

Two consequences. First, a fleet of agents routing writes through Discussions burns the secondary budget several times faster than the equivalent REST issue writes, *and* pays a category-lookup query before each one. In GitHub Actions the automatic token is capped at 1,000 GraphQL points per hour per repository, so an unattended CI agent hits that ceiling far sooner via Discussions than via Issues. Second — and this is the failure that actually hurts — the 30-per-minute search bucket means an agent instructed to "search for prior art before acting" across many repositories exhausts it in under a minute and then either stalls or, worse, silently proceeds as though no prior art existed.

### 4.3 What a purpose-built agent tracker still buys you, precisely

The strongest prior-art argument for keeping work outside GitHub is the graph-native agent tracker, of which the best-known is Beads [38]. Two things have changed since that argument was first made, and any current recommendation should reflect both.

**It changed shape.** Beads is now backed by Dolt rather than by a Git-committed JSONL file: "Beads uses Dolt as its database", `.beads/issues.jsonl` is "an export for viewers and interchange, not the source of truth or a backup", and "Beads works without git" [38]. Adoption therefore means a second version-controlled database per repository plus a second push step. The property that originally made it attractive to a Git-first maintainer — *the tracker merges like source* — is not the current design.

**Its GitHub gap narrowed but did not close, and the residue is now nameable.** Beads models ten relationship types, split into blocking (`blocks`, `parent-child`, `conditional-blocks`, `waits-for`) and non-blocking (`related`, `tracks`, `discovered-from`, `caused-by`, `validates`, `supersedes`), with readiness defined as "an issue is ready when ALL of its blocking dependencies are closed" [39]. GitHub now natively covers *parent-child* (sub-issues) and *blocks* (dependencies). What it does **not** have is any of the six non-blocking semantic edges. In particular there is no `discovered-from` edge, so an agent that finds a bug while doing something else has nowhere structured to record the causal link — it degrades to prose in a comment, which no query traverses. `supersedes` is likewise absent, which matters because that is the ADR relation expressed as a tracker edge.

The second residue is **atomic claim**. Beads ships `bd update <id> --claim` (atomically sets assignee and status) and `bd ready --claim --json` [40]. GitHub has assignment but no test-and-set: `POST /repos/{owner}/{repo}/issues/{n}/assignees` is *additive* — already-assigned users are not replaced, and ineligible users are silently ignored. Two agents that self-assign the same issue therefore both end up assigned, and **neither request fails**. A research preprint proposing a Git-log-based coordination substrate reports duplicate work falling from 78% to zero and throughput more than tripling once a real claim primitive is introduced [41]; treat that as a self-reported result from a single-author preprint evaluating its own tool, not as an established finding, but the direction is consistent with the mechanism.

The third consideration cuts the *other* way: Beads has shipped a bidirectional GitHub Issues bridge since March 2026 (`bd github sync|push|pull|status|repos`, with `--prefer-newer`/`--prefer-github`/`--prefer-local` conflict policies), plus Jira and Linear bridges. So the choice is not "two unreconciled trackers"; it is "choose a sync direction and a conflict policy, and run a second store".

**Pragmatic default, stated plainly.** For a maintainer running agents sequentially, the six missing edge types are a prose problem, not a blocker, and the sidecar is not worth its weight. Adopt one only when you run genuinely parallel agents on a single repository, or when `discovered-from` provenance becomes something you query rather than something you merely wish existed. Two further practitioner observations point the same way: agents do not reach for a sidecar tracker unprompted ("you need to say 'track this in beads' or 'check bd ready'"), and the working convention among its own users is to keep only near-term work in it and leave the distant backlog in the existing tracker, because every item in the polled store is a retrieval candidate that costs tokens [42]. That heuristic generalises past any one tool: **the store an agent polls at session start should contain only actionable-now work.**

The tracker-as-control-plane pattern is real and is being productised — one published orchestration spec polls the tracker on a configurable interval defaulting to 30 seconds and gives every eligible open issue its own sandbox and agent [43] — but that pattern needs a claim primitive to be safe, and GitHub does not have one.

---

## 5. What real projects do, and how much of it survives here

### 5.1 The public evidence is mostly about a problem you do not have

A hand-checked sample of very large, very active engineering repositories shows both postures at scale. Discussions are **off**, with zero discussions, on the CPython, Rust, Node, React, VS Code, TypeScript, Kubernetes, PyTorch, NumPy, pandas, Homebrew, Hugo, Ollama, uv and Claude Code repositories. Discussions are **on and heavily used** on Next.js (28,562 discussions against 2,118 open issues), Supabase (13,069 / 272), Tailwind CSS (9,953 / 25), Zed (8,025 / 2,492), Airflow (4,989 / 1,099) and Vite (3,984 / 503). Both are viable at scale; no majority claim is made here, and none is supported by a hand-picked sample.

What *is* clear is that the split, where it works, is **enforced by a mechanism that does not bind agents**. Every project that successfully routes traffic between the two surfaces does it with `.github/ISSUE_TEMPLATE/config.yml` — `blank_issues_enabled: false` plus `contact_links` deep-linking to a named discussion category. That is verbatim the case for Tailwind CSS, whose config links to `?category=help` and `?category=ideas` [44], and the same shape appears in Zed (`?category=feature-requests`), Airflow and Vite. GitHub's documentation scopes the feature precisely: the configuration file "will customize the template chooser when the file is merged into the repository's default branch" [45]. It is a web-UI funnel. It does not constrain REST or GraphQL, so `gh issue create` and any agent calling the API bypass the entire policy silently. (That last step is an inference from the absence of any documented API-side gate, not a quoted statement — but a well-supported one. Note also that repository maintainers retain a "Blank issue" escape hatch even when the flag is false, so the funnel constrains outside contributors more than owners.)

The corollary is the single most important transfer failure in this report: **the observed success of the public split is partly an artefact of enforcement that does not exist on the agent's side of the API.** In an agent-operated repository the allocation rule must live where the agent reads it — the preloaded instruction file, a skill, or the physical structure of the repository — because the config file is decorative from the agent's perspective.

The second transfer failure is that the public rule sorts by **audience**: outsiders' questions go to Discussions to protect a small, high-signal issue tracker from inbound support load. In a private repository with a handful of colleagues and several agents there is no inbound support load to deflect, no anonymous reporters to educate, and no template chooser in the agents' path. Almost none of that advice survives.

### 5.2 The one internal-facing source, and how to read it

The most transferable published source is GitHub Engineering's own communication handbook, because it addresses internal asynchronous work rather than community management [46]. It states that "Issues on GitHub.com are the atomic unit of work across teams and the primary means by which work is planned, tracked, managed, coordinated, communicated, and shared", and that "Discussions are intended for long-lived conversations that don't involve a todo/shipped state (although you can now 'close' a discussion if it is time bound)". It scopes Discussions to "Q&A, internal updates, or social discussions, as well as a starting point for feature ideas and designs", and routes upstream ambiguity — "should we even do this", or "we should do this but there are so many ways to implement it" — to a Discussion, from which "Issues can come out of discussions eventually, once decisions have been made".

It also independently reinvents the stream/log split and adds a stage: chat → issue/discussion/PR → Markdown. Announcements and longer-term decisions "should be documented in a discussion, issue, or pull request" as "a more durable, permanent record"; for the hardened form, "prefer formats like Markdown", because "open formats not only allow for diffing, but also facilitate targeted discussions through line-by-line commenting". And it prescribes a ritual worth stealing verbatim: keep the issue body up to date, "and regularly summarize the discussion as a comment that restates the current understanding of the problem and its proposed solution" [46]. That ritual is expensive for humans and nearly free for an agent — which makes it the cheapest available mitigation for the fact that agents read threads linearly and expensively.

**Two caveats a careful reader must apply.** First, that document is from 2023 — its last substantive commit predates every Issues capability discussed in §3 and §4, and it is explicitly a community version of an internal document informed by a 2023 survey. Cite it for its *test*, not its currency. Second, it describes a many-hundred-engineer, many-team coordination problem, not a maintainer with agents. Its funnel ("start ambiguous things in a Discussion, graduate to Issues once decided") exists because dozens of people must weigh in before the shape is settled. When the number of humans is one or three, the graduation step is pure overhead — the deliberation and the work item can be the same object.

The transferable test is therefore **not** "is this a support question?" but **"is the shape of this work settled, and does anything remain undone until someone acts?"** The second half is mechanically checkable and is the basis of §9.

### 5.3 The pattern that actually removes the decision: split by repository

The cleanest production instance of the stream/log split is a **two-repository** split. One large project's code repository has Discussions disabled and 2,871 open issues; a separate architecture repository has Discussions enabled with 814 discussions and exactly one open issue, alongside a folder of 22 numbered ADRs [47]. Its README states the rule outright: create a discussion per topic, and "if a decision is made, it is recorded as an Architecture Decision Record and stored in the ADR folder". It has also customised its categories to domain concepts and made three of the four answerable — repurposing the accepted-answer mechanism as the marker of architectural resolution — and it is actively used, not a museum.

This is the refinement the classic stream/log framing misses, and for an agent it is worth more than any feature: **the deliberation surface lives in a different repository from the work surface, so the per-item allocation decision disappears.** An agent working in the code repository has no Discussions tab to be tempted by. An agent working in the architecture repository has no issue tracker. Allocation becomes a repository choice made once by a human rather than a judgment call made hundreds of times by an agent — and, per §5.1, a judgment call made hundreds of times by an agent is exactly what you cannot enforce.

### 5.4 Abandonment cases, and what they actually say

Three documented abandonments all cite surface-count reduction, not any deficiency in Discussions:

- One large project stripped its Discussions to a single Announcements category whose description is the migration notice pointing at an external forum; four discussions remain against 330 open issues — and `hasDiscussionsEnabled` still reads `true` [48]. **The enabled boolean is not evidence of use.** Any agent heuristic must check volume and recency instead.
- A named OSS maintainer publicly consolidated on Issues in November 2024 for four reasons: to manage tasks in a single Project; to aggregate information in Issues; to make the operation simple, with the sub-reason "to reduce options and avoid unnecessary hesitation"; and because "GitHub Issues are more powerful than GitHub Discussions at the moment". The supporting text adds "we can't manage topics in Projects until we create Issues", "we can assign people to Issues", and "we can add Issues to Milestones" [49]. Worth knowing: this is a flip-flop, not a one-way conclusion — the same maintainer closed Discussions in early 2023, proposed reopening them in mid-2023, and closed them again in late 2024. The reason that survives all three rounds is "reduce options".
- A C++ project disabled Discussions in May 2024 "so we can concentrate our conversations in one place", moving to an external forum [50]. For an agent-operated repository this is strictly worse than either GitHub surface: an external forum is unreachable by the repository's CLI, has no schema to introspect, and drops out of the repository's addressable memory entirely.

The "reduce options and avoid unnecessary hesitation" argument is **stronger for agents than for humans**. A human develops a habit; an agent re-evaluates a nondeterministic branch afresh every session with no memory of how it decided last time, producing an inconsistently partitioned corpus. Fewer surfaces yields a more uniformly searchable archive.

### 5.5 RFC practice, and the fourth surface

The dominant pattern for a first-class design process is a dedicated repository where the proposal is a **pull request against a Markdown file**, with Discussions disabled: the Rust RFCs repository (214 open PRs, actively pushed in August 2026) [51], the Kubernetes enhancements repository, and the React and Svelte RFC repositories all follow it. The Vue RFC repository is the notable exception, running deliberation in Discussions. Activity is mixed across both camps — the React and Svelte RFC repositories have been dormant since mid- and late-2024, staler than the Discussions-based one — so no causal claim should be drawn from the comparison. What matters is what the PR-as-RFC pattern *is*.

**The pull request is a fourth surface, and for agents it is the best-instrumented one on the platform.** It collapses the deliberation stream and the decision log into a single addressable object: the file diff *is* the proposal, review threads are line-anchored to it, merging *is* the acceptance, and the merge commit is immutable. It has full, stable CLI coverage, and unlike an ADR file dropped on the default branch it carries a built-in approval gate. Where a decision genuinely needs review before it binds, the pull request — not a Discussion — is the deliberation surface.

Two linking conventions from this world are worth adopting wholesale:

- **Backlinks belong in the durable artifact, pointing backwards.** One project's accepted proposals carry a `Reference Issues:` frontmatter field naming the originating discussion [52][53]. Backlinks written in the ephemeral direction ("see the ADR", in a comment) rot silently; a frontmatter field is reviewed in the pull request that lands the file. (That field name is inherited from an older RFC template lineage, which is itself evidence of durability.)
- **Better still, put the identifier in the filename.** Kubernetes prefixes each enhancement proposal with its tracking issue number: "KEPs are now prefixed with their associated tracking issue number. This gives both the KEP a unique identifier and provides an easy breadcrumb for people to find the issue where the current state of the KEP is being updated" [54]. This survives file moves, template changes, frontmatter drift, and any tool that rewrites metadata, and it is recoverable by an agent **from a directory listing alone, with zero file reads**. It is the most robust ADR↔issue linking convention in circulation.

### 5.6 The counterexample: what putting decisions in Discussions actually costs

One major framework runs its RFC process in a Discussions category. Across 26 RFC discussions since 2021, **status is encoded in title-string prefixes** — `[Complete]`, `[Summary]`, `[Closed]`, `[Watch This Space]` — while the structured fields are unused or actively misleading: only 3 of 26 have `closed: true`, closedness does not correlate with the `[Complete]` prefix (a January 2026 discussion titled `[Complete] RFC: ...` is `closed: false`), exactly 1 of 26 carries any label, and `isAnswered` is null throughout because the single RFCs category is not answerable [55]. To determine whether an RFC was accepted, an agent must regex the title; the one structured field that exists gives the wrong answer. The project also hand-authors a *second* `[Summary]` discussion to crystallise a completed RFC — manually reimplementing the decision-log step, with no machine-readable link between the two objects.

That is the concrete cost of filing decisions where there are no queryable state fields. It is also a warning about the stock configuration: most repositories with Discussions enabled are running GitHub's unedited six-category template with its default descriptions. "This repository has Discussions" almost always means "nobody turned them off", not "somebody made an allocation decision". Only repositories with *edited* category names, descriptions and answerability made a choice, and only those are worth imitating.

*(An unpublished audit of one maintainer's roughly 250 personal repositories found Discussions enabled on 87 of a 100-repository sample, with 58 of those 87 at exactly zero discussions, 79 at two or fewer, and 86 discussions in total across all 87 enabled surfaces — an average of one per enabled surface. Readers cannot verify that figure; it is offered only as an illustration of how little signal the enabled flag carries, and as a prompt to run the same query against your own estate before assuming your revealed preference matches your stated policy.)*

---

## 6. The blocking-question workflow

**The problem.** An agent, mid-task, needs an answer only a specific non-technical human can give. It must (a) not guess, (b) reach that human through a channel they actually read, (c) leave a machine-checkable marker so no agent proceeds on the blocked work, and (d) capture the answer somewhere a session six months from now will find without being told.

**The allocation answer, up front: this is an Issue. Always. However deliberative the content is.** A Discussion has no assignee and no `assignee:` qualifier [1][12], cannot be a node in the dependency graph, cannot appear on a board or in a milestone, has no stale/no-response automation path, has no semantic search, and has no CLI verb for recording that it was resolved. The only thing it adds is the answer pointer — and most of that value is available by editing the answer into the issue body.

One clarification about agent capability, because stale advice circulates here. GitHub's coding agent **can** ask clarifying questions as of March 2026 (documented for its Jira integration) and can pause for plan approval before writing code as of April 2026 [56][57]. So the argument is not "agents cannot ask". The argument is that a clarifying question raised inside an agent run reaches whoever happens to be watching that run — not a named stakeholder, with a due answer, that survives the session and is queryable afterwards. That is what an assigned, dependency-linked Issue provides and an in-run question does not.

### 6.1 The recipe

**Step 0 — Leave the tripwire where the agent will trip over it.** Write the ambiguity inline into the spec or design file, in a form the next session cannot miss and cannot silently resolve. GitHub's spec-driven toolkit uses `[NEEDS CLARIFICATION: what is missing — option A/B/C?]` markers with an explicit rule to flag rather than assume [58]. The marker is the *agent's* interlock; it is not the ask. Do not skip it: an Issue is invisible to a session that starts by reading the working tree.

**Step 1 — One question per Issue.** Never batch. A batched question gets a partial answer, and a partially-answered Issue has no correct state.

**Step 2 — Write the body as an email, because it is one.** Replying to the notification email posts the comment — GitHub documents this for issues, pull requests and discussions alike [8]. The issue body is therefore literally the message a non-technical stakeholder reads on a phone. So:

- Title: the question in plain language. No ticket-speak, no bracketed prefixes.
- First line of the body: the question. Not context, not background — the question.
- Then the options, lettered **A / B / C**, each with one line of consequence, so a reply can be a single letter.
- Then: what the agent will assume if no answer arrives, and by when.
- Then, and only then, the technical context, below a horizontal rule.

Nothing that renders badly in plain-text mail. No agent jargon. No internal identifiers the person has never seen.

**Step 3 — Create the obligation.** Assign the stakeholder if they are eligible. If they are not — a personal-account repository with an outside stakeholder is the common case [2] — then `@mention` them in the body, which makes them assignable from that point on, and apply a routing label. **Read the assignee list back after assigning**, because the assignees endpoint silently ignores ineligible users rather than erroring; a successful HTTP response does not mean the person is assigned.

**Step 4 — Make the block machine-checkable.** Link the dependent work item to the question with a `blocked-by` edge [5]. This converts "the agent must infer from prose that it is blocked" into a one-line session-start gate:

```bash
gh issue list --state open --search 'is:blocked'          # do not touch these
gh issue list --state open --search 'label:needs-answer'  # these are waiting on a human
```

**Step 5 — Escalate on a timer.** A routing label plus a scheduled workflow gives the question a nudge cadence and a visible age. This tooling operates on issues and labels only; there is no equivalent for Discussions. (Choose carefully: the best-known no-response bot was archived in 2021 and its own README disclaims it [59]; use a maintained scheduled-stale action instead.)

**Step 6 — Close only after the answer exists in a file, and let a workflow do the closing.** This is the ordering that matters, and it is the one part of the recipe with a proven generic implementation. The pattern is: a structured issue form collects the answer, a parser action converts the issue body to JSON, a workflow triggered by a label writes or updates a committed file, commits it, and *then* closes the issue with a confirmation comment [60][61]. The authority to close belongs to the workflow, not to the human and not to the agent, and it is exercised only after the durable artifact exists. That is the guarantee you want: **an issue can never be closed with the answer stranded inside it.** (Caveat: issue forms structure only the opening post, so a stakeholder's free-text reply in a comment still needs an agent to transcribe it into the form's shape before the parser runs.)

**Step 7 — Retrieve with `--state all`, always.** `gh issue list` defaults to `--state open` [29], and so does `gh discussion list` [30]. An agent running the obvious command is structurally blind to every settled question. Any pre-work or alignment procedure must pass `--state all` or run an explicit closed pass. This is the mechanism behind "the answer fell out of view", and it is a flag, not a discipline problem.

### 6.2 Why not a Discussion, restated as a checklist

| Requirement | Issue | Discussion |
|---|---|---|
| Names a specific human durably | assignee | `@mention` only (transient) |
| Notifies that human automatically | yes [11] | on mention only |
| Queryable "who owes me an answer" | `assignee:` + `is:blocked` [5][12] | `is:unanswered category:...` — a property of the thread, not of a person |
| Blocks dependent work machine-readably | `blocked-by` edge [5] | none |
| Visible in any rollup or board | yes [3] | never [3] |
| Has stale / no-response automation | yes | none |
| Findable later by meaning | semantic search [7] | keyword only [7] |
| CLI verb to record resolution | `gh issue close --reason` | none — GraphQL only [27] |
| Answerable by replying to email | yes [8] | yes [8] |

The last row is the honest one: email reply works on both, so "they will never log into GitHub" is not a reason to prefer either surface. Every other row favours Issues.

Note also that the *polling* side favours Issues even more sharply than the writing side. The notifications REST API cannot be filtered server-side by reason — its only query parameters are `all`, `participating`, `since`, `before`, `page` and `per_page`, with `reason` returned in the payload but not filterable [62] — so an agent resuming work cannot cheaply ask "what was I assigned?" through notifications. On Issues it does not need to: `gh issue list --assignee @me --state open` and `--search 'label:needs-answer is:open'` are deterministic state queries with no notification dependency at all. On Discussions there is no state to query, because there is no assignee.

Unanswered threads also rot with no surfacing mechanism. A community request asking for a particular agent capability sat in the "Unanswered" state for more than seven months with no assignee, no dependency, and nothing to raise it [63]. That is a single anecdote, not a measured response rate — no study of Discussion answer rates was located — but the *mechanism* is structural rather than anecdotal: with no assignee, no Project membership, no milestone and no stale automation, nothing exists that could surface a rotting Discussion.

One last constraint that will bite a cross-repository skill: **issue types are organization-scoped**, so `gh issue create --type Question` succeeds on organization repositories and fails on personal ones [18][64]. Use a *label* for "this is a blocking question". Labels are the portable axis, and labels are what the timeout automations key off anyway.

---

## 7. ADRs: stream, log, and retrieval six months later

### 7.1 Stream and log are the right idea and the wrong number of tiers

The classic framing — deliberation is a *stream*, conclusions are a *log* — is correct and incomplete. It sorts by durability and says nothing about **obligation**, which is the axis with a native platform primitive. The refinement proposed here is three tiers, mapped to three concrete homes:

| Tier | Question it answers | Home | Why there |
|---|---|---|---|
| **Obligation** | Who must act, and what is blocked until they do? | Issue *metadata*: assignee, `blocked-by`, label, state | The only surface with assignment [1], dependencies [5] and a terminal state |
| **Stream** | How did we get here? What did we try and reject? | Issue *comments*, or a pull request's review threads | Cheap to append; expensive to read; never load-bearing |
| **Log** | What is true now, and why? | Committed Markdown, `docs/decisions/NNNN-*.md` | The only surface a cold agent finds without being told it exists |

The important structural point: **obligation and stream can be the same object; the log must be a different one.** An Issue is a perfectly good deliberation vehicle *and* a perfectly good obligation record. What it cannot be is the log, for the mechanical reason in §6 step 7 — the default query hides it the moment it is closed. Where a decision needs review before it binds, promote the stream to a pull request against the log file (§5.5) rather than to a Discussion.

### 7.2 The hardened record lives in the repository, and the reason is mechanical

An agent starting cold reads the working tree for free, offline, unauthenticated, and without knowing in advance what is there. Anything on a GitHub surface requires it to know to ask, to be authenticated, and to spend rate-limit budget. This is not an aesthetic preference for plain text; it reflects how current agents are built — a preloaded instruction file combined with just-in-time retrieval: "CLAUDE.md files are naively dropped into context up front, while primitives like glob and grep allow it to navigate its environment and retrieve files just-in-time, effectively bypassing the issues of stale indexing and complex syntax trees", with the agent holding "lightweight identifiers (file paths, stored queries, web links)" and dereferencing them on demand [65].

Two design consequences follow directly, and they are frequently missed:

1. **Write the ADR to be grep-hit-able, not merely readable.** Grep matches strings, not meaning. The decision's distinguishing nouns must appear in the *filename* and in the *first lines*, because an agent typically reads only the neighbourhood of the hit.
2. **Front-load the conclusion.** GitHub's guidance for writing an issue an agent can act on is: background (why it matters, what it touches), expected outcome (what "done" looks like), technical details (file names, functions, components), and formatting rules [66]. The same ordering applies to an ADR, with one addition: the decision goes in the first paragraph, above the context. A retrieving agent that opens the file reads the top and may stop there. The same discipline applies to Issues used as running journals — edit the settled conclusion back into the body, because a semantic hit surfaces the issue, not the comment.

There is also a compaction argument. A forty-comment thread is not merely expensive to read; it is actively degrading, because model recall accuracy falls as context length grows even when all the relevant information is present [65], and because superseded proposals in the thread compete for attention with the accepted one. A four-hundred-word ADR with the decision in the first paragraph is the compaction step performed *once*, by the party who actually knew the answer, instead of re-performed lossily by every future agent.

### 7.3 Immutability and superseding, mechanically

Use the community-standard skeleton and then constrain it. MADR 4.0.0 (September 2024) puts decisions in `docs/decisions/` with filenames `NNNN-title-with-dashes.md`, and encodes status in YAML frontmatter as a literal string: `status: {proposed | rejected | accepted | deprecated | … | superseded by ADR-0123}`, alongside `date`, `decision-makers`, `consulted` and `informed` [67][68][69]. Agent-facing ADR guidance in circulation already encodes immutability as prose: store in `docs/decisions/`, "match the existing convention first", "don't delete old ADRs — they capture historical context", lifecycle `PROPOSED → ACCEPTED → (SUPERSEDED or DEPRECATED)` [70].

Four refinements:

**(a) Superseding is greppable text, so make the rule mechanical.** Because MADR expresses superseding as a string in a fixed field rather than as a Git operation, an agent can follow an exact rule: *never edit a file whose frontmatter status is `accepted`; instead create the next record and rewrite only the old file's single status line to `superseded by ADR-NNNN`.*

**(b) Enforce it in CI, because nothing else will.** Today immutability is a prose rule in a skill file with zero mechanical enforcement — nothing stops an agent from editing an accepted ADR. A CI check that fails any pull request touching a file whose frontmatter status is `accepted`, other than its status line, is roughly fifteen lines of script and appears to be nobody's shipped tool. If immutability matters to you, write it.

**(c) Number by the issue, not by a counter.** This is a deliberate break with MADR's consecutive numbering. A fresh counter carries no information an agent can use; the tracking-issue number makes the ADR↔issue link free, unbreakable, and recoverable from `ls` alone [54]. `docs/decisions/0142-store-backend-is-pluggable.md`, where 142 is the issue it resolved, beats `0007-store-backend.md` on every retrieval axis. If you value strict consecutive numbering for human browsing, generate an index file instead — that is what ADR index generators are for.

**(d) Record who was consulted.** MADR's `consulted` and `informed` fields are the natural home for the stakeholder who answered a blocking question. It is the one place a human's authority over a decision is captured in a queryable form.

### 7.4 There is no standard tool for the promotion step

The published ADR tooling inventory lists a dozen or more tools — log generators, managers, viewers, catalogue plugins, IDE extensions — and **every one of them creates or renders ADR files; none ingests a GitHub Issue or Discussion** [71]. (The most-cited command-line tool in that list is filed there under unmaintained.) There is a third-party Action that syncs ADR files into Discussions, but it is a single-release, low-adoption project with no activity in many months; depending on it is a maintenance risk rather than a shortcut.

So the promotion step — settled Issue becomes committed ADR — is a gap you must fill yourself, and there is no standard to conform to. Do not instruct an agent to "use the standard tool"; there is not one. Use the issue-form → parser → commit → close chain from §6 step 6, or a post-merge hook, and own it.

### 7.5 The volume discipline nobody applies

The strongest available evidence on repository-level context files is that they do not help. A 2026 evaluation found that "providing context files does not generally improve task success rates, while increasing inference cost by over 20% on average", and that "this observation holds across different LLMs, coding agents, and for both LLM-generated and developer-committed context files" — with the null result attributed specifically to repository *overviews* being unhelpful while explicit *instructions* are well followed [72].

Read carefully, this is not an argument against ADRs; it is an argument against three specific habits:

- **Do not put overview in the preloaded file.** The always-loaded instruction file — a format now stewarded by the Agentic AI Foundation under the Linux Foundation, reported in use by over 60,000 open-source projects, with nearest-file-in-the-tree precedence [73], and read by GitHub's coding agent since August 2025 [74] — should contain routing rules and prohibitions ("decisions live in `docs/decisions/`; work lives in Issues; never write to X") and no description of what the project is. Everything in it is paid for on every turn of every session in every repository.
- **Do not preload ADRs.** They are retrieved just-in-time by grep. That is what makes them cheap.
- **Do not let ADRs accrete.** Each new record should supersede or displace an old one wherever it can. Volume is the enemy regardless of authorship — "have a human write it" is explicitly not the fix.

Two mechanical conventions from the field are worth adopting alongside this. First, a **versioned, content-hashed delimiter for machine-managed regions** inside instruction files — a `<!-- BEGIN ... v:1 profile:full hash:... -->` block plus a separate marker declaring that a divergence between two instruction files is intentional [75]. The version-plus-hash lets a tool detect whether its own block was hand-edited, and the divergence marker converts "these two files disagree" from a lint failure into a declared decision. This matters because an installer that rewrites your instruction file without such a marker can silently overwrite rules you wrote — a real, reported hazard [76]. Second, a **session-completion checklist that ends at `git push`**, with its prohibitions written as bans on specific sentences the agent might emit ("never stop before pushing — that leaves work stranded locally"; "never say 'ready to push when you are' — you must push") and a handoff artifact that is a ready-to-paste prompt naming a specific follow-up issue identifier [75]. The identifier is the cheapest possible session-start context: one string the next agent dereferences, rather than a summary it must trust.

---

## 8. Failure modes and anti-patterns

Each is stated as a mechanism, not a vibe, with its mitigation. Several are *silent* failures, which is what makes them dangerous unattended.

**8.1 Closed-item amnesia is a CLI default, not a discipline problem.**
`gh issue list` defaults to `--state open` [29], and `gh discussion list` does the same [30]. An agent doing routine reconnaissance never sees a question settled and closed six months ago, and will re-litigate it or re-implement a rejected design.
*Mitigation:* mandate `--state all` in every reconnaissance procedure; better, promote the conclusion to a file, which has no state filter at all.

**8.2 Silent filter failure — the worst class of bug in this area.**
The advanced search qualifiers `no:type`, `no:parent-issue` and `has:sub-issue` take effect only when `advanced_search=true` is passed. Without it they are **silently ignored and the unfiltered result set is returned**: on a large repository, the unfiltered count and the `has:sub-issue` count were both 10,751 without the flag, and 5 with it. The agent believes it filtered.
*Mitigation:* assert on cardinality. Run the query with and without the filter; if the counts are identical, treat the filter as ignored and fail loudly.

**8.3 Search-bucket exhaustion produces confident false negatives.**
Search allows 30 requests per minute; semantic and hybrid issue search allow 10 [7][34]. An agent told to check prior art across many repositories exhausts the bucket in under a minute and then reports "nothing found".
*Mitigation:* budget searches explicitly, cache within a session, and treat any 403 as a hard stop rather than an empty result. Never let "search returned nothing" and "search did not run" produce the same downstream behaviour.

**8.4 Version-gated capability, in both directions.**
An installed CLI may lack `gh discussion` and the issue-graph flags entirely; a newer one has them, but the discussion command set is declared preview and "subject to change without notice" [26]. Both "assume it exists" and "assume it does not" are wrong.
*Mitigation:* feature-detect at session start and branch; never hard-code a preview invocation into a skill file without a fallback.

**8.5 Token-scope fragmentation makes surfaces conditionally available per host.**
Writing Discussions and touching Projects require scopes that a minimal repository token does not carry; the failure arrives as a permission error mid-task rather than as an upfront capability check. Issues and repository files need only repository scope.
*Mitigation:* make Issues plus Markdown the mandatory substrate and treat Projects and Discussions as optional enrichment behind an explicit capability check. This is an operational observation from a two-host setup rather than a documented platform behaviour; verify against your own tokens.

**8.6 Misallocation is common, slow to correct, and does not self-heal unattended.**
Across 259 npm and 148 PyPI repositories, the dominant reason for converting an issue into a discussion was that it held a non-actionable topic — 55.0% and 42.0% respectively — while the dominant reason for the reverse was asking a contributor to clarify an idea into actionable work (35.1% and 34.7%). The median time merely to *raise* a conversion intent was 15.2 and 35.1 hours [77].
*Mitigation:* if experienced human maintainers misfile at that rate and take a day or two to notice, an agent under time pressure will do at least as badly, and nobody is watching. **Remove the choice** rather than improving the judgment — that is what §9 does.

**8.7 Allocation is close to irreversible for an agent, in both directions.**
There is no conversion API either way: the GraphQL mutation list contains only `convertProjectV2DraftIssueItemToIssue` and `convertPullRequestToDraft`, and there is no `transferDiscussion`. Issue→Discussion is a UI-only conversion that **consumes the issue** — destroying the number, and with it any `blocked-by` edge or ADR filename that referenced it [78]. Discussion→Issue is *not* a conversion but a documented UI action that copies the body and retains labels while leaving the discussion intact, requiring triage permission [79] — so it leaves two live objects an agent will later find and may treat as duplicates. Bulk label-based conversion was removed effective 6 June 2025 [80], so there is no supported way to fix a misfiled backlog in batch. Long-standing requests for a proper reverse conversion remain open [81][82].
*Mitigation:* default to Issue-first, because an Issue can always be closed and pointed at a file, and never convert an issue that other work depends on. If you promote a discussion to an issue, cross-link both and lock or close one immediately.

**8.8 The Discussions graveyard has no surfacing mechanism.**
With no assignee, no Project membership, no milestone and no stale automation, nothing exists that could raise a rotting thread. The request to allow discussions on Projects has been open since April 2021 with 21 upvotes and five comments [21] — a specimen of the failure, filed in the surface it describes. An agent asked "what is outstanding?" enumerates Issues and Project items and will never surface it.
*Mitigation:* do not put anything with an outstanding state in a Discussion. If you must, mirror it as an Issue and treat the Discussion as commentary.

**8.9 Closing a Discussion buries rather than resolves.**
Closed discussions are hidden from the default view, and users routinely confuse "Close discussion" with "Mark as answer" — creating rework for maintainers who must reopen them [83].
*Mitigation:* mark the answer; close only as `OUTDATED` when genuinely superseded. And apply the §8.1 fix: `--state all`.

**8.10 `hasDiscussionsEnabled` carries no information.**
A large project reads `true` with four discussions and a redirect notice in its only category description [48].
*Mitigation:* an agent's heuristic must check discussion count and last-activity date, never the boolean. Corollary for maintainers: if your estate is Issues-only in practice, **disable Discussions**, so the surface cannot be chosen by accident. Enabled-and-unused is worse than off, because it presents an option nobody chose.

**8.11 Agent-generated tracker spam, which the platform itself treats as a threat.**
GitHub's own agentic-workflow platform caps `create-issue` and `create-discussion` at **a maximum of 1 per workflow run by default**, offers an opt-in `expires` field that auto-closes generated items after a stated period, and buffers all writes through a separate safe-output server that validates them *after* the agent exits rather than executing inline [84]. A default of one is strikingly conservative and is a useful calibration point against the instinct to let agents journal freely. The cost side is documented elsewhere: the maintainer of a widely-used project reported roughly 20% of a year's bug-bounty submissions were AI slop against about 5% genuine, each report engaging three to four people for thirty minutes to three hours, against a seven-person team with roughly three hours a week each [85]; the programme was shuttered in January 2026 [86]. The transferable lesson is not "external AI submitters are the problem" — it is that **machine-generated content scales without limit while human triage capacity is fixed at one person.** Note also which mitigation was actually chosen: not better filtering, but *removing the incentive to generate volume*.
*Mitigation:* cap creations per unattended session at a small integer; never write an instruction that rewards item creation ("file an issue for anything you notice"); require every new issue to name a concrete next action and an owner; buffer writes and validate at session end.

**8.12 Over-documentation is a measured cost with no measured benefit.**
See §7.5 [72].
*Mitigation:* a high, explicit bar for creating any new durable document — irreversibility of the decision, not merely its interestingness — and supersession rather than accretion.

**8.13 Board fiction and split-brain in Projects.**
Agents automate deterministic transitions well (merged pull request → Done) and cannot infer the judgment-bearing fields at all (priority, blocked-ness, continued relevance). The result is a board where every card has a fresh timestamp and a rotten priority: it *looks* authoritative and is therefore trusted, whereas a visibly three-week-stale board signals its own unreliability. A Project also adds a second place where status lives and can disagree with the Issue.
*Mitigation:* use the Project as a pure derived view over issue state; put nothing in it that would be lost if it were deleted; never use draft issues. **This is the weakest-supported item in this section** — no credible measurement of board staleness was located in either direction, and the figures circulating on the topic trace to vendor marketing. The reasoning is mechanism-based, not evidence-based; treat it accordingly.

**8.14 Provenance laundering on migration.**
Moving discussions between repositories cannot set creation date or author, so every migrated item shows as created by the token user; categories must be pre-created by hand or content falls back to a default category; the tooling self-throttles to roughly one creation every three seconds against content-creation rate limits [23]. For a decision log, provenance *is* the content.
*Mitigation:* keep provenance-bearing records in Git, where authorship and date are anchored in commit history and survive any move.

**8.15 The taxonomy bootstrap wall.**
An agent cannot create a Discussions category; there is no mutation, management is web-UI only, and the cap is 25 per repository [20]. Across many repositories this means an agent can file only into categories a human pre-provisioned, and it must handle "category does not exist here" as an unfixable error. Issues have no equivalent gate — labels are API-creatable.
*Mitigation:* if Discussions are part of your policy, provision categories by hand from a template at repository-creation time. If that is not going to happen, the policy is not implementable and you should say so.

**8.16 The silent assignment race.**
`POST .../assignees` is additive: already-assigned users are not replaced, and ineligible users are silently ignored. Two agents self-assigning the same issue both succeed.
*Mitigation:* read the assignee list back after every assign and treat "more assignees than I expected" as a conflict; keep one writer per repository; or adopt a tracker with a real claim primitive (§4.3) if you genuinely run parallel agents.

**8.17 The enforcement gap.**
Every allocation rule that large projects rely on is enforced by a web-UI funnel that agents never traverse [45].
*Mitigation:* the rule must live where the agent reads it — the preloaded instruction file, a skill, or the physical repository split (§5.3). The strongest form of enforcement available to you is *removing the surface*.

---

## 9. Recommendation

### 9.1 The allocation table

| Content kind | Surface | Why |
|---|---|---|
| A task, bug, or chore someone must do | **Issue** | Only assignable [1]; only dispatchable to an agent [33]; only board- and dependency-addressable [3][5] |
| A question that blocks work, aimed at a named human | **Issue**, assigned or `@mention`ed, labelled, with a `blocked-by` edge from the dependent work | Assignment is the only notifying, queryable obligation [11][12]; `is:blocked` is the machine-checkable gate [5] |
| Decomposition of a larger piece of work | **Issues**: parent plus sub-issues (≤100 children, ≤8 levels) | Typed hierarchy, REST-traversable in both directions [4][15]; children inherit Project and Milestone [22] |
| Work discovered mid-task | **Issue**, cross-referenced in prose | No native `discovered-from` edge exists; prose is the only option on GitHub (§4.3) |
| Session journal, progress, evidence, reasoning | **Comments on the owning Issue**, with the settled part edited back into the body | Cheap to append; conclusions must be in the body because a retrieving agent reads the body first [66] |
| A settled architectural or design decision | **Committed Markdown**, `docs/decisions/NNNN-*.md`; the issue is then closed pointing at it | The only surface a cold agent finds without being told [65]; diffable, reviewable, line-commentable [46] |
| A decision that needs review before it binds | **Pull request** against the ADR file | Collapses stream and log into one object with a built-in approval gate and full, stable CLI coverage (§5.5) |
| Alternatives considered and rejected, and why | **The same ADR** (an "Alternatives Considered" section) | A closed issue is invisible to default queries [29]; a rejected option in a thread competes for attention with the accepted one |
| Standing rules an agent must obey every session | **Preloaded instruction file** — routing and prohibitions only, never overview | Paid for on every turn; overviews measurably do not help [72] |
| Reference material, specs, research reports | **Committed Markdown** under `docs/` | Grep-retrievable at zero cost: no token, no network, no rate limit |
| Cross-repository roadmap or status | **Project**, as a derived view over Issues | Its universe is Issues and pull requests only [3]; it must hold nothing that would be lost if deleted |
| Anything that must appear on a board, in a milestone, or in a dependency query | **Issue**, always | Structural: Discussions are not Project items and have no milestone [1][3] |
| Anything whose provenance is the content | **Git** | Author and date are unsettable through the Discussions API [23] |
| Open-ended human conversation with no completion state | **Discussion** *if the repository has deliberately enabled and customised them*; otherwise a labelled Issue, or nothing | Discussions' one operational advantage is isolation from agent-generated issue volume [8] |
| A question where "which comment is the answer" must be machine-readable, and humans will re-read the thread | **Discussion in an answerable category** | The single capability Issues structurally lack [1] |
| **Default for everything else** | **A comment on an existing Issue** | Creating a new item is the expensive, hard-to-reverse operation [80][84] |

### 9.2 The decision procedure, for an agent to execute mechanically

Evaluate in order. Stop at the first match. Do not re-evaluate later steps.

```text
0. CAPABILITY CHECK (once per session, before any write)
   - gh --version; gh issue create --help | grep -q -- '--blocked-by'  -> hasIssueGraph
   - gh discussion --help                                             -> hasDiscussionCLI
   - Treat every absent capability as "use the fallback", never as "skip the step".

1. Does something remain UNDONE until a person or process acts?
   YES -> ISSUE. Stop.
       - One task or one question per issue. Never batch.
       - Body: conclusion or question first, options as A/B/C, then context.
       - Assign if eligible; otherwise @mention in the body AND apply the routing label.
       - Read the assignee list back; a 2xx does not mean the assignment took.
       - Add `blocked-by` edges from every dependent item.

2. Is this a CONCLUSION that a future session must find without being told it exists?
   YES -> COMMITTED MARKDOWN in docs/decisions/, named <issue-number>-<distinguishing-nouns>.md.
       - Decision in the first paragraph, above the context.
       - Frontmatter: status, date, decision-makers, consulted, informed.
       - Then link the file FROM the issue and close the issue.
       - Never edit a file whose status is `accepted`, except its single status line.

3. Is this working notes, progress, evidence, or reasoning about an item that already exists?
   -> COMMENT on that item. Then edit the settled part back into the item's body.

4. Is this a status or rollup VIEW over items that already exist?
   -> PROJECT. It may hold no information of its own. No draft issues, ever.

5. Anything left over
   -> DISCUSSION only if the repository has deliberately enabled and customised Discussions.
      Agents may READ and COMMENT. Agents may NOT open, close, or mark answers.
      Otherwise: a comment on the nearest relevant issue, or nothing.

HARD LIMITS (unattended sessions)
   - Create at most 2 new items per session unless explicitly asked to decompose.
   - Never create a Discussion.
   - Never convert between surfaces.
   - Every reconnaissance query passes --state all.
   - Verify any filtered query by cardinality: identical counts with and without the
     filter means the filter was ignored.
   - Land what you opened: close or comment on every item you created, and push,
     before the session ends.
```

### 9.3 The default posture, stated as a recommendation

1. **Turn Discussions off** on repositories where agents do most of the writing, unless you can name the specific answerable category that justifies keeping them. Enabled-and-empty is worse than disabled, because it presents an option nobody chose.
2. **If you keep them, keep them in a different repository from the work** (§5.3). That converts a per-item judgment into a one-time human choice and removes the temptation entirely.
3. **Customise the categories or do not bother.** The stock six-category template is the signature of a decision never made.
4. **Never let a Discussion hold outstanding state.** No assignee, no board, no milestone and no automation means nothing will surface it.

### 9.4 Label vocabulary design

Labels are the fleet-wide single source of truth for classification, because they are the only classification axis that works identically on Issues *and* Discussions, and on personal *and* organization repositories. Issue types are a strictly organization-level bonus [17][18][64]; never build a cross-repository procedure that depends on them.

**The property that makes labels agent-safe is per-axis mutual exclusivity.** If each axis admits exactly one value, "set status to X" is a *replace* operation, and labels stop accumulating. Without that rule, agents monotonically add and never remove — which is the actual mechanism of label sprawl, not the number of labels. The best-documented agent-oriented vocabulary in circulation uses 15 labels across three mutually exclusive axes — 7 status, 4 priority, 4 kind — and justifies the shallow priority scale directly: "why only four levels? Many projects have found that finer gradations collapse into a single bucket in practice" [87]. That is one maintainer's convention on a young project, not measured evidence; the **axis design** transfers, the specific counts are illustrative.

Recommended starting shape:

```yaml
# .github/labels.yml — committed, synced by a workflow, versioned like code.
# Rule: exactly one label per axis per item. Setting is a REPLACE, never an ADD.

status:      # lifecycle; every triaged item has exactly one
  - needs-triage       # default on creation
  - needs-info         # cannot proceed without more detail from the reporter
  - accepted           # shape is settled; ready to be worked
  - in-progress
  - blocked            # human-visible mirror; the blocked-by edge is the source of truth
  - stale

priority:    # only on accepted items; four levels, deliberately coarse
  - p0
  - p1
  - p2
  - p3

kind:        # what sort of thing this is
  - bug
  - feature
  - docs
  - chore

routing:     # OPTIONAL fourth axis, at most one label, for items awaiting a human decision
  - needs-answer       # a blocking question; the PERSON is named by assignment or @mention
```

Design rules, stated so an agent can follow them:

- **Never encode state in a title prefix.** Titles are unqueryable prose; the failure is documented in §5.6.
- **Never add a label per person.** People are named by assignment or `@mention`; a per-person label is a taxonomy that grows with your address book.
- **Never add a label you will not remove.** A label that is only ever added is a tag, and tags accumulate without bound under agent operation.
- **Add a domain axis only if you will query it.** A fourth or fifth axis encoding project-specific semantics — which subsystem, which use case, how much ownership sensitivity a topic carries — is legitimate *if and only if* some procedure actually filters on it. Otherwise it is decoration that costs an agent a decision on every write.
- **Freeze the strings.** The label name is the machine contract; colour and description are for humans. Commit the vocabulary to the repository and sync it with a workflow, so it is versioned and reviewable rather than edited ad hoc in the UI.
- **Do not mirror the dependency graph in labels beyond one flag.** A `blocked` marker for humans is fine; the `blocked-by` edge is the source of truth [5], and duplicating structure into labels creates a second thing that can disagree.

---

## 10. Open questions

These are genuinely unresolved by the available evidence. Each is given a pragmatic default and the reasoning behind it.

**10.1 Does the Issues semantic index cover comment bodies, or only title and body?**
Lexical search returns text-match metadata for title, body and comment body, but no source located states whether the *semantic* index covers comments. This matters: if it does not, journaling in comments makes the conclusion technically stored and practically unfindable.
*Default:* assume title and body only. Edit every settled conclusion back into the issue body — and, per §7, into a file. That costs one edit and removes the risk entirely.

**10.2 Is there any measured evidence for allocation rules at solo-maintainer-plus-agents scale?**
No. The entire evidence base is either large public projects whose rules exist to manage anonymous inbound load, or one large multi-team organisation's 2023 internal handbook. The only cited practitioner operating at something like solo scale abandoned Discussions twice and reinstated them once.
*Default:* rely on the **structural** facts, which are scale-independent because they follow from the type system — no assignment, no Project membership, no milestone, no dependencies, no semantic search, no CLI outcome verb — and discount the **conventional** advice, which is not.

**10.3 Does a decision-record regime help or hurt agent success?**
The one rigorous measurement available says repository-level context files do not improve task success and cost over 20% more [72] — but it measured *preloaded overview files*, not decision records retrieved just-in-time by grep. Those are different interventions and the result does not transfer cleanly.
*Default:* keep ADRs, keep them out of the preloaded context, keep them few, and supersede rather than accrete. If you can measure it on your own workload, do; the field has not.

**10.4 Does the two-repository split beat the two-surface split for agents?**
One production existence proof [47], N=1, and its context is a large public project with a governance body rather than a solo maintainer.
*Default:* if you already maintain a natural "meta" repository, put deliberation there. If you do not, creating one purely for this is probably not worth the second clone an agent must know about — and *knowing about it* is exactly the cost §3.5 says files avoid.

**10.5 Will the preview Discussions CLI stabilise, and will the outcome verbs arrive?**
The command set is declared preview and subject to change [26], and the two verbs that record an outcome — close and mark-as-answer — are precisely the ones missing [27]. That asymmetry biases an unattended agent toward opening threads it cannot resolve.
*Default:* do not build unattended automation on it. Re-evaluate when close and mark-answer ship outside preview.

**10.6 Are cross-organization sub-issues actually usable?**
The September 2025 changelog states that sub-issues support cross-organization parent/child links [22], while the REST reference for adding a sub-issue still states the sub-issue must belong to the same repository owner as the parent [15]. That is an unresolved contradiction in GitHub's own documentation.
*Default:* verify empirically before relying on it, and do not design a cross-repository hierarchy that fails if the constraint is real.

**10.7 Will an atomic claim primitive land on Issues?**
No signal either way. The additive, non-erroring assignees endpoint is the current state, and it makes the parallel-agent race silent.
*Default:* one writer per repository. If you must run parallel agents on one repository, use a sidecar with a real claim (§4.3) and accept the second store — that is the one scenario where the sidecar clearly pays for itself.

**10.8 What is the right cap on agent-created items per session?**
The only published calibration point is a platform default of one issue and one discussion per workflow run [84], which is conservative by design for a hostile threat model rather than tuned for a trusted maintainer's own agent.
*Default:* two per unattended session, raised explicitly when the human asks for a decomposition. Pair it with a time-to-live on generated items, which the same platform offers and almost nobody enables.

---

## 11. References

1. [GitHub GraphQL API reference — objects, interfaces, unions and enums (Discussion, Issue, Assignable, Labelable, DiscussionStateReason)](https://docs.github.com/en/graphql/reference/objects#discussion)
2. [Assigning issues and pull requests to other GitHub users — GitHub Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/assigning-issues-and-pull-requests-to-other-github-users)
3. [GitHub GraphQL API reference — unions (ProjectV2ItemContent)](https://docs.github.com/en/graphql/reference/unions#projectv2itemcontent)
4. [Adding sub-issues — GitHub Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
5. [Dependencies on issues — GitHub Changelog, 2025-08-21](https://github.blog/changelog/2025-08-21-dependencies-on-issues/)
6. [Issue fields are now generally available — GitHub Changelog, 2026-07-02](https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/)
7. [Improved search for GitHub Issues is now generally available — GitHub Changelog, 2026-04-02](https://github.blog/changelog/2026-04-02-improved-search-for-github-issues-is-now-generally-available/)
8. [Configuring notifications — GitHub Docs](https://docs.github.com/en/subscriptions-and-notifications/get-started/configuring-notifications)
9. [Communicating on GitHub — GitHub Docs](https://docs.github.com/en/get-started/using-github/communicating-on-github)
10. [About discussions — GitHub Docs](https://docs.github.com/en/discussions/collaborating-with-your-community-using-discussions/about-discussions)
11. [About notifications — GitHub Docs](https://docs.github.com/en/account-and-profile/managing-subscriptions-and-notifications-on-github/setting-up-notifications/about-notifications)
12. [Searching discussions — GitHub Docs](https://docs.github.com/en/search-github/searching-on-github/searching-discussions)
13. [Multiple assignees for issues and pull requests now available in all repositories — GitHub Changelog, 2025-09-11](https://github.blog/changelog/2025-09-11-multiple-assignees-for-issues-and-pull-requests-now-available-in-all-repositories/)
14. [Evolving GitHub Issues and Projects — GitHub Changelog, 2025-04-09](https://github.blog/changelog/2025-04-09-evolving-github-issues-and-projects/)
15. [REST API endpoints for sub-issues — GitHub Docs](https://docs.github.com/en/rest/issues/sub-issues)
16. [REST API endpoints for issue dependencies — GitHub Docs](https://docs.github.com/en/rest/issues/issue-dependencies)
17. [GitHub Issues & Projects: REST API support for issue types — GitHub Changelog, 2025-03-18](https://github.blog/changelog/2025-03-18-github-issues-projects-rest-api-support-for-issue-types/)
18. [Managing issue types in an organization — GitHub Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/configuring-issues/managing-issue-types-in-an-organization)
19. [Using the GraphQL API for Discussions — GitHub Docs](https://docs.github.com/en/graphql/guides/using-the-graphql-api-for-discussions)
20. [Managing categories for discussions — GitHub Docs](https://docs.github.com/en/discussions/managing-discussions-for-your-community/managing-categories-for-discussions)
21. [Assign a discussion to a Project — GitHub community discussion #3775](https://github.com/orgs/community/discussions/3775)
22. [A REST API for GitHub Projects, sub-issues improvements, and more — GitHub Changelog, 2025-09-11](https://github.blog/changelog/2025-09-11-a-rest-api-for-github-projects-sub-issues-improvements-and-more/)
23. [Johanning J. "GitHub Discussions Migration Utility"](https://josh-ops.com/posts/github-discussions-migration-utility/)
24. [github/rest-api-description — the official OpenAPI description of the GitHub REST API](https://github.com/github/rest-api-description)
25. [REST API for discussions appears to be missing — github/docs issue #44098](https://github.com/github/docs/issues/44098)
26. [GitHub CLI v2.94.0 release notes](https://github.com/cli/cli/releases/tag/v2.94.0)
27. [gh discussion — GitHub CLI manual](https://cli.github.com/manual/gh_discussion)
28. [List, view, and create discussions in GitHub CLI — GitHub Changelog, 2026-06-10](https://github.blog/changelog/2026-06-10-list-view-and-create-discussions-in-github-cli/)
29. [gh issue list — GitHub CLI manual](https://cli.github.com/manual/gh_issue_list)
30. [gh discussion list — GitHub CLI manual](https://cli.github.com/manual/gh_discussion_list)
31. [github/github-mcp-server — README and toolset inventory](https://github.com/github/github-mcp-server)
32. [github/github-mcp-server — remote server documentation](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)
33. [About GitHub Copilot cloud agent — GitHub Docs](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent)
34. [Rate limits and node limits for the GraphQL API — GitHub Docs](https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-graphql-api)
35. [First party discussions support — cli/cli issue #9644](https://github.com/cli/cli/issues/9644)
36. [Manage sub-issues, types, and dependencies from GitHub CLI — GitHub Changelog, 2026-06-10](https://github.blog/changelog/2026-06-10-manage-sub-issues-types-and-dependencies-from-github-cli/)
37. [Add Issues 2.0 support: issue types, sub-issues, and relationships — cli/cli pull request #13057](https://github.com/cli/cli/pull/13057)
38. [beads — distributed graph issue tracker for AI agents](https://github.com/gastownhall/beads)
39. [beads — Dependencies and Gates (docs/core-concepts/dependencies.md)](https://github.com/gastownhall/beads/blob/main/docs/core-concepts/dependencies.md)
40. [beads — Agent Coordination (docs/multi-agent/coordination.md)](https://github.com/gastownhall/beads/blob/main/docs/multi-agent/coordination.md)
41. [Sarkar D. Before the Pull Request: Mining Multi-Agent Coordination. arXiv:2606.19616 (preprint; single author; evaluates the tool it proposes)](https://arxiv.org/abs/2606.19616)
42. [Bull I. "Beads — Memory for your Agent"](https://ianbull.com/posts/beads/)
43. [An open-source spec for Codex orchestration: Symphony — OpenAI, 2026-04-27](https://openai.com/index/open-source-codex-orchestration-symphony/)
44. [tailwindlabs/tailwindcss — .github/ISSUE_TEMPLATE/config.yml](https://github.com/tailwindlabs/tailwindcss/blob/main/.github/ISSUE_TEMPLATE/config.yml)
45. [Configuring issue templates for your repository — GitHub Docs](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository)
46. [github/how-engineering-communicates — how-github-engineering-communicates.md (GitHub Engineering, 2023)](https://github.com/github/how-engineering-communicates/blob/main/how-github-engineering-communicates.md)
47. [home-assistant/architecture — a deliberation repository with an adr/ folder](https://github.com/home-assistant/architecture)
48. [langchain-ai/langchain — Discussions (abandonment in place)](https://github.com/langchain-ai/langchain/discussions)
49. [suzuki-shunsuke. "We don't use GitHub Discussions in our OSS projects anymore" (2024-11-30)](https://github.com/suzuki-shunsuke/suzuki-shunsuke/issues/2)
50. [Beman Project. "Disabling the GitHub Discussions feature in favor of discourse" (2024-05-14)](https://discourse.bemanproject.org/t/disabling-the-github-discussions-feature-in-favor-of-discourse/107)
51. [rust-lang/rfcs — RFC as a pull request against a Markdown file](https://github.com/rust-lang/rfcs)
52. [withastro/roadmap — a four-stage RFC process across Discussions, Issues, pull requests and merged Markdown](https://github.com/withastro/roadmap)
53. [withastro/roadmap — proposals/0018-astro-request.md (backlink in frontmatter)](https://github.com/withastro/roadmap/blob/main/proposals/0018-astro-request.md)
54. [kubernetes/enhancements — keps/README.md (tracking-issue-number filename prefix)](https://github.com/kubernetes/enhancements/blob/master/keps/README.md)
55. [angular/angular — Discussions, RFCs category](https://github.com/angular/angular/discussions/categories/rfcs)
56. [Copilot coding agent for Jira — GitHub Changelog, 2026-03-05](https://github.blog/changelog/2026-03-05-copilot-coding-agent-for-jira-public-preview/)
57. [Research, plan, and code with Copilot cloud agent — GitHub Changelog, 2026-04-01](https://github.blog/changelog/2026-04-01-research-plan-and-code-with-copilot-cloud-agent/)
58. [github/spec-kit — templates/spec-template.md ([NEEDS CLARIFICATION] marker convention)](https://github.com/github/spec-kit/blob/main/templates/spec-template.md)
59. [probot/no-response — archived in 2021; its README disclaims the app](https://github.com/probot/no-response)
60. [Buck S. "Codeless Contributions with GitHub Issue Forms" (2021-10-14)](https://stefanbuck.com/blog/codeless-contributions-with-github-issue-forms)
61. [stefanbuck/github-issue-parser](https://github.com/stefanbuck/github-issue-parser)
62. [REST API endpoints for notifications — GitHub Docs](https://docs.github.com/en/rest/activity/notifications)
63. [Allow/force Copilot to ask clarification questions — GitHub community discussion #169482](https://github.com/orgs/community/discussions/169482)
64. [Issue types for personal repos — GitHub community discussion #175785](https://github.com/orgs/community/discussions/175785)
65. [Anthropic. "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
66. [Assigning and completing issues with coding agent in GitHub Copilot — The GitHub Blog](https://github.blog/ai-and-ml/github-copilot/assigning-and-completing-issues-with-coding-agent-in-github-copilot/)
67. [MADR — template/adr-template.md (status frontmatter, including "superseded by ADR-0123")](https://github.com/adr/madr/blob/develop/template/adr-template.md)
68. [MADR 4.0.0 release (2024-09-17)](https://github.com/adr/madr/releases/tag/4.0.0)
69. [MADR documentation index — the docs/decisions convention and the NNNN filename pattern](https://github.com/adr/madr/blob/develop/docs/index.md)
70. [addyosmani/agent-skills — skills/documentation-and-adrs/SKILL.md](https://github.com/addyosmani/agent-skills/blob/main/skills/documentation-and-adrs/SKILL.md)
71. [ADR tooling index — adr.github.io](https://adr.github.io/adr-tooling/)
72. [Gloaguen T, Mündler N, Müller M, Raychev V, Vechev M. Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents? arXiv:2602.11988 (2026)](https://arxiv.org/abs/2602.11988)
73. [AGENTS.md — an open format for guiding coding agents](https://agents.md/)
74. [Copilot coding agent now supports AGENTS.md custom instructions — GitHub Changelog, 2025-08-28](https://github.blog/changelog/2025-08-28-copilot-coding-agent-now-supports-agents-md-custom-instructions/)
75. [beads — AGENTS.md (machine-managed region markers; the "Landing the Plane" session-completion checklist)](https://github.com/gastownhall/beads/blob/main/AGENTS.md)
76. [Holbreich A. "Beads: issue tracking for agent work" (2026-05-05)](https://alexander.holbreich.org/posts/2026/beads-ai-native-issue-tracking/)
77. [Wang D, Kondo M, Kamei Y, Kula RG, Ubayashi N. When Conversations Turn Into Work: A Taxonomy of Converted Discussions and Issues in GitHub. Empirical Software Engineering, 2023. arXiv:2307.07117](https://arxiv.org/abs/2307.07117)
78. [Moderating discussions — GitHub Docs](https://docs.github.com/en/discussions/managing-discussions-for-your-community/moderating-discussions)
79. [Creating an issue (including "Creating an issue from discussion") — GitHub Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue)
80. [Deprecation of bulk conversion of issues to discussions via labels — GitHub Changelog, 2025-05-22](https://github.blog/changelog/2025-05-22-deprecation-of-bulk-conversion-of-issues-to-discussions-via-labels/)
81. [Allow converting Discussion to Issue — github/feedback issue #3297](https://github.com/github/feedback/issues/3297)
82. [Convert Discussion into Issue — GitHub community discussion #2861](https://github.com/orgs/community/discussions/2861)
83. [Restrict the ability to close discussion to maintainers — GitHub community discussion #52698](https://github.com/orgs/community/discussions/52698)
84. [Safe Outputs — GitHub Agentic Workflows documentation](https://github.github.com/gh-aw/reference/safe-outputs/)
85. [Stenberg D. "Death by a thousand slops" (2025-07-14)](https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/)
86. [The Register. "Curl shutters bug bounty program to remove incentive for submitting AI slop" (2026-01-21)](https://www.theregister.com/2026/01/21/curl_ends_bug_bounty/)
87. [Labels and Triage: How We Organize Issues and PRs — gastown discussion #1399](https://github.com/steveyegge/gastown/discussions/1399)

---

### Note on sources deliberately not cited

Four widely repeated figures were checked and rejected, and are named here so they are not reintroduced: a "40–70% of Kanban cards are stale" statistic, which traces only to vendor marketing; a "60–80% of vulnerability submissions are invalid" figure, which traces to a vendor's own product pages for the service that filters them; a specific percentage drop in agent success from LLM-generated context files, which is a secondary-coverage embellishment of a paper whose own framing is more cautious [72]; and a numeric range for context-length recall degradation attributed to unnamed syntheses. A documentation URL that GitHub's own API error bodies point at for REST discussions endpoints returns HTTP 404; that 404 is itself the evidence for §4.1(a) and is therefore described in the text rather than listed as a reference.
