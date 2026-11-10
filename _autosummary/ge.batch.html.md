# ge.batch

File a batch of related issues: dependency order, cross-references, `blocked_by` edges.

A batch is a list of records, each with a `key` local to the batch:

```default
[
  {"key": "A", "title": "Parser", "body": "First piece."},
  {"key": "B", "title": "Printer", "body": "Uses the parser of {#A}.",
   "labels": ["enhancement"], "depends_on": ["A", "#12"]}
]
```

[`file_issues()`](#ge.batch.file_issues) validates the whole batch before filing anything (field
types, unique keys, known references, no dependency cycle), then:

1. creates the issues in dependency order, replacing each `{#KEY}` in a body
   with the `#number` that issue became (write `{{#x}}` for a literal `{#x}`);
2. updates every body whose final text differs from what was last sent: the
   ones that referred to a key filed later, and any record edited since. A body
   someone has edited on GitHub since is never overwritten: it is listed in
   `body_conflicts` instead (`force=True` overwrites);
3. creates a GitHub `blocked_by` dependency edge for every `depends_on`
   that the blocked issue does not already have.

`depends_on` takes batch keys and existing issues (`12`, `"#12"`,
`"owner/repo#12"`). Progress is written to a map file after every step, so
an interrupted run is resumed by running it again. Each body carries a hidden
marker for its record (its key and the batch name), so an issue created just
before a crash (or after a lost map) is found among the repository’s recent
issues and adopted, not filed twice.
The map’s shape is stable, for writing the links back into a source document:

```default
{"repo": "owner/repo",
 "issues": {"A": {"number": 7, "url": "...", "id": 123, "body_sha": "..."}},
 "edges": [{"blocked": "B", "blocker": "A"}],
 "edge_errors": [{"blocked": "B", "blocker": "#12", "error": "..."}],
 "body_conflicts": ["C"]}
```

The batch knows nothing about any document format: produce the records however you like.

### Module Attributes

| [`REF_PATTERN`](#ge.batch.REF_PATTERN)    | `{#KEY}` in a body becomes `#number` once KEY is filed; `{{#KEY}}` stays literal.   |
|-----------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`EXISTING_ISSUE`](#ge.batch.EXISTING_ISSUE) | `12`, `#12`, `owner/repo#12`.                                                       |
| [`DEFAULT_PAUSE`](#ge.batch.DEFAULT_PAUSE)  | Seconds after each write to GitHub; it throttles bursts of content creation.        |
| [`ADOPT_PAGES`](#ge.batch.ADOPT_PAGES)    | Pages of 100 of the repository's most recent issues searched for an unrecorded one. |

### Functions

| [`file_issues`](#ge.batch.file_issues)(records, repo, \*[, map_path, ...])   | File *records* as issues in *repo* (`owner/name` or URL); return the map (see module doc).   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`load_records`](#ge.batch.load_records)(path)                                | Records from a `.json` file (a list), or `.yaml` / `.yml` when PyYAML is installed.          |
| [`marker`](#ge.batch.marker)(record[, batch])                           | Hidden line identifying the record an issue was filed from.                                  |
| [`render_body`](#ge.batch.render_body)(body, numbers)                        | Replace `{#KEY}` with `#number` for every key already filed.                                 |
| [`validate`](#ge.batch.validate)(records)                                 | Check a batch and return its keys in filing order; raise ValueError on any problem.          |

### ge.batch.ADOPT_PAGES *= 3*

Pages of 100 of the repository’s most recent issues searched for an unrecorded one.

### ge.batch.DEFAULT_PAUSE *= 1.0*

Seconds after each write to GitHub; it throttles bursts of content creation.

### ge.batch.EXISTING_ISSUE *= re.compile('^(?:(?P<repo>[\\\\w.-]+/[\\\\w.-]+))?#?(?P<number>\\\\d+)$')*

`12`, `#12`, `owner/repo#12`.

* **Type:**
  An existing issue named in `depends_on`

### ge.batch.REF_PATTERN *= re.compile('(?<!\\\\{)\\\\{#([^{}\\\\s]+)\\\\}(?!\\\\})')*

`{#KEY}` in a body becomes `#number` once KEY is filed; `{{#KEY}}` stays literal.

### ge.batch.file_issues(records, repo, \*, map_path=None, batch=None, force=False, api=None, pause=1.0, adopt_pages=3, sleep=<built-in function sleep>, log=<built-in function print>)

File *records* as issues in *repo* (`owner/name` or URL); return the map (see module doc).

*api* defaults to [`ge.util.gh_api()`](ge.util.html.md#ge.util.gh_api); pass a fake to test.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### ge.batch.load_records(path)

Records from a `.json` file (a list), or `.yaml` / `.yml` when PyYAML is installed.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### ge.batch.marker(record, batch=None)

Hidden line identifying the record an issue was filed from.

It hashes the key and the *batch* name, so two batches using the same keys
in one repository never adopt each other’s issues; without a batch name the
title stands in for it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### ge.batch.render_body(body, numbers)

Replace `{#KEY}` with `#number` for every key already filed.

```pycon
>>> render_body("after {#A}, before {#B}, literal {{#A}}", {"A": 7})
'after #7, before {#B}, literal {#A}'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### ge.batch.validate(records)

Check a batch and return its keys in filing order; raise ValueError on any problem.

```pycon
>>> validate([{"key": "B", "title": "b", "depends_on": ["A"]},
...           {"key": "A", "title": "a", "body": "see {#B}"}])
['A', 'B']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
