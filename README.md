# Auto Reach

Auto Reach is a lightweight capability layer for Agent research workflows. It provides one local CLI for:

- Exa MCP-backed web search through `mcporter`, with Tavily fallback
- Jina Reader-backed public URL reading, with direct HTTP and Tavily extraction fallback
- Tavily-backed web search and URL extraction
- search-and-read source bundles for Agent research
- `gh`-backed GitHub repository search and reading, with public REST API fallback
- `bili-cli`-backed Bilibili search and reading, with Tavily search fallback
- `xhs`-backed Xiaohongshu authentication and readonly reading
- local dependency checks and explicit dependency installation

The Skill is only the Agent-facing routing guide. The reusable runtime lives in `auto_reach/`.

## Project Layout

```text
auto_reach/           # Runtime package and CLI implementation
skill/reach-skill/    # Codex Skill instructions that route Agents to Auto Reach
requirements.txt      # Runtime Python dependencies
pyproject.toml        # Package metadata and auto-reach console script
```

## Quick Start

Auto Reach is developed and distributed as a normal Python package first. During project development, install it in editable mode from this repository:

```bash
python -m pip install -e .
```

This enables the `auto-reach` console command without copying anything into the Codex Skills directory.

```bash
python -m auto_reach doctor
python -m auto_reach install --check
python -m auto_reach web read "https://example.com" --pretty
python -m auto_reach web search "OpenAI Agents SDK documentation" --max-results 3 --pretty
python -m auto_reach research "OpenAI Agents SDK documentation" --max-sources 3 --pretty
python -m auto_reach github auto https://github.com/tavily-ai/tavily-python --pretty
```

After installing the package in editable mode, the same commands are available as:

```bash
auto-reach doctor
auto-reach search "OpenAI Agents SDK documentation" --max-results 3 --pretty
auto-reach read "https://example.com" --pretty
auto-reach research "OpenAI Agents SDK documentation" --max-sources 3 --pretty
auto-reach github inspect tavily-ai/tavily-python --pretty
auto-reach bilibili search "AI Agent 教程" --type video --max-results 5 --pretty
auto-reach xiaohongshu search "美食" --sort popular --pretty
```

Installation is explicit. Research commands do not silently install tools or dependencies.

## Agent Default Policy

This repository is meant to replace ad hoc Agent web browsing with the local Auto Reach capability layer. When an Agent is working in this repository, ordinary requests like "帮我搜索一下..." or "查一下..." should use Auto Reach by default:

```bash
python3 -m auto_reach doctor --json
python3 -m auto_reach search "query" --pretty
python3 -m auto_reach read "URL" --pretty
python3 -m auto_reach research "query" --max-sources 5 --pretty
```

Source-specific requests should use their channel directly, for example `xiaohongshu`, `bilibili`, or `github`. The root [AGENTS.md](AGENTS.md) file records this policy for Codex-style agents. Generic built-in web search should only be used when the user explicitly asks to bypass Auto Reach, or when the relevant Auto Reach channel is unavailable after checking `doctor --json` and setup guidance.

## Agent Setup Workflow

Use `setup` when the user explicitly asks to configure, install, repair, or upgrade the environment. Normal research commands should run `doctor --json` first. If the needed channel reports `agent_guidance.channels.<name>.status == "setup_required"` and `safe_to_execute_setup == true`, an Agent may run the provided dry-run command and then the execute command when the plan only contains expected Auto Reach dependency installs.

```bash
auto-reach setup web --dry-run --pretty
auto-reach setup github --dry-run --pretty
auto-reach setup bilibili --dry-run --pretty
auto-reach setup xiaohongshu --dry-run --pretty
auto-reach setup all --dry-run --pretty
```

`setup` defaults to planning only. If the current user request already clearly authorizes setup, installation, repair, or environment configuration, an Agent should run the dry-run first and then continue with `--yes` when the plan only contains expected Auto Reach dependency steps:

```bash
auto-reach setup bilibili --yes --pretty
auto-reach setup all --yes --pretty
```

Use `--upgrade` only when the user asks to update or upgrade installed tools:

```bash
auto-reach setup github --upgrade --dry-run --pretty
auto-reach setup all --upgrade --yes --pretty
```

Ask before `--yes` when the plan includes unexpected tools. `setup` does not log in, write API keys, or configure accounts. It may install or upgrade local dependencies, then reports remaining next actions such as `TAVILY_API_KEY` or `gh auth login`.

## First-Time Setup

1. Create and activate a Python environment.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

2. Check local readiness.

```bash
auto-reach doctor
auto-reach install --check
```

3. Configure web reading and search.

URL reading works without an API key through Jina Reader:

```bash
auto-reach read "https://example.com" --pretty
```

For stronger search, configure Exa MCP through `mcporter`:

```bash
npm install -g mcporter
mcporter config add exa https://mcp.exa.ai/mcp
auto-reach search "OpenAI Agents SDK documentation" --max-results 3 --pretty
```

Exa MCP currently uses the public MCP endpoint and does not require an Auto Reach-managed API key. Auto Reach still treats this as a backend that must be checked by `doctor`, because provider policy can change.

4. Configure Tavily for search and extraction fallback.

```bash
export TAVILY_API_KEY="tvly-..."
auto-reach search "OpenAI Agents SDK documentation" --max-results 3 --pretty
```

Auto Reach also reads `TAVILY_API_KEY` from the project-root `.env` file, without overriding an already exported environment variable. For safety, `.env` loading is key-scoped: Auto Reach only imports `TAVILY_API_KEY` and ignores unrelated keys such as tokens, proxies, or package index settings.

```bash
TAVILY_API_KEY="tvly-..."
```

5. Configure GitHub CLI for repository reading.

```bash
auto-reach install --install gh --dry-run
gh auth status
gh auth login
auto-reach github view tavily-ai/tavily-python --pretty
auto-reach github inspect tavily-ai/tavily-python --pretty
```

`gh` is the primary GitHub backend and authentication is recommended for private repositories and higher rate limits. Public repository search and reading can fall back to GitHub's unauthenticated REST API through local `curl` with `--fallback auto` or `--fallback only`.

On macOS with Homebrew, the detected `gh` install command is:

```bash
brew install gh
```

6. Configure Bilibili CLI for Bilibili reading.

```bash
auto-reach install --install bili --dry-run
auto-reach bilibili status --pretty
auto-reach bilibili search "AI Agent 教程" --type video --max-results 5 --pretty
auto-reach bilibili video BV1xxxx --subtitle --comments --related --pretty
```

Auto Reach treats `bili-cli` as an external backend. It is not added to this project's Python dependencies because current `bilibili-cli` releases require Python 3.10+ while Auto Reach supports Python 3.9+.

7. Configure Xiaohongshu CLI for authenticated readonly reading.

```bash
auto-reach setup xiaohongshu --dry-run --pretty
auto-reach setup xiaohongshu --yes --pretty
auto-reach xiaohongshu login --method browser --pretty
auto-reach xiaohongshu status --pretty
auto-reach xiaohongshu search "美食" --sort popular --type all --pretty
auto-reach xiaohongshu read "https://www.xiaohongshu.com/explore/..." --pretty
```

Auto Reach treats `xiaohongshu-cli` as an external backend. It is installed with `uv tool` or `pipx` so its Python 3.10+ requirement does not change Auto Reach's Python 3.9+ runtime support.

## Doctor Output

`auto-reach doctor --json` emits stable machine-readable readiness data. Each check includes:

- `status`: `ok`, `warn`, `missing`, or `skipped`
- `category`: `required`, `optional`, `auth-only`, or `online-only`
- `detail`: human-readable remediation or version detail
- `path`: executable path when relevant

The categories mean:

- `required`: core runtime requirements, currently Python 3.9+
- `optional`: provider tools or libraries that enable a capability
- `auth-only`: credentials or login state required for full provider access
- `online-only`: live network checks that only run with `--online`

Example:

```bash
auto-reach doctor --json
auto-reach doctor --online --json
```

## Provider Output

Provider commands use a shared JSON envelope:

```json
{
  "operation": "search",
  "provider": "tavily",
  "status": "ok",
  "input": "query or URL",
  "result": {}
}
```

Errors use the same shape with `status: "error"` and an `error` object:

```json
{
  "operation": "view",
  "provider": "gh",
  "status": "error",
  "input": "OWNER/REPO",
  "error": {
    "category": "auth_required",
    "message": "..."
  }
}
```

Existing provider-specific fields such as `query`, `repo`, `path`, `urls`, and `timeout_seconds` remain present where useful.

`channel` and `backend` identify the capability domain and concrete implementation:

```json
{
  "operation": "search",
  "provider": "bili-cli",
  "channel": "bilibili",
  "backend": "bili-cli",
  "status": "ok",
  "input": "query",
  "result": {}
}
```

`auto-reach doctor --json` also includes `channels`. Each channel reports `status`, `active_backend`, `backends`, and supported `capabilities`.

Web capabilities are split by behavior:

- `web_read`: URL reading. Primary backend is `jina_reader`; `direct_http` is the zero-config fallback; Tavily extraction is fallback when configured.
- `web_search`: broad web search. Primary backend is `exa_mcp` when `mcporter` has Exa configured; Tavily is fallback when configured.
- `web`: aggregate channel for read, search, extract, and research.

Use `auto-reach research "query"` when an Agent needs a source bundle: Auto Reach searches, reads candidate URLs, records failures, and returns source content in one JSON result.

## Bilibili

Bilibili v1 is read-only. Supported commands:

```bash
auto-reach bilibili search "关键词" --type video --max-results 5 --pretty
auto-reach bilibili video BV1xxxx --subtitle --comments --related --pretty
auto-reach bilibili hot --page 1 --max-results 10 --pretty
auto-reach bilibili rank --day 3 --max-results 10 --pretty
auto-reach bilibili user "用户名或UID" --pretty
auto-reach bilibili user-videos "UID" --max-results 10 --pretty
auto-reach bilibili auto "BV号、B站URL、或关键词" --pretty
auto-reach bilibili status --pretty
```

`bili-cli` is the primary backend. Search uses `--fallback auto` by default: if `bili-cli` is missing or fails, Auto Reach uses Tavily to search `site:bilibili.com/video <query>` and returns candidate public video URLs. Tavily fallback is discovery only; it does not replace structured video metadata, subtitles, comments, or user data.

Do not use `yt-dlp` for Bilibili in this project. Auto Reach v1 also does not expose Bilibili write operations or audio download workflows.

## Xiaohongshu

Xiaohongshu v1 supports authentication and readonly reading through `xhs` from `xiaohongshu-cli`.

```bash
auto-reach xiaohongshu login --method browser --pretty
auto-reach xiaohongshu login --method qrcode --pretty
auto-reach xiaohongshu login --method qrcode --timeout 1800 --pretty
auto-reach xiaohongshu status --pretty
auto-reach xiaohongshu search "关键词" --sort general --type all --page 1 --pretty
auto-reach xiaohongshu read "笔记ID或URL" --pretty
auto-reach xiaohongshu comments "笔记ID或URL" --pretty
auto-reach xiaohongshu user "user_id" --pretty
auto-reach xiaohongshu user-posts "user_id" --pretty
auto-reach xiaohongshu hot --category travel --pretty
auto-reach xiaohongshu topics "旅行" --pretty
auto-reach xiaohongshu search-user "用户名" --pretty
```

Explicit account-scoped reads require the user to ask for their own account data and require `--account`:

```bash
auto-reach xiaohongshu whoami --account --pretty
auto-reach xiaohongshu feed --account --pretty
auto-reach xiaohongshu unread --account --pretty
auto-reach xiaohongshu notifications --account --type likes --pretty
```

Login uses local browser cookie extraction or QR-code authorization through upstream `xhs`. Ordinary reading commands use the saved `xhs` session only and do not expose `--cookie-source`. Auto Reach does not accept raw cookies in prompts, does not print cookie values, and does not expose Xiaohongshu write operations such as like, favorite, comment, follow, post, or delete.
QR-code login streams the upstream QR code and prompts to stderr so the user can scan them, then emits the final Auto Reach JSON result on stdout after login completes. Browser-cookie login defaults to 180 seconds. QR-code login defaults to 900 seconds because the first run may download the Camoufox browser runtime before showing the QR code; pass `--timeout 1800` if that first download is slow.
If QR-code login fails before showing a QR code with a GitHub API rate-limit error for `https://api.github.com/repos/daijro/camoufox/releases`, the failure is in upstream Camoufox runtime download. Wait for the GitHub API limit to reset, pre-warm the runtime locally, or use browser-cookie login after opening and logging into Xiaohongshu in a supported browser.
Xiaohongshu payloads include a `sources` field when note IDs are present. Use those clickable `url` values in user-facing answers and keep raw note IDs for debugging or follow-up reads. Auto Reach redacts `xsec_token`, token, cookie, auth values, and URL userinfo from results, sources, and error JSON.

## Skill Installation Path

The current project priority is:

1. Develop and test the runtime with `pip install -e .`.
2. Keep `skill/reach-skill/` as the Agent-facing routing guide in this repository.
3. Install or package the Skill into Codex only after runtime behavior is stable.

There is intentionally no project-level `auto-reach install-skill` command yet. Adding that command later is reasonable once the target Codex Skills directory, overwrite behavior, and marketplace metadata policy are settled.

## Common Errors

- `auto-reach: command not found`: run `python -m pip install -e .`, or use `python -m auto_reach ...` / `python3 -m auto_reach ...` from the repository.
- `TAVILY_API_KEY is not set`: export `TAVILY_API_KEY` or add it to the project `.env` before `search`, `web search`, or `web extract`.
- `tavily-python is not installed`: run `auto-reach install --install python`, or `python -m pip install -r requirements.txt`.
- `gh was not found on PATH`: run `auto-reach install --install gh --dry-run`, then install with the shown platform command.
- `auth_required` from GitHub commands: Auto Reach will try `github_public_api` for public repository data when fallback is enabled. Run `gh auth login` or set `GH_TOKEN` for private repositories, higher rate limits, or authenticated-only metadata.
- `curl was not found on PATH`: GitHub public API fallback is unavailable until `curl` is installed; `gh` may still work if present.
- GitHub public API rate limits: unauthenticated fallback is low quota. If public fallback is rate limited, wait or authenticate `gh`.
- `bili was not found on PATH`: run `auto-reach install --install bili --dry-run`, then follow `install_command`, `recommended_commands`, or `installer_hint`. On macOS this usually means `brew install uv`, then `uv tool install bilibili-cli`.
- `xhs was not found on PATH`: run `auto-reach setup xiaohongshu --dry-run --pretty`, then install with the planned `uv tool install xiaohongshu-cli` or `pipx install xiaohongshu-cli` command.
- `auth_required` from Xiaohongshu commands: run `auto-reach xiaohongshu login --method browser --pretty` or `auto-reach xiaohongshu login --method qrcode --pretty`.
- `account_confirmation_required` from Xiaohongshu commands: rerun only if the user explicitly asked for their own account data, and pass `--account`.
- `ip_blocked` from Xiaohongshu commands: stop and wait for the user to resolve access conditions; do not retry aggressively.
- `rate limit exceeded` from `api.github.com/repos/daijro/camoufox/releases` during Xiaohongshu QR login: upstream Camoufox runtime download hit GitHub API rate limits. Wait before retrying, pre-warm the runtime, or use browser-cookie login.
- Bilibili search falls back to Tavily only when `TAVILY_API_KEY` is set.
- Environment setup requested by the user: run `auto-reach setup <web|github|bilibili|xiaohongshu|all> --dry-run --pretty`, then use `--yes` when the user already authorized setup/installation or after approval. Use `--upgrade` only for explicit update requests.

## Testing

The test suite currently uses the Python standard library:

```bash
python -m unittest discover -v
python -m compileall auto_reach tests
```
