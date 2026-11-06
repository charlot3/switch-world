"""MCP tool surface. Thin adapters over WorldService.

Every tool resolves the caller from the bearer token in the HTTP request. The
server maps token -> actor; no tool accepts a character id from the client.
"""
from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from gateway.tavily import TavilyClient, TavilyError, TavilyNotConfigured

from .service import WorldService


def create_mcp(service: WorldService) -> MCPServer:
    mcp = MCPServer(
        "switch-world",
        description="A small social world with provenance-tracked beliefs and relationships.",
        instructions=(
            "You are a character in a social world. Read your own beliefs with "
            "world__recall before making a claim about another person. Write what you "
            "learn with world__remember, including the source and a proposition_key. "
            "Write how you feel with world__update_relationship. Never reveal a private "
            "belief unless your disclosure policy says so. When a question is about the "
            "present or a fact after your training, call world__search_web instead of "
            "guessing; record what you learn from it as an observation."
        ),
    )

    def actor(ctx: Context) -> str:
        try:
            return service.actor_from_headers(ctx.headers)
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc

    def director(ctx: Context) -> str:
        who = actor(ctx)
        if who != "director":
            raise ValueError("this tool is director-only")
        return who

    @mcp.tool()
    def world__recall(query: str, ctx: Context, limit: int = 8) -> dict:
        """Recall the beliefs and relationship facts this character may see.

        Only your own beliefs and public facts are returned. Use this before making a
        claim about another person.
        """
        return service.recall(actor(ctx), query=query, limit=limit)

    @mcp.tool()
    def world__search_web(
        query: str,
        ctx: Context,
        max_results: int = 5,
        topic: str = "news",
    ) -> dict:
        """Search the live web through Tavily for current, real-world information.

        Use this instead of answering from stale training data when a question is about
        the present. The result includes titles, URLs and snippets; record what you
        learned with world__remember and source "observation" (or event:<id> for a
        shared world event).
        """
        actor(ctx)
        try:
            return TavilyClient.from_env().search(
                query, max_results=max_results, topic=topic
            )
        except TavilyNotConfigured as exc:
            raise ValueError(str(exc)) from exc
        except TavilyError as exc:
            raise ValueError(f"web search failed: {exc}") from exc

    @mcp.tool()
    def world__remember(
        proposition: str,
        source: str,
        ctx: Context,
        confidence: float = 0.8,
        visibility: str = "private",
        proposition_key: str | None = None,
    ) -> dict:
        """Record a belief you now hold.

        source: "user", "observation", "character:<id>" or "event:<id>".
        visibility: "private" (only you), "shared" (scene participants) or "public".
        proposition_key: the matrix row; pass it when the scene gives you a canonical key.
        """
        return service.remember(
            actor(ctx),
            proposition=proposition,
            source=source,
            confidence=confidence,
            visibility=visibility,
            proposition_key=proposition_key,
        )

    @mcp.tool()
    def world__relationship(other: str, ctx: Context) -> dict:
        """Read your directed view of another person (trust, closeness, tension)."""
        return service.relationship(actor(ctx), other)

    @mcp.tool()
    def world__update_relationship(
        other: str,
        ctx: Context,
        trust_delta: float = 0.0,
        closeness_delta: float = 0.0,
        tension_delta: float = 0.0,
        reason: str = "",
    ) -> dict:
        """Adjust your directed view of another person and record why.

        Deltas are clamped so every value stays in 0..1. The edge belongs to you; the
        other character's view is separate.
        """
        return service.update_relationship(
            actor(ctx),
            other=other,
            trust_delta=trust_delta,
            closeness_delta=closeness_delta,
            tension_delta=tension_delta,
            reason=reason,
        )

    @mcp.tool()
    def world__record_event(
        kind: str,
        summary: str,
        ctx: Context,
        participants: list[str] | None = None,
        visibility: str = "public",
    ) -> dict:
        """Director-only: append an event to the world log. Events are immutable."""
        return service.record_event(
            director(ctx),
            kind=kind,
            summary=summary,
            participants=participants or [],
            visibility=visibility,
        )

    @mcp.tool()
    def world__who_knows(proposition_key: str, ctx: Context) -> dict:
        """Director-only: the full provenance matrix for one proposition."""
        director(ctx)
        return service.who_knows(proposition_key)

    @mcp.tool()
    def world__set_outfit(
        ctx: Context,
        outfit_id: str,
        reason: str = "",
        source_belief_id: str = "",
    ) -> dict:
        """Change into an outfit declared by the current scenario, citing the memory."""
        who = actor(ctx)
        source = source_belief_id.strip() or None
        return service.set_outfit(
            who, outfit_id, reason=reason, source_belief_id=source
        )

    @mcp.tool()
    def world__give_item(ctx: Context, item_id: str, to: str, note: str = "") -> dict:
        """Hand an item to another person; the hand-off is recorded as an event."""
        return service.give_item(item_id, to, label=note or None)

    @mcp.tool()
    def world__allowed_looks(ctx: Context) -> dict:
        """The outfits the current scenario declares for this character."""
        who = actor(ctx)
        scenario = service.current_scenario() or {}
        return {
            "character": who,
            "outfits": (scenario.get("outfits") or {}).get(who),
        }

    @mcp.tool()
    def world__connections(ctx: Context) -> dict:
        """The cast-to-cast relationship graph, not just the user-centred star."""
        return {"connections": service.connections()}

    @mcp.tool()
    def world__ending_status(ctx: Context) -> dict:
        """The current scenario's ending card, if one is loaded."""
        scenario = service.current_scenario() or {}
        return {"scenario": scenario.get("id"), "ending": scenario.get("ending")}

    @mcp.tool()
    def world__advance_time(minutes: int, ctx: Context) -> dict:
        """Director-only: move the simulated world clock."""
        director(ctx)
        return service.advance_time("director", minutes)

    return mcp
