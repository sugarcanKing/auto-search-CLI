# Xiaohongshu Reference

Use this reference when the user asks to authorize Xiaohongshu access, gives a Xiaohongshu URL, or asks to search/read Xiaohongshu notes, comments, users, hot content, topics, or public user pages. Account-scoped commands are allowed only when the user explicitly asks for their own account data.

## Commands

```bash
auto-reach doctor
auto-reach setup xiaohongshu --dry-run --pretty
auto-reach xiaohongshu login --method browser --pretty
auto-reach xiaohongshu login --method qrcode --pretty
auto-reach xiaohongshu login --method qrcode --timeout 1800 --pretty
auto-reach xiaohongshu status --pretty
auto-reach xiaohongshu auto "小红书URL或关键词" --pretty
auto-reach xiaohongshu search "关键词" --sort general --type all --page 1 --pretty
auto-reach xiaohongshu read "笔记ID或URL" --pretty
auto-reach xiaohongshu comments "笔记ID或URL" --pretty
auto-reach xiaohongshu user "user_id" --pretty
auto-reach xiaohongshu user-posts "user_id" --pretty
auto-reach xiaohongshu hot --category travel --pretty
auto-reach xiaohongshu topics "旅行" --pretty
auto-reach xiaohongshu search-user "用户名" --pretty
auto-reach xiaohongshu logout --pretty
```

Explicit account-scoped commands require `--account` and should only be used when the user asks for "我的" current-user data:

```bash
auto-reach xiaohongshu whoami --account --pretty
auto-reach xiaohongshu feed --account --pretty
auto-reach xiaohongshu unread --account --pretty
auto-reach xiaohongshu notifications --account --type likes --pretty
```

If doctor reports `xhs-cli` as missing and the user has authorized setup, use:

```bash
auto-reach setup xiaohongshu --dry-run --pretty
auto-reach setup xiaohongshu --yes --pretty
```

Use `--upgrade` only when the user explicitly asks to update Xiaohongshu tooling.

## Routing

- Use this route before generic web search for Xiaohongshu-specific tasks, including "小红书上怎么说", Xiaohongshu notes, comments, users, and sentiment/discussion summaries.
- Do not use Tavily or general web search as a substitute unless Xiaohongshu auth/tooling is blocked or the user explicitly asks for web fallback.
- Use `auto` for Xiaohongshu URLs and ambiguous Xiaohongshu text.
- Use `search` for note discovery. This uses upstream `xhs`, not Tavily.
- Use `read` for a known note URL, note ID, or short index produced by a previous `xhs` list command.
- Use `comments` and `sub-comments` only for reading existing public/authorized comments.
- Use `user`, `user-posts`, `hot`, `topics`, and `search-user` for readonly discovery.
- Use `whoami`, `feed`, `unread`, and `notifications` only in explicit account mode when the user asks for their own account data; pass `--account`.

## Authentication

- `login --method browser` asks upstream `xhs` to extract valid local browser cookies.
- `login --method qrcode` starts upstream QR-code login for the user to scan and confirm.
- QR-code login streams the QR code and prompts to stderr. If running this through an Agent tool, show that stderr content to the user so they can scan it.
- Browser-cookie login defaults to 180 seconds.
- QR-code login defaults to 900 seconds because the first run may download the Camoufox browser runtime before showing the QR code. Use `--timeout 1800` if the first download is slow.
- If QR-code login fails before showing a QR code with a GitHub API error such as `403 Client Error: rate limit exceeded` for `https://api.github.com/repos/daijro/camoufox/releases`, treat it as an upstream Camoufox runtime download failure, not an Auto Reach login failure. Do not keep retrying aggressively; wait for the GitHub API limit to reset, pre-warm/install the Camoufox runtime locally, or switch to `login --method browser` after the user has a valid Xiaohongshu web session.
- Never ask the user to paste raw cookies into chat.
- Never print cookie values, saved cookie files, or browser cookie contents.
- Do not pass or expose `--cookie-source` on ordinary reading commands. Browser cookie extraction is only part of `login --method browser`.
- If `auth_required` occurs, ask the user to run one of the login commands.
- If `verification_required` occurs, ask the user to complete verification in the browser and retry.
- If `rate_limited`, `ip_blocked`, or IP block occurs, stop and report the provider error.

## Boundaries

- `xhs-cli` is the primary Xiaohongshu backend.
- Tavily is not the default fallback for Xiaohongshu.
- Do not run write actions: `like`, `favorite`, `unfavorite`, `comment`, `reply`, `follow`, `unfollow`, `post`, `delete`, or `delete-comment`.
- Do not bypass captcha, verification, rate limits, or access controls.
- Do not use raw browser automation or manual cookie extraction outside upstream `xhs`.
- Ordinary reading commands are bounded to short timeouts and page ranges. Do not use unbounded comment crawling.
- Auto Reach redacts `xsec_token`, token, cookie, auth, and URL userinfo from errors, command echoes, results, and `sources`. Use clickable source URLs without raw tokens.

## Final Answer Style

- Give the user the answer, not the command log.
- Cite Xiaohongshu notes as clickable links from the provider `sources` field.
- Do not show bare note IDs unless the user asks for debugging details.
- Do not list `doctor`, `status`, `search`, `read`, or `comments` commands in normal final answers.
- Include retrieval commands only when the user asks how to reproduce the result or troubleshoot the toolchain.
