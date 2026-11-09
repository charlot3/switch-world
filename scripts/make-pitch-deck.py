#!/usr/bin/env python3
"""Build the Geek Room pitch deck for the Tavily Research Agent brief.

    uv run python scripts/make-pitch-deck.py

The deck presents Four Hearts as a pre-meeting briefing agent: a company or
person plus a meeting time, researched over the last 30 days, written as one
page with source-backed findings, discussion points and open questions.

The deck is a draft: replace the screenshots or copy with the final recording,
then export to PDF if the submission form asks for one.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "switch-world-geekroom-pitch.pptx"

BG = RGBColor(16, 10, 20)
INK = RGBColor(245, 236, 240)
MUTED = RGBColor(184, 164, 178)
ROSE = RGBColor(224, 96, 126)


def textbox(slide, left, top, width, height, text, size=18, color=INK, bold=False):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.font.size = Pt(size)
    paragraph.font.color.rgb = color
    paragraph.font.bold = bold
    paragraph.font.name = "Avenir Next"
    return box


def bullets(slide, items, left=0.9, top=1.75, width=11.5, height=4.8, size=18):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = f"· {item}"
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = INK
        paragraph.font.name = "Avenir Next"
        paragraph.space_after = Pt(12)
        paragraph.level = 0


def title_slide(prs, title, eyebrow, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = BG
    textbox(slide, 0.8, 0.55, 11.5, 0.4, eyebrow.upper(), 11, ROSE, True)
    textbox(slide, 0.8, 1.15, 11.5, 1.0, title, 38, INK, True)
    if subtitle:
        textbox(slide, 0.8, 2.35, 11.0, 0.9, subtitle, 18, MUTED)
    textbox(slide, 0.8, 6.9, 11.5, 0.3, "Four Hearts · Geek Room edition · 2026", 9, MUTED)
    return slide


def content_slide(
    prs,
    title,
    eyebrow,
    items,
    image=None,
    image_height=4.4,
    text_size=17,
):
    slide = title_slide(prs, title, eyebrow)
    if image:
        bullets(slide, items, left=0.8, top=1.8, width=5.3, height=4.6, size=14)
        picture = slide.shapes.add_picture(
            str(ROOT / image), Inches(6.4), Inches(1.5), height=Inches(image_height)
        )
        ratio = picture.width / picture.height
        if picture.width > Inches(6.1):
            picture.width = Inches(6.1)
            picture.height = int(picture.width / ratio)
        picture.left = int(Inches(6.4) + (Inches(6.1) - picture.width) / 2)
    else:
        bullets(slide, items, left=0.8, top=1.8, width=11.6, height=4.7, size=text_size)
    return slide


def main() -> int:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    title_slide(
        prs,
        "Four Hearts",
        "Tavily Research Agent · Geek Room Global AI Hackathon",
        "A social research room that prepares a pre-meeting briefing.",
    )

    content_slide(
        prs,
        "The problem",
        "Pre-meeting research is manual and easy to fake",
        [
            "Someone skims the last 30 days of news the night before, or walks in unprepared.",
            "A generic agent answers from stale weights and invents sources; a confident wrong fact is worse than no brief.",
            "The Tavily Research Agent brief is narrower: a company or person plus a meeting time, researched over the last 30 days, in one page.",
            "That page needs source-backed findings, discussion points and open questions — not another chat log.",
        ],
        text_size=18,
    )

    content_slide(
        prs,
        "The product",
        "Four characters research, then argue it out",
        [
            "Give Four Hearts a subject and a meeting time.",
            "Alice, Emily, Sophia and Mia read the same Tavily findings in character.",
            "The room argues: Alice anchors, Emily challenges, Sophia frames, Mia pokes.",
            "Every claim carries a source; every reply and silence is recorded.",
            "Output: one page with findings, discussion points, open questions, sources and provenance.",
        ],
        image="docs/geekroom-dashboard.png",
        image_height=4.0,
    )

    content_slide(
        prs,
        "The demo",
        "Subject + meeting → Tavily → room → one page",
        [
            "uv run director --briefing --subject Anthropic --meeting 2026-11-18T10:00:00+09:00",
            "2–3 news-shaped Tavily queries cover the last 30 days; each distinct result becomes a world_event and a shared belief (source event:<id>).",
            "The four characters discuss the findings through the same group-turn pipeline; silent characters are recorded.",
            "briefing.py writes briefing-<slug>.md and records a briefing event pointing at it.",
            "Offline fixture is labelled; a live key takes the same path.",
        ],
        image="docs/geekroom-ledger.png",
        image_height=4.0,
    )

    content_slide(
        prs,
        "Architecture",
        "Bifrost gateway + Tavily + ledger + scene card",
        [
            "Room / dashboard → world engine (MCP) → beliefs · relationships · events.",
            "Bifrost is the model control plane for the Four Hearts profile: routing, fallbacks, per-character token budgets and request logs.",
            "Tavily is the only web access: the same adapter serves the briefing and world__search_web.",
            "The ledger records who learned what, from where; the scene card exports the same provenance.",
            "Switch remains the Flip transport; the briefing demo runs without it.",
        ],
        text_size=18,
    )

    content_slide(
        prs,
        "Proof",
        "What is actually running",
        [
            "435 passing tests and 85% coverage; the briefing has its own end-to-end test on the offline fixture.",
            "docs/briefing-example.md is a labelled offline-fixture page: findings, room discussion, open questions and provenance.",
            "Bifrost profile: OpenCode Go DeepSeek V4.1 Flash through the gateway, with data/logs/bifrost.jsonl.",
            "Live Tavily is a drop-in: set TAVILY_API_KEY and unset TAVILY_OFFLINE; the fixture is never presented as live.",
        ],
        text_size=18,
    )

    content_slide(
        prs,
        "Roadmap",
        "From one briefing to a research habit",
        [
            "Record the demo with a live Tavily key; keep the labelled fixture as the fallback.",
            "Provider-per-character routing through Bifrost (config, not a rewrite).",
            "Briefing templates per meeting type, and a diff against the last brief.",
            "Ship the one-page artifact and its provenance, not a chat log.",
        ],
        text_size=18,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
