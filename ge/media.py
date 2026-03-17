"""Media download and video frame extraction.

Downloads images and videos from GitHub issues/PRs, handling private repo
auth via gh token. Extracts representative frames from videos using ffmpeg.
"""

import subprocess
import re
from pathlib import Path

from ge.util import (
    extract_media_urls,
    rewrite_media_refs,
    gh_auth_token,
    ensure_dir,
    check_ffmpeg,
)


def _sanitize_filename(url):
    """Derive a safe filename from a URL, preserving extension.

    >>> _sanitize_filename('https://github.com/user/repo/assets/123/screenshot.png')
    'screenshot.png'
    >>> _sanitize_filename('https://example.com/img?v=2')
    'img'
    """
    # Strip query params
    clean = url.split("?")[0].split("#")[0]
    name = clean.rstrip("/").split("/")[-1]
    # Remove unsafe chars
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "unnamed"


def _download_file(url, dest_path):
    """Download a file, using gh auth token for GitHub URLs.

    Returns True on success, False on failure.
    """
    headers = []
    if "github" in url or "githubusercontent" in url:
        try:
            token = gh_auth_token()
            headers = ["-H", f"Authorization: token {token}"]
        except Exception:
            pass  # Try without auth

    cmd = ["curl", "-sL", "-o", str(dest_path), "--max-time", "30"] + headers + [url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False

    # Verify we got something real (not an HTML error page for small files)
    if dest_path.stat().st_size == 0:
        dest_path.unlink(missing_ok=True)
        return False
    return True


def download_media(
    markdown,
    output_dir=".ge/media",
    *,
    download_images=True,
    download_videos=True,
):
    """Download all media referenced in markdown to a local directory.

    Returns a dict with:
      - url_map: {original_url: local_path} for successful downloads
      - manifest: list of dicts with url, local_path, kind, alt, status
      - rewritten_markdown: markdown with URLs replaced by local paths

    >>> # result = download_media('![img](https://example.com/a.png)', '/tmp/media')
    """
    media = extract_media_urls(markdown)
    out = ensure_dir(output_dir)

    url_map = {}
    manifest = []

    # Deduplicate filenames
    used_names = set()

    for item in media:
        if item["kind"] == "image" and not download_images:
            continue
        if item["kind"] == "video" and not download_videos:
            continue

        url = item["url"]
        name = _sanitize_filename(url)

        # Ensure unique filename
        base_name = name
        counter = 1
        while name in used_names:
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            name = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(name)

        dest = out / name
        ok = _download_file(url, dest)

        entry = {
            "url": url,
            "local_path": str(dest) if ok else None,
            "kind": item["kind"],
            "alt": item["alt"],
            "status": "ok" if ok else "failed",
        }
        manifest.append(entry)
        if ok:
            url_map[url] = str(dest)

    rewritten = rewrite_media_refs(markdown, url_map)
    return {
        "url_map": url_map,
        "manifest": manifest,
        "rewritten_markdown": rewritten,
    }


def extract_video_frames(
    video_path,
    *,
    n_frames=5,
    output_dir=None,
    mode="scene",
    scene_threshold=0.3,
):
    """Extract representative frames from a video file using ffmpeg.

    Two modes are available:

    - ``mode='scene'`` (default): Uses ffmpeg's scene change detection filter
      to extract frames where visual content actually changes. Better for bug
      reproduction videos where you want one frame per distinct UI state.
      ``scene_threshold`` controls sensitivity (0.0–1.0, lower = more frames).
      Falls back to 'uniform' if scene detection yields no frames.

    - ``mode='uniform'``: Extracts ``n_frames`` evenly-spaced frames.

    Returns list of paths to extracted frame images (JPEG).

    >>> # frames = extract_video_frames('.ge/media/demo.mp4')
    >>> # frames = extract_video_frames('.ge/media/demo.mp4', mode='uniform', n_frames=5)
    """
    check_ffmpeg()
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_dir is None:
        output_dir = video_path.parent / f"{video_path.stem}_frames"
    out = ensure_dir(output_dir)

    if mode == "scene":
        frames = _extract_scene_frames(video_path, out, scene_threshold)
        if frames:
            return frames
        # Fall back to uniform if scene detection found nothing

    return _extract_uniform_frames(video_path, out, n_frames)


def _extract_scene_frames(video_path, output_dir, threshold=0.3):
    """Extract frames at scene changes using ffmpeg's scene filter.

    Uses ``-vf "select=gt(scene\\,THRESHOLD)"`` to pick frames where the
    visual content changes significantly. This is zero extra dependency
    beyond ffmpeg itself.
    """
    pattern = str(output_dir / "scene_%03d.jpg")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select=gt(scene\\,{threshold})",
            "-vsync",
            "vfr",
            "-q:v",
            "2",
            pattern,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    # Collect generated frames
    frame_paths = sorted(
        str(p) for p in output_dir.glob("scene_*.jpg") if p.stat().st_size > 0
    )
    return frame_paths


def _extract_uniform_frames(video_path, output_dir, n_frames=5):
    """Extract n evenly-spaced frames from a video."""
    # Get video duration
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except (ValueError, TypeError):
        duration = 10.0  # fallback

    if n_frames == 1:
        timestamps = [duration / 2]
    else:
        timestamps = [duration * i / (n_frames - 1) for i in range(n_frames)]

    frame_paths = []
    for i, ts in enumerate(timestamps):
        frame_name = f"frame_{i:03d}_{ts:.1f}s.jpg"
        frame_path = output_dir / frame_name
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(ts),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            capture_output=True,
            text=True,
        )
        if frame_path.exists():
            frame_paths.append(str(frame_path))

    return frame_paths


def process_all_media(markdown, output_dir=".ge/media"):
    """Download all media and extract video frames.

    Returns a dict with:
      - url_map, manifest, rewritten_markdown (from download_media)
      - video_frames: {video_local_path: [frame_paths]}
      - images: list of local image paths (for user to paste into agent)
      - all_visual_files: combined list of images + video frames

    >>> # result = process_all_media(issue_body)
    """
    dl = download_media(markdown, output_dir)
    video_frames = {}
    all_images = []

    for entry in dl["manifest"]:
        if entry["status"] != "ok":
            continue
        local = entry["local_path"]
        if entry["kind"] == "video":
            try:
                frames = extract_video_frames(local)
                video_frames[local] = frames
                all_images.extend(frames)
            except Exception as e:
                video_frames[local] = []
                entry["frame_extraction_error"] = str(e)
        else:
            all_images.append(local)

    return {
        **dl,
        "video_frames": video_frames,
        "images": [
            p
            for p in all_images
            if p.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
        ],
        "all_visual_files": all_images,
    }
