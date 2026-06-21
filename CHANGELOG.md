# Changelog

All notable changes to this project are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/);
each section corresponds to a git version tag (which is also the release
published to PyPI). Entries are commit subjects and PR titles, verbatim.

## [0.1.11] - 2026-05-27

- Rename autonomy skills with ge- prefix ([#3](https://github.com/thorwhalen/ge/pull/3))

## [0.1.10] - 2026-05-27

- Add autonomous-execution capability: GitHub-backed memory + headless runner + skills ([#2](https://github.com/thorwhalen/ge/pull/2))

## [0.1.9] - 2026-03-31

- Rewrite README (skills-first structure), add CLAUDE.md, remove root SKILL.md

## [0.1.8] - 2026-03-31

- Add .claude/skills symlinks to bundled ge skills

## [0.1.7] - 2026-03-31

- Update README with flexible input forms and confirmation workflow

## [0.1.6] - 2026-03-31

- Add resolve_target() and rewrite ge skill for flexible "work on THIS" input

## [0.1.5] - 2026-03-31

- Add AI image description and clipboard montage for visual context

## [0.1.4] - 2026-03-31

- Fix CLI examples: use --number for prepare commands

## [0.1.3] - 2026-03-31

- Fix media detection: bare GitHub asset URLs, file extensions, video frame dirs

## [0.1.2] - 2026-03-31

- Move default output directory from .ge/ to ~/.cache/ge/<owner>/<repo>/<kind>_<number>/

## [0.1.1] - 2026-03-17

- Add skills management functionality and documentation
- Add unit tests for ge.analysis, ge.media, and ge.util modules
- Initial project setup via wads
