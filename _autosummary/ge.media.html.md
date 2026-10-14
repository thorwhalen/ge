# ge.media

Media download and video frame extraction.

Downloads images and videos from GitHub issues/PRs, handling private repo
auth via gh token. Extracts representative frames from videos using ffmpeg.
Provides AI-powered image description and clipboard montage utilities.

### Functions

| [`copy_images_to_clipboard`](#ge.media.copy_images_to_clipboard)(\*image_paths[, ...])   | Create a montage of images and copy it to the macOS clipboard.       |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`describe_images`](#ge.media.describe_images)(\*image_paths[, prompt, ...])    | Use the Claude API to describe images, returning a text description. |
| [`download_media`](#ge.media.download_media)(markdown[, output_dir, ...])      | Download all media referenced in markdown to a local directory.      |
| [`extract_video_frames`](#ge.media.extract_video_frames)(video_path, \*[, ...])      | Extract representative frames from a video file using ffmpeg.        |
| [`process_all_media`](#ge.media.process_all_media)(markdown[, output_dir])        | Download all media and extract video frames.                         |

### ge.media.copy_images_to_clipboard(\*image_paths, tile='3x', geometry='800x600+10+10', montage_path=None)

Create a montage of images and copy it to the macOS clipboard.

Combines multiple images into a single grid image using ImageMagick,
then copies it to the clipboard via `osascript` so the user can
paste it into Claude Code with Cmd+V.

* **Parameters:**
  * **\*image_paths** – Paths to image files to combine.
  * **tile** – Montage tile layout (e.g. ‘3x’ for 3 columns).
  * **geometry** – Tile geometry (size+padding).
  * **montage_path** – Where to save the montage file. Defaults to
    `/tmp/ge_montage.png`.
* **Returns:**
  Path to the montage file.
* **Return type:**
  [*str*](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> # path = copy_images_to_clipboard('img1.png', 'img2.png')
```

### ge.media.describe_images(\*image_paths, prompt='Describe what you see in these images in detail. If they appear to be screenshots of a bug or UI issue, describe the problem visible.', model='claude-sonnet-4-5-20250514', max_tokens=4096)

Use the Claude API to describe images, returning a text description.

Requires the `anthropic` package and a valid `ANTHROPIC_API_KEY`.

* **Parameters:**
  * **\*image_paths** – One or more paths to image files.
  * **prompt** – The text prompt sent alongside the images.
  * **model** – Claude model to use for vision analysis.
  * **max_tokens** – Maximum tokens in the response.
* **Returns:**
  The model’s textual description of the images.
* **Return type:**
  [*str*](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> # description = describe_images('screenshot.png', 'error.jpg')
```

### ge.media.download_media(markdown, output_dir=None, , download_images=True, download_videos=True)

Download all media referenced in markdown to a local directory.

Returns a dict with:

> - url_map: {original_url: local_path} for successful downloads
> - manifest: list of dicts with url, local_path, kind, alt, status
> - rewritten_markdown: markdown with URLs replaced by local paths
```pycon
>>> # result = download_media('![img](https://example.com/a.png)', '/tmp/media')
```

### ge.media.extract_video_frames(video_path, , n_frames=5, output_dir=None, mode='scene', scene_threshold=0.3)

Extract representative frames from a video file using ffmpeg.

Two modes are available:

- `mode='scene'` (default): Uses ffmpeg’s scene change detection filter
  to extract frames where visual content actually changes. Better for bug
  reproduction videos where you want one frame per distinct UI state.
  `scene_threshold` controls sensitivity (0.0–1.0, lower = more frames).
  Falls back to ‘uniform’ if scene detection yields no frames.
- `mode='uniform'`: Extracts `n_frames` evenly-spaced frames.

Returns list of paths to extracted frame images (JPEG).

```pycon
>>> # frames = extract_video_frames('demo.mp4')
>>> # frames = extract_video_frames('demo.mp4', mode='uniform', n_frames=5)
```

### ge.media.process_all_media(markdown, output_dir=None)

Download all media and extract video frames.

Returns a dict with:

> - url_map, manifest, rewritten_markdown (from download_media)
> - video_frames: {video_local_path: [frame_paths]}
> - images: list of local image paths (for user to paste into agent)
> - all_visual_files: combined list of images + video frames
```pycon
>>> # result = process_all_media(issue_body)
```
