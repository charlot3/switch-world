#!/usr/bin/env python3
"""Build the Geek Room pitch deck from the repository screenshots.

    uv run python scripts/make-pitch-deck.py

The deck is a draft: replace the screenshots or copy with the final recording, then
export to PDF if the submission form asks for one.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "switch-world-geekroom-pitch.pptx"

BG = RGBColor(16, 10, 20)
PANEL = RGBColor(30, 20, 34)
INK = RGBColor(245, 236, 240)
MUTED = RGBColor(184, 164, 178)
ROSE = RGBColor(224, 96, 126)
GOLD = RGBColor(189, 127, 36)


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
        paragraph.text = item
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = INK if index == 0 else MUTED
        paragraph.font.name = "Avenir Next"
        paragraph.space_after = Pt(12)
        paragraph.level = 0


def title_slide(prs, title, eyebrow, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = BG
    textbox(slide, 0.8, 0.55, 8.5, 0.4, eyebrow.upper(), 11, ROSE, True)
    textbox(slide, 0.8, 1.15, 11.5, 1.0, title, 38, INK, True)
    if subtitle:
        textbox(slide, 0.8, 2.35, 11.0, 0.8, subtitle, 18, MUTED)
    textbox(slide, 0.8, 6.9, 11.5, 0.3, "Four Hearts · Geek Room edition · 2026", 9, MUTED)
    return slide


def content_slide(prs, title, eyebrow, items, image=None, image_height=4.6):
    slide = title_slide(prs, title, eyebrow)
    if image:
        bullets(slide, items, left=0.8, top=1.8, width=5.2, height=4.6, size=15)
        picture = slide.shapes.add_picture(
            str(ROOT / image), Inches(6.35), Inches(1.45), height=Inches(image_height)
        )
        # Center in the right half if the aspect ratio leaves room.
        ratio = picture.width / picture.height
        if picture.width > Inches(6.2):
            picture.width = Inches(6.2)
            picture.height = int(picture.width / ratio)
        picture.left = int(Inches(6.35) + (Inches(6.2) - picture.width) / 2)
    else:
        bullets(slide, items, left=0.8, top=1.8, width=11.6, height=4.6, size=17)
    return slide


def main() -> int:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    title_slide(
        prs,
        "Four Hearts",
        "Geek Room Global AI Hackathon · switch-world",
        "A social world with a memory you can audit.",
    )

    content_slide(
        prs,
        "The problem",
        "Why multi-agent stories break",
        [
            "Canon drifts: a character invents a fact and the worldline is gone.",
            "Provenance is lost: nobody knows who learned what, from whom.",
            "Real life is missing: characters answer the present from stale weights.",
            "A writers' room, tabletop GM or social-simulation researcher needs all three.",
        ],
    )

    content_slide(
        prs,
        "The product",
        "One scene, one auditable artifact",
        [
            "Four characters with private facts, goals and relationships.",
            "A secret ledger: source, confidence and visibility for every belief.",
            "An authored canon: five beats, three branches, invariants.",
            "A scene card: who knew what, from whom, and what moved.",
        ],
    )

    content_slide(
        prs,
        "The demo",
        "Bifrost generates the café scene",
        [
            "Human seeds one secret; Alice decides whether to tell Emily.",
            "The branch is classified from the ledger, not from the prose.",
            "The dashboard shows the branch, the matrix and the cast card.",
        ],
        image="docs/geekroom-dashboard.png",
        image_height=4.4,
    )

    content_slide(
        prs,
        "Architecture",
        "One world engine, two provider layers",
        [
            "Human → Switch or dashboard → world engine (MCP) → beliefs · relationships · events.",
            "Bifrost is the model control plane: routing, fallbacks, budgets, logs.",
            "Tavily is the real-world input: news → shared world event → character memory.",
            "Switch is the Flip transport; the Geek Room demo can run without it.",
        ],
    )

    content_slide(
        prs,
        "Bifrost",
        "Every character call goes through the gateway",
        [
            "world/models.json: model, fallbacks, temperature, token budget per character.",
            "data/logs/bifrost.jsonl: character, model, tokens, latency, status.",
            "DeepSeek V4.1 Flash through Bifrost; per-character model config and token logs.",
            "Bifrost UI at :8080 is the gateway-side observability evidence.",
        ],
        image="docs/geekroom-settings.png",
        image_height=4.3,
    )

    content_slide(
        prs,
        "Tavily",
        "The present becomes shared memory",
        [
            "Packaged demo: TAVILY_OFFLINE=1 and a labelled fixture, never passed off as live.",
            "TAVILY_API_KEY is the live switch: set it and unset TAVILY_OFFLINE.",
            "Scheduler turns one search into a public world_event; each character records source event:<id>.",
            "world__search_web gives a character live retrieval in DMs when a key is set.",
        ],
        image="docs/geekroom-ledger.png",
        image_height=4.3,
    )

    content_slide(
        prs,
        "Two editions",
        "One codebase, two deadlines",
        [
            "Flip the Switch: main / tag flip-2026-11-05; Switch is the transport.",
            "Four Hearts: geekroom branch; Bifrost + Tavily are additive.",
            "Same canon, same world engine, same scene card.",
            "Flip deadline 2026-11-08; Geek Room deadline 2026-11-15.",
        ],
    )

    content_slide(
        prs,
        "Proof",
        "What is actually running",
        [
            "426 passing tests and 85% coverage for world engine, canon, Bifrost and Tavily.",
            "A real Bifrost → DeepSeek V4.1 Flash café scene with token logs.",
            "A labelled Tavily fixture event shared by all four characters; a live key is a drop-in.",
            "Reproducible runbook: docs/GEEKROOM.md; screenshots in docs/.",
        ],
    )

    content_slide(
        prs,
        "Next",
        "From a scene to a writer's room",
        [
            "Different provider models per character; failover in the demo.",
            "Live Tavily key and a background daily scheduler.",
            "A longer authored arc and a deck/video cut for Geek Room.",
            "The artifact stays the same: a scene and its provenance.",
        ],
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
