# GitHub Reference

Use this reference when the user asks what a public repository does, how it is structured, whether it is usable, or how to learn from it.

## Inspection Priority

Read in this order:

1. Repository name, description, stars/forks if available, default branch, and latest visible activity.
2. `README`, `docs/`, examples, and screenshots.
3. Manifests and dependency files such as `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `requirements.txt`, or `pom.xml`.
4. Entry points, CLI definitions, app routes, package exports, or main modules.
5. Tests, CI workflows, and release notes when assessing maturity.

## Tool Preference

- Use `gh` when it is installed and authenticated, especially for repository metadata, issues, releases, and file listings.
- Use `git` for public clone or shallow inspection when source layout matters.
- Use raw GitHub URLs or web reading when only a few files are needed.
- Do not require authentication for public repository MVP analysis.

## Analysis Pattern

1. Identify the repository's purpose in one sentence.
2. Map the main modules or folders to their responsibilities.
3. Identify the public interface: CLI commands, library exports, app entry points, or workflow files.
4. Note setup requirements and external services.
5. Call out uncertainty when the README, manifests, and code disagree.

## Public Repo Limits

- Do not access private repositories unless the user explicitly provides access through the current environment.
- Do not create issues, stars, forks, pull requests, comments, or releases.
- Do not run untrusted code from the repository as part of analysis unless the user explicitly asks and the risk is acceptable.
- Prefer reading files over executing project commands.

## Fallbacks

- If `gh` is missing or not logged in, use public GitHub web pages, raw URLs, or `git ls-remote`.
- If cloning is too large or unnecessary, inspect only README, manifests, docs, and top-level tree.
- If the repository is unavailable, search for mirrors, package registry pages, or documentation sites.
