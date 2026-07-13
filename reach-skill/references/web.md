# Web Page Reference

Use this reference when the user provides one or more URLs or asks to summarize, inspect, or extract facts from a web page.

## Default Tool

Use the encapsulated page extraction entrypoint:

```bash
python reach-skill/scripts/reach_web.py auto "https://example.com/page" --pretty
python reach-skill/scripts/reach_web.py extract "https://example.com/page" --format markdown --pretty
```

Use `auto` when the input may be either a URL or a query. It extracts direct HTTP URLs and searches non-URL text. Pass multiple URLs to `extract` when comparing sources. Use `--extract-depth advanced` only when basic extraction misses important content.

## Reading Order

1. Extract the provided URL with `reach_web.py extract`.
2. Identify the page title, publisher, date if present, and main content area.
3. Extract only the sections relevant to the user's request.
4. Follow links only when needed to resolve missing context, definitions, citations, or next-step documentation.
5. Preserve important numbers, names, dates, and constraints exactly.

## Static vs Dynamic Pages

Use a static fetch or reader first when it gives complete content. Use a browser/rendered page when:

- The page requires client-side rendering.
- Navigation, tabs, accordions, or lazy-loaded content hide the requested information.
- The static text is empty, truncated, or mostly boilerplate.

If both static and rendered access fail, explain what failed and use search to find an accessible copy, official mirror, or cached documentation.

## Extraction Rules

- Separate page facts from your own interpretation.
- Do not quote long passages. Summarize instead, and quote only short phrases when necessary.
- Keep page metadata with the extracted facts when it affects reliability.
- For documentation pages, capture version selectors, deprecation notices, prerequisites, and examples that affect implementation.

## Fallbacks

- Try the root domain or documentation index if a deep URL fails.
- Search the exact page title or URL.
- For GitHub-hosted docs, switch to `github.md` and inspect the repository directly.
- If the page is gated, private, or blocked, do not bypass it; ask for accessible content or use public alternatives.
- If `reach_web.py` returns `timeout`, retry once with a narrower URL or shorter task; then switch to search or browser fallback.
- If it returns `network_resolution` or `network_connection`, treat it as environment/network instability rather than missing content.
