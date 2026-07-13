# Search Reference

Use this reference when the user asks for broad research, comparison, discovery, or current information that is not tied to a single known URL.

## Query Design

- Start with the user's exact terms, then add disambiguating terms such as product name, programming language, company, version, or date.
- Prefer official and primary-source queries early:
  - `<topic> official docs`
  - `<project> GitHub`
  - `<company> blog release notes`
  - `<standard or API> specification`
- Use domain filters when the likely source is known:
  - `site:github.com <repo or library>`
  - `site:docs.<vendor>.com <feature>`
  - `site:<vendor>.com pricing docs changelog`
- For errors, search the exact error in quotes first, then remove local paths, hashes, and machine-specific values.

## Source Selection

Prefer sources in this order:

1. Official documentation, source repositories, standards, or release notes.
2. Maintainer-authored issues, discussions, or blog posts.
3. Reputable third-party technical writeups.
4. Forum or social sources only when primary sources are absent or when debugging lived experience matters.

Avoid relying on low-signal pages that only aggregate or rewrite other content. If a search result claims something important, follow it to the primary source before using it.

## Working Pattern

1. Run a narrow search for primary sources.
2. Open the best primary sources and capture the relevant facts.
3. If the result set is weak, broaden the search with synonyms.
4. If sources disagree, report the disagreement and prefer the newer or more authoritative primary source.
5. Include source links in the final answer when the environment supports browsing links.

## Fallbacks

- If search fails, try known official domains directly.
- If the topic is a code project, move to `github.md` and inspect the repository.
- If search results are stale, look for changelogs, release pages, or dated docs.
- If only secondary sources are available, say that the finding is based on secondary sources.
