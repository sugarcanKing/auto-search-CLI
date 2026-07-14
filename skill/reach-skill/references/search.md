# Search Reference

Use this reference for broad research, comparison, discovery, or current information that is not tied to a single known URL.

## Commands

```bash
auto-reach doctor
auto-reach install --check
auto-reach search "query" --max-results 5 --search-depth basic --pretty
auto-reach web auto "query or URL" --pretty
```

Use `web auto` when the input may be a URL. It routes direct HTTP URLs to extraction. Use `--search-depth advanced` only when the first result set is weak or the task needs broader discovery. Use `--include-raw-content markdown` only for small tasks; otherwise search first, choose URLs, then extract.

If doctor reports `tavily_python` as missing, inspect `doctor --json`:

```bash
auto-reach doctor --json
```

Then use `agent_guidance.channels.web`.

- If `status` is `setup_required` and `safe_to_execute_setup` is `true`, run `dry_run_command`, inspect that it only installs Auto Reach Python requirements, then run `execute_command`.
- If `next_actions` mentions `TAVILY_API_KEY`, report it to the user; do not create or edit credentials automatically.
- After successful setup, rerun `auto-reach doctor --json`, then retry `auto-reach search`.

## Query Design

- Start with the user's exact terms, then add product, language, company, version, or date.
- Prefer primary-source queries early: `<topic> official docs`, `<project> GitHub`, `<company> release notes`, `<standard> specification`.
- Use domain filters when useful: `site:github.com`, `site:docs.vendor.com`, `site:vendor.com changelog`.
- For errors, search the exact error in quotes first, then remove local paths, hashes, and machine-specific values.

## Source Selection

Prefer sources in this order:

1. Official documentation, source repositories, standards, or release notes.
2. Maintainer-authored issues, discussions, or blog posts.
3. Reputable third-party technical writeups.
4. Forum/social sources only when primary sources are absent or lived debugging context matters.

Follow important claims back to primary sources before using them.

## Fallbacks

- If search fails, try known official domains directly.
- If the topic is a code project, switch to `github.md`.
- If results look stale, search changelogs, releases, and dated docs.
- If only secondary sources are available, say so.
