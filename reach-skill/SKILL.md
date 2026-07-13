---
name: reach-skill
description: Route public research tasks through the Auto Reach capability layer for Tavily-backed web search, Tavily-backed page extraction, and gh-backed GitHub repository reading. Use for online topic research, URL summarization, source comparison, GitHub repository search, GitHub URL routing, and public repository inspection. Do not use for video subtitles, social media automation, posting, form submission, private data access, credential management, or dependency installation unless the user explicitly asks for setup.
---

# Reach Skill

## Role

This Skill is the Agent-facing routing guide. The runtime implementation lives in the Auto Reach capability layer and should be called through `auto-reach` or `python -m auto_reach`.

Always run a readiness check before retrieval:

```bash
auto-reach doctor
```

If the console command is unavailable in the current environment, try:

```bash
python -m auto_reach doctor
```

If doctor reports missing dependencies, stop the retrieval path and show the user the setup command from `auto-reach install --check`. Do not silently install dependencies during research.

## Routing

| User intent | Primary command | Reference |
| --- | --- | --- |
| Broad web research or current information | `auto-reach search "query"` | `references/search.md` |
| User gives a non-GitHub URL | `auto-reach web auto "URL"` | `references/web.md` |
| Read or summarize selected URLs | `auto-reach web extract "URL"` | `references/web.md` |
| User gives a GitHub URL or `OWNER/REPO` | `auto-reach github auto "input"` | `references/github.md` |
| Search GitHub repositories | `auto-reach github search "query"` | `references/github.md` |
| Inspect a public GitHub repository | `auto-reach github inspect OWNER/REPO` | `references/github.md` |

Read the matching reference file before running the task command.

## Workflow

1. Classify the input as web query, web URL, GitHub URL, `OWNER/REPO`, or GitHub search.
2. Run `auto-reach doctor` once before local retrieval.
3. Use one primary route from the table.
4. Prefer primary sources: official docs, source repos, standards, release notes, vendor pages.
5. Report wrapper errors directly when dependencies, auth, network, private access, or timeouts block the route.
6. Separate sourced facts from inference in the final answer.

## Safety Boundaries

- Do not log in, manage cookies, harvest credentials, or bypass access controls.
- Do not post, comment, vote, submit forms, open issues, star, fork, or mutate remote systems.
- Do not scrape private, gated, or unauthorized content.
- Do not install tools automatically during research.
- Treat `not_found_or_private`, `auth_required`, and `forbidden_or_rate_limited` as terminal until the user changes access or asks for fallback.
- Use wrapper timeouts. If a provider times out repeatedly, report the failure and switch to an explicit fallback.

## Output

- Name the sources or tools used.
- Include links or repository paths when available.
- For GitHub analysis, include purpose, main folders, public interface, setup signals, and confidence level.
