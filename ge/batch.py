"""File a batch of related issues: dependency order, cross-references, ``blocked_by`` edges.

A batch is a list of records, each with a ``key`` local to the batch::

    [
      {"key": "A", "title": "Parser", "body": "First piece."},
      {"key": "B", "title": "Printer", "body": "Uses the parser of {#A}.",
       "labels": ["enhancement"], "depends_on": ["A", "#12"]}
    ]

:func:`file_issues` validates the whole batch before filing anything (unique
keys, known references, no dependency cycle), then:

1. creates the issues in dependency order, replacing each ``{#KEY}`` in a body
   with the ``#number`` that issue became;
2. patches the bodies that referred to a key filed later;
3. creates a GitHub ``blocked_by`` dependency edge for every ``depends_on``.

``depends_on`` takes batch keys and existing issues (``12``, ``"#12"``,
``"owner/repo#12"``). Progress is written to a map file after every step, so
an interrupted run is resumed by running it again; nothing is filed twice.
The map's shape is stable, for writing the links back into a source document::

    {"repo": "owner/repo",
     "issues": {"A": {"number": 7, "url": "...", "id": 123}},
     "bodies_final": ["A"],
     "edges": [["B", "A"]],
     "edge_errors": {}}

``edges`` lists ``[blocked, blocker]`` pairs already created. The batch knows
nothing about any document format: produce the records however you like.
"""

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

#: ``{#KEY}`` in a body becomes ``#number`` once KEY is filed.
REF_PATTERN = re.compile(r"\{#([^{}\s]+)\}")
#: An existing issue named in ``depends_on``: ``12``, ``#12``, ``owner/repo#12``.
EXISTING_ISSUE = re.compile(r"^(?:(?P<repo>[\w.-]+/[\w.-]+))?#?(?P<number>\d+)$")
#: Seconds between two issue creations; GitHub throttles bursts of content creation.
DEFAULT_PAUSE = 1.0

Api = Callable[..., dict]  # gh_api's signature: (endpoint, *, method=..., body=...)


def _refs(text: str) -> set[str]:
    """Keys referred to as ``{#KEY}`` in *text*.

    >>> sorted(_refs("after {#A} and {#B.2}, not {A} or #3"))
    ['A', 'B.2']
    """
    return set(REF_PATTERN.findall(text or ""))


def _is_existing(dep) -> bool:
    return isinstance(dep, int) or bool(EXISTING_ISSUE.match(str(dep)))


def validate(records: Iterable[Mapping]) -> list[str]:
    """Check a batch and return its keys in filing order; raise ValueError on any problem.

    >>> validate([{"key": "B", "title": "b", "depends_on": ["A"]},
    ...           {"key": "A", "title": "a", "body": "see {#B}"}])
    ['A', 'B']
    """
    records = list(records)
    problems, keys = [], [r.get("key") for r in records]
    seen = set()
    for i, (r, k) in enumerate(zip(records, keys)):
        if not k or not isinstance(k, str):
            problems.append(f"record {i}: missing or non-string 'key'")
        elif k in seen:
            problems.append(f"record {i}: duplicate key {k!r}")
        seen.add(k)
        if not r.get("title"):
            problems.append(f"record {k or i}: missing 'title'")
    for r in records:
        for dep in r.get("depends_on", ()):
            if dep not in seen and not _is_existing(dep):
                problems.append(f"{r.get('key')}: depends_on {dep!r} is neither a key nor an issue")
        for ref in _refs(r.get("body", "")) - seen:
            problems.append(f"{r.get('key')}: body refers to unknown key {{#{ref}}}")
    if problems:
        raise ValueError("invalid batch:\n  " + "\n  ".join(problems))
    graph = {r["key"]: [d for d in r.get("depends_on", ()) if d in seen] for r in records}
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as e:
        raise ValueError(f"invalid batch: dependency cycle {e.args[1]}") from None
    position = {k: i for i, k in enumerate(keys)}  # keep input order among peers
    return sorted(order, key=lambda k: (_depth(k, graph), position[k]))


def _depth(key: str, graph: Mapping[str, list], _memo=None) -> int:
    """Length of the longest dependency chain under *key* (graph is acyclic)."""
    memo = {} if _memo is None else _memo
    if key not in memo:
        memo[key] = 1 + max((_depth(d, graph, memo) for d in graph[key]), default=-1)
    return memo[key]


def render_body(body: str, numbers: Mapping[str, int]) -> str:
    """Replace ``{#KEY}`` with ``#number`` for every key already filed.

    >>> render_body("after {#A}, before {#B}", {"A": 7})
    'after #7, before {#B}'
    """
    return REF_PATTERN.sub(lambda m: f"#{numbers[m[1]]}" if m[1] in numbers else m[0], body or "")


def _load_map(path: Path | None, repo: str) -> dict:
    state = {"repo": repo, "issues": {}, "bodies_final": [], "edges": [], "edge_errors": {}}
    if path and path.exists():
        state.update(json.loads(path.read_text()))
        if state["repo"] != repo:
            raise ValueError(f"{path} records a batch filed in {state['repo']}, not {repo}")
    return state


def _issue_id(dep, repo: str, state: Mapping, api: Api) -> int:
    """GitHub's internal id (not the number) of a batch key or an existing issue."""
    if isinstance(dep, str) and dep in state["issues"]:
        return state["issues"][dep]["id"]
    m = EXISTING_ISSUE.match(str(dep))
    return api(f"repos/{m['repo'] or repo}/issues/{m['number']}")["id"]


def file_issues(
    records: Iterable[Mapping],
    repo: str,
    *,
    map_path: str | Path | None = None,
    api: Api | None = None,
    pause: float = DEFAULT_PAUSE,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> dict:
    """File *records* as issues in *repo* (``owner/name``); return the map (see module doc).

    *api* defaults to :func:`ge.util.gh_api`; pass a fake to test or dry-run.
    """
    if api is None:
        from ge.util import gh_api as api
    records = list(records)
    order = validate(records)
    records = {r["key"]: r for r in records}
    path = Path(map_path) if map_path else None
    state = _load_map(path, repo)

    def save():
        if path:
            path.write_text(json.dumps(state, indent=2) + "\n")

    numbers = lambda: {k: v["number"] for k, v in state["issues"].items()}  # noqa: E731

    for key in order:  # 1. create
        if key in state["issues"]:
            continue
        r = records[key]
        payload = {"title": r["title"], "body": render_body(r.get("body", ""), numbers())}
        for field in ("labels", "assignees", "milestone"):
            if r.get(field):
                payload[field] = r[field]
        made = api(f"repos/{repo}/issues", method="POST", body=payload)
        state["issues"][key] = {"number": made["number"], "url": made["html_url"], "id": made["id"]}
        if not REF_PATTERN.search(payload["body"]):  # else it refers to a key filed later
            state["bodies_final"].append(key)
        save()
        log(f"{key}  #{made['number']}  {made['html_url']}")
        sleep(pause)

    for key in order:  # 2. resolve forward references
        if key in state["bodies_final"]:
            continue
        number = state["issues"][key]["number"]
        api(
            f"repos/{repo}/issues/{number}",
            method="PATCH",
            body={"body": render_body(records[key].get("body", ""), numbers())},
        )
        state["bodies_final"].append(key)
        save()

    done = {tuple(e) for e in state["edges"]}
    for key in order:  # 3. dependency edges
        number = state["issues"][key]["number"]
        for dep in records[key].get("depends_on", ()):
            edge = (key, str(dep))
            if edge in done:
                continue
            try:
                blocker = _issue_id(dep, repo, state, api)
                api(
                    f"repos/{repo}/issues/{number}/dependencies/blocked_by",
                    method="POST",
                    body={"issue_id": blocker},
                )
            except RuntimeError as e:
                if "already" not in str(e).lower():  # an existing edge counts as done
                    state["edge_errors"][f"{key} <- {dep}"] = str(e)
                    save()
                    log(f"{key}: blocked_by {dep} failed: {e}")
                    continue
            state["edges"].append(list(edge))
            state["edge_errors"].pop(f"{key} <- {dep}", None)
            done.add(edge)
            save()
    return state


def load_records(path: str | Path) -> list[dict]:
    """Records from a ``.json`` file (a list), or ``.yaml`` / ``.yml`` when PyYAML is installed."""
    path = Path(path)
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError(f"{path} is YAML: pip install pyyaml, or give a .json file") from None
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path} must hold a list of records, got {type(data).__name__}")
    return data
