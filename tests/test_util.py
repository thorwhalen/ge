"""Tests for ge.util — URL parsing, media extraction, filesystem helpers."""

import pytest
from unittest.mock import patch

from ge.util import (
    parse_repo_spec,
    parse_issue_url,
    extract_media_urls,
    rewrite_media_refs,
    ensure_dir,
    check_ffmpeg,
)


# ---------------------------------------------------------------------------
# parse_repo_spec
# ---------------------------------------------------------------------------


class TestParseRepoSpec:
    def test_owner_repo_string(self):
        assert parse_repo_spec('thorwhalen/dol') == ('thorwhalen', 'dol')

    def test_full_https_url(self):
        assert parse_repo_spec('https://github.com/thorwhalen/dol') == (
            'thorwhalen',
            'dol',
        )

    def test_http_url(self):
        assert parse_repo_spec('http://github.com/thorwhalen/dol') == (
            'thorwhalen',
            'dol',
        )

    def test_url_with_issues_path(self):
        assert parse_repo_spec(
            'https://github.com/thorwhalen/dol/issues/42'
        ) == ('thorwhalen', 'dol')

    def test_url_with_pull_path(self):
        assert parse_repo_spec(
            'https://github.com/thorwhalen/dol/pull/7'
        ) == ('thorwhalen', 'dol')

    def test_trailing_slash(self):
        assert parse_repo_spec('thorwhalen/dol/') == ('thorwhalen', 'dol')

    def test_trailing_slash_url(self):
        assert parse_repo_spec('https://github.com/thorwhalen/dol/') == (
            'thorwhalen',
            'dol',
        )

    def test_leading_trailing_whitespace(self):
        assert parse_repo_spec('  thorwhalen/dol  ') == ('thorwhalen', 'dol')

    def test_invalid_single_segment(self):
        with pytest.raises(ValueError, match='Cannot parse repo spec'):
            parse_repo_spec('just-a-name')

    def test_invalid_empty_string(self):
        with pytest.raises(ValueError, match='Cannot parse repo spec'):
            parse_repo_spec('')


# ---------------------------------------------------------------------------
# parse_issue_url
# ---------------------------------------------------------------------------


class TestParseIssueUrl:
    def test_issue_url(self):
        assert parse_issue_url(
            'https://github.com/thorwhalen/dol/issues/42'
        ) == ('thorwhalen', 'dol', 42, 'issue')

    def test_pull_url(self):
        assert parse_issue_url(
            'https://github.com/thorwhalen/dol/pull/7'
        ) == ('thorwhalen', 'dol', 7, 'pr')

    def test_http_issue_url(self):
        assert parse_issue_url(
            'http://github.com/thorwhalen/dol/issues/1'
        ) == ('thorwhalen', 'dol', 1, 'issue')

    def test_number_is_int(self):
        _, _, number, _ = parse_issue_url(
            'https://github.com/a/b/issues/999'
        )
        assert isinstance(number, int)

    def test_discussion_url(self):
        owner, repo, number, kind = parse_issue_url(
            'https://github.com/thorwhalen/dol/discussions/10'
        )
        assert owner == 'thorwhalen'
        assert repo == 'dol'
        assert number == 10
        assert kind == 'discussion'

    def test_invalid_random_url(self):
        with pytest.raises(ValueError, match='Cannot parse'):
            parse_issue_url('https://example.com/not-github')

    def test_invalid_missing_number(self):
        with pytest.raises(ValueError, match='Cannot parse'):
            parse_issue_url('https://github.com/thorwhalen/dol/issues/')


# ---------------------------------------------------------------------------
# extract_media_urls
# ---------------------------------------------------------------------------


class TestExtractMediaUrls:
    def test_markdown_image(self):
        md = '![screenshot](https://example.com/img.png)'
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0] == {
            'url': 'https://example.com/img.png',
            'alt': 'screenshot',
            'kind': 'image',
        }

    def test_html_img_tag(self):
        md = '<img src="https://example.com/photo.jpg" width="400">'
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0]['kind'] == 'image'
        assert urls[0]['url'] == 'https://example.com/photo.jpg'

    def test_html_img_single_quotes(self):
        md = "<img src='https://example.com/photo.jpg'>"
        urls = extract_media_urls(md)
        assert len(urls) == 1

    def test_video_tag(self):
        md = '<video src="https://example.com/demo.mp4" controls></video>'
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0]['kind'] == 'video'

    def test_bare_video_url_mp4(self):
        md = 'Check this out:\nhttps://example.com/clip.mp4\nPretty cool.'
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0]['kind'] == 'video'
        assert urls[0]['url'] == 'https://example.com/clip.mp4'

    def test_bare_video_url_mov(self):
        urls = extract_media_urls('https://example.com/clip.mov')
        assert urls[0]['kind'] == 'video'

    def test_bare_video_url_webm(self):
        urls = extract_media_urls('https://example.com/clip.webm')
        assert urls[0]['kind'] == 'video'

    def test_deduplication(self):
        md = (
            '![a](https://example.com/img.png)\n'
            '![b](https://example.com/img.png)'
        )
        urls = extract_media_urls(md)
        assert len(urls) == 1

    def test_deduplication_across_formats(self):
        """Same URL in markdown image and HTML img should appear once."""
        url = 'https://example.com/img.png'
        md = f'![alt]({url})\n<img src="{url}">'
        urls = extract_media_urls(md)
        assert len(urls) == 1

    def test_mixed_content(self):
        md = (
            'Some text here.\n'
            '![logo](https://example.com/logo.png)\n'
            'More text.\n'
            '<video src="https://example.com/vid.mp4" controls></video>\n'
            'https://example.com/bare.webm\n'
            'End.'
        )
        urls = extract_media_urls(md)
        assert len(urls) == 3
        kinds = {u['kind'] for u in urls}
        assert kinds == {'image', 'video'}

    def test_bare_github_asset_url(self):
        """Bare GitHub user-attachment URLs (no extension) are detected."""
        md = (
            'Bug demo:\n'
            'https://github.com/user-attachments/assets/4959e593-3dcd-4a5d-88ab-25794a499f36\n'
            'See above.'
        )
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0]['kind'] == 'unknown'
        assert '4959e593' in urls[0]['url']

    def test_github_asset_url_dedup_with_img_tag(self):
        """A GitHub asset URL in an <img> tag is not duplicated by the bare URL pattern."""
        uuid = 'aaaa-bbbb-cccc-dddd'
        url = f'https://github.com/user-attachments/assets/{uuid}'
        md = f'<img src="{url}" />\n{url}'
        urls = extract_media_urls(md)
        assert len(urls) == 1
        assert urls[0]['kind'] == 'image'  # img tag wins (matched first)

    def test_github_asset_mixed_images_and_videos(self):
        """Mixed <img> tags and bare asset URLs in same markdown."""
        md = (
            '<img src="https://github.com/user-attachments/assets/img-uuid-1" />\n'
            'https://github.com/user-attachments/assets/vid-uuid-1\n'
        )
        urls = extract_media_urls(md)
        assert len(urls) == 2
        kinds = {u['kind'] for u in urls}
        assert kinds == {'image', 'unknown'}

    def test_empty_markdown(self):
        assert extract_media_urls('') == []

    def test_no_media(self):
        assert extract_media_urls('Just plain text, no images or videos.') == []


# ---------------------------------------------------------------------------
# rewrite_media_refs
# ---------------------------------------------------------------------------


class TestRewriteMediaRefs:
    def test_simple_replacement(self):
        md = '![bug](https://example.com/bug.png)'
        result = rewrite_media_refs(
            md, {'https://example.com/bug.png': 'media/bug.png'}
        )
        assert result == '![bug](media/bug.png)'

    def test_multiple_replacements(self):
        md = (
            '![a](https://example.com/a.png)\n'
            '![b](https://example.com/b.png)'
        )
        mapping = {
            'https://example.com/a.png': 'local/a.png',
            'https://example.com/b.png': 'local/b.png',
        }
        result = rewrite_media_refs(md, mapping)
        assert 'local/a.png' in result
        assert 'local/b.png' in result
        assert 'example.com' not in result

    def test_url_not_in_map_left_alone(self):
        md = '![x](https://example.com/x.png) ![y](https://other.com/y.png)'
        result = rewrite_media_refs(
            md, {'https://example.com/x.png': 'local/x.png'}
        )
        assert 'local/x.png' in result
        assert 'https://other.com/y.png' in result

    def test_empty_map(self):
        md = '![img](https://example.com/img.png)'
        assert rewrite_media_refs(md, {}) == md


# ---------------------------------------------------------------------------
# ensure_dir
# ---------------------------------------------------------------------------


class TestEnsureDir:
    def test_creates_directory(self, tmp_path):
        target = tmp_path / 'a' / 'b' / 'c'
        result = ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_existing_directory(self, tmp_path):
        target = tmp_path / 'existing'
        target.mkdir()
        result = ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_returns_path_object(self, tmp_path):
        from pathlib import Path

        result = ensure_dir(str(tmp_path / 'new'))
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# check_ffmpeg
# ---------------------------------------------------------------------------


class TestCheckFfmpeg:
    @patch('ge.util.shutil.which', return_value=None)
    def test_raises_when_ffmpeg_missing(self, mock_which):
        with pytest.raises(EnvironmentError, match='ffmpeg not found'):
            check_ffmpeg()
        mock_which.assert_called_once_with('ffmpeg')

    @patch('ge.util.shutil.which', return_value='/usr/local/bin/ffmpeg')
    def test_no_error_when_ffmpeg_present(self, mock_which):
        check_ffmpeg()  # should not raise
        mock_which.assert_called_once_with('ffmpeg')
