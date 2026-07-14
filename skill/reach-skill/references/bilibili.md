# Bilibili Reference

Use this reference when the user gives a Bilibili URL, a BV identifier, or asks to search/read public Bilibili videos.

## Commands

```bash
auto-reach doctor
auto-reach install --check
auto-reach bilibili auto "BV号、B站URL、或关键词" --pretty
auto-reach bilibili search "关键词" --type video --max-results 5 --pretty
auto-reach bilibili video BV1xxxx --subtitle --comments --related --pretty
auto-reach bilibili hot --page 1 --max-results 10 --pretty
auto-reach bilibili rank --day 3 --max-results 10 --pretty
auto-reach bilibili user "用户名或UID" --pretty
auto-reach bilibili user-videos "UID" --max-results 10 --pretty
auto-reach bilibili status --pretty
```

If doctor reports `bili-cli` as missing, stop and ask the user to run:

```bash
auto-reach install --install bili --dry-run
```

If the user explicitly asks to configure or repair Bilibili support, use:

```bash
auto-reach setup bilibili --dry-run --pretty
```

When the current user request already authorizes setup, installation, repair, or environment configuration, continue with:

```bash
auto-reach setup bilibili --yes --pretty
```

Ask before `--yes` when the user only asked for research or when the dry-run plan includes unexpected tools. Use `--upgrade` only when the user asks to update Bilibili tooling.

## Routing

- Use `auto` for Bilibili URLs, `b23.tv` URLs, BV identifiers, or ambiguous text.
- Use `search` for discovery. Default fallback is Tavily search over `site:bilibili.com/video`.
- Use `video` when the user gives a known BV ID or video URL and wants details, subtitles, comments, or related videos.
- Use `hot` or `rank` for public trending/ranking requests.
- Use `user` and `user-videos` only for public user profile/video listing.

## Boundaries

- `bili-cli` is the primary Bilibili backend.
- Tavily is search discovery fallback only; it returns candidate public video URLs and does not replace structured Bilibili details.
- Do not use `yt-dlp` for Bilibili in this project.
- Do not run write actions such as like, coin, triple, follow, unfollow, dynamic posting, or deletion.
- Do not download audio or video in v1.
- If both `bili-cli` and Tavily fallback fail, report both error categories from the wrapper output.
