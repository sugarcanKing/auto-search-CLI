# GitHub Reference

Use this reference when the user asks to find, compare, inspect, or learn from GitHub repositories. This skill treats GitHub Projects boards as out of scope; "GitHub project" means repository unless the user says otherwise.

## Default Tool

Use the encapsulated GitHub entrypoint backed by the official `gh` CLI:

```bash
python reach-skill/scripts/reach_github.py auto "https://github.com/tavily-ai/tavily-python" --pretty
python reach-skill/scripts/reach_github.py search "agent skill" --limit 5 --pretty
python reach-skill/scripts/reach_github.py view tavily-ai/tavily-python --pretty
python reach-skill/scripts/reach_github.py read-dir tavily-ai/tavily-python --pretty
python reach-skill/scripts/reach_github.py read-file tavily-ai/tavily-python README.md --pretty
python reach-skill/scripts/reach_github.py inspect tavily-ai/tavily-python --pretty
```

The wrapper returns JSON for stable agent consumption and keeps GitHub command details out of `SKILL.md`.

Use `auto` when the input may be a GitHub URL, `OWNER/REPO`, or search terms:

- Repository URL or `OWNER/REPO` routes to `inspect`.
- `blob` or raw file URL routes to `read-file`.
- `tree` URL routes to `read-dir`.
- Other text routes to repository search.

## Inspection Priority

Read in this order:

1. Repository metadata from `reach_github.py view`.
2. Root tree from `reach_github.py read-dir`.
3. `README`, `docs/`, examples, and screenshots.
4. Manifests such as `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `requirements.txt`, or `pom.xml`.
5. Entry points, CLI definitions, app routes, package exports, or main modules.
6. Tests, CI workflows, and release notes when assessing maturity.

Use `reach_github.py inspect OWNER/REPO` for the normal first pass. It combines metadata, root directory listing, README, and common manifests into one JSON result.

## Search Pattern

1. Start with `reach_github.py search "specific terms" --limit 5`.
2. Add `--language` when the user specifies an ecosystem.
3. Add `--match name`, `--match description`, or `--match readme` when the query is too broad.
4. Use `--include-forks true` only when forks are relevant; use `--include-forks only` when looking for active forks.
5. Avoid archived repositories unless the user asks or no maintained alternative exists.

## Analysis Pattern

1. Identify the repository's purpose in one sentence.
2. Map the main folders to their responsibilities.
3. Identify the public interface: CLI commands, library exports, app entry points, or workflow files.
4. Note setup requirements and external services.
5. Call out uncertainty when README, manifests, and code disagree.

## Public Repo Limits

- Do not create issues, stars, forks, pull requests, comments, releases, or other mutations.
- Do not run untrusted code from the repository unless the user explicitly asks and the risk is acceptable.
- Do not access private repositories unless the user explicitly provides access through the current environment.
- Prefer reading files over executing project commands.

## Failure Handling

- `not_found_or_private`: Treat as either nonexistent repository, private repository, or insufficient token access. Do not retry repeatedly.
- `auth_required`: Ask the user to authenticate `gh` or provide a public source.
- `forbidden_or_rate_limited`: Stop GitHub CLI calls and use web/search fallback if public data is enough.
- `timeout`: Retry once with a smaller read target, then fall back.
- Missing `gh`: Use web search with `site:github.com`, raw URLs, or `git ls-remote`.

## Fallbacks

- If `gh` is missing, use public GitHub web pages, raw URLs, Tavily search with `site:github.com`, or `git ls-remote`.
- If `gh repo read-dir` or `gh repo read-file` is unavailable, the wrapper falls back to `gh api` for repository contents.
- If cloning is too large or unnecessary, inspect only README, manifests, docs, and top-level tree.
- If the repository is unavailable, search for mirrors, package registry pages, or documentation sites.
