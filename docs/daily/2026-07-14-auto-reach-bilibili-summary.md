## 今日工作报告：Auto Reach Channel 化与 Bilibili 接入

日期：2026-07-14

### 一、今日目标

今天的核心目标是验证并增强 Auto Reach 作为 Agent 能力层的有效性，重点接入 Bilibili 能力，并让 Agent 在缺少本地依赖时能够通过能力层获得可执行的 setup 指引。

### 二、完成事项

1. 完成 channel 模型落地

- 将 `web`、`github`、`bilibili` 统一抽象为 channel。
- 每个 channel 通过 backend 暴露健康状态、能力列表和 active backend。
- `doctor --json` 新增 `channels` 和 `agent_guidance`，让 Agent 能判断能力是否 ready、是否需要 setup、是否可安全执行 setup。

2. 接入 Bilibili 只读能力

- 新增 `auto-reach bilibili` 命令组。
- 支持 `search`、`video`、`hot`、`rank`、`user`、`user-videos`、`auto`、`status`。
- 主 backend 使用 `bili-cli`，明确不使用 `yt-dlp`。
- 写操作和下载工作流不接入 v1，包括 like、coin、triple、dynamic-post、dynamic-delete、unfollow、audio。

3. 完成 Bilibili fallback 策略

- Bilibili 搜索默认先走 `bili-cli`。
- 当主 backend 缺失或失败时，可 fallback 到 Tavily 搜索 `site:bilibili.com/video <query>`。
- Tavily fallback 只返回候选链接、标题、摘要，不伪装成 Bilibili 结构化详情。

4. 完成显式 setup 模式

- 新增 `auto-reach setup <web|github|bilibili|all>`。
- 默认 dry-run，不执行安装。
- `--yes` 是唯一执行开关。
- `--upgrade` 只在用户明确要求更新时使用。
- setup 只处理本地依赖，不自动处理 API Key、登录、Cookie、账号认证。

5. 提升 Agent 自动修复能力

- `doctor --json` 新增 `agent_guidance`。
- 当 channel 缺少可安装本地依赖时，Agent 可以读取：
  - `status`
  - `safe_to_execute_setup`
  - `dry_run_command`
  - `execute_command`
  - `next_actions`
- Skill 和 reference 文档已更新：普通研究任务可根据 `agent_guidance` 自动修复本地依赖，但不得自动处理认证。

6. 修复 review 中发现的问题

- 修复 `setup --dry-run --yes` 同时传入时仍执行安装的问题，改为 argparse 互斥参数。
- 收紧 `.env` 自动加载范围：默认只读项目根 `.env`，且只白名单加载 `TAVILY_API_KEY`。
- 删除 doctor 中不存在的 curl web fallback 提示。
- backend 探活状态区分为 `missing`、`broken`、`timeout`、`error`、`ok`。
- broken/timeout/error 的 primary backend 不再被标记为 active backend。
- 抽出轻量 provider 公共层，统一 JSON 输出、timeout clamp 和 subprocess 调用入口。

7. 实测验证

- `bili-cli` 已通过 `uv tool install bilibili-cli` 安装。
- 当前 `bili` 可被 Auto Reach 从 `~/.local/bin` 发现，即使该目录不在 shell PATH 中。
- `auto-reach bilibili search` 已能返回 `backend: bili-cli` 的结构化结果。
- `auto-reach bilibili video` 已能读取视频详情。
- `auto-reach bilibili hot` 已能读取热门列表。

### 三、测试结果

- `python3 -m unittest discover -v`：53 个测试通过。
- `python3 -m compileall auto_reach tests`：通过。
- 真实命令验证：
  - `python3 -m auto_reach setup web --dry-run --yes --pretty` 正确失败，exit code 为 2。
  - `python3 -m auto_reach bilibili search "AI Agent 教程" --type video --max-results 1 --pretty` 成功。
  - `python3 -m auto_reach doctor --json` 能输出 channel 和 agent guidance。

### 四、当前能力状态

- Bilibili：可用，主 backend 为 `bili-cli`。
- Web/Search：在正确 Python 环境中可用；缺依赖时 doctor 会给出可执行 setup 指引。
- GitHub：`gh` 已安装，但认证状态需要用户按需执行 `gh auth login`。
- Skill：仍作为 Agent routing guide，不承担运行时逻辑。

### 五、主要经验

- Agent 能力层不能只返回“缺依赖”，还要告诉 Agent 下一步能不能自动修、怎么 dry-run、怎么执行、哪些不能自动处理。
- `doctor` 是 Agent 自动化体验的核心，不只是给人看的检查命令。
- `.env` 读取必须收紧范围和 key 白名单，否则 Agent 在不可信目录运行时有环境注入风险。
- 外部 CLI wrapper 不能只按 README 假设实现，必须用实际 `--help` 和真实命令验证参数兼容性。
- Channel/backend 分离是正确方向，但 v1 需要保持轻量，不要提前做复杂多后端生态。

## 明日待办：接入小红书搜索能力

1. 调研小红书可用方案

- 明确是否存在稳定 CLI、公开 API、第三方 SDK 或网页搜索可行路径。
- 优先只做公开内容搜索发现，不做登录、发帖、评论、点赞、收藏等写操作。
- 明确合规边界，不绕过登录、风控、验证码或访问控制。

2. 设计 `xiaohongshu` channel

- 新增 channel 名称：`xiaohongshu`。
- 初版能力建议只做：
  - search
  - note candidates
  - auto route
- backend 初版可以先使用 Tavily 搜索 fallback：
  - `site:xiaohongshu.com <query>`
  - 只返回候选链接、标题、摘要、来源。

3. 评估是否需要专用 backend

- 如果没有稳定公开 CLI，不强行接专用 backend。
- 可以先做 `tavily_search_fallback` 作为唯一 backend，并在 doctor 中标记为 search discovery。
- 如果未来找到可靠只读 backend，再接入为 primary backend。

4. 更新 CLI

- 新增：
  - `auto-reach xiaohongshu search "关键词" --max-results 5 --pretty`
  - `auto-reach xiaohongshu auto "关键词或URL" --pretty`
- 暂不实现下载、登录态读取、评论读取、用户主页深度抓取。

5. 更新 doctor/setup

- doctor 新增 `xiaohongshu` channel。
- 如果只依赖 Tavily，则 setup web 能修复它的依赖。
- agent guidance 中明确：缺 Tavily 可自动 setup，缺 API Key 只能提示用户。

6. 更新 Skill 文档

- 新增 `skill/reach-skill/references/xiaohongshu.md`。
- 写明安全边界：
  - 不登录
  - 不写操作
  - 不绕过风控
  - 不保证完整搜索，只做公开发现

7. 补测试

- CLI 参数解析测试。
- doctor channel schema 测试。
- Tavily fallback query 构造测试。
- 缺 Tavily 依赖和缺 Key 的错误测试。
- Safety 测试：不出现登录、发布、点赞、收藏、下载等命令。
