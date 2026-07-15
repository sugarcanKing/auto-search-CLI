---
name: reach-skill
description: Route public research tasks through the Auto Reach capability layer for Tavily-backed web search, Tavily-backed page extraction, gh-backed GitHub repository reading, bili-cli-backed Bilibili reading, and xhs-backed Xiaohongshu authentication plus readonly reading. Use for online topic research, URL summarization, source comparison, GitHub repository search, GitHub URL routing, public repository inspection, Bilibili video lookup, Bilibili search, Xiaohongshu login/status, Xiaohongshu note search, and Xiaohongshu readonly reading. Do not use for social media posting, form submission, private data access, credential harvesting, Bilibili write actions, Xiaohongshu write actions, Bilibili audio download workflows, or dependency installation unless the user explicitly asks for setup.
---

# Reach Skill

## Role

This Skill is the Agent-facing routing guide. The runtime implementation lives in the Auto Reach capability layer and should be called through `auto-reach`, `python -m auto_reach`, or `python3 -m auto_reach`.

Default to Auto Reach for search and retrieval tasks while using this Skill. If the user asks to search, look up, research, summarize a URL, inspect GitHub, read Bilibili, or read Xiaohongshu, use the matching `auto-reach` route instead of the model's generic web search. Use generic web search only when the user explicitly asks to bypass Auto Reach or when the relevant Auto Reach channel is unavailable after checking readiness and setup guidance.

Always run a readiness check before retrieval:

```bash
auto-reach doctor
```

If the console command is unavailable in the current environment, try:

```bash
python -m auto_reach doctor
python3 -m auto_reach doctor
```

If doctor reports missing dependencies, inspect `agent_guidance.channels` in `doctor --json`. When the needed channel is `setup_required` and `safe_to_execute_setup` is `true`, run its `dry_run_command`, inspect the planned steps, then run its `execute_command` if the plan only contains expected Auto Reach dependency installs. Do not automate credentials, API keys, account login, or unexpected tools.

For Xiaohongshu tasks, route through Auto Reach even when general web search is available. If the user asks about "小红书", "小红书上", notes, comments, Xiaohongshu user discussion, or Xiaohongshu sentiment, use `auto-reach xiaohongshu` first. Do not replace Xiaohongshu retrieval with generic web search unless the user explicitly asks for a web fallback or Xiaohongshu auth/tooling is blocked. Treat current-user Xiaohongshu data as account-scoped; use `--account` only when the user explicitly asks for "我的" feed, notifications, unread counts, or current profile.

If the user explicitly asks to configure, install, repair, update, or upgrade the environment, use setup mode:

```bash
auto-reach setup all --dry-run --pretty
```

When the user's current request already clearly authorizes setup, installation, repair, or environment configuration, run the matching `setup <target> --dry-run --pretty` first, then run `setup <target> --yes --pretty` if the plan only contains expected Auto Reach dependency steps. For ordinary research, only use automatic setup when `doctor --json` marks the needed channel as `setup_required` and `safe_to_execute_setup`. Ask before `--yes` when the plan includes unexpected tools. Use `--upgrade` only when the user explicitly asks to update or upgrade dependencies.

## Routing

| User intent | Primary command | Reference |
| --- | --- | --- |
| Broad web research or current information | `auto-reach search "query"` | `references/search.md` |
| User gives a non-GitHub URL | `auto-reach web auto "URL"` | `references/web.md` |
| Read or summarize selected URLs | `auto-reach web extract "URL"` | `references/web.md` |
| User gives a GitHub URL or `OWNER/REPO` | `auto-reach github auto "input"` | `references/github.md` |
| Search GitHub repositories | `auto-reach github search "query"` | `references/github.md` |
| Inspect a public GitHub repository | `auto-reach github inspect OWNER/REPO` | `references/github.md` |
| User gives a Bilibili URL or BV ID | `auto-reach bilibili auto "input"` | `references/bilibili.md` |
| Search Bilibili videos | `auto-reach bilibili search "query"` | `references/bilibili.md` |
| User gives a Xiaohongshu URL or asks to read/search Xiaohongshu | `auto-reach xiaohongshu auto "input"` | `references/xiaohongshu.md` |
| User asks to authorize Xiaohongshu access | `auto-reach xiaohongshu login --method browser` | `references/xiaohongshu.md` |

Read the matching reference file before running the task command.

## Workflow

1. Classify the input as web query, web URL, GitHub URL, `OWNER/REPO`, GitHub search, Bilibili URL, BV ID, Bilibili search, Xiaohongshu URL, or Xiaohongshu search/read request.
2. Run `auto-reach doctor` once before local retrieval.
3. Use one primary route from the table. Broad search uses `auto-reach search`; Xiaohongshu-specific tasks must use the Xiaohongshu route, not generic web search.
4. Prefer primary sources: official docs, source repos, standards, release notes, vendor pages.
5. Report wrapper errors directly when dependencies, auth, network, private access, or timeouts block the route.
6. Separate sourced facts from inference in the final answer.

## Safety Boundaries

- Do not harvest credentials or bypass access controls.
- Do not log in or manage cookies unless the user explicitly asks to authorize Xiaohongshu access; then only use `auto-reach xiaohongshu login --method browser` or `--method qrcode`.
- Do not use Xiaohongshu account-scoped commands unless the user explicitly asks for their own account data; those commands require `--account`.
- Do not post, comment, vote, submit forms, open issues, star, fork, or mutate remote systems.
- Do not scrape private, gated, or unauthorized content.
- Do not install arbitrary tools automatically during research.
- Use `doctor --json` `agent_guidance` for installable local dependencies. It may authorize `setup <target> --dry-run` followed by `setup <target> --yes` for expected Auto Reach dependency installs.
- Never automate credentials, API keys, cookies, or browser auth state. Xiaohongshu login is allowed only through the explicit `auto-reach xiaohongshu login` commands when the user authorizes it.
- Never ask users to paste raw Xiaohongshu cookies or echo cookie values.
- Do not use `yt-dlp` for Bilibili. Use `auto-reach bilibili` and report wrapper errors or Tavily fallback results.
- Do not run Bilibili write actions such as like, coin, triple, follow, unfollow, or dynamic posting.
- Do not run Xiaohongshu write actions such as like, favorite, unfavorite, follow, unfollow, comment, reply, post, delete, or delete-comment.
- Treat `not_found_or_private`, `auth_required`, and `forbidden_or_rate_limited` as terminal until the user changes access or asks for fallback.
- Use wrapper timeouts. If a provider times out repeatedly, report the failure and switch to an explicit fallback.

## Output

- Name the sources or tools used.
- Include links or repository paths when available.
- For Xiaohongshu answers, cite clickable note links from provider `sources` when available. Do not show bare note IDs in the final answer unless the user asks for debugging details.
- Xiaohongshu source links and errors are token-redacted. Do not reconstruct or expose `xsec_token`, cookies, auth values, or URL userinfo in final answers.
- Do not list executed commands, `doctor` output, status checks, or step-by-step retrieval logs in normal final answers. Include commands only when the user asks how to reproduce or debug the run.
- Optimize normal research answers for the user-facing result: concise conclusion, key evidence, and source links.
- For GitHub analysis, include purpose, main folders, public interface, setup signals, and confidence level.
