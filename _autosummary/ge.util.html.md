# ge.util

Internal utilities: gh CLI wrapper, subprocess helpers, URL parsing.

### Functions

| [`check_ffmpeg`](#ge.util.check_ffmpeg)()                                 | Check if ffmpeg is available.                                                 |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`default_output_dir`](#ge.util.default_output_dir)(repo, number[, kind])       | Compute the default output directory under the user's cache.                  |
| [`ensure_dir`](#ge.util.ensure_dir)(path)                               | Create directory if it doesn't exist, return Path.                            |
| [`extract_media_urls`](#ge.util.extract_media_urls)(markdown)                   | Extract image and video URLs from GitHub-flavored markdown.                   |
| [`gh_api`](#ge.util.gh_api)(endpoint, \*[, method, params, ...])    | Call the GitHub REST API via gh CLI.                                          |
| [`gh_auth_token`](#ge.util.gh_auth_token)()                                | Get the current gh auth token for authenticated downloads.                    |
| [`parse_github_url`](#ge.util.parse_github_url)(url)                          | Parse a full GitHub issue/PR/discussion URL into (owner, repo, number, kind). |
| [`parse_issue_url`](#ge.util.parse_issue_url)(url)                           | Parse a full GitHub issue/PR/discussion URL into (owner, repo, number, kind). |
| [`parse_repo_spec`](#ge.util.parse_repo_spec)(repo_spec)                     | Parse 'owner/repo' or full GitHub URL into (owner, repo).                     |
| [`resolve_target`](#ge.util.resolve_target)(user_input, \*[, current_repo]) | Resolve flexible user input into a structured target for ge workflows.        |
| [`rewrite_media_refs`](#ge.util.rewrite_media_refs)(markdown, url_to_local)     | Replace media URLs in markdown with local file paths.                         |

### ge.util.check_ffmpeg()

Check if ffmpeg is available.

### ge.util.default_output_dir(repo, number, kind='issue')

Compute the default output directory under the user’s cache.

Returns `~/.cache/ge/<owner>/<repo>/<kind>_<number>`, e.g.
`~/.cache/ge/thorwhalen/dol/issue_42`.

```pycon
>>> import os; home = os.path.expanduser('~')
>>> p = default_output_dir('thorwhalen/dol', 42, 'issue')
>>> str(p) == os.path.join(home, '.cache', 'ge', 'thorwhalen', 'dol', 'issue_42')
True
```

### ge.util.ensure_dir(path)

Create directory if it doesn’t exist, return Path.

### ge.util.extract_media_urls(markdown)

Extract image and video URLs from GitHub-flavored markdown.

Returns list of dicts with keys: url, alt, kind (‘image’, ‘video’, or ‘unknown’).

```pycon
>>> urls = extract_media_urls('![screenshot](https://example.com/img.png)')
>>> urls[0]['kind']
'image'
```

### ge.util.gh_api(endpoint, , method='GET', params=None, paginate=False, raw=False)

Call the GitHub REST API via gh CLI.

```pycon
>>> # gh_api('repos/octocat/Hello-World/issues/1')
```

### ge.util.gh_auth_token()

Get the current gh auth token for authenticated downloads.

```pycon
>>> # token = gh_auth_token()
```

### ge.util.parse_github_url(url)

Parse a full GitHub issue/PR/discussion URL into (owner, repo, number, kind).

```pycon
>>> parse_github_url('https://github.com/thorwhalen/dol/issues/42')
('thorwhalen', 'dol', 42, 'issue')
>>> parse_github_url('https://github.com/thorwhalen/dol/pull/7')
('thorwhalen', 'dol', 7, 'pr')
>>> parse_github_url('https://github.com/thorwhalen/dol/discussions/5')
('thorwhalen', 'dol', 5, 'discussion')
```

### ge.util.parse_issue_url(url)

Parse a full GitHub issue/PR/discussion URL into (owner, repo, number, kind).

```pycon
>>> parse_github_url('https://github.com/thorwhalen/dol/issues/42')
('thorwhalen', 'dol', 42, 'issue')
>>> parse_github_url('https://github.com/thorwhalen/dol/pull/7')
('thorwhalen', 'dol', 7, 'pr')
>>> parse_github_url('https://github.com/thorwhalen/dol/discussions/5')
('thorwhalen', 'dol', 5, 'discussion')
```

### ge.util.parse_repo_spec(repo_spec)

Parse ‘owner/repo’ or full GitHub URL into (owner, repo).

```pycon
>>> parse_repo_spec('thorwhalen/dol')
('thorwhalen', 'dol')
>>> parse_repo_spec('https://github.com/thorwhalen/dol')
('thorwhalen', 'dol')
>>> parse_repo_spec('https://github.com/thorwhalen/dol/issues/42')
('thorwhalen', 'dol')
```

### ge.util.resolve_target(user_input, , current_repo=None)

Resolve flexible user input into a structured target for ge workflows.

Accepts any of these forms:

> - A GitHub URL: `https://github.com/owner/repo/issues/42`
> - A folder path to pre-prepared context: `~/.cache/ge/owner/repo/issue_42`
> - A bare number: `42` or `#42` (uses *current_repo*)
> - `owner/repo#42` or `owner/repo/42`
> - `owner/repo 42`

Returns a dict with:

> - `repo`: `"owner/repo"` (or None if only a folder was given)
> - `number`: int
> - `kind`: `"issue"` | `"pr"` | `"discussion"` | None
> - `context_dir`: path to pre-prepared context (str or None)
> - `context_md`: path to the context markdown file (str or None)
> - `has_prepared_context`: bool — whether context files already exist
> - `source`: how the input was resolved (`"url"`, `"folder"`,
>   `"number"`, `"repo_number"`)
```pycon
>>> r = resolve_target('https://github.com/owner/repo/issues/42')
>>> r['repo'], r['number'], r['kind'], r['source']
('owner/repo', 42, 'issue', 'url')
```

```pycon
>>> r = resolve_target('#42', current_repo='owner/repo')
>>> r['repo'], r['number'], r['source']
('owner/repo', 42, 'number')
```

```pycon
>>> r = resolve_target('owner/repo#42')
>>> r['repo'], r['number'], r['source']
('owner/repo', 42, 'repo_number')
```

### ge.util.rewrite_media_refs(markdown, url_to_local)

Replace media URLs in markdown with local file paths.

```pycon
>>> md = '![bug](https://example.com/bug.png)'
>>> rewrite_media_refs(md, {'https://example.com/bug.png': 'media/bug.png'})
'![bug](media/bug.png)'
```
