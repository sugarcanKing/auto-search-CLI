# Web Page Reference

Use this reference when the user provides URLs or asks to summarize, inspect, or extract facts from web pages.

## Commands

```bash
auto-reach doctor
auto-reach install --check
auto-reach web auto "https://example.com/page" --pretty
auto-reach web extract "https://example.com/page" --format markdown --pretty
```

Use `web auto` when the input may be either a URL or a query. Pass multiple URLs to `extract` when comparing sources. Use `--extract-depth advanced` only when basic extraction misses important content.

If doctor reports `tavily_python` as missing, stop and ask the user to run:

```bash
auto-reach install --install python
```

## Reading Order

1. Extract the provided URL.
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
