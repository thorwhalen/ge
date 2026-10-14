# ge.context

Context assembly and rendering.

Combines issue/PR data, comments, media, and analysis into a single
structured context document that an AI agent can consume.

### Functions

| [`prepare_discussion`](#ge.context.prepare_discussion)(repo, number, \*[, ...])        | Prepare full context for a GitHub Discussion.                 |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------|
| [`prepare_issue`](#ge.context.prepare_issue)(repo, number, \*[, output_dir, ...]) | Prepare full context for working on a GitHub issue.           |
| [`prepare_pr`](#ge.context.prepare_pr)(repo, number, \*[, output_dir, ...])    | Prepare full context for working on or reviewing a GitHub PR. |
| [`render_discussion_context`](#ge.context.render_discussion_context)(ctx)                     | Render discussion context as a structured markdown document.  |
| [`render_issue_context`](#ge.context.render_issue_context)(ctx)                          | Render issue context as a structured markdown document.       |
| [`render_pr_context`](#ge.context.render_pr_context)(ctx)                             | Render PR context as a structured markdown document.          |

### ge.context.prepare_discussion(repo, number, , output_dir=None, download_media_flag=True, describe_media=True)

Prepare full context for a GitHub Discussion.

Fetches the discussion and its comments via GraphQL, downloads media,
and writes a context document.

```pycon
>>> # ctx = prepare_discussion('owner/repo', 5)
```

### ge.context.prepare_issue(repo, number, , output_dir=None, download_media_flag=True, describe_media=True)

Prepare full context for working on a GitHub issue.

Fetches the issue, comments, media, and performs staleness analysis.
Writes a context document and manifest to output_dir.

When `describe_media` is True (default) and the `anthropic` package
is installed with `ANTHROPIC_API_KEY` set, downloaded images are sent
to the Claude API for automated description.  The description is included
in the context document so the agent has visual context without manual
image pasting.

Returns dict with all assembled context.

```pycon
>>> # ctx = prepare_issue('owner/repo', 42)
```

### ge.context.prepare_pr(repo, number, , output_dir=None, download_media_flag=True, include_diff=True, describe_media=True)

Prepare full context for working on or reviewing a GitHub PR.

```pycon
>>> # ctx = prepare_pr('owner/repo', 7)
```

### ge.context.render_discussion_context(ctx)

Render discussion context as a structured markdown document.

### ge.context.render_issue_context(ctx)

Render issue context as a structured markdown document.

### ge.context.render_pr_context(ctx)

Render PR context as a structured markdown document.
