"""One context projection for DM and group prompts.

The model does not need the whole transcript. This module assembles the optional
context blocks in a fixed order and trims the oldest material first until the prompt
fits a hard byte budget. The relationship/social block is never trimmed, and at most
the latest six memories are carried.

Trimming order: old DMs, then old scene lines, then memories (only as a last resort).
The final text is clipped at a UTF-8 boundary, so a long CJK line can never split a
codepoint.
"""
from __future__ import annotations

CONTEXT_BUDGET_BYTES = 12 * 1024
MEMORY_LIMIT = 6


def _size(text: str) -> int:
    return len((text or "").encode("utf-8"))


def clip_bytes(text: str, limit: int) -> str:
    """Hard-clip text to `limit` UTF-8 bytes without splitting a codepoint."""
    raw = (text or "").encode("utf-8")
    if len(raw) <= limit:
        return text or ""
    cut = raw[: max(0, limit)]
    while cut:
        try:
            return cut.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def project_context(
    *,
    social_block: str = "",
    extra: str = "",
    message: str = "",
    history_lines: list[str] | None = None,
    scene_lines: list[str] | None = None,
    memories: list[str] | None = None,
    history_label: str = "Recent private DM",
    scene_label: str = "Recent scene (public)",
    memory_label: str = "Your memories and public facts",
    reserved: int = 0,
    budget: int = CONTEXT_BUDGET_BYTES,
) -> dict:
    """Assemble a prompt body under `budget` bytes (including `reserved`).

    `reserved` is the byte size of a separate system prompt the caller will send
    alongside this body, so the *whole* prompt stays inside the cap.
    """
    history = list(history_lines or [])
    scene = list(scene_lines or [])
    memory = list(memories or [])[:MEMORY_LIMIT]
    trimmed = {"history": 0, "scene": 0, "memories": 0}

    def render() -> dict:
        parts = {
            "memory_text": "\n".join(memory) or "(nothing relevant)",
            "scene_text": "\n".join(scene) or "(no recent scene lines)",
            "history_text": "\n".join(history) or "(no earlier context)",
        }
        blocks = [
            social_block.strip(),
            extra.strip(),
            f"{memory_label}:\n{parts['memory_text']}" if memory_label else "",
            f"{scene_label}:\n{parts['scene_text']}" if scene_label else "",
            f"{history_label}:\n{parts['history_text']}" if history_label else "",
            message.strip(),
        ]
        body = "\n\n".join(block for block in blocks if block)
        return {**parts, "text": body, "size": reserved + _size(body)}

    projected = render()
    while projected["size"] > budget and history:
        history.pop(0)
        trimmed["history"] += 1
        projected = render()
    while projected["size"] > budget and scene:
        scene.pop(0)
        trimmed["scene"] += 1
        projected = render()
    while projected["size"] > budget and memory:
        memory.pop()
        trimmed["memories"] += 1
        projected = render()

    text = projected["text"]
    limit = max(0, budget - max(0, reserved))
    if _size(text) > limit:
        text = clip_bytes(text, limit)
    return {
        **projected,
        "text": text,
        "size": reserved + _size(text),
        "trimmed": trimmed,
        "budget": budget,
    }
