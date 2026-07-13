---
name: reach-skill
description: Research and retrieve public information from Tavily-backed web search, web page extraction, and GitHub repositories. Use when Codex needs to investigate a topic online, design search queries, read and summarize URLs, compare public sources, inspect public GitHub repositories, or decide which web/GitHub retrieval path to use. Do not use for video subtitles, social media account automation, posting, form submission, private data access, or credential management.
---

# Reach Skill

## Overview

Use this skill as a routing layer for lightweight online research. First classify the user's intent, then choose the smallest reliable retrieval path, then cite or name the sources used.

This skill covers only:

- Web search through the encapsulated `scripts/reach_web.py search` entrypoint
- Web page extraction through the encapsulated `scripts/reach_web.py extract` entrypoint
- Public GitHub repository analysis

## Routing

| User intent | First path                                                           | Fallback | Reference |
| --- |----------------------------------------------------------------------| --- | --- |
| Research a broad topic, product, company, library, or error | Use ` reach-skill/scripts/reach_web.py search` with targeted queries | Search official domains, docs, or GitHub directly | `references/search.md` |
| Read, summarize, or extract facts from one or more URLs | Use `scripts/reach_web.py extract` on selected URLs                  | Use curl or a browser/rendered page when extraction fails | `references/web.md` |
| Understand a public GitHub repository | Inspect README, manifest files, and directory structure              | Use `gh`, `git`, or raw GitHub URLs depending on availability | `references/github.md` |

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
- Do not install tools automatically. If `tavily-python` or `TAVILY_API_KEY` is missing, explain the missing dependency and use an available fallback.
- Do not handle video subtitle workflows in this MVP.
- Do not treat this skill as a general report-writing skill; use it only for retrieval and source-grounded investigation.

## Output Expectations

- Name the sources or tools used.
- Separate sourced facts from inference.
- Prefer concise answers with links or repository paths when available.
- For GitHub analysis, include the repository's apparent purpose, main entry points, important manifests, and confidence level.
