# Repository Guidelines

## Project Structure & Module Organization

This repository is currently a minimal scaffold. Keep production code under `src/`. When tests are added, place them in a top-level `tests/` directory that mirrors the structure of `src/`. Reserve the repository root for project metadata and tooling files such as `README.md`, `Makefile`, `package.json`, or `pyproject.toml`.

Do not treat `.codex` as project data; it is a local tooling artifact and should remain uncommitted.

## Build, Test, and Development Commands

No build, test, lint, or run commands are configured yet. Before opening a PR, verify the repository state with:

- `git status --short` to review tracked and untracked changes
- `find src -type f` to confirm the files you are introducing

If you add a runtime or toolchain, expose the common entry points from the repository root and document them here. Prefer standard commands such as `make test`, `npm test`, or `pytest` instead of hidden one-off scripts.

## Coding Style & Naming Conventions

Because no formatter is configured yet, keep style conservative and easy to review:

- use spaces, not tabs
- keep filenames and directories lowercase
- prefer descriptive module names such as `src/parser.py` or `src/data_loader.ts`
- use the formatter and linter native to the stack you introduce, and add their config in the same change

Keep modules focused. Avoid mixing unrelated experiments or generated output into `src/`.

## Testing Guidelines

There is no test framework in place yet. Any non-trivial feature should introduce repeatable automated tests alongside the implementation. Mirror `src/` in `tests/` and use the naming convention native to the chosen stack, for example `test_parser.py` or `parser.test.ts`.

Document the exact test command in the PR description until a shared project command exists.

## Commit & Pull Request Guidelines

This branch has no commit history yet, so there is no established convention to copy. Use short, imperative commit subjects such as `Add parser scaffold` or `Introduce test harness`. Keep each commit focused on one change.

PRs should explain scope, rationale, and verification steps. Link related issues when available. Include screenshots only when the change affects user-facing output.
