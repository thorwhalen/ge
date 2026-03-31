"""Media download and video frame extraction.

Downloads images and videos from GitHub issues/PRs, handling private repo
auth via gh token. Extracts representative frames from videos using ffmpeg.
Provides AI-powered image description and clipboard montage utilities.
"""

import subprocess
import re
import shutil
import base64
import sys
from pathlib import Path

from ge.util import (
    extract_media_urls,
    rewrite_media_refs,
    gh_auth_token,
    ensure_dir,
    check_ffmpeg,
)


def _detect_media_type(filepath):
    """Detect media type from file magic bytes.

    Returns (kind, extension) where kind is 'image' or 'video',
    or (None, None) if unrecognized.

    >>> import tempfile, os
    >>> f = os.path.join(tempfile.mkdtemp(), 'test')
    >>> _ = open(f, 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n' + b'\\x00' * 20)
    >>> _detect_media_type(f)
    ('image', '.png')
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(12)
    except OSError:
        return None, None
    if len(header) < 4:
        return None, None
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", ".png"
    if header[:3] == b"\xff\xd8\xff":
        return "image", ".jpg"
    if header[:4] == b"GIF8":
        return "image", ".gif"
    if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image", ".webp"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video", ".mp4"
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return "video", ".webm"
    if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"AVI ":
        return "video", ".avi"
    return None, None


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
    output_dir=None,
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
    if output_dir is None:
        output_dir = str(Path.home() / ".cache" / "ge" / "media")
    media = extract_media_urls(markdown)
    out = ensure_dir(output_dir)

    url_map = {}
    manifest = []

    # Deduplicate filenames
    used_names = set()

    for item in media:
        kind = item["kind"]
        if kind == "image" and not download_images:
            continue
        if kind == "video" and not download_videos:
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

        # Detect actual content type and add extension if missing
        if ok:
            detected_kind, ext = _detect_media_type(dest)
            if detected_kind:
                kind = detected_kind
            if ext and not dest.suffix:
                new_dest = dest.with_name(dest.name + ext)
                dest.rename(new_dest)
                dest = new_dest

        entry = {
            "url": url,
            "local_path": str(dest) if ok else None,
            "kind": kind,
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

    >>> # frames = extract_video_frames('demo.mp4')
    >>> # frames = extract_video_frames('demo.mp4', mode='uniform', n_frames=5)
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


def process_all_media(markdown, output_dir=None):
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
                video_path = Path(local)
                # Frames go into a directory named after the video's stem (UUID)
                frame_dir = video_path.parent / video_path.stem
                frames = extract_video_frames(local, output_dir=str(frame_dir))
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


# ---------------------------------------------------------------------------
# Image description via Claude API (approach 1)
# ---------------------------------------------------------------------------

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _encode_image(path):
    """Read an image file and return (base64_data, media_type)."""
    p = Path(path)
    ext = p.suffix.lower()
    media_type = _IMAGE_MEDIA_TYPES.get(ext)
    if not media_type:
        # Try detecting from magic bytes
        kind, detected_ext = _detect_media_type(str(p))
        if kind == "image" and detected_ext:
            media_type = _IMAGE_MEDIA_TYPES.get(detected_ext, "image/png")
        else:
            media_type = "image/png"  # fallback
    with open(p, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()
    return data, media_type


def describe_images(
    *image_paths,
    prompt="Describe what you see in these images in detail. If they appear to be screenshots of a bug or UI issue, describe the problem visible.",
    model="claude-sonnet-4-5-20250514",
    max_tokens=4096,
):
    """Use the Claude API to describe images, returning a text description.

    Requires the ``anthropic`` package and a valid ``ANTHROPIC_API_KEY``.

    Args:
        *image_paths: One or more paths to image files.
        prompt: The text prompt sent alongside the images.
        model: Claude model to use for vision analysis.
        max_tokens: Maximum tokens in the response.

    Returns:
        str: The model's textual description of the images.

    >>> # description = describe_images('screenshot.png', 'error.jpg')
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required for image description.\n"
            "Install it with: pip install anthropic\n"
            "Then set ANTHROPIC_API_KEY in your environment."
        )

    client = anthropic.Anthropic()
    content = []
    for path in image_paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        data, media_type = _encode_image(p)
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )
    content.append({"type": "text", "text": prompt})

    msg = client.messages.create(
        model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": content}]
    )
    return msg.content[0].text


# ---------------------------------------------------------------------------
# Clipboard montage (approach 4: Claude Code orchestrates, user pastes)
# ---------------------------------------------------------------------------


def _check_imagemagick():
    """Check if ImageMagick's ``magick`` command is available."""
    if not shutil.which("magick"):
        raise EnvironmentError(
            "ImageMagick not found (needed for image montage).\n"
            "Install it with:\n"
            "  brew install imagemagick       # macOS\n"
            "  sudo apt install imagemagick   # Debian/Ubuntu\n"
            "  https://imagemagick.org        # other platforms"
        )


def copy_images_to_clipboard(
    *image_paths,
    tile="3x",
    geometry="800x600+10+10",
    montage_path=None,
):
    """Create a montage of images and copy it to the macOS clipboard.

    Combines multiple images into a single grid image using ImageMagick,
    then copies it to the clipboard via ``osascript`` so the user can
    paste it into Claude Code with Cmd+V.

    Args:
        *image_paths: Paths to image files to combine.
        tile: Montage tile layout (e.g. '3x' for 3 columns).
        geometry: Tile geometry (size+padding).
        montage_path: Where to save the montage file. Defaults to
            ``/tmp/ge_montage.png``.

    Returns:
        str: Path to the montage file.

    >>> # path = copy_images_to_clipboard('img1.png', 'img2.png')
    """
    _check_imagemagick()
    if not image_paths:
        raise ValueError("At least one image path is required.")

    if montage_path is None:
        montage_path = "/tmp/ge_montage.png"
    montage_path = str(montage_path)

    # Validate all paths exist
    for p in image_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"Image not found: {p}")

    # Create montage
    cmd = [
        "magick",
        "montage",
        *[str(p) for p in image_paths],
        "-geometry",
        geometry,
        "-tile",
        tile,
        montage_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"montage failed: {result.stderr.strip()}")

    # Copy to clipboard (macOS only)
    if sys.platform == "darwin":
        copy_cmd = [
            "osascript",
            "-e",
            f'set the clipboard to '
            f'(read (POSIX file "{montage_path}") as JPEG picture)',
        ]
        result = subprocess.run(copy_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to copy to clipboard: {result.stderr.strip()}"
            )

    return montage_path
