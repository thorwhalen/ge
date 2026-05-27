"""CLI entry point for ge.

Usage::

    python -m ge prepare owner/repo --number 42
    python -m ge prepare https://github.com/owner/repo/issues/42
    python -m ge analyze-issue owner/repo 42
    python -m ge analyze-pr owner/repo 7
"""

import json

import argh


def prepare(
    url_or_spec: str,
    number: int = None,
    *,
    output_dir: str = None,
    describe_media: bool = True,
):
    """Prepare full context for a GitHub issue or PR.

    Fetches all data, downloads media, runs freshness analysis,
    and writes a structured context document to output_dir.

    When --describe-media is enabled (default), images are described via
    the Claude API for automated visual context. Requires: pip install anthropic
    and ANTHROPIC_API_KEY set.

    By default, context is written to ~/.cache/ge/<owner>/<repo>/<kind>_<number>/.

    Examples:
        ge prepare owner/repo --number 42
        ge prepare https://github.com/owner/repo/pull/7
        ge prepare owner/repo --number 42 -d   # disable image descriptions
    """
    from ge import prepare as _prepare

    kwargs = {"describe_media": describe_media}
    if output_dir is not None:
        kwargs["output_dir"] = output_dir
    ctx = _prepare(url_or_spec, number, **kwargs)
    kind = ctx["kind"]
    num = ctx["number"]
    actual_dir = ctx.get("output_dir", output_dir or "?")

    # Summary output
    print(f"\n{'=' * 60}")
    print(f"Prepared {kind} #{num}: {ctx['title']}")
    print(f"{'=' * 60}")

    analysis = ctx.get("analysis", {})
    rec = analysis.get("recommendation", "?")
    print(f"\nRecommendation: {rec}")
    for sig in analysis.get("signals", []):
        print(f"  • {sig}")

    media = ctx.get("media", {})
    n_images = len(media.get("images", []))
    n_videos = len(media.get("video_frames", {}))
    if n_images or n_videos:
        print(f"\nMedia: {n_images} image(s), {n_videos} video(s)")
        if media.get("image_descriptions"):
            print("Image descriptions: included (AI-generated via Claude API)")
        elif media.get("all_visual_files"):
            print(
                "Image descriptions: not available (install anthropic + set ANTHROPIC_API_KEY)"
            )
        if media.get("all_visual_files"):
            print("Visual files:")
            for f in media["all_visual_files"]:
                print(f"  {f}")

    md_file = f"{actual_dir}/{kind}_{num}_context.md"
    json_file = f"{actual_dir}/{kind}_{num}_context.json"
    print(f"\nContext files:")
    print(f"  Markdown: {md_file}")
    print(f"  JSON:     {json_file}")
    print()


def analyze_issue(repo: str, number: int):
    """Analyze a GitHub issue for staleness and relevance (no media download)."""
    from ge.analysis import analyze_issue as _analyze

    result = _analyze(repo, number)
    print(json.dumps(result, indent=2, default=str))


def analyze_pr(repo: str, number: int):
    """Analyze a GitHub PR for review state and merge readiness."""
    from ge.analysis import analyze_pr as _analyze

    result = _analyze(repo, number)
    print(json.dumps(result, indent=2, default=str))


def fetch_issue(repo: str, number: int):
    """Fetch and display raw issue data (JSON)."""
    from ge.github import get_issue

    print(json.dumps(get_issue(repo, number), indent=2))


def fetch_pr(repo: str, number: int):
    """Fetch and display raw PR data (JSON)."""
    from ge.github import get_pr

    print(json.dumps(get_pr(repo, number), indent=2))


def fetch_discussion(repo: str, number: int):
    """Fetch and display a GitHub Discussion (JSON)."""
    from ge.github import get_discussion

    result = get_discussion(repo, number)
    print(json.dumps(result, indent=2))


def prepare_discussion(repo: str, number: int, *, output_dir: str = None):
    """Prepare full context for a GitHub Discussion.

    Fetches the discussion, comments, downloads media, and writes
    a structured context document to output_dir.

    By default, context is written to ~/.cache/ge/<owner>/<repo>/discussion_<number>/.

    Examples:
        ge prepare-discussion owner/repo --number 5
    """
    from ge.context import prepare_discussion as _prepare

    kwargs = {}
    if output_dir is not None:
        kwargs["output_dir"] = output_dir
    ctx = _prepare(repo, number, **kwargs)
    num = ctx["number"]
    actual_dir = ctx.get("output_dir", output_dir or "?")

    print(f"\n{'=' * 60}")
    print(f"Prepared discussion #{num}: {ctx['title']}")
    print(f"{'=' * 60}")

    media = ctx.get("media", {})
    n_images = len(media.get("images", []))
    if n_images:
        print(f"\nMedia: {n_images} image(s)")

    md_file = f"{actual_dir}/discussion_{num}_context.md"
    json_file = f"{actual_dir}/discussion_{num}_context.json"
    print(f"\nContext files:")
    print(f"  Markdown: {md_file}")
    print(f"  JSON:     {json_file}")
    print()


def media(markdown_file: str, *, output_dir: str = None):
    """Download media from a markdown file (for standalone use).

    By default, media is saved to ~/.cache/ge/media/.
    """
    from pathlib import Path
    from ge.media import process_all_media

    if output_dir is None:
        output_dir = str(Path.home() / ".cache" / "ge" / "media")
    text = Path(markdown_file).read_text()
    result = process_all_media(text, output_dir)
    print(f"Downloaded {len(result['images'])} image(s)")
    for entry in result["manifest"]:
        status = "✓" if entry["status"] == "ok" else "✗"
        print(f"  {status} {entry['kind']}: {entry['url']}")
        if entry["local_path"]:
            print(f"    → {entry['local_path']}")


def video_frames(
    video_path: str,
    *,
    n_frames: int = 5,
    output_dir: str = None,
    mode: str = "scene",
    scene_threshold: float = 0.3,
):
    """Extract frames from a video file.

    Modes: 'scene' (default) detects visual changes; 'uniform' extracts evenly-spaced frames.
    """
    from ge.media import extract_video_frames

    frames = extract_video_frames(
        video_path,
        n_frames=n_frames,
        output_dir=output_dir,
        mode=mode,
        scene_threshold=scene_threshold,
    )
    print(f"Extracted {len(frames)} frames:")
    for f in frames:
        print(f"  {f}")


def describe_images(
    *image_paths: str,
    prompt: str = "Describe what you see in these images in detail. If they appear to be screenshots of a bug or UI issue, describe the problem visible.",
    model: str = "claude-sonnet-4-5-20250514",
):
    """Describe images using the Claude API (vision).

    Requires: pip install anthropic, and ANTHROPIC_API_KEY set.

    Examples:
        ge describe-images screenshot.png error.jpg
        ge describe-images frame1.jpg frame2.jpg --prompt "What changed between these frames?"
    """
    from ge.media import describe_images as _describe

    description = _describe(*image_paths, prompt=prompt, model=model)
    print(description)


def copy_images(
    *image_paths: str,
    tile: str = "3x",
    geometry: str = "800x600+10+10",
    montage_path: str = None,
):
    """Create a montage of images and copy to clipboard (macOS).

    Combines images into a grid and copies to clipboard for pasting
    into Claude Code with Cmd+V. Requires ImageMagick.

    Examples:
        ge copy-images screenshot1.png screenshot2.png
        ge copy-images media/*.jpg --tile 4x
    """
    from ge.media import copy_images_to_clipboard

    kwargs = {}
    if montage_path is not None:
        kwargs["montage_path"] = montage_path
    path = copy_images_to_clipboard(
        *image_paths, tile=tile, geometry=geometry, **kwargs
    )
    print(f"Montage saved to: {path}")
    print("Copied to clipboard. Paste into Claude Code with Cmd+V.")


def resolve(target: str, *, current_repo: str = None):
    """Resolve a flexible target reference into a structured result.

    Accepts a GitHub URL, folder path, bare number (#42), or owner/repo#42.
    Shows what was resolved and whether pre-prepared context exists.

    Examples:
        ge resolve https://github.com/owner/repo/issues/42
        ge resolve ~/.cache/ge/owner/repo/issue_42
        ge resolve '#42' --current-repo owner/repo
        ge resolve 'owner/repo#42'
    """
    from ge.util import resolve_target

    result = resolve_target(target, current_repo=current_repo)
    print(json.dumps(result, indent=2))


def install_skills(*, target_dir: str = None):
    """Install ge skills as symlinks in ~/.claude/skills/.

    Creates symlinks so Claude Code can discover ge skills globally.
    Run without arguments to install to the default location.

    Examples:
        ge install-skills
        ge install-skills --target-dir ~/.claude/skills
    """
    from ge import install_skills as _install

    _install(target_dir=target_dir)


# ---------------------------------------------------------------------------
# Memory layer (GitHub-backed durable memory for autonomous execution)
# ---------------------------------------------------------------------------


def roadmap_show(repo: str, issue: int):
    """Show parsed roadmap tasks from a roadmap issue (JSON)."""
    from ge.memory import cli_roadmap_show

    print(cli_roadmap_show(repo, issue))


def roadmap_next(repo: str, issue: int):
    """Print the id of the next todo task in the roadmap (or empty)."""
    from ge.memory import cli_roadmap_next

    nxt = cli_roadmap_next(repo, issue)
    if nxt:
        print(nxt)


def roadmap_set(repo: str, issue: int, task_id: str, state: str):
    """Set a roadmap task's state (todo|doing|done)."""
    from ge.memory import cli_roadmap_set

    print(cli_roadmap_set(repo, issue, task_id, state))


def roadmap_append(repo: str, issue: int, title: str):
    """Append a new todo task to the roadmap."""
    from ge.memory import cli_roadmap_append

    print(cli_roadmap_append(repo, issue, title))


def decision_log(
    repo: str, target: int, summary: str, *, rationale: str = ""
):
    """Append a decision-tagged comment to an issue or PR."""
    from ge.memory import cli_decision_log

    print(cli_decision_log(repo, target, summary, rationale=rationale))


def decisions_show(repo: str, target: int):
    """Show decisions logged on an issue or PR (JSON)."""
    from ge.memory import cli_decisions_show

    print(cli_decisions_show(repo, target))


def triage_show(repo: str, issue: int):
    """Show the triage backlog from a tracking issue (JSON, in order)."""
    from ge.memory import cli_triage_show

    print(cli_triage_show(repo, issue))


def triage_set(
    repo: str,
    issue: int,
    ref: str,
    verdict: str,
    *,
    order: int = 0,
    rationale: str = "",
):
    """Add or update a triage entry (ref is 'owner/repo#N')."""
    from ge.memory import cli_triage_set

    print(
        cli_triage_set(
            repo, issue, ref, verdict, order=order, rationale=rationale
        )
    )


def check_requirements(*, project_scope: bool = False):
    """Check gh CLI installation, auth, and (optionally) project scope."""
    from ge.memory import cli_check_requirements

    print(cli_check_requirements(project_scope=project_scope))


# ---------------------------------------------------------------------------
# Autonomous runner (Layer 3)
# ---------------------------------------------------------------------------


def run_roadmap(
    repo: str,
    roadmap_issue: int,
    *,
    mode: str = "auto",
    decisions_target: int = None,
    max_sessions: int = 50,
    cwd: str = None,
):
    """Launch claude in a loop to drive a roadmap issue to completion.

    Each iteration is one headless `claude -p` invocation that performs
    one roadmap step. State persists between iterations via the
    GitHub-backed roadmap issue.

    Modes:
        auto   — `--permission-mode auto` (default; safer)
        bypass — `--dangerously-skip-permissions` (on request only)

    Examples:
        ge run-roadmap owner/repo 1
        ge run-roadmap owner/repo 1 --mode bypass --max-sessions 20
    """
    from ge.run import cli_run_roadmap

    print(
        cli_run_roadmap(
            repo,
            roadmap_issue,
            mode=mode,
            decisions_target=decisions_target,
            max_sessions=max_sessions,
            cwd=cwd,
        )
    )


def run_triage(
    tracking_repo: str,
    tracking_issue: int,
    repos: str,
    *,
    phase: str = "analyze",
    mode: str = "auto",
    max_sessions: int = 50,
    cwd: str = None,
):
    """Launch claude in a loop to drive a cross-repo triage backlog.

    `repos` is a comma-separated list of `owner/repo` strings. Phase A
    (`analyze`) classifies/orders; Phase B (`execute`) opens one PR per
    iteration (stops at PR — does not merge).

    Examples:
        ge run-triage owner/track 9 "a/b,c/d" --phase analyze
        ge run-triage owner/track 9 "a/b,c/d" --phase execute --mode bypass
    """
    from ge.run import cli_run_triage

    print(
        cli_run_triage(
            tracking_repo,
            tracking_issue,
            repos,
            phase=phase,
            mode=mode,
            max_sessions=max_sessions,
            cwd=cwd,
        )
    )


def uninstall_skills(*, target_dir: str = None):
    """Remove ge skill symlinks from ~/.claude/skills/.

    Only removes symlinks that point back into ge's own skill directory.

    Examples:
        ge uninstall-skills
    """
    from ge import uninstall_skills as _uninstall

    _uninstall(target_dir=target_dir)


# SSOT: all CLI commands
_cli_commands = [
    prepare,
    prepare_discussion,
    analyze_issue,
    analyze_pr,
    fetch_issue,
    fetch_pr,
    fetch_discussion,
    media,
    video_frames,
    describe_images,
    copy_images,
    resolve,
    install_skills,
    uninstall_skills,
    # Memory layer
    roadmap_show,
    roadmap_next,
    roadmap_set,
    roadmap_append,
    decision_log,
    decisions_show,
    triage_show,
    triage_set,
    check_requirements,
    # Autonomous runner
    run_roadmap,
    run_triage,
]


def main():
    """Dispatch CLI commands via argh."""
    argh.dispatch_commands(_cli_commands)


if __name__ == "__main__":
    main()
