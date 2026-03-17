"""Tests for ge.media module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ge.media import (
    _sanitize_filename,
    download_media,
    extract_video_frames,
    process_all_media,
)


# ---------------------------------------------------------------------------
# _sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_simple_url_with_extension(self):
        url = 'https://github.com/user/repo/assets/123/screenshot.png'
        assert _sanitize_filename(url) == 'screenshot.png'

    def test_url_with_query_params(self):
        assert _sanitize_filename('https://example.com/img?v=2') == 'img'

    def test_url_with_hash_fragment(self):
        assert _sanitize_filename('https://example.com/photo.jpg#section') == 'photo.jpg'

    def test_url_ending_in_slash(self):
        assert _sanitize_filename('https://example.com/photo.jpg/') == 'photo.jpg'

    def test_trailing_slash_falls_back_to_domain(self):
        # After stripping trailing slash, last segment is 'example.com'
        assert _sanitize_filename('https://example.com/') == 'example.com'

    def test_truly_empty_returns_unnamed(self):
        # A URL whose path is just slashes yields 'unnamed'
        assert _sanitize_filename('/') == 'unnamed'

    def test_bare_domain(self):
        assert _sanitize_filename('https://example.com') == 'example.com'

    def test_special_characters_are_replaced(self):
        result = _sanitize_filename('https://example.com/my file (1).png')
        # spaces and parens should become underscores
        assert '(' not in result
        assert ' ' not in result
        assert result.endswith('.png')


# ---------------------------------------------------------------------------
# download_media
# ---------------------------------------------------------------------------


class TestDownloadMedia:
    """Test download_media with _download_file mocked out."""

    _MARKDOWN = (
        '![img1](https://example.com/a.png) '
        '![img2](https://example.com/b.png) '
        '<video src="https://example.com/demo.mp4"></video>'
    )

    @patch('ge.media._download_file', return_value=True)
    def test_manifest_created(self, mock_dl, tmp_path):
        result = download_media(self._MARKDOWN, str(tmp_path / 'media'))
        assert 'manifest' in result
        assert len(result['manifest']) == 3
        for entry in result['manifest']:
            assert entry['status'] == 'ok'
            assert entry['local_path'] is not None

    @patch('ge.media._download_file', return_value=True)
    def test_url_map_populated(self, mock_dl, tmp_path):
        result = download_media(self._MARKDOWN, str(tmp_path / 'media'))
        assert len(result['url_map']) == 3

    @patch('ge.media._download_file', return_value=True)
    def test_rewritten_markdown_has_local_paths(self, mock_dl, tmp_path):
        out_dir = str(tmp_path / 'media')
        result = download_media(self._MARKDOWN, out_dir)
        rewritten = result['rewritten_markdown']
        # Original remote URLs should no longer appear
        assert 'https://example.com/a.png' not in rewritten
        assert 'https://example.com/b.png' not in rewritten
        # Local paths should appear instead
        assert out_dir in rewritten

    @patch('ge.media._download_file', return_value=True)
    def test_unique_filenames_for_duplicates(self, mock_dl, tmp_path):
        """Two different URLs that produce the same filename get distinct local names."""
        md = (
            '![a](https://example.com/path1/icon.png) '
            '![b](https://example.com/path2/icon.png)'
        )
        result = download_media(md, str(tmp_path / 'media'))
        local_paths = [e['local_path'] for e in result['manifest']]
        assert len(set(local_paths)) == 2  # two distinct paths

    @patch('ge.media._download_file', return_value=True)
    def test_skip_images_flag(self, mock_dl, tmp_path):
        result = download_media(
            self._MARKDOWN, str(tmp_path / 'media'), download_images=False,
        )
        kinds = [e['kind'] for e in result['manifest']]
        assert 'image' not in kinds
        assert 'video' in kinds

    @patch('ge.media._download_file', return_value=True)
    def test_skip_videos_flag(self, mock_dl, tmp_path):
        result = download_media(
            self._MARKDOWN, str(tmp_path / 'media'), download_videos=False,
        )
        kinds = [e['kind'] for e in result['manifest']]
        assert 'video' not in kinds
        assert 'image' in kinds

    @patch('ge.media._download_file', return_value=False)
    def test_failed_download_status(self, mock_dl, tmp_path):
        result = download_media(self._MARKDOWN, str(tmp_path / 'media'))
        for entry in result['manifest']:
            assert entry['status'] == 'failed'
            assert entry['local_path'] is None
        assert result['url_map'] == {}


# ---------------------------------------------------------------------------
# extract_video_frames
# ---------------------------------------------------------------------------


class TestExtractVideoFrames:
    @patch('ge.media.check_ffmpeg')
    def test_file_not_found(self, mock_check, tmp_path):
        with pytest.raises(FileNotFoundError, match='Video not found'):
            extract_video_frames(tmp_path / 'nonexistent.mp4', n_frames=3)

    @patch('ge.media.check_ffmpeg')
    @patch('ge.media.subprocess.run')
    def test_returns_frame_paths_uniform_mode(self, mock_run, mock_check, tmp_path):
        """In uniform mode, n_frames evenly-spaced frames are extracted."""
        video = tmp_path / 'demo.mp4'
        video.write_bytes(b'\x00' * 100)

        n_frames = 3

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'ffprobe':
                return MagicMock(stdout='10.0\n', returncode=0)
            # ffmpeg: create the output file so the code sees it exists
            out_file = Path(cmd[-1])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b'\xff\xd8')  # minimal JPEG header
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        frames = extract_video_frames(video, n_frames=n_frames, mode='uniform')
        assert len(frames) == n_frames
        for f in frames:
            assert f.endswith('.jpg')

    @patch('ge.media.check_ffmpeg')
    @patch('ge.media.subprocess.run')
    def test_scene_mode_creates_frames(self, mock_run, mock_check, tmp_path):
        """In scene mode (default), scene-change frames are extracted."""
        video = tmp_path / 'demo.mp4'
        video.write_bytes(b'\x00' * 100)

        def side_effect(cmd, **kwargs):
            # The scene mode ffmpeg call uses a pattern like scene_%03d.jpg
            # We simulate ffmpeg creating 2 scene frames
            if cmd[0] == 'ffmpeg':
                pattern_arg = cmd[-1]  # e.g. .../demo_frames/scene_%03d.jpg
                out_dir = Path(pattern_arg).parent
                out_dir.mkdir(parents=True, exist_ok=True)
                # Create fake scene frames
                (out_dir / 'scene_001.jpg').write_bytes(b'\xff\xd8')
                (out_dir / 'scene_002.jpg').write_bytes(b'\xff\xd8')
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        frames = extract_video_frames(video)
        assert len(frames) == 2
        for f in frames:
            assert 'scene_' in f
            assert f.endswith('.jpg')

    @patch('ge.media.check_ffmpeg')
    @patch('ge.media.subprocess.run')
    def test_scene_mode_falls_back_to_uniform(self, mock_run, mock_check, tmp_path):
        """When scene detection finds no frames, falls back to uniform mode."""
        video = tmp_path / 'demo.mp4'
        video.write_bytes(b'\x00' * 100)

        call_count = [0]

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'ffprobe':
                return MagicMock(stdout='6.0\n', returncode=0)
            if cmd[0] == 'ffmpeg':
                call_count[0] += 1
                if call_count[0] == 1:
                    # Scene detection call: return success but create no files
                    return MagicMock(returncode=0)
                else:
                    # Uniform extraction calls: create frame files
                    out_file = Path(cmd[-1])
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    out_file.write_bytes(b'\xff\xd8')
                    return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        frames = extract_video_frames(video, n_frames=2)
        assert len(frames) == 2
        for f in frames:
            assert 'frame_' in f

    @patch('ge.media.check_ffmpeg')
    @patch('ge.media.subprocess.run')
    def test_default_output_dir(self, mock_run, mock_check, tmp_path):
        """When output_dir is None, frames go to <video_stem>_frames/ directory."""
        video = tmp_path / 'clip.mp4'
        video.write_bytes(b'\x00')

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'ffmpeg':
                # Scene mode: create a frame so it doesn't fall back
                pattern_arg = cmd[-1]
                out_dir = Path(pattern_arg).parent
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / 'scene_001.jpg').write_bytes(b'\xff\xd8')
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        frames = extract_video_frames(video)
        # All frames should be under clip_frames/
        for f in frames:
            assert 'clip_frames' in f


# ---------------------------------------------------------------------------
# process_all_media
# ---------------------------------------------------------------------------


class TestProcessAllMedia:
    @patch('ge.media.extract_video_frames')
    @patch('ge.media.download_media')
    def test_images_populated(self, mock_dl, mock_frames, tmp_path):
        mock_dl.return_value = {
            'url_map': {'https://x.com/a.png': '/tmp/a.png'},
            'manifest': [
                {'url': 'https://x.com/a.png', 'local_path': '/tmp/a.png',
                 'kind': 'image', 'alt': '', 'status': 'ok'},
            ],
            'rewritten_markdown': '![a](/tmp/a.png)',
        }

        result = process_all_media('![a](https://x.com/a.png)', str(tmp_path))
        assert result['images'] == ['/tmp/a.png']
        mock_frames.assert_not_called()

    @patch('ge.media.extract_video_frames')
    @patch('ge.media.download_media')
    def test_video_frames_populated(self, mock_dl, mock_frames, tmp_path):
        mock_dl.return_value = {
            'url_map': {'https://x.com/v.mp4': '/tmp/v.mp4'},
            'manifest': [
                {'url': 'https://x.com/v.mp4', 'local_path': '/tmp/v.mp4',
                 'kind': 'video', 'alt': '', 'status': 'ok'},
            ],
            'rewritten_markdown': '![v](/tmp/v.mp4)',
        }
        mock_frames.return_value = ['/tmp/v_frames/frame_000.jpg', '/tmp/v_frames/frame_001.jpg']

        result = process_all_media('vid', str(tmp_path))
        assert '/tmp/v.mp4' in result['video_frames']
        assert len(result['video_frames']['/tmp/v.mp4']) == 2

    @patch('ge.media.extract_video_frames')
    @patch('ge.media.download_media')
    def test_all_visual_files_combines_images_and_frames(self, mock_dl, mock_frames, tmp_path):
        mock_dl.return_value = {
            'url_map': {
                'https://x.com/a.png': '/tmp/a.png',
                'https://x.com/v.mp4': '/tmp/v.mp4',
            },
            'manifest': [
                {'url': 'https://x.com/a.png', 'local_path': '/tmp/a.png',
                 'kind': 'image', 'alt': '', 'status': 'ok'},
                {'url': 'https://x.com/v.mp4', 'local_path': '/tmp/v.mp4',
                 'kind': 'video', 'alt': '', 'status': 'ok'},
            ],
            'rewritten_markdown': 'rewritten',
        }
        mock_frames.return_value = ['/tmp/v_frames/frame_000.jpg']

        result = process_all_media('md', str(tmp_path))
        assert '/tmp/a.png' in result['all_visual_files']
        assert '/tmp/v_frames/frame_000.jpg' in result['all_visual_files']
        # images filters to image extensions only
        assert '/tmp/a.png' in result['images']
        assert '/tmp/v_frames/frame_000.jpg' in result['images']

    @patch('ge.media.extract_video_frames', side_effect=Exception('ffmpeg missing'))
    @patch('ge.media.download_media')
    def test_frame_extraction_error_handled(self, mock_dl, mock_frames, tmp_path):
        mock_dl.return_value = {
            'url_map': {'https://x.com/v.mp4': '/tmp/v.mp4'},
            'manifest': [
                {'url': 'https://x.com/v.mp4', 'local_path': '/tmp/v.mp4',
                 'kind': 'video', 'alt': '', 'status': 'ok'},
            ],
            'rewritten_markdown': 'md',
        }

        result = process_all_media('md', str(tmp_path))
        # Should not raise; video_frames entry should be empty list
        assert result['video_frames']['/tmp/v.mp4'] == []
        # Error recorded in manifest entry
        assert 'frame_extraction_error' in result['manifest'][0]
