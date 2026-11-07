"""Tavily search adapter: the cast's window onto the present.

The logic is the same as the legacy ``gateway/tavily.py`` (news search,
offline fixture, citation formatting), but it lives behind a small,
constructor-injected client so a composition root can build it and tests can
pass a transport. No environment is read at import time.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.tavily.com"
FIXTURE_PATH = Path(__file__).with_name("tavily_fixture.json")


class TavilyError(RuntimeError):
    pass


class TavilyNotConfigured(TavilyError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str
    published_date: str = ""
    score: float = 0.0


def _normalize(raw: dict) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in raw.get("results") or []:
        results.append(
            SearchResult(
                title=str(item.get("title") or "").strip(),
                url=str(item.get("url") or "").strip(),
                content=str(item.get("content") or "").strip(),
                published_date=str(item.get("published_date") or "").strip(),
                score=float(item.get("score") or 0.0),
            )
        )
    return [result for result in results if result.title or result.content]


class TavilyClient:
    """A small search client with an injectable HTTP transport."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 25.0,
        transport: Callable[[str, dict, dict], dict] | None = None,
        offline: bool | None = None,
        fixture_path: Path | str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("TAVILY_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.transport = transport or self._http_post
        self.offline = (
            (os.environ.get("TAVILY_OFFLINE") == "1") if offline is None else offline
        )
        self.fixture_path = Path(fixture_path or FIXTURE_PATH)

    @classmethod
    def from_env(cls) -> "TavilyClient":
        return cls()

    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise TavilyError(f"Tavily is unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise TavilyError(
                f"Tavily HTTP {response.status_code}: {response.text[:400]}"
            )
        return response.json()

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        topic: str = "news",
        time_range: str | None = "week",
        include_answer: bool = True,
    ) -> dict:
        query = (query or "").strip()
        if not query:
            raise TavilyError("query is required")
        if not self.api_key and not self.offline:
            raise TavilyNotConfigured(
                "TAVILY_API_KEY is not set; export it or use TAVILY_OFFLINE=1 for the "
                "clearly-labelled local fixture"
            )
        if self.offline:
            payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
            raw = {
                "query": query,
                "answer": payload.get("answer", ""),
                "results": payload.get("results", []),
            }
            results = _normalize(raw)
            return {
                "query": query,
                "answer": raw["answer"],
                "results": [result.__dict__ for result in results[:max_results]],
                "offline": True,
            }

        payload: dict = {
            "query": query,
            "max_results": max(1, min(int(max_results), 20)),
            "topic": topic,
            "include_answer": include_answer,
            "include_raw_content": False,
        }
        if time_range:
            payload["time_range"] = time_range
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        raw = self.transport(self.base_url + "/search", payload, headers)
        results = _normalize(raw)
        return {
            "query": query,
            "answer": str(raw.get("answer") or ""),
            "results": [result.__dict__ for result in results],
            "offline": False,
        }


def format_context(results: list[dict], max_chars: int = 2400) -> str:
    """Compact, citation-bearing context for a character prompt or event summary."""
    parts: list[str] = []
    used = 0
    for index, result in enumerate(results, start=1):
        title = result.get("title") or "untitled"
        url = result.get("url") or "(no url)"
        content = (result.get("content") or "").replace("\n", " ").strip()
        block = f"[{index}] {title} ({url})\n{content}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


__all__ = [
    "SearchResult",
    "TavilyClient",
    "TavilyError",
    "TavilyNotConfigured",
    "format_context",
]
