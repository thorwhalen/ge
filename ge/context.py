"""Context assembly and rendering.

Combines issue/PR data, comments, media, and analysis into a single
structured context document that an AI agent can consume.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from ge.github import (
    get_issue,
    get_pr,
    get_comments,
    get_review_comments,
    get_reviews,
    get_pr_diff,
    get_discussion,
)
from ge.media import process_all_media
from ge.analysis import analyze_issue, analyze_pr
from ge.util import ensure_dir, parse_repo_spec


def prepare_issue(repo, number, *, output_dir=".ge", download_media_flag=True):
    """Prepare full context for working on a GitHub issue.

    Fetches the issue, comments, media, and performs staleness analysis.
    Writes a context document and manifest to output_dir.

    Returns dict with all assembled context.

    >>> # ctx = prepare_issue('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    out = ensure_dir(output_dir)

    issue = get_issue(repo, number)
    comments = get_comments(repo, number)
    analysis = analyze_issue(repo, number)

    # Collect all markdown text for media extraction
    body = issue.get("body") or ""
    comment_bodies = [c.get("body", "") for c in comments]
    all_markdown = body + "\n" + "\n".join(comment_bodies)

    # Download media
    media_result = None
    if download_media_flag:
        media_dir = str(out / "media")
        media_result = process_all_media(all_markdown, media_dir)

    context = {
        "kind": "issue",
        "repo": f"{owner}/{name}",
        "number": number,
        "url": issue.get("html_url", ""),
        "title": issue.get("title", ""),
        "state": issue.get("state", ""),
        "author": issue.get("user", {}).get("login", ""),
        "created_at": issue.get("created_at", ""),
        "updated_at": issue.get("updated_at", ""),
        "labels": [l["name"] for l in issue.get("labels", [])],
        "assignees": [a["login"] for a in issue.get("assignees", [])],
        "body": media_result["rewritten_markdown"] if media_result else body,
        "original_body": body,
        "comments": [
            {
                "author": c.get("user", {}).get("login", ""),
                "created_at": c.get("created_at", ""),
                "body": c.get("body", ""),
            }
            for c in comments
        ],
        "analysis": analysis,
        "media": {
            "manifest": media_result["manifest"] if media_result else [],
            "images": media_result["images"] if media_result else [],
            "video_frames": media_result["video_frames"] if media_result else {},
            "all_visual_files": media_result["all_visual_files"]
            if media_result
            else [],
        },
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write context JSON
    context_file = out / f"issue_{number}_context.json"
    context_file.write_text(json.dumps(context, indent=2))

    # Render human/agent-readable markdown
    rendered = render_issue_context(context)
    md_file = out / f"issue_{number}_context.md"
    md_file.write_text(rendered)

    return context


def prepare_pr(
    repo, number, *, output_dir=".ge", download_media_flag=True, include_diff=True
):
    """Prepare full context for working on or reviewing a GitHub PR.

    >>> # ctx = prepare_pr('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    out = ensure_dir(output_dir)

    pr = get_pr(repo, number)
    comments = get_comments(repo, number)
    review_comments = get_review_comments(repo, number)
    reviews = get_reviews(repo, number)
    analysis = analyze_pr(repo, number)

    diff = get_pr_diff(repo, number) if include_diff else None

    # Collect all markdown for media extraction
    body = pr.get("body") or ""
    all_bodies = [body] + [c.get("body", "") for c in comments]
    all_bodies += [c.get("body", "") for c in review_comments]
    all_markdown = "\n".join(all_bodies)

    media_result = None
    if download_media_flag:
        media_dir = str(out / "media")
        media_result = process_all_media(all_markdown, media_dir)

    context = {
        "kind": "pr",
        "repo": f"{owner}/{name}",
        "number": number,
        "url": pr.get("html_url", ""),
        "title": pr.get("title", ""),
        "state": pr.get("state", ""),
        "merged": pr.get("merged", False),
        "draft": pr.get("draft", False),
        "author": pr.get("user", {}).get("login", ""),
        "head_branch": pr.get("head", {}).get("ref", ""),
        "base_branch": pr.get("base", {}).get("ref", ""),
        "created_at": pr.get("created_at", ""),
        "updated_at": pr.get("updated_at", ""),
        "labels": [l["name"] for l in pr.get("labels", [])],
        "body": media_result["rewritten_markdown"] if media_result else body,
        "original_body": body,
        "comments": [
            {
                "author": c.get("user", {}).get("login", ""),
                "created_at": c.get("created_at", ""),
                "body": c.get("body", ""),
            }
            for c in comments
        ],
        "review_comments": [
            {
                "author": c.get("user", {}).get("login", ""),
                "path": c.get("path", ""),
                "line": c.get("line"),
                "body": c.get("body", ""),
            }
            for c in review_comments
        ],
        "reviews": [
            {
                "author": r.get("user", {}).get("login", ""),
                "state": r.get("state", ""),
                "body": r.get("body", ""),
            }
            for r in reviews
        ],
        "diff": diff,
        "analysis": analysis,
        "media": {
            "manifest": media_result["manifest"] if media_result else [],
            "images": media_result["images"] if media_result else [],
            "video_frames": media_result["video_frames"] if media_result else {},
            "all_visual_files": media_result["all_visual_files"]
            if media_result
            else [],
        },
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }

    context_file = out / f"pr_{number}_context.json"
    context_file.write_text(json.dumps(context, indent=2, default=str))

    rendered = render_pr_context(context)
    md_file = out / f"pr_{number}_context.md"
    md_file.write_text(rendered)

    return context


# ---------------------------------------------------------------------------
# Rendering: structured markdown for agent consumption
# ---------------------------------------------------------------------------


def render_issue_context(ctx):
    """Render issue context as a structured markdown document."""
    lines = []
    a = lines.append

    a(f"# Issue #{ctx['number']}: {ctx['title']}")
    a(f"")
    a(f"**Repo:** {ctx['repo']}  ")
    a(f"**URL:** {ctx['url']}  ")
    a(f"**State:** {ctx['state']}  ")
    a(f"**Author:** @{ctx['author']}  ")
    a(f"**Created:** {ctx['created_at']}  ")
    a(f"**Labels:** {', '.join(ctx['labels']) or 'none'}")
    a(f"")

    # Analysis / freshness
    analysis = ctx.get("analysis", {})
    if analysis.get("signals"):
        a(f"## Freshness Analysis")
        a(f"")
        a(f"**Recommendation:** `{analysis.get('recommendation', '?')}`")
        a(f"")
        for sig in analysis["signals"]:
            a(f"- {sig}")
        a(f"")
        if analysis.get("related_prs"):
            a("**Related PRs:**")
            for pr in analysis["related_prs"]:
                a(f"- #{pr['number']} ({pr['state']}): {pr['title']} — {pr['url']}")
            a("")
        if analysis.get("related_commits"):
            a("**Related commits:**")
            for c in analysis["related_commits"]:
                a(f"- `{c['sha']}` {c['message']} ({c['date']})")
            a("")

    # Body
    a(f"## Issue Body")
    a(f"")
    a(ctx.get("body", "*empty*"))
    a(f"")

    # Comments
    if ctx.get("comments"):
        a(f"## Comments ({len(ctx['comments'])})")
        a(f"")
        for i, c in enumerate(ctx["comments"], 1):
            a(f"### Comment {i} — @{c['author']} ({c['created_at']})")
            a(f"")
            a(c["body"])
            a(f"")

    # Media
    media = ctx.get("media", {})
    if media.get("all_visual_files"):
        a(f"## Media Files")
        a(f"")
        a(f"The following visual files were downloaded from this issue.")
        a(f"**To give the agent visual context, paste these images into the chat.**")
        a(f"")
        for f in media["all_visual_files"]:
            a(f"- `{f}`")
        a(f"")
        if media.get("video_frames"):
            a("Video frames extracted:")
            for vid, frames in media["video_frames"].items():
                a(f"- `{vid}` → {len(frames)} frames")
            a("")

    return "\n".join(lines)


def render_pr_context(ctx):
    """Render PR context as a structured markdown document."""
    lines = []
    a = lines.append

    a(f"# PR #{ctx['number']}: {ctx['title']}")
    a(f"")
    a(f"**Repo:** {ctx['repo']}  ")
    a(f"**URL:** {ctx['url']}  ")
    a(
        f"**State:** {ctx['state']} {'(MERGED)' if ctx.get('merged') else ''} {'(DRAFT)' if ctx.get('draft') else ''}  "
    )
    a(f"**Author:** @{ctx['author']}  ")
    a(
        f"**Branch:** `{ctx.get('head_branch', '?')}` → `{ctx.get('base_branch', '?')}`  "
    )
    a(f"**Created:** {ctx['created_at']}  ")
    a(f"**Labels:** {', '.join(ctx['labels']) or 'none'}")
    a(f"")

    # Analysis
    analysis = ctx.get("analysis", {})
    if analysis.get("signals"):
        a(f"## PR Analysis")
        a(f"")
        a(f"**Recommendation:** `{analysis.get('recommendation', '?')}`")
        a(f"")
        for sig in analysis["signals"]:
            a(f"- {sig}")
        a(f"")
        if analysis.get("linked_issues"):
            a(
                f"**Linked issues:** {', '.join(f'#{n}' for n in analysis['linked_issues'])}"
            )
            a(f"")

    # Body
    a(f"## PR Description")
    a(f"")
    a(ctx.get("body", "*empty*"))
    a(f"")

    # Reviews
    if ctx.get("reviews"):
        a(f"## Reviews")
        a(f"")
        for r in ctx["reviews"]:
            a(f"- **@{r['author']}**: {r['state']}")
            if r.get("body"):
                a(f"  > {r['body'][:200]}")
        a(f"")

    # Review comments (inline code comments)
    if ctx.get("review_comments"):
        a(f"## Inline Review Comments ({len(ctx['review_comments'])})")
        a(f"")
        for rc in ctx["review_comments"]:
            line_info = f" (line {rc['line']})" if rc.get("line") else ""
            a(f"**@{rc['author']}** on `{rc['path']}`{line_info}:")
            a(f"> {rc['body'][:300]}")
            a(f"")

    # Comments
    if ctx.get("comments"):
        a(f"## Discussion Comments ({len(ctx['comments'])})")
        a(f"")
        for i, c in enumerate(ctx["comments"], 1):
            a(f"### Comment {i} — @{c['author']} ({c['created_at']})")
            a(f"")
            a(c["body"])
            a(f"")

    # Diff (potentially large, include at end)
    if ctx.get("diff"):
        a(f"## Diff")
        a(f"")
        a("```diff")
        # Truncate very large diffs
        diff = ctx["diff"]
        if len(diff) > 50_000:
            a(diff[:50_000])
            a(f"\n... (truncated, full diff is {len(diff)} chars)")
        else:
            a(diff)
        a("```")
        a(f"")

    # Media
    media = ctx.get("media", {})
    if media.get("all_visual_files"):
        a(f"## Media Files")
        a(f"")
        a(f"**To give the agent visual context, paste these images into the chat.**")
        a(f"")
        for f in media["all_visual_files"]:
            a(f"- `{f}`")
        a(f"")

    return "\n".join(lines)


def prepare_discussion(repo, number, *, output_dir=".ge", download_media_flag=True):
    """Prepare full context for a GitHub Discussion.

    Fetches the discussion and its comments via GraphQL, downloads media,
    and writes a context document.

    >>> # ctx = prepare_discussion('owner/repo', 5)
    """
    owner, name = parse_repo_spec(repo)
    out = ensure_dir(output_dir)

    disc = get_discussion(repo, number)
    if disc is None:
        raise ValueError(f"Discussion #{number} not found in {repo}")

    body = disc.get("body") or ""
    comment_nodes = disc.get("comments", {}).get("nodes", [])
    comment_bodies = [c.get("body", "") for c in comment_nodes]
    all_markdown = body + "\n" + "\n".join(comment_bodies)

    media_result = None
    if download_media_flag:
        media_dir = str(out / "media")
        media_result = process_all_media(all_markdown, media_dir)

    context = {
        "kind": "discussion",
        "repo": f"{owner}/{name}",
        "number": number,
        "url": disc.get("url", ""),
        "title": disc.get("title", ""),
        "author": (disc.get("author") or {}).get("login", ""),
        "created_at": disc.get("createdAt", ""),
        "body": media_result["rewritten_markdown"] if media_result else body,
        "original_body": body,
        "comments": [
            {
                "author": (c.get("author") or {}).get("login", ""),
                "created_at": c.get("createdAt", ""),
                "body": c.get("body", ""),
            }
            for c in comment_nodes
        ],
        "media": {
            "manifest": media_result["manifest"] if media_result else [],
            "images": media_result["images"] if media_result else [],
            "video_frames": media_result["video_frames"] if media_result else {},
            "all_visual_files": media_result["all_visual_files"]
            if media_result
            else [],
        },
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }

    context_file = out / f"discussion_{number}_context.json"
    context_file.write_text(json.dumps(context, indent=2))

    rendered = render_discussion_context(context)
    md_file = out / f"discussion_{number}_context.md"
    md_file.write_text(rendered)

    return context


def render_discussion_context(ctx):
    """Render discussion context as a structured markdown document."""
    lines = []
    a = lines.append

    a(f"# Discussion #{ctx['number']}: {ctx['title']}")
    a("")
    a(f"**Repo:** {ctx['repo']}  ")
    a(f"**URL:** {ctx['url']}  ")
    a(f"**Author:** @{ctx['author']}  ")
    a(f"**Created:** {ctx['created_at']}")
    a("")

    a("## Discussion Body")
    a("")
    a(ctx.get("body", "*empty*"))
    a("")

    if ctx.get("comments"):
        a(f"## Comments ({len(ctx['comments'])})")
        a("")
        for i, c in enumerate(ctx["comments"], 1):
            a(f"### Comment {i} — @{c['author']} ({c['created_at']})")
            a("")
            a(c["body"])
            a("")

    media = ctx.get("media", {})
    if media.get("all_visual_files"):
        a("## Media Files")
        a("")
        a("**To give the agent visual context, paste these images into the chat.**")
        a("")
        for f in media["all_visual_files"]:
            a(f"- `{f}`")
        a("")

    return "\n".join(lines)
