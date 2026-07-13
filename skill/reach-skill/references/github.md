# GitHub Reference

Use this reference for finding, comparing, inspecting, or learning from GitHub repositories. "GitHub project" means repository unless the user explicitly means Projects boards.

## Commands

```bash
auto-reach doctor
auto-reach install --check
auto-reach github auto "https://github.com/tavily-ai/tavily-python" --pretty
auto-reach github search "agent skill" --limit 5 --pretty
auto-reach github view tavily-ai/tavily-python --pretty
auto-reach github read-dir tavily-ai/tavily-python --pretty
auto-reach github read-file tavily-ai/tavily-python README.md --pretty
auto-reach github inspect tavily-ai/tavily-python --pretty
```

If doctor reports `gh` as missing, stop and ask the user to run:

```bash
auto-reach install --install gh
```

If automatic installation is unavailable, install GitHub CLI from `https://cli.github.com/`, then run `gh auth login` if authenticated access is needed.

## Auto Routing

Use `auto` when the input may be a GitHub URL, `OWNER/REPO`, or search terms:

- Repository URL or `OWNER/REPO` routes to `inspect`.
- `blob` or raw file URL routes to `read-file`.
- `tree` URL routes to `read-dir`.
- Other text routes to repository search.

## Inspection Priority

1. Repository metadata from `view`.
2. Root tree from `read-dir`.
3. README, docs, examples, and screenshots.
4. Manifests such as `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `requirements.txt`, or `pom.xml`.
5. Entry points, CLI definitions, app routes, package exports, or main modules.
6. Tests, CI workflows, and release notes when assessing maturity.

Use `inspect OWNER/REPO` for the first pass; it combines metadata, root listing, README, and common manifests.

## Search Pattern

1. Start with `github search "specific terms" --limit 5`.
2. Add `--language` when the ecosystem is known.
3. Add `--match name`, `--match description`, or `--match readme` when the query is broad.
4. Use `--include-forks true` only when forks matter.
5. Avoid archived repositories unless requested.

## Safety And Failures

- Do not create issues, stars, forks, pull requests, comments, releases, or other mutations.
- Do not run untrusted repository code unless the user explicitly asks and accepts the risk.
- `not_found_or_private`: nonexistent repo, private repo, or insufficient token access. Do not retry repeatedly.
- `auth_required`: ask the user to authenticate `gh` or provide a public source.
- `forbidden_or_rate_limited`: stop GitHub CLI calls and use web/search fallback only if public data is enough.
- Missing `gh`: prefer setup first; use public GitHub pages or raw URLs only as an explicit fallback.
