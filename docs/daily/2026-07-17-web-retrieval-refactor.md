## 今日工作报告：Auto Reach 联网能力分层重构

日期：2026-07-17

### 背景

此前 `web` 能力基本等同于 Tavily：搜索走 Tavily，URL 抽取也走 Tavily。这导致普通网页读取、动态页面、反爬页面、缺 API Key 等情况都会把整个联网能力拖垮。

今天的目标是把 Tavily 从“唯一主干”降级为“一个 backend”，并引入更接近 Agent-Reach 思路的多后端联网层。

### 完成事项

1. 拆分联网能力面

- 新增 `web_read`：负责 URL 读取。
- 新增 `web_search`：负责全网搜索。
- 保留聚合 `web` channel：覆盖 read、search、extract、research。

2. 增加 Jina Reader URL 读取

- 新增 `auto-reach web read URL` 和顶层快捷命令 `auto-reach read URL`。
- 默认优先使用 Jina Reader：`https://r.jina.ai/URL`。
- Jina 失败时先 fallback 到 direct HTTP，再 fallback 到 Tavily extraction。
- 普通 URL 读取不再强依赖 `TAVILY_API_KEY`。

3. 增加 Exa MCP 搜索后端

- `auto-reach web search` 新增 `--backend auto|exa|tavily`。
- `auto` 默认先尝试 Exa MCP，再 fallback Tavily。
- Exa 通过 `mcporter` 调用：
  - `mcporter config add exa https://mcp.exa.ai/mcp`
  - `mcporter call 'exa.web_search_exa(query: "...", numResults: 5)'`
- `doctor --json` 新增 `mcporter`、`exa_mcp` 检查，并在 `web_search` channel 中展示 active backend。

4. 增加 research source bundle

- 新增 `auto-reach web research "query"` 和顶层快捷命令 `auto-reach research "query"`。
- 流程为：搜索 -> 读取候选 URL -> 输出 sources / failed_sources。
- Agent 可以直接基于 source bundle 写带来源的答案。

5. 更新 setup

- `auto-reach setup web` 现在会规划：
  - Python requirements，用于 Tavily fallback。
  - `mcporter` 安装，用于 Exa MCP。
  - Exa MCP endpoint 注册。
- 不处理 Exa API Key，不保存搜索凭据。

6. 更新文档和 Skill

- README 增加 Jina Reader、Exa MCP、research 命令说明。
- `skill/reach-skill/SKILL.md` 更新路由表。
- `references/search.md` 和 `references/web.md` 更新默认 backend 和 fallback 规则。

### 当前设计

```text
web_read:
  1. jina_reader
  2. direct_http
  3. tavily_extract

web_search:
  1. exa_mcp
  2. tavily

research:
  web_search -> web_read -> source bundle
```

### 验证

- 定向测试通过：
  - `tests.test_web_provider`
  - `tests.test_doctor`
  - `tests.test_setup`
  - `tests.test_cli`
  - `tests.test_install`
- `python3 -m auto_reach web --help` 已展示 `search/read/extract/auto/research`。
- `python3 -m auto_reach doctor --json` 已展示 `web_read`、`web_search`、`jina_reader`、`exa_mcp`、`tavily`。

### 后续

- 做真实联网 smoke test：Jina 读取、Tavily search、Exa MCP search。
- 根据真实 Exa MCP 输出格式优化结果归一化。
- 将 `research` 的 source 选择策略升级为官方源优先、去重和失败重试。
- 后续再做 `policy install` / `skill install`，把能力层安装到其他 Agent 工作区。
