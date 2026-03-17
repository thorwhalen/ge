# ge — Tool & Integration Survey

This document surveys existing tools, libraries, skills, and services that
could be integrated into `ge` to improve its capabilities. It is intended
as a reference for AI agents working on `ge` to evaluate and incorporate
these tools.

---

## 1. Python GitHub API Libraries

`ge` currently shells out to `gh` CLI for all GitHub access. This is simple
and handles auth well, but Python libraries offer richer data structures,
pagination, and async support.

### 1.1 ghapi (fastai)

The most Pythonic GitHub API library. Uses the OpenAPI spec to dynamically
generate 100% API coverage in a 35kB package. Tab completion, auto-pagination,
built-in documentation. Created by Jeremy Howard (fast.ai).

**Why it matters for ge:** Could replace our `subprocess` + `json.loads` calls
with native Python objects. The dynamic generation means it's always up-to-date
with the latest GitHub API endpoints, including timeline, discussions, and
search. Also has a CLI mode.

```python
from ghapi.all import GhApi
api = GhApi(owner='thorwhalen', repo='dol', token=token)
issue = api.issues.get(42)
comments = api.issues.list_comments(42)
timeline = api.issues.list_events_for_timeline(42)
```

- PyPI: `pip install ghapi`
- [ghapi docs](https://ghapi.fast.ai/) 
- [GitHub repo](https://github.com/fastai/ghapi) [1]
- [GitHub blog announcement](https://github.blog/developer-skills/programming-languages-and-frameworks/learn-about-ghapi-a-new-third-party-python-client-for-the-github-api/) [2]

### 1.2 githubkit

A modern, fully typed, sync+async GitHub SDK. Uses Pydantic for response
validation and GitHub's official OpenAPI schema for code generation. Supports
REST, GraphQL, webhooks, and GHEC versioning. Built-in HTTP cache and retry.

**Why it matters for ge:** If we want typed responses and async support
(e.g., for batch-fetching multiple issues in parallel), githubkit is the
most complete modern option. Pydantic models mean IDE autocompletion on
all response fields.

```python
from githubkit import GitHub
github = GitHub("<token>")
resp = github.rest.issues.get("owner", "repo", 42)
issue = resp.parsed_data  # fully typed Pydantic model
```

- PyPI: `pip install githubkit`
- [githubkit docs](https://yanyongyu.github.io/githubkit/) 
- [GitHub repo](https://github.com/yanyongyu/githubkit) [3]

### 1.3 PyGithub

The most established Python GitHub library (10+ years). Covers the full
REST API v3 with an OOP interface. Large community and ecosystem.

**Why it matters for ge:** Battle-tested, widely used. However, it's
synchronous-only and uses a heavier OOP style. Good fallback if ghapi
or githubkit don't fit.

- PyPI: `pip install PyGithub`
- [GitHub repo](https://github.com/PyGithub/PyGithub) [4]

### 1.4 Recommendation

**ghapi** is the best fit for `ge`'s philosophy: minimal, dynamic, Pythonic,
CLI-capable. Consider it as an optional backend that `ge` can use when
available, falling back to `gh` CLI subprocess when it's not installed.
This keeps the zero-dependency `gh`-based approach as default while enabling
richer programmatic access.

---

## 2. GitHub MCP Servers

For agents that support MCP natively, these servers provide GitHub tools
without needing CLI wrappers.

### 2.1 GitHub's Official MCP Server

GitHub's own MCP server (16k+ stars). Provides tools for repository
management, issue/PR automation, CI/CD monitoring, code search, and
security analysis. Supports both remote (hosted by GitHub) and local
(Docker/binary) modes. Has dynamic toolset discovery to avoid overwhelming
the model.

**Why it matters for ge:** If `ge` eventually provides an MCP interface,
this is the reference implementation. Its tool design (how it structures
issue/PR data for LLM consumption) is worth studying. It also supports
read-only mode, which is useful for analysis without risk.

- [GitHub repo](https://github.com/github/github-mcp-server) [5]

### 2.2 gh-mcp (munch-group)

A Python MCP server that wraps the `gh` CLI — very similar to `ge`'s
approach but exposed as MCP instead of a skill. Covers repos, PRs,
issues, workflows, releases, and search.

**Why it matters for ge:** Direct inspiration for an MCP version of `ge`.
Since it also wraps `gh` CLI, the auth story is identical.

- [Playbooks page](https://playbooks.com/mcp/munch-group/gh-mcp) [6]

### 2.3 mcp-github-projects

MCP server for GitHub Projects V2 (the board/kanban feature). Uses
GraphQL API.

**Why it matters for ge:** If we want to integrate project board context
(e.g., which column an issue is in, priority fields), this provides the
GraphQL queries we'd need.

- PyPI: `pip install mcp-github-projects`
- [PyPI page](https://pypi.org/project/mcp-github-projects/) [7]

### 2.4 FastMCP / MCP Python SDK

The official Python SDK for building MCP servers. If `ge` adds an MCP
interface, this is what we'd build on.

- [GitHub repo](https://github.com/modelcontextprotocol/python-sdk) [8]

---

## 3. Claude Code GitHub Integrations

### 3.1 claude-code-action (Anthropic official)

The official GitHub Action for Claude Code. Lets you @claude in any issue
or PR comment and Claude will analyze code, implement changes, and create
PRs. Built on the Claude Agent SDK.

**Why it matters for ge:** This is the CI/CD counterpart to what `ge` does
locally. Understanding its architecture helps us ensure `ge`'s context
documents are compatible with what claude-code-action would also produce.
We could potentially have `ge prepare` output a format that claude-code-action
workflows can also consume.

- [GitHub repo](https://github.com/anthropics/claude-code-action) [9]
- [Docs](https://code.claude.com/docs/en/github-actions) [10]

### 3.2 Claude Agent SDK (Python)

Anthropic's Python SDK for programmatically running Claude Code. Supports
custom tools, hooks, streaming, and multi-turn conversations.

**Why it matters for ge:** If we want `ge` to not just *prepare* context
but actually *orchestrate* Claude working on the issue, the Agent SDK is
how we'd do it. A future `ge work <url>` command could use this to
spawn an agent with full context.

- [GitHub repo](https://github.com/anthropics/claude-agent-sdk-python) [11]

---

## 4. Existing Claude Code Skills (GitHub-related)

These are skills from the community that overlap with `ge`'s domain.
Worth studying for patterns, instructions, and gaps.

### 4.1 git-pushing

Automates git operations and repository interactions. 

- [awesome-claude-skills listing](https://github.com/ComposioHQ/awesome-claude-skills) [12]

### 4.2 finishing-a-development-branch

Guides completion of development work by presenting clear options and
handling the chosen workflow (merge, rebase, squash, etc.).

**Why it matters for ge:** Complementary to `ge` — once the agent has
fixed an issue, this skill handles the branch/PR submission workflow.

- [awesome-claude-skills listing](https://github.com/ComposioHQ/awesome-claude-skills) [12]

### 4.3 review-implementing

Evaluates code implementation plans and aligns with specs. 

**Why it matters for ge:** Could be composed with `ge` — first `ge`
prepares the context, then this skill guides the implementation review.

- [awesome-claude-skills listing](https://github.com/BehiSecc/awesome-claude-skills) [13]

### 4.4 test-fixing

Detects failing tests and proposes patches or fixes.

- [awesome-claude-skills listing](https://github.com/BehiSecc/awesome-claude-skills) [13]

### 4.5 subagent-driven-development

Dispatches independent subagents for individual tasks with code review
checkpoints between iterations.

**Why it matters for ge:** For complex issues that touch multiple files/systems,
`ge` could decompose the issue into subtasks and dispatch subagents.

- [awesome-claude-skills listing](https://github.com/ComposioHQ/awesome-claude-skills) [12]

### 4.6 Anthropic Official Skills Repo

Anthropic's own skill examples covering creative, technical, enterprise,
and document workflows. Good reference for skill structure and patterns.

- [GitHub repo](https://github.com/anthropics/skills) [14]

### 4.7 Changelog Generator

Automatically creates user-facing changelogs from git commits.

**Why it matters for ge:** After `ge` helps fix an issue and submit a PR,
this could generate the changelog entry.

- [awesome-claude-skills listing](https://github.com/ComposioHQ/awesome-claude-skills) [12]

---

## 5. Video Frame Extraction

`ge` currently uses evenly-spaced ffmpeg frame extraction. Smarter
approaches exist.

### 5.1 PySceneDetect

The standard Python library for detecting scene changes in video.
Multiple detection algorithms: ContentDetector (HSV differences for
fast cuts), AdaptiveDetector (rolling average, handles camera motion),
ThresholdDetector (fades), and HashDetector (perceptual hashing).

**Why it matters for ge:** Instead of extracting N evenly-spaced frames,
we can detect actual scene changes and extract one frame per scene. For
a bug reproduction video, this means we get one frame per distinct UI
state rather than potentially multiple frames of the same state.

```python
from scenedetect import detect, ContentDetector
scene_list = detect('bug_video.mp4', ContentDetector())
# scene_list is [(start_timecode, end_timecode), ...]
# Extract one frame per scene at the midpoint
```

Can also save images directly and split videos:

```python
from scenedetect import detect, ContentDetector, split_video_ffmpeg
scene_list = detect('video.mp4', ContentDetector())
split_video_ffmpeg('video.mp4', scene_list)
```

- PyPI: `pip install scenedetect[opencv]`
- [Website & docs](https://www.scenedetect.com/) 
- [GitHub repo](https://github.com/Breakthrough/PySceneDetect) [15]
- [API docs](https://www.scenedetect.com/docs/latest/api.html) [16]

### 5.2 ffmpeg scene filter (no extra dependency)

If we want to avoid the scenedetect dependency, ffmpeg itself has a
scene change filter:

```bash
ffmpeg -i video.mp4 -vf "select=gt(scene\,0.3)" -vsync vfr frame_%03d.jpg
```

This extracts frames where the scene change score exceeds 0.3 (0-1 scale).
Simpler than PySceneDetect but less configurable.

**Why it matters for ge:** Zero extra Python dependencies. Can be used as
the default, with PySceneDetect as an optional upgrade.

---

## 6. Image Description / Vision Models

Since Claude Code can't read image files from disk, generating text
descriptions of images could bridge the gap.

### 6.1 Moondream

A tiny (1.86B parameter) vision-language model that runs locally. Does
image captioning, visual question answering, object detection, and
pointing. Uses only ~5GB VRAM. Available via HuggingFace Transformers
or the `moondream` Python package (which supports both local and cloud).

**Why it matters for ge:** If the user has a GPU (or uses the cloud API),
`ge` could auto-describe screenshots from issues. The description gets
embedded in the context document, giving the agent *some* visual
understanding even without pasting images. Especially valuable for UI
bug screenshots.

```python
import moondream as md
from PIL import Image

model = md.vl(api_key="<key>")  # or local endpoint
image = Image.open(".ge/media/screenshot.png")
caption = model.caption(image)["caption"]
answer = model.query(image, "What error message is shown?")["answer"]
```

- PyPI: `pip install moondream`
- [GitHub repo](https://github.com/vikhyat/moondream) [17]
- [HuggingFace model](https://huggingface.co/vikhyatk/moondream2) [18]
- [Moondream docs](https://docs.moondream.ai/) [19]

### 6.2 Ollama + LLaVA

For users running Ollama locally, LLaVA models can describe images
via a simple API call. No cloud dependency.

```python
import ollama
response = ollama.chat(
    model="llava",
    messages=[{
        'role': 'user',
        'content': 'Describe this screenshot of a UI bug',
        'images': ['.ge/media/screenshot.png'],
    }]
)
```

**Why it matters for ge:** Many developers already have Ollama running.
`ge` could detect it and use it opportunistically for image descriptions.

- [Ollama](https://ollama.com/) [20]

### 6.3 Anthropic API (direct)

If the user has an Anthropic API key, we can send images directly to
Claude's vision API for description. This gives the highest quality
descriptions but costs money per call.

**Why it matters for ge:** Premium option. Could be gated behind a
`--describe-images` flag or config setting.

---

## 7. Other Relevant Tools

### 7.1 Playwright MCP

Browser automation via MCP. Can take screenshots of live web pages.

**Why it matters for ge:** For issues about web UI bugs, the agent could
navigate to the relevant page and take a fresh screenshot to compare
against the issue's screenshot.

- [npm package](https://www.npmjs.com/package/@modelcontextprotocol/server-playwright) [21]

### 7.2 Composio Connect

Lets Claude take actions across 500+ apps (Gmail, Slack, GitHub, Notion,
etc.). Handles auth.

**Why it matters for ge:** If `ge` needs to cross-reference Slack
discussions or Notion docs related to an issue, Composio provides the
connectors.

- [Website](https://composio.dev/) [22]

### 7.3 Serena MCP

Code intelligence MCP server with symbol navigation, call hierarchies,
and project memory. Supports 20+ languages.

**Why it matters for ge:** When `ge` identifies files referenced in an
issue, Serena could help the agent understand the code structure
(find_symbol, call hierarchies) before making changes.

- [GitHub repo](https://github.com/oraios/serena) [23]

---

## 8. Integration Priority Matrix

| Tool | Effort | Impact | Priority |
|------|--------|--------|----------|
| PySceneDetect (smarter video frames) | Low | Medium | P1 |
| ffmpeg scene filter (zero-dep) | Very Low | Medium | P1 |
| ghapi (replace subprocess) | Medium | Medium | P2 |
| Moondream (image descriptions) | Medium | High | P2 |
| Ollama/LLaVA (local image desc) | Low | Medium | P2 |
| Claude-code-action compatibility | Low | High | P2 |
| MCP server interface | Medium | Medium | P3 |
| GitHub official MCP (reference) | Study | — | P3 |
| Anthropic API vision | Low | High | P3 |
| Claude Agent SDK orchestration | High | High | P4 |
| Serena (code intelligence) | Medium | Medium | P4 |
| Playwright (live screenshots) | Medium | Low | P5 |

---

## REFERENCES

[1] [fastai/ghapi](https://github.com/fastai/ghapi) — GitHub repo
[2] [GitHub Blog: Learn about ghapi](https://github.blog/developer-skills/programming-languages-and-frameworks/learn-about-ghapi-a-new-third-party-python-client-for-the-github-api/) — Announcement post  
[3] [yanyongyu/githubkit](https://github.com/yanyongyu/githubkit) — GitHub repo
[4] [PyGithub/PyGithub](https://github.com/PyGithub/PyGithub) — GitHub repo
[5] [github/github-mcp-server](https://github.com/github/github-mcp-server) — GitHub's official MCP server
[6] [munch-group/gh-mcp](https://playbooks.com/mcp/munch-group/gh-mcp) — gh CLI MCP wrapper
[7] [mcp-github-projects](https://pypi.org/project/mcp-github-projects/) — PyPI
[8] [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) — MCP Python SDK
[9] [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action) — Official GitHub Action
[10] [Claude Code GitHub Actions docs](https://code.claude.com/docs/en/github-actions) — Official docs
[11] [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — Agent SDK
[12] [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) — Curated skill list
[13] [BehiSecc/awesome-claude-skills](https://github.com/BehiSecc/awesome-claude-skills) — Another curated list
[14] [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's official skill examples
[15] [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) — Scene detection library
[16] [PySceneDetect API docs](https://www.scenedetect.com/docs/latest/api.html) — API reference
[17] [vikhyat/moondream](https://github.com/vikhyat/moondream) — Tiny vision-language model
[18] [vikhyatk/moondream2 on HuggingFace](https://huggingface.co/vikhyatk/moondream2) — Model card
[19] [Moondream docs](https://docs.moondream.ai/) — Official documentation
[20] [Ollama](https://ollama.com/) — Local LLM runner
[21] [Playwright MCP](https://www.npmjs.com/package/@modelcontextprotocol/server-playwright) — Browser automation
[22] [Composio](https://composio.dev/) — Multi-app connector for AI agents
[23] [oraios/serena](https://github.com/oraios/serena) — Code intelligence MCP server
