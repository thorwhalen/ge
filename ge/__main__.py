"""CLI entry point for ge.

Usage::

    python -m ge prepare owner/repo --number 42
    python -m ge prepare https://github.com/owner/repo/issues/42
    python -m ge analyze-issue owner/repo 42
    python -m ge analyze-pr owner/repo 7
"""

import json

import argh


def prepare(url_or_spec: str, number: int = None, *, output_dir: str = None):
    """Prepare full context for a GitHub issue or PR.

    Fetches all data, downloads media, runs freshness analysis,
    and writes a structured context document to output_dir.

    By default, context is written to ~/.cache/ge/<owner>/<repo>/<kind>_<number>/.

    Examples:
        ge prepare owner/repo --number 42
        ge prepare https://github.com/owner/repo/pull/7
    """
    from ge import prepare as _prepare

    kwargs = {}
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
        if media.get("all_visual_files"):
            print("Visual files (paste these into your agent for visual context):")
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
    install_skills,
    uninstall_skills,
]


def main():
    """Dispatch CLI commands via argh."""
    argh.dispatch_commands(_cli_commands)


if __name__ == "__main__":
    main()
