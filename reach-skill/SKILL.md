---
name: reach-skill
description: Research and retrieve public information from Tavily-backed web search, web page extraction, and gh-backed GitHub repositories. Use when Codex needs to investigate a topic online, design search queries, read and summarize URLs, compare public sources, search GitHub repositories, inspect public GitHub repositories, or decide which web/GitHub retrieval path to use. Do not use for video subtitles, social media account automation, posting, form submission, private data access, or credential management.
---

# Reach Skill

## Overview

Use this skill as a routing layer for lightweight online research. First classify the user's intent, then choose the smallest reliable retrieval path, then cite or name the sources used.

This skill covers only:

- Web search through the encapsulated `scripts/reach_web.py search` entrypoint
- Web page extraction through the encapsulated `scripts/reach_web.py extract` entrypoint
- Automatic web input routing through `scripts/reach_web.py auto`
- Public GitHub repository search and analysis through the encapsulated `scripts/reach_github.py` entrypoint

## Routing

| User intent | First path | Fallback | Reference |
| --- | --- | --- | --- |
| User gives a non-GitHub URL | Use `scripts/reach_web.py auto URL` or `scripts/reach_web.py extract URL` | Use curl or browser rendering when extraction fails | `references/web.md` |
| User gives a GitHub URL | Use `scripts/reach_github.py auto URL` | Use GitHub web/raw URLs when `gh` is unavailable | `references/github.md` |
| Research a broad topic, product, company, library, or error | Use `scripts/reach_web.py auto "query"` or `scripts/reach_web.py search` | Search official domains, docs, or GitHub directly | `references/search.md` |
| Read, summarize, or extract facts from one or more URLs | Use `scripts/reach_web.py extract` on selected URLs | Use curl or a browser/rendered page when extraction fails | `references/web.md` |
| Search for GitHub repositories | Use `scripts/reach_github.py search` with targeted query terms | Use web search with `site:github.com` when `gh` is unavailable | `references/github.md` |
| Understand a public GitHub repository | Use `scripts/reach_github.py auto` or `scripts/reach_github.py inspect` on `OWNER/REPO` | Use `git`, raw GitHub URLs, or web reading when `gh` is unavailable | `references/github.md` |

Before complex GitHub or local-tool workflows, run:

```bash
python reach-skill/scripts/doctor.py
```

To verify live Tavily access when quota use is acceptable, run:

```bash
python reach-skill/scripts/doctor.py --online
```

For machine-readable status, run:

```bash
python reach-skill/scripts/doctor.py --json
```

## Workflow

1. Restate the research target briefly if it is ambiguous.
2. Select exactly one primary route from the routing table.
3. Read the matching reference file before doing the work.
4. Prefer primary sources: official docs, source repositories, standards, release notes, or vendor pages.
5. Use secondary sources only to discover primary sources or compare claims.
6. Report uncertainty when sources disagree or when a source could not be accessed.
7. Keep retrieved content scoped to the user's question; do not collect unrelated data.

## Safety Boundaries

- Do not log in, manage cookies, harvest credentials, or bypass access controls.
- Do not post, comment, vote, submit forms, open issues, or mutate remote systems.
- Do not scrape private or gated content.
- Do not install tools automatically. If `tavily-python`, `TAVILY_API_KEY`, or `gh` is missing, explain the missing dependency and use an available fallback.
- Treat `not_found_or_private`, `auth_required`, and `forbidden_or_rate_limited` wrapper errors as terminal until the user provides access or a different public source.
- Use wrapper timeouts instead of long-running manual retries. If a provider times out repeatedly, report the failure and switch fallback route.
- Do not handle video subtitle workflows in this MVP.
- Do not treat this skill as a general report-writing skill; use it only for retrieval and source-grounded investigation.

## Output Expectations

- Name the sources or tools used.
- Separate sourced facts from inference.
- Prefer concise answers with links or repository paths when available.
- For GitHub analysis, include the repository's apparent purpose, main entry points, important manifests, and confidence level.
