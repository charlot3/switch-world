"""Pre-meeting briefing: research a subject, let the room react, write one page.

This is the Tavily Research Agent use case. Given a company or person and a
meeting time it

1. runs two or three news-shaped Tavily queries through the existing search
   adapter;
2. records one public ``world_event`` and one shared belief per *distinct*
   search result (``fetch_world_event`` does the recording; identical results
   are never recorded twice);
3. posts one group message naming the subject, the meeting and the strongest
   findings, and lets the four characters answer in character through the
   injected transport (or a model-backed in-band room);
4. composes a one-page markdown briefing with snapshot, recent developments,
   discussion points, open questions, sources and provenance;
5. writes it through the artifact store as ``briefing-<slug>.md`` and records a
   ``briefing`` event pointing at the file.

The offline fixture is labelled in the page itself, so a demo never presents a
fixture item as a live result. No transport or model is required: without one
the research still runs and the briefing records that the room never met.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from switch_world.application.defaults import (
    cloud_room_transport,
    default_artifact_store,
)
from switch_world.application.facade import WorldService
from switch_world.application.group_planning import MAX_MESSAGE
from switch_world.application.scene import say_in_group
from switch_world.application.social import clean_scene_line
from switch_world.application.tavily_beat import (
    default_search_client,
    fetch_world_event,
)
from switch_world.domain import slugify

WINDOW_DAYS = 30
DEFAULT_QUERY_TEMPLATES = (
    "{subject} news",
    "{subject} launch",
    "{subject} hiring",
)
MAX_QUERIES = 3
MAX_SOURCES = 8
MAX_DEVELOPMENTS = 5
OFFLINE_NOTE = (
    "> **Offline fixture.** These results come from the bundled Tavily fixture, "
    "not live search. They are clearly labelled and are not a claim about the "
    "real world; set `TAVILY_API_KEY` to research the actual subject."
)
FALLBACK_QUESTIONS = (
    "What has {subject} shipped or announced in the last 30 days that changes our view?",
    "Which of these developments should we verify directly with {subject}?",
    "What would make us walk away from this meeting?",
    "Who inside {subject} owns the decision we care about?",
)


class _ReplaySearchClient:
    """Replay one already-fetched response for ``fetch_world_event``.

    The briefing searches first, chooses one unused result per query, then asks
    ``fetch_world_event`` to record it. Replaying the response keeps the search
    count at one per query and still reuses the shared recording path.
    """

    def __init__(self, response: Mapping[str, Any]) -> None:
        self._response = dict(response)

    def search(self, query: str, **_: Any) -> dict:
        return {**self._response, "query": query}


def _search(client: Any, query: str) -> dict:
    """Call the search adapter with the news defaults, tolerating small fakes.

    ``TavilyClient`` accepts ``topic`` and ``time_range``; a minimal test double
    may only accept ``query``. The fallbacks keep the use case adapter-agnostic
    without hiding a genuine error from the full call.
    """
    try:
        return client.search(
            query, max_results=5, topic="news", time_range="week"
        )
    except TypeError:
        pass
    try:
        return client.search(query, max_results=5)
    except TypeError:
        return client.search(query)


def _normalise_queries(subject: str, queries: Iterable[str] | None) -> list[str]:
    raw = [str(query).strip() for query in (queries or []) if str(query).strip()]
    if not raw:
        raw = [template.format(subject=subject) for template in DEFAULT_QUERY_TEMPLATES]
    return raw[:MAX_QUERIES]


def _normalise_result(raw: Mapping[str, Any]) -> dict:
    return {
        "title": str(raw.get("title") or "").strip() or "Untitled result",
        "url": str(raw.get("url") or "").strip(),
        "content": str(raw.get("content") or "").strip(),
        "date": str(raw.get("published_date") or raw.get("date") or "").strip(),
    }


def _result_key(result: Mapping[str, Any]) -> str:
    url = str(result.get("url") or "").strip().lower()
    if url:
        return "url:" + url
    return "title:" + str(result.get("title") or "").strip().lower()


def _as_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _now(clock: Any | None) -> datetime:
    if clock is None:
        return datetime.now(timezone.utc)
    if isinstance(clock, datetime):
        return clock
    now = getattr(clock, "now", None)
    if callable(now):
        return now()
    if isinstance(now, datetime):
        return now
    if callable(clock):
        return clock()
    raise TypeError("clock must be a datetime, a callable, or expose now()")


def _one_line(text: Any, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def _finding(content: str) -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    # The bundled offline fixture prefixes every item with the same sentence.
    text = re.sub(r"^A fixture item for the local demo\.\s*", "", text, flags=re.I)
    if not text:
        return "No snippet was returned for this result."
    return _one_line(text, 180)


def _clean_line(text: Any) -> str:
    """A character's line with the room's placeholders and meta lines removed."""
    cleaned = clean_scene_line(str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _collect_sources(
    responses: Sequence[tuple[str, Mapping[str, Any]]]
) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for query, response in responses:
        for raw in response.get("results") or []:
            if not isinstance(raw, Mapping):
                continue
            item = _normalise_result(raw)
            key = _result_key(item)
            if key in seen:
                continue
            seen.add(key)
            item["query"] = query
            sources.append(item)
            if len(sources) >= MAX_SOURCES:
                return sources
    return sources


def _record_search_events(
    service: WorldService,
    responses: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[dict]:
    """Record one ``world_event`` per distinct top result, in query order.

    Each search nominates its first result the briefing has not seen. A query
    whose whole result set is a duplicate of earlier searches records nothing,
    so the offline fixture (which returns the same three items for every query)
    yields three distinct events rather than nine duplicates.
    """
    used: set[str] = set()
    records: list[dict] = []
    for query, response in responses:
        results = [
            _normalise_result(raw)
            for raw in (response.get("results") or [])
            if isinstance(raw, Mapping)
        ]
        chosen = next(
            (item for item in results if _result_key(item) not in used), None
        )
        if chosen is None:
            continue
        used.add(_result_key(chosen))
        reordered = [chosen] + [
            item for item in results if _result_key(item) != _result_key(chosen)
        ]
        replay = _ReplaySearchClient(
            {
                "answer": response.get("answer", ""),
                "offline": bool(response.get("offline")),
                "results": [
                    {
                        "title": item["title"],
                        "url": item["url"],
                        "content": item["content"],
                        "published_date": item["date"],
                    }
                    for item in reordered
                ],
            }
        )
        try:
            records.append(
                fetch_world_event(
                    service,
                    query=query,
                    client=replay,
                    max_results=len(reordered),
                )
            )
        except (ValueError, RuntimeError):
            # A single unusable result must not sink the briefing.
            continue
    return records


def _in_window(
    sources: Sequence[Mapping[str, Any]], start: date, end: date
) -> list[dict]:
    found: list[dict] = []
    for item in sources:
        value = _as_date(item.get("date"))
        if value is None or start <= value <= end:
            found.append(dict(item))
    return found


def _group_message(
    subject: str, meeting: str, developments: Sequence[Mapping[str, Any]]
) -> str:
    findings = "; ".join(
        f"{index}. {_one_line(item.get('title'), 80)} "
        f"({_as_date(item.get('date')).isoformat() if _as_date(item.get('date')) else 'date unknown'})"
        for index, item in enumerate(developments[:3], start=1)
    )
    if not findings:
        findings = "no dated item was returned"
    message = (
        f"Pre-meeting briefing for {subject}, meeting {meeting}. "
        f"Top findings from the last {WINDOW_DAYS} days: {findings}. "
        f"What should we ask {subject}, and what are we missing?"
    )
    if len(message) > MAX_MESSAGE:
        message = message[: MAX_MESSAGE - 1].rstrip() + "…"
    return message


def _discussion(replies: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for reply in replies:
        text = _clean_line(reply.get("text"))
        if not text:
            continue
        lines.append((str(reply.get("character") or "character"), text))
    return lines


def _open_questions(
    discussion: Sequence[tuple[str, str]], subject: str
) -> list[str]:
    questions: list[str] = []
    for _character, text in discussion:
        if text.rstrip().endswith(("?", "？")):
            questions.append(text.rstrip())
    for template in FALLBACK_QUESTIONS:
        questions.append(template.format(subject=subject))
    unique: list[str] = []
    seen: set[str] = set()
    for question in questions:
        key = question.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(question)
    return unique[:6]


def _provenance_lines(service: WorldService, records: Sequence[dict]) -> list[str]:
    lines: list[str] = []
    for record in records:
        event = record["event"]
        key = record["key"]
        holders = service.who_knows(key).get("holders") or []
        if holders:
            held = ", ".join(
                f"{item['holder']} ({float(item.get('confidence') or 0.0):.2f})"
                for item in holders
            )
        else:
            held = ", ".join(
                f"{holder} (0.90)" for holder in record.get("holders") or []
            )
        lines.append(
            f"- **world_event {event['id']}** — "
            f"\"{_one_line(event.get('summary'), 120)}\" recorded by **director**. "
            f"Shared belief `{key}` held by {held} "
            f"(source `event:{event['id']}`)."
        )
    return lines


def _render(
    *,
    service: WorldService,
    subject: str,
    meeting: str,
    meeting_dt: datetime | None,
    now: datetime,
    sources: Sequence[Mapping[str, Any]],
    developments: Sequence[Mapping[str, Any]],
    discussion: Sequence[tuple[str, str]],
    questions: Sequence[str],
    records: Sequence[dict],
    replies: Sequence[Mapping[str, Any]],
    silent: Sequence[str],
    offline: bool,
    name: str,
    window_start: date,
    window_end: date,
) -> str:
    lines: list[str] = [f"# Pre-Meeting Briefing — {subject}", ""]
    if offline:
        lines.extend([OFFLINE_NOTE, ""])

    in_window = sum(
        1
        for item in sources
        if _as_date(item.get("date")) is not None
        and window_start <= _as_date(item.get("date")) <= window_end
    )
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- **Subject:** {subject}")
    lines.append(f"- **Meeting:** {meeting}")
    lines.append(
        f"- **Research window:** {window_start.isoformat()} → "
        f"{window_end.isoformat()} ({WINDOW_DAYS} days)"
    )
    lines.append(f"- **Briefing prepared:** {now.date().isoformat()}")
    lines.append(
        f"- **Sources reviewed:** {len(sources)} unique result(s), "
        f"{in_window} dated inside the window"
    )
    if replies:
        speakers = ", ".join(str(reply.get("character")).title() for reply in replies)
        note = f"{speakers} replied in character"
        if silent:
            note += f"; {', '.join(name.title() for name in silent)} stayed silent"
        lines.append(f"- **Room:** {note}")
    else:
        lines.append(
            "- **Room:** no transport or model was configured, so the cast did "
            "not discuss the findings"
        )
    if meeting_dt is not None and meeting_dt.date() < now.date():
        lines.append("- **Note:** the meeting time is in the past; check the date")
    lines.append("")

    lines.append("## Recent developments (last 30 days)")
    lines.append("")
    if developments:
        for index, item in enumerate(developments, start=1):
            when = _as_date(item.get("date"))
            lines.append(
                f"{index}. **{_one_line(item.get('title'), 120)}** — "
                f"{_finding(str(item.get('content') or ''))}  "
            )
            lines.append(
                f"   *{when.isoformat() if when else 'date unknown'}* · "
                f"{item.get('url') or '(no url)'}"
            )
    else:
        lines.append("- No result fell inside the research window.")
    lines.append("")

    lines.append("## Discussion points")
    lines.append("")
    if discussion:
        for character, text in discussion:
            lines.append(f"- **{character.title()}:** {text}")
    else:
        lines.append("- No character line survived the room's safety filter.")
    lines.append("")

    lines.append("## Open questions")
    lines.append("")
    for question in questions:
        lines.append(f"- {question}")
    lines.append("")

    lines.append("## Sources")
    lines.append("")
    for index, item in enumerate(sources, start=1):
        lines.append(
            f"{index}. {item.get('title')} — {item.get('url') or '(no url)'} "
            f"({item.get('date') or 'date unknown'})"
        )
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    provenance = _provenance_lines(service, records)
    if provenance:
        lines.extend(provenance)
    else:
        lines.append("- No search event was recorded for this briefing.")
    lines.append(
        f"- **briefing** recorded by **director** from {len(sources)} unique "
        f"source(s); written to `{name}`."
    )
    lines.append("")
    return "\n".join(lines)


def prepare_briefing(
    service: WorldService,
    subject: str,
    meeting: str,
    queries: Sequence[str] | None = None,
    search_client: Any | None = None,
    transport: Any | None = None,
    model: Any | None = None,
    clock: Any | None = None,
    artifacts: Any | None = None,
) -> dict:
    """Research ``subject``, have the room discuss it, and write one page.

    ``transport`` wins when supplied; a bare ``model`` is wrapped in the same
    in-band room the cloud/Bifrost roots use. With neither, the briefing is
    written without character discussion. ``artifacts`` is the injected
    ``ArtifactStore``; without one the process export directory is used.
    """
    subject = str(subject or "").strip()
    meeting = str(meeting or "").strip()
    if not subject:
        raise ValueError("subject is required")
    if not meeting:
        raise ValueError("meeting is required")

    resolved_queries = _normalise_queries(subject, queries)
    client = search_client if search_client is not None else default_search_client()

    responses: list[tuple[str, Mapping[str, Any]]] = []
    failures: list[BaseException] = []
    for query in resolved_queries:
        try:
            response = _search(client, query)
        except Exception as exc:  # noqa: BLE001 - reported if every query fails
            failures.append(exc)
            continue
        responses.append((query, response or {}))
    if not responses:
        detail = "; ".join(str(error) for error in failures) or "no response"
        raise ValueError(f"Tavily search failed for every query: {detail}")

    offline = any(bool(response.get("offline")) for _query, response in responses)
    sources = _collect_sources(responses)
    if not sources:
        raise ValueError(f"Tavily returned no results for {subject!r}")

    now = _now(clock)
    meeting_dt = _parse_datetime(meeting)
    anchor = meeting_dt or now
    window_start = (anchor - timedelta(days=WINDOW_DAYS)).date()
    window_end = anchor.date()
    developments = _in_window(sources, window_start, window_end)
    if not developments:
        developments = list(sources)
    developments = developments[:MAX_DEVELOPMENTS]

    records = _record_search_events(service, responses)
    recorded_by_key = {
        _result_key(_normalise_result({"title": record["title"], "url": record["url"]})): record
        for record in records
    }
    for item in sources:
        record = recorded_by_key.get(_result_key(item))
        if record is not None:
            item["event_id"] = record["event"]["id"]
            item["proposition_key"] = record["key"]

    replies: list[dict] = []
    silent: list[str] = []
    if transport is not None or model is not None:
        if transport is None:
            transport = cloud_room_transport(model)
        message = _group_message(subject, meeting, developments)
        group = say_in_group(service, message, transport=transport)
        replies = list(group.get("replies") or [])
        silent = list(group.get("silent") or [])

    discussion = _discussion(replies)
    questions = _open_questions(discussion, subject)

    store = artifacts if artifacts is not None else default_artifact_store()
    slug = slugify(subject)
    name = f"briefing-{slug}.md"
    text = _render(
        service=service,
        subject=subject,
        meeting=meeting,
        meeting_dt=meeting_dt,
        now=now,
        sources=sources,
        developments=developments,
        discussion=discussion,
        questions=questions,
        records=records,
        replies=replies,
        silent=silent,
        offline=offline,
        name=name,
        window_start=window_start,
        window_end=window_end,
    )
    ref = store.write(name, text)

    source_list = [
        {
            "title": item["title"],
            "url": item["url"],
            "date": item["date"],
            "event_id": item.get("event_id"),
        }
        for item in sources
    ]
    briefing_event = service.record_event(
        "director",
        "briefing",
        (
            f"Pre-meeting briefing: {subject} — meeting {meeting} — "
            f"{len(sources)} source(s) -> {ref.path}"
        ),
        participants=[],
        visibility="public",
        metadata={
            "subject": subject,
            "meeting": meeting,
            "name": ref.name,
            "path": ref.path,
            "source_count": len(sources),
            "source_list": source_list,
            "offline": offline,
            "search_event_ids": [record["event"]["id"] for record in records],
            "replies": [
                {"character": reply.get("character"), "text": reply.get("text")}
                for reply in replies
            ],
            "silent": silent,
        },
    )

    events = [record["event"] for record in records] + [briefing_event]
    return {
        "subject": subject,
        "meeting": meeting,
        "briefing": text,
        "path": ref.path,
        "sources": source_list,
        "events": events,
        "replies": replies,
    }


__all__ = ["prepare_briefing"]
