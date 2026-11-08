"""Turn a Tavily result into a shared world event and shared-event memory.

The scheduler is deliberately small: one search, one public event, one shared belief per
character. That is enough to make the World Feed and the belief matrix show a real-world
input without turning the simulation into a news bot.

    uv run director --tavily-event
    uv run director --tavily-event --query "AI agents news this week"

The event is public. The belief is `shared` because every character saw the same event;
a character can still form a private opinion about it later through world__remember.
"""
from __future__ import annotations

import os

from switch_world.application.facade import WorldService
from switch_world.domain import slugify

DEFAULT_QUERY = os.environ.get(
    "WORLD_NEWS_QUERY",
    "AI agents, creative tools and human-agent collaboration news this week",
)


def latest_world_event(service: WorldService) -> dict | None:
    return service.latest_event("world_event")


def world_context(service: WorldService, max_chars: int = 700) -> str:
    event = latest_world_event(service)
    if not event:
        return ""
    summary = event.get("summary", "")
    return summary[:max_chars]


def fetch_world_event(
    service: WorldService,
    query: str | None = None,
    client=None,
    max_results: int = 3,
) -> dict:
    if client is None:
        from switch_world.adapters.search.tavily import TavilyClient

        client = TavilyClient.from_env()
    query = (query or DEFAULT_QUERY).strip()
    response = client.search(query, max_results=max_results, topic="news", time_range="week")
    results = response.get("results") or []
    if not results:
        raise ValueError("Tavily returned no results for: " + query)

    top = results[0]
    offline = bool(response.get("offline"))
    marker = " [offline fixture]" if offline else ""
    title = top.get("title") or "untitled"
    url = top.get("url") or ""
    event = service.record_event(
        "director",
        "world_event",
        f"Real world: {title} — {url}{marker}",
        participants=[],
        visibility="public",
    )

    key = "world-" + slugify(title)[:60]
    content = (top.get("content") or "").strip()
    proposition = f"Real-world context: {title}. {content[:600]}"
    holders: list[str] = []
    for character in service.characters():
        service.remember(
            character["id"],
            proposition=proposition,
            source=f"event:{event['id']}",
            confidence=0.9,
            visibility="shared",
            proposition_key=key,
        )
        holders.append(character["id"])

    return {
        "query": query,
        "offline": offline,
        "event": event,
        "key": key,
        "title": title,
        "url": url,
        "holders": holders,
        "results": results,
        "answer": response.get("answer", ""),
    }
