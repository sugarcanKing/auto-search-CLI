# Web Page Reference

Use this reference when the user provides URLs or asks to summarize, inspect, or extract facts from web pages.

## Commands

```bash
auto-reach doctor
auto-reach install --check
auto-reach web auto "https://example.com/page" --pretty
auto-reach web read "https://example.com/page" --pretty
auto-reach web extract "https://example.com/page" --format markdown --pretty
```

Use `web auto` when the input may be either a URL or a query. URL inputs route to `web read`.

Default URL read order:

1. Jina Reader (`jina_reader`), no local API key required.
2. Direct HTTP through local `curl` (`direct_http`), no API key required.
3. Tavily extraction fallback, when configured.

Use `extract` only when you specifically need Tavily extraction options or multiple URLs in one Tavily call. Use `--extract-depth advanced` only when basic extraction misses important content.

If doctor reports `tavily_python` as missing, inspect `doctor --json`:

```bash
auto-reach doctor --json
```

Then use `agent_guidance.channels.web`.

- If `status` is `setup_required` and `safe_to_execute_setup` is `true`, run `dry_run_command`, inspect that it only installs expected Auto Reach web dependencies, then run `execute_command`.
- If `web_read` is ready but `web_search` is `setup_recommended`, continue URL reading through Jina Reader.
- If `next_actions` mentions `TAVILY_API_KEY`, report it to the user; do not create or edit credentials automatically.
- After successful setup, rerun `auto-reach doctor --json`, then retry the web command.

## Reading Order

1. Read the provided URL with `auto-reach web read`.
2. Identify title, publisher, date if present, and main content.
3. Keep only sections relevant to the user's request.
4. Follow links only when needed to resolve missing context.
5. Preserve important numbers, names, dates, and constraints exactly.

## Dynamic Pages

Use rendered/browser access when static extraction is empty, truncated, boilerplate-heavy, or hidden behind client-side UI. If both static and rendered access fail, explain what failed and search for an accessible official copy.

## Extraction Rules

- Separate page facts from interpretation.
- Avoid long quotes; summarize instead.
- Preserve page metadata when it affects reliability.
- For docs, capture versions, deprecations, prerequisites, and examples that affect implementation.

## Fallbacks

- Try the root domain or docs index if a deep URL fails.
- Search the exact page title or URL.
- For GitHub-hosted docs, switch to `github.md`.
- If a page is gated/private/blocked, do not bypass it.
- If the wrapper returns `timeout`, retry once with a narrower URL or shorter task, then switch fallback.
