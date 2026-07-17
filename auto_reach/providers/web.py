"""Tavily-backed web search and page extraction."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from html.parser import HTMLParser
from typing import Any, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from auto_reach.env import get_env

from .base import clamp_timeout, emit_json, provider_error, provider_success, run_process


MAX_SEARCH_TIMEOUT = 60.0
MAX_EXTRACT_TIMEOUT = 45.0
MAX_JINA_TIMEOUT = 45.0
MAX_EXA_TIMEOUT = 45.0
JINA_READER_PREFIX = "https://r.jina.ai/"
JINA_USER_AGENT = "Mozilla/5.0 (compatible; AutoReach/0.1; +https://github.com/auto-reach)"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)
            self.parts.append(" ")

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(content: str) -> str:
    extractor = TextExtractor()
    try:
        extractor.feed(content)
        text = extractor.text()
    except Exception:
        return content
    return text or content


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def classify_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    category = "provider_error"
    retryable = False

    if "mcporter was not found" in lowered:
        category = "missing_tool"
    elif "exa mcp is not configured" in lowered:
        category = "setup_required"
    elif "tavily-python is not installed" in lowered:
        category = "missing_dependency"
    elif "tavily_api_key is not set" in lowered or "api key" in lowered:
        category = "auth_required"
    elif "timed out" in lowered or "timeout" in lowered:
        category = "timeout"
        retryable = True
    elif "failed to resolve" in lowered or "nameresolutionerror" in lowered or "dns" in lowered:
        category = "network_resolution"
        retryable = True
    elif "connection" in lowered:
        category = "network_connection"
        retryable = True
    elif "http error" in lowered or "http " in lowered:
        category = "http_error"
    elif "401" in lowered or "unauthorized" in lowered:
        category = "auth_required"
    elif "403" in lowered or "forbidden" in lowered or "quota" in lowered or "credit" in lowered:
        category = "quota_or_forbidden"

    return {
        "type": exc.__class__.__name__,
        "message": message,
        "category": category,
        "retryable": retryable,
    }


def emit(payload: dict[str, Any], pretty: bool) -> None:
    emit_json(payload, pretty)


def load_client() -> Any:
    api_key = get_env("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set. Export it before using Tavily search or extraction.")

    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily-python is not installed. Run: auto-reach install --check") from exc

    return TavilyClient(api_key=api_key)


def ensure_mcporter_exa() -> str:
    mcporter = shutil.which("mcporter")
    if not mcporter:
        raise RuntimeError("mcporter was not found. Install it with: npm install -g mcporter")

    try:
        result = run_process([mcporter, "config", "list"], timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("mcporter config list timed out") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(output.strip() or "mcporter config list failed")
    if "exa" not in output.lower():
        raise RuntimeError("Exa MCP is not configured. Run: mcporter config add exa https://mcp.exa.ai/mcp")
    return mcporter


def parse_mcporter_output(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return {"raw": ""}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return {"raw": stripped}


def command_exa_search(args: argparse.Namespace) -> dict[str, Any]:
    mcporter = ensure_mcporter_exa()
    timeout = clamp_timeout(args.timeout, MAX_EXA_TIMEOUT)
    call = f'exa.web_search_exa(query: {json.dumps(args.query, ensure_ascii=False)}, numResults: {int(args.max_results)})'
    command = [mcporter, "call", call]
    try:
        result = run_process(command, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"mcporter Exa search timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    output = (result.stdout or "").strip()
    if result.returncode != 0:
        detail = (result.stderr or output or "mcporter Exa search failed").strip()
        raise RuntimeError(detail)

    return provider_success(
        operation="search",
        provider="exa",
        channel="web_search",
        backend="exa_mcp",
        input=args.query,
        query=args.query,
        timeout_seconds=timeout,
        result=parse_mcporter_output(output),
    )


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_url(args.query):
        read_args = argparse.Namespace(
            url=args.query,
            backend=getattr(args, "read_backend", "auto"),
            extract_depth="basic",
            format="markdown",
            timeout=clamp_timeout(args.timeout, MAX_JINA_TIMEOUT),
            include_usage=args.include_usage,
        )
        payload = command_read(read_args)
        payload["routed_from"] = "search"
        payload["route_reason"] = "Input looked like an HTTP URL, so Auto Reach read the page instead of searching for it."
        return payload

    backend = getattr(args, "backend", "tavily")
    if backend == "exa":
        return command_exa_search(args)
    if backend == "auto":
        try:
            payload = command_exa_search(args)
            payload["fallback_used"] = False
            return payload
        except Exception as primary_exc:
            try:
                tavily_args = argparse.Namespace(**{**vars(args), "backend": "tavily"})
                payload = command_tavily_search(tavily_args)
                payload["fallback_used"] = True
                payload["primary_error"] = classify_error(primary_exc)
                return payload
            except Exception as fallback_exc:
                raise RuntimeError(
                    "Both Exa and Tavily search failed. "
                    f"Exa: {primary_exc}; Tavily: {fallback_exc}"
                ) from fallback_exc
    return command_tavily_search(args)


def command_tavily_search(args: argparse.Namespace) -> dict[str, Any]:
    client = load_client()
    result = client.search(
        query=args.query,
        search_depth=args.search_depth,
        topic=args.topic,
        time_range=args.time_range,
        max_results=args.max_results,
        include_domains=args.include_domain or None,
        exclude_domains=args.exclude_domain or None,
        include_answer=args.include_answer,
        include_raw_content=args.include_raw_content,
        timeout=clamp_timeout(args.timeout, MAX_SEARCH_TIMEOUT),
        include_usage=args.include_usage,
    )
    return provider_success(
        operation="search",
        provider="tavily",
        channel="web_search",
        backend="tavily",
        input=args.query,
        query=args.query,
        timeout_seconds=clamp_timeout(args.timeout, MAX_SEARCH_TIMEOUT),
        result=result,
    )


def command_extract(args: argparse.Namespace) -> dict[str, Any]:
    client = load_client()
    result = client.extract(
        urls=args.urls,
        extract_depth=args.extract_depth,
        format=args.format,
        timeout=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
        include_usage=args.include_usage,
    )
    return provider_success(
        operation="extract",
        provider="tavily",
        channel="web_read",
        backend="tavily",
        input=args.urls,
        urls=args.urls,
        timeout_seconds=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
        result=result,
    )


def jina_url(url: str) -> str:
    normalized = url if url.startswith(("http://", "https://")) else f"https://{url}"
    return f"{JINA_READER_PREFIX}{normalized}"


def command_jina_read(args: argparse.Namespace) -> dict[str, Any]:
    timeout = clamp_timeout(args.timeout, MAX_JINA_TIMEOUT)
    reader_url = jina_url(args.url)
    status_code: int | None = None
    curl = shutil.which("curl")
    if curl:
        command = [
            curl,
            "--location",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "-H",
            f"User-Agent: {JINA_USER_AGENT}",
            "-H",
            "Accept: text/plain, text/markdown, */*",
            "--write-out",
            "\n%{http_code}",
            reader_url,
        ]
        try:
            result = run_process(command, timeout=timeout + 2)
        except Exception as exc:
            raise RuntimeError(f"Jina Reader failed for {args.url}: {exc}") from exc
        body, separator, status_text = (result.stdout or "").rpartition("\n")
        content = body if separator and status_text.isdigit() else (result.stdout or "")
        status_code = int(status_text) if separator and status_text.isdigit() else None
        if result.returncode != 0:
            detail = (result.stderr or content or "curl request failed").strip()
            raise RuntimeError(f"Jina Reader failed for {args.url}: {detail}")
        if status_code is not None and (status_code < 200 or status_code >= 300):
            raise RuntimeError(f"Jina Reader returned HTTP {status_code} for {args.url}")
    else:
        request = Request(
            reader_url,
            headers={
                "User-Agent": JINA_USER_AGENT,
                "Accept": "text/plain, text/markdown, */*",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                status_code = getattr(response, "status", None)
                content = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"Jina Reader failed for {args.url}: {exc}") from exc

    if not content.strip():
        raise RuntimeError(f"Jina Reader returned empty content for {args.url}")

    return provider_success(
        operation="read",
        provider="jina",
        channel="web_read",
        backend="jina_reader",
        input=args.url,
        url=args.url,
        timeout_seconds=timeout,
        result={
            "url": args.url,
            "reader_url": reader_url,
            "status_code": status_code,
            "format": "markdown",
            "content": content,
        },
    )


def command_direct_read(args: argparse.Namespace) -> dict[str, Any]:
    timeout = clamp_timeout(args.timeout, MAX_JINA_TIMEOUT)
    url = args.url if args.url.startswith(("http://", "https://")) else f"https://{args.url}"
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl was not found for direct HTTP reading")
    command = [
        curl,
        "--location",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout),
        "-H",
        f"User-Agent: {JINA_USER_AGENT}",
        "--write-out",
        "\n%{http_code}",
        url,
    ]
    try:
        result = run_process(command, timeout=timeout + 2)
    except Exception as exc:
        raise RuntimeError(f"Direct HTTP read failed for {url}: {exc}") from exc

    body, separator, status_text = (result.stdout or "").rpartition("\n")
    content = body if separator and status_text.isdigit() else (result.stdout or "")
    status_code = int(status_text) if separator and status_text.isdigit() else None
    if result.returncode != 0:
        detail = (result.stderr or content or "curl request failed").strip()
        raise RuntimeError(f"Direct HTTP read failed for {url}: {detail}")
    if status_code is not None and (status_code < 200 or status_code >= 300):
        raise RuntimeError(f"Direct HTTP read returned HTTP {status_code} for {url}")

    text = html_to_text(content)
    if not text.strip():
        raise RuntimeError(f"Direct HTTP read returned empty content for {url}")

    return provider_success(
        operation="read",
        provider="direct-http",
        channel="web_read",
        backend="direct_http",
        input=args.url,
        url=url,
        timeout_seconds=timeout,
        result={
            "url": url,
            "status_code": status_code,
            "format": "text",
            "content": text,
        },
    )


def command_read(args: argparse.Namespace) -> dict[str, Any]:
    backend = getattr(args, "backend", "auto")
    if backend == "jina":
        return command_jina_read(args)
    if backend == "tavily":
        extract_args = argparse.Namespace(
            urls=[args.url],
            extract_depth=args.extract_depth,
            format=args.format,
            timeout=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
            include_usage=args.include_usage,
        )
        payload = command_extract(extract_args)
        payload["operation"] = "read"
        payload["routed_from"] = "read"
        return payload
    if backend == "direct":
        return command_direct_read(args)

    try:
        payload = command_jina_read(args)
        payload["fallback_used"] = False
        return payload
    except Exception as primary_exc:
        direct_error: Exception | None = None
        try:
            payload = command_direct_read(args)
            payload["fallback_used"] = True
            payload["primary_error"] = classify_error(primary_exc)
            return payload
        except Exception as exc:
            direct_error = exc
        try:
            extract_args = argparse.Namespace(
                urls=[args.url],
                extract_depth=args.extract_depth,
                format=args.format,
                timeout=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
                include_usage=args.include_usage,
            )
            payload = command_extract(extract_args)
            payload["operation"] = "read"
            payload["fallback_used"] = True
            payload["primary_error"] = classify_error(primary_exc)
            payload["secondary_error"] = classify_error(direct_error) if direct_error else None
            return payload
        except Exception as fallback_exc:
            raise RuntimeError(
                "Jina Reader, direct HTTP, and Tavily extract all failed. "
                f"Jina: {primary_exc}; Direct HTTP: {direct_error}; Tavily: {fallback_exc}"
            ) from fallback_exc


def command_auto(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_url(args.input):
        read_args = argparse.Namespace(
            url=args.input,
            backend=args.read_backend,
            extract_depth=args.extract_depth,
            format=args.format,
            timeout=args.timeout,
            include_usage=args.include_usage,
        )
        payload = command_read(read_args)
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input looked like an HTTP URL."
        return payload

    search_args = argparse.Namespace(
        query=args.input,
        search_depth=args.search_depth,
        topic=args.topic,
        time_range=args.time_range,
        max_results=args.max_results,
        include_domain=args.include_domain,
        exclude_domain=args.exclude_domain,
        include_answer=args.include_answer,
        include_raw_content=args.include_raw_content,
        timeout=args.timeout,
        include_usage=args.include_usage,
        backend=args.search_backend,
        read_backend=args.read_backend,
    )
    payload = command_search(search_args)
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input did not look like an HTTP URL."
    return payload


def iter_search_candidates(search_payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = search_payload.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("results"), list):
            return [item for item in result["results"] if isinstance(item, dict)]
        if isinstance(result.get("raw"), str):
            return [{"title": "Exa result", "url": url} for url in extract_urls_from_text(result["raw"])]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for token in text.replace(")", " ").replace("]", " ").replace("\n", " ").split():
        candidate = token.strip("<>,.;\"'")
        if looks_like_url(candidate) and candidate not in urls:
            urls.append(candidate)
    return urls


def candidate_url(candidate: dict[str, Any]) -> str | None:
    for key in ("url", "link", "href"):
        value = candidate.get(key)
        if isinstance(value, str) and looks_like_url(value):
            return value
    return None


def content_from_read_payload(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("content", "raw_content", "markdown", "text"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        results = result.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            for key in ("raw_content", "content", "markdown", "text"):
                value = results[0].get(key)
                if isinstance(value, str):
                    return value
    if isinstance(result, str):
        return result
    return ""


def command_research(args: argparse.Namespace) -> dict[str, Any]:
    search_args = argparse.Namespace(
        query=args.query,
        search_depth=args.search_depth,
        topic=args.topic,
        time_range=args.time_range,
        max_results=max(args.max_sources * 2, args.max_sources),
        include_domain=args.include_domain,
        exclude_domain=args.exclude_domain,
        include_answer=False,
        include_raw_content=None,
        timeout=args.timeout,
        include_usage=False,
        backend=args.search_backend,
        read_backend=args.read_backend,
    )
    search_payload = command_search(search_args)
    sources: list[dict[str, Any]] = []
    failed_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for candidate in iter_search_candidates(search_payload):
        url = candidate_url(candidate)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        read_args = argparse.Namespace(
            url=url,
            backend=args.read_backend,
            extract_depth="basic",
            format="markdown",
            timeout=args.timeout,
            include_usage=False,
        )
        try:
            read_payload = command_read(read_args)
            content = content_from_read_payload(read_payload)
            sources.append(
                {
                    "title": candidate.get("title") or candidate.get("name"),
                    "url": url,
                    "search_candidate": candidate,
                    "read_backend": read_payload.get("backend"),
                    "read_provider": read_payload.get("provider"),
                    "read_status": "ok",
                    "content": content[: args.max_chars_per_source],
                    "content_truncated": len(content) > args.max_chars_per_source,
                }
            )
        except Exception as exc:
            failed_sources.append(
                {
                    "title": candidate.get("title") or candidate.get("name"),
                    "url": url,
                    "read_status": "error",
                    "error": classify_error(exc),
                }
            )
        if len(sources) >= args.max_sources:
            break

    return provider_success(
        operation="research",
        provider="auto-reach",
        channel="research",
        backend="web_search+web_read",
        input=args.query,
        query=args.query,
        result={
            "search": search_payload,
            "sources": sources,
            "failed_sources": failed_sources,
            "notes": [
                "Use source URLs in the final answer.",
                "Treat content as retrieved excerpts; follow primary sources when claims conflict.",
            ],
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach web", description="Auto Reach web search and extraction.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web through Tavily.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--backend", choices=["auto", "exa", "tavily"], default="auto", help="Search backend.")
    search_parser.add_argument("--max-results", type=int, default=5, help="Maximum search results to return.")
    search_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Tavily search depth.",
    )
    search_parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    search_parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    search_parser.add_argument("--include-domain", action="append", default=[], help="Restrict to a domain.")
    search_parser.add_argument("--exclude-domain", action="append", default=[], help="Exclude a domain.")
    search_parser.add_argument("--include-answer", action="store_true", help="Include Tavily's generated answer.")
    search_parser.add_argument("--include-raw-content", choices=["markdown", "text"])
    search_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    search_parser.add_argument("--timeout", type=float, default=25)
    search_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    search_parser.set_defaults(func=command_search)

    read_parser = subparsers.add_parser("read", help="Read a URL through Jina Reader with Tavily fallback.")
    read_parser.add_argument("url", help="HTTP URL to read.")
    read_parser.add_argument("--backend", choices=["auto", "jina", "direct", "tavily"], default="auto", help="Read backend.")
    read_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    read_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    read_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details when using Tavily.")
    read_parser.add_argument("--timeout", type=float, default=25)
    read_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    read_parser.set_defaults(func=command_read)

    extract_parser = subparsers.add_parser("extract", help="Extract readable content from URLs through Tavily.")
    extract_parser.add_argument("urls", nargs="+", help="One or more URLs to extract.")
    extract_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    extract_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    extract_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    extract_parser.add_argument("--timeout", type=float, default=20)
    extract_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    extract_parser.set_defaults(func=command_extract)

    auto_parser = subparsers.add_parser("auto", help="Search text input or extract direct URLs.")
    auto_parser.add_argument("input", help="Search query or HTTP URL.")
    auto_parser.add_argument("--search-backend", choices=["auto", "exa", "tavily"], default="auto")
    auto_parser.add_argument("--read-backend", choices=["auto", "jina", "direct", "tavily"], default="auto")
    auto_parser.add_argument("--max-results", type=int, default=5, help="Maximum search results to return.")
    auto_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Tavily search depth when input is not a URL.",
    )
    auto_parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    auto_parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    auto_parser.add_argument("--include-domain", action="append", default=[], help="Restrict search to a domain.")
    auto_parser.add_argument("--exclude-domain", action="append", default=[], help="Exclude a domain from search.")
    auto_parser.add_argument("--include-answer", action="store_true", help="Include Tavily's generated answer.")
    auto_parser.add_argument("--include-raw-content", choices=["markdown", "text"])
    auto_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    auto_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    auto_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    auto_parser.add_argument("--timeout", type=float, default=25)
    auto_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    auto_parser.set_defaults(func=command_auto)

    research_parser = subparsers.add_parser("research", help="Search and read top source URLs into a source bundle.")
    research_parser.add_argument("query", help="Research query.")
    research_parser.add_argument("--max-sources", type=int, default=5, help="Number of successfully read sources.")
    research_parser.add_argument("--max-chars-per-source", type=int, default=6000)
    research_parser.add_argument("--search-backend", choices=["auto", "exa", "tavily"], default="auto")
    research_parser.add_argument("--read-backend", choices=["auto", "jina", "direct", "tavily"], default="auto")
    research_parser.add_argument("--search-depth", choices=["basic", "advanced", "fast", "ultra-fast"], default="basic")
    research_parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    research_parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    research_parser.add_argument("--include-domain", action="append", default=[], help="Restrict search to a domain.")
    research_parser.add_argument("--exclude-domain", action="append", default=[], help="Exclude a domain from search.")
    research_parser.add_argument("--timeout", type=float, default=25)
    research_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    research_parser.set_defaults(func=command_research)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = args.func(args)
        emit(payload, bool(getattr(args, "pretty", False)))
        return 0
    except Exception as exc:
        emit(
            provider_error(
                operation=getattr(args, "command", "unknown"),
                provider="auto-reach-web",
                channel="web",
                backend=getattr(args, "backend", getattr(args, "search_backend", getattr(args, "read_backend", None))),
                input=getattr(args, "query", getattr(args, "input", getattr(args, "url", getattr(args, "urls", None)))),
                error=classify_error(exc),
            ),
            bool(getattr(args, "pretty", False)),
        )
        return 1
