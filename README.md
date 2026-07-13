# Auto Reach

Auto Reach is a lightweight capability layer for Agent research workflows. It provides one local CLI for:

- Tavily-backed web search
- Tavily-backed URL extraction
- `gh`-backed GitHub repository search and reading
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
```

Installation is explicit. Research commands do not silently install tools or dependencies.
