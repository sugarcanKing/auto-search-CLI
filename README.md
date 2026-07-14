# Auto Reach

Auto Reach is a lightweight capability layer for Agent research workflows. It provides one local CLI for:

- Tavily-backed web search
- Tavily-backed URL extraction
- `gh`-backed GitHub repository search and reading
- `bili-cli`-backed Bilibili search and reading, with Tavily search fallback
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
python -m auto_reach web search "OpenAI Agents SDK documentation" --max-results 3 --pretty
python -m auto_reach github auto https://github.com/tavily-ai/tavily-python --pretty
```

After installing the package in editable mode, the same commands are available as:

```bash
auto-reach doctor
auto-reach search "OpenAI Agents SDK documentation" --max-results 3 --pretty
auto-reach github inspect tavily-ai/tavily-python --pretty
auto-reach bilibili search "AI Agent 教程" --type video --max-results 5 --pretty
```

Installation is explicit. Research commands do not silently install tools or dependencies.

## Agent Setup Workflow

Use `setup` when the user explicitly asks to configure, install, repair, or upgrade the environment. Normal research commands should run `doctor --json` first. If the needed channel reports `agent_guidance.channels.<name>.status == "setup_required"` and `safe_to_execute_setup == true`, an Agent may run the provided dry-run command and then the execute command when the plan only contains expected Auto Reach dependency installs.

```bash
auto-reach setup web --dry-run --pretty
auto-reach setup github --dry-run --pretty
auto-reach setup bilibili --dry-run --pretty
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

3. Configure Tavily for web search and extraction.

```bash
export TAVILY_API_KEY="tvly-..."
auto-reach search "OpenAI Agents SDK documentation" --max-results 3 --pretty
```

Auto Reach also reads `TAVILY_API_KEY` from the project-root `.env` file, without overriding an already exported environment variable. For safety, `.env` loading is key-scoped: Auto Reach only imports `TAVILY_API_KEY` and ignores unrelated keys such as tokens, proxies, or package index settings.

```bash
TAVILY_API_KEY="tvly-..."
```

4. Configure GitHub CLI for repository reading.

```bash
auto-reach install --install gh --dry-run
gh auth status
gh auth login
auto-reach github view tavily-ai/tavily-python --pretty
auto-reach github inspect tavily-ai/tavily-python --pretty
```

On macOS with Homebrew, the detected `gh` install command is:

```bash
brew install gh
```

5. Configure Bilibili CLI for Bilibili reading.

```bash
auto-reach install --install bili --dry-run
auto-reach bilibili status --pretty
auto-reach bilibili search "AI Agent 教程" --type video --max-results 5 --pretty
auto-reach bilibili video BV1xxxx --subtitle --comments --related --pretty
```

Auto Reach treats `bili-cli` as an external backend. It is not added to this project's Python dependencies because current `bilibili-cli` releases require Python 3.10+ while Auto Reach supports Python 3.9+.

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
- `auth_required` from GitHub commands: run `gh auth login` or set `GH_TOKEN`. Public repository reads may still require authentication with the `gh repo` commands used by Auto Reach.
- `bili was not found on PATH`: run `auto-reach install --install bili --dry-run`, then follow `install_command`, `recommended_commands`, or `installer_hint`. On macOS this usually means `brew install uv`, then `uv tool install bilibili-cli`.
- Bilibili search falls back to Tavily only when `TAVILY_API_KEY` is set.
- Environment setup requested by the user: run `auto-reach setup <web|github|bilibili|all> --dry-run --pretty`, then use `--yes` when the user already authorized setup/installation or after approval. Use `--upgrade` only for explicit update requests.

## Testing

The test suite currently uses the Python standard library:

```bash
python -m unittest discover -v
python -m compileall auto_reach tests
```
