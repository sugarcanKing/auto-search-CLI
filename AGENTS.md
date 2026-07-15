# Auto Reach Agent Policy

This repository is an Agent capability-layer project. When working in this repository, use the local Auto Reach capability layer for search, retrieval, and research instead of the model's built-in web search by default.

## Default Retrieval Rule

- For broad web search or current information, use `python3 -m auto_reach search "query"` or `python3 -m auto_reach web search "query"`.
- For URL extraction or summarization, use `python3 -m auto_reach web auto "URL"` or `python3 -m auto_reach web extract "URL"`.
- For GitHub repository search/reading, use `python3 -m auto_reach github ...`.
- For Bilibili search/reading, use `python3 -m auto_reach bilibili ...`.
- For Xiaohongshu search/reading/auth, use `python3 -m auto_reach xiaohongshu ...`.
- Do not use the model's generic web browsing/search path unless the user explicitly asks to bypass Auto Reach, or Auto Reach cannot support the requested source after `doctor --json` and setup guidance have been considered.

## Readiness

Run `python3 -m auto_reach doctor --json` before retrieval when channel readiness is unknown.

If the needed channel reports `setup_required` and `safe_to_execute_setup` is true, run the dry-run command first. Execute setup only when the user has authorized setup/installation or the current task clearly asks to configure the environment.

Do not automate API keys, account login, cookies, browser auth state, or captcha handling unless the user explicitly asks for the supported Auto Reach auth command, such as `python3 -m auto_reach xiaohongshu login --method browser`.

## Final Answers

- Give the user the answer, not the command log.
- Include source links when the provider returns them.
- Do not list executed commands, `doctor` output, status checks, or intermediate JSON unless the user asks for debugging or reproducibility.
- For Xiaohongshu, cite clickable note links from provider `sources`; do not show bare note IDs unless asked.
