#!/usr/bin/env python3
"""Generate the four galgame-style vector portraits for the dashboard.

The art is intentionally vector and stylised: consistent silhouettes, distinct hair,
eyes and outfits, a soft visual-novel colour wash, and no generated media. Outputs
`web/assets/portraits/<id>.svg` (portrait) and `<id>-avatar.svg` (square crop).

Tone: 17+ romantic atmosphere, fully clothed, adult characters. No explicit content.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "assets" / "portraits"

CHARACTERS = {
    "alice": dict(
        name="Alice Moreau",
        skin=("#f7ddce", "#e8b9a3"),
        hair=("#5a3325", "#a86743"),
        eye="#8a5a3b",
        cloth=("#f1e4cf", "#d8c09c"),
        inner="#8e3145",
        accent="#c96a7c",
        hair_style="bun",
        outfit="cardigan",
        accessory="glasses_gold",
        scene="bookshop",
        blush=0.22,
        eye_open=0.92,
        brow_tilt=-2,
        mouth="soft",
    ),
    "emily": dict(
        name="Emily Park",
        skin=("#f4d8d3", "#e2b6b1"),
        hair=("#1b1720", "#403446"),
        eye="#4a2f37",
        cloth=("#2c2933", "#494354"),
        inner="#f4efe9",
        accent="#a99bd6",
        hair_style="bob",
        outfit="blazer",
        accessory="earrings_silver",
        scene="studio",
        blush=0.12,
        eye_open=0.78,
        brow_tilt=-6,
        mouth="smirk",
    ),
    "sophia": dict(
        name="Sophia Adeyemi",
        skin=("#b9785c", "#8e543d"),
        hair=("#21171b", "#4b3036"),
        eye="#b9792f",
        cloth=("#17151a", "#302a36"),
        inner="#d8c3a1",
        accent="#d9a441",
        hair_style="curls",
        outfit="turtleneck",
        accessory="glasses_gold",
        scene="office",
        blush=0.16,
        eye_open=0.7,
        brow_tilt=-1,
        mouth="dry",
    ),
    "mia": dict(
        name="Mia Rossi",
        skin=("#f6d7c2", "#e5b295"),
        hair=("#8a3f2a", "#c06a40"),
        eye="#4f7a4f",
        cloth=("#d6a23f", "#b57c22"),
        inner="#f7f0e2",
        accent="#e07a5f",
        hair_style="ponytail",
        outfit="apron",
        accessory="freckles",
        scene="truck",
        blush=0.3,
        eye_open=1.0,
        brow_tilt=4,
        mouth="grin",
    ),
}


def scene_svg(c: dict) -> str:
    if c["scene"] == "bookshop":
        return f"""
  <rect x="52" y="90" width="238" height="318" rx="8" fill="#f2c98f" opacity=".13"/>
  <rect x="52" y="90" width="238" height="318" rx="8" fill="none" stroke="#f2c98f" stroke-opacity=".35" stroke-width="3"/>
  <path d="M171 90 V408 M52 249 H290" stroke="#f2c98f" stroke-opacity=".28" stroke-width="3"/>
  <rect x="410" y="120" width="140" height="520" rx="6" fill="#1b1017" opacity=".55"/>
  <path d="M410 250 H550 M410 380 H550 M410 510 H550" stroke="#f2c98f" stroke-opacity=".18" stroke-width="2"/>
  <g opacity=".55">
    <rect x="424" y="165" width="15" height="80" rx="2" fill="#8e3145"/>
    <rect x="443" y="155" width="13" height="90" rx="2" fill="#c96a7c"/>
    <rect x="460" y="172" width="18" height="73" rx="2" fill="#d8c09c"/>
    <rect x="482" y="160" width="12" height="85" rx="2" fill="#a86743"/>
    <rect x="424" y="300" width="18" height="75" rx="2" fill="#d8c09c"/>
    <rect x="446" y="290" width="12" height="85" rx="2" fill="#8e3145"/>
    <rect x="462" y="305" width="16" height="70" rx="2" fill="#c96a7c"/>
  </g>"""
    if c["scene"] == "studio":
        return """
  <rect x="70" y="100" width="150" height="190" rx="4" fill="#a99bd6" opacity=".12"/>
  <rect x="70" y="100" width="150" height="190" rx="4" fill="none" stroke="#a99bd6" stroke-opacity=".3" stroke-width="3"/>
  <rect x="430" y="70" width="120" height="150" rx="4" fill="#a99bd6" opacity=".1"/>
  <rect x="430" y="70" width="120" height="150" rx="4" fill="none" stroke="#a99bd6" stroke-opacity=".26" stroke-width="3"/>
  <path d="M70 640 H550" stroke="#a99bd6" stroke-opacity=".2" stroke-width="3"/>
  <rect x="430" y="470" width="120" height="170" rx="4" fill="#17151a" opacity=".5"/>"""
    if c["scene"] == "office":
        return """
  <rect x="58" y="110" width="150" height="560" rx="6" fill="#1b1017" opacity=".6"/>
  <path d="M58 250 H208 M58 390 H208 M58 530 H208" stroke="#d9a441" stroke-opacity=".2" stroke-width="2"/>
  <g opacity=".5">
    <rect x="72" y="150" width="14" height="90" rx="2" fill="#d9a441"/>
    <rect x="90" y="140" width="12" height="100" rx="2" fill="#8e543d"/>
    <rect x="106" y="158" width="18" height="82" rx="2" fill="#d8c3a1"/>
    <rect x="128" y="146" width="12" height="94" rx="2" fill="#b9792f"/>
    <rect x="72" y="290" width="18" height="92" rx="2" fill="#d8c3a1"/>
    <rect x="94" y="280" width="12" height="102" rx="2" fill="#d9a441"/>
    <rect x="110" y="296" width="16" height="86" rx="2" fill="#4b3036"/>
  </g>
  <circle cx="486" cy="250" r="70" fill="#d9a441" opacity=".22"/>
  <path d="M486 180 V140 M450 140 H522" stroke="#d9a441" stroke-opacity=".5" stroke-width="4"/>"""
    return """
  <path d="M0 470 Q150 420 300 460 Q450 500 600 450 V900 H0 Z" fill="#2a1a2e" opacity=".55"/>
  <path d="M40 190 Q300 120 560 190" fill="none" stroke="#f2c98f" stroke-opacity=".35" stroke-width="2"/>
  <path d="M40 280 Q300 210 560 280" fill="none" stroke="#f2c98f" stroke-opacity=".25" stroke-width="2"/>
  <g fill="#f7d9a0">
    <circle cx="100" cy="210" r="6"/><circle cx="180" cy="190" r="5"/><circle cx="260" cy="182" r="6"/>
    <circle cx="340" cy="182" r="5"/><circle cx="420" cy="190" r="6"/><circle cx="500" cy="210" r="5"/>
  </g>
  <rect x="430" y="520" width="140" height="300" rx="10" fill="#1b1017" opacity=".6"/>
  <rect x="450" y="545" width="100" height="60" rx="6" fill="#e07a5f" opacity=".35"/>"""


def hair_svg(c: dict) -> tuple[str, str]:
    """Return (back hair, front hair). The back is drawn before the face, the front after."""
    style = c["hair_style"]
    if style == "bun":
        back = f"""
  <path d="M300 208 C402 208 456 288 450 410 L442 505 C438 536 418 540 412 508 L402 432
           C402 350 362 300 300 300 C238 300 198 350 198 432 L188 508 C182 540 162 536 158 505
           L150 410 C144 288 198 208 300 208 Z" fill="url(#hair)"/>
  <circle cx="300" cy="196" r="62" fill="url(#hair)"/>
  <path d="M245 196 Q300 160 355 196" fill="none" stroke="#f0c9a8" stroke-opacity=".25" stroke-width="5"/>
  <path d="M188 330 C166 402 170 488 194 548" fill="none" stroke="url(#hair)" stroke-width="28" stroke-linecap="round"/>
  <path d="M412 330 C434 402 430 488 406 548" fill="none" stroke="url(#hair)" stroke-width="24" stroke-linecap="round"/>"""
        front = f"""
  <path d="M182 330 C214 252 322 226 412 300 C368 290 300 300 252 342 C224 366 202 390 182 420 Z" fill="url(#hair)"/>
  <path d="M196 300 C250 254 340 250 394 286" fill="none" stroke="#f0c9a8" stroke-opacity=".2" stroke-width="5"/>"""
        return back, front
    if style == "bob":
        back = f"""
  <path d="M300 204 C412 204 466 288 460 420 L455 548 L408 548 L408 432
           C408 350 368 300 300 300 C232 300 192 350 192 432 L192 548 L145 548
           L140 420 C134 288 188 204 300 204 Z" fill="url(#hair)"/>"""
        front = f"""
  <path d="M178 342 C184 254 250 218 300 218 C350 218 416 254 422 342
           C400 300 354 280 300 280 C246 280 200 300 178 342 Z" fill="url(#hair)"/>
  <path d="M186 244 C250 210 350 210 414 244" fill="none" stroke="#b9a7d6" stroke-opacity=".22" stroke-width="6"/>"""
        return back, front
    if style == "curls":
        back = f"""
  <path d="M300 208 C402 208 456 288 450 410 L442 505 C438 536 418 540 412 508 L402 432
           C402 350 362 300 300 300 C238 300 198 350 198 432 L188 508 C182 540 162 536 158 505
           L150 410 C144 288 198 208 300 208 Z" fill="url(#hair)"/>
  <g fill="url(#hair)">
    <circle cx="166" cy="350" r="34"/><circle cx="154" cy="430" r="36"/><circle cx="164" cy="508" r="32"/>
    <circle cx="434" cy="350" r="34"/><circle cx="446" cy="430" r="36"/><circle cx="436" cy="508" r="32"/>
    <circle cx="450" cy="540" r="46"/>
  </g>"""
        front = f"""
  <path d="M182 340 C220 258 300 232 340 250 C292 258 252 292 232 352 Z" fill="url(#hair)"/>
  <path d="M420 340 C382 258 310 232 270 250 C312 258 350 292 368 352 Z" fill="url(#hair)"/>
  <path d="M180 250 C250 212 350 212 420 250" fill="none" stroke="#d9a441" stroke-opacity=".18" stroke-width="6"/>"""
        return back, front
    back = f"""
  <path d="M300 208 C402 208 456 288 450 410 L442 505 C438 536 418 540 412 508 L402 432
           C402 350 362 300 300 300 C238 300 198 350 198 432 L188 508 C182 540 162 536 158 505
           L150 410 C144 288 198 208 300 208 Z" fill="url(#hair)"/>
  <path d="M430 270 C510 286 540 380 522 486 C512 548 486 586 452 566
           C482 500 492 420 452 350 C442 326 436 296 430 270 Z" fill="url(#hair)"/>
  <ellipse cx="438" cy="282" rx="24" ry="16" fill="#e07a5f"/>"""
    front = f"""
  <path d="M170 330 C208 250 320 224 414 300 C370 288 300 300 250 342 C222 366 198 392 170 420 Z" fill="url(#hair)"/>
  <path d="M198 330 C176 402 180 488 204 548" fill="none" stroke="url(#hair)" stroke-width="24" stroke-linecap="round"/>
  <path d="M212 292 C260 250 340 246 390 280" fill="none" stroke="#f0b08a" stroke-opacity=".2" stroke-width="5"/>"""
    return back, front


def eye_svg(c: dict, cx: int, side: int) -> str:
    """One large visual-novel eye, with a lifted outer corner, iris depth and lashes."""
    cy = 418
    open_ = c["eye_open"]
    h = 31 * open_
    tilt = c["brow_tilt"] * side
    outer = cx - 48 if side == -1 else cx + 48
    inner = cx + 40 if side == -1 else cx - 40
    lash = "#24141c"
    flick = -12 if side == -1 else 12
    return f"""
  <path d="M{outer} {cy} Q{cx} {cy - h - 10} {inner} {cy - 4} Q{cx} {cy + h + 2} {outer} {cy} Z" fill="#fffaf4"/>
  <path d="M{outer} {cy} Q{cx} {cy - h - 10} {inner} {cy - 4} Q{cx} {cy + h + 2} {outer} {cy} Z" fill="{c['eye']}" opacity=".08"/>
  <ellipse cx="{cx}" cy="{cy - 2}" rx="20" ry="{24 * open_:.1f}" fill="url(#iris)"/>
  <ellipse cx="{cx}" cy="{cy - 2}" rx="8" ry="{13 * open_:.1f}" fill="#140c12"/>
  <circle cx="{cx - 7}" cy="{cy - 11}" r="5.5" fill="#fff" opacity=".95"/>
  <circle cx="{cx + 7}" cy="{cy + 8}" r="3" fill="#fff" opacity=".6"/>
  <path d="M{outer - 4} {cy - 2} Q{cx} {cy - h - 18} {inner + 4} {cy - 7}" fill="none" stroke="{lash}" stroke-width="6" stroke-linecap="round"/>
  <path d="M{outer - 2} {cy - 1} Q{outer + flick} {cy - 18} {outer + flick - 4} {cy - 26}" fill="none" stroke="{lash}" stroke-width="4" stroke-linecap="round"/>
  <path d="M{outer + 10} {cy - 18} L{outer + 2} {cy - 30} M{outer + 20} {cy - 22} L{outer + 14} {cy - 34}" fill="none" stroke="{lash}" stroke-width="3" stroke-linecap="round"/>
  <path d="M{outer + 4} {cy + 3} Q{cx} {cy + h + 10} {inner - 2} {cy + 2}" fill="none" stroke="{lash}" stroke-opacity=".3" stroke-width="2" stroke-linecap="round"/>
  <path d="M{outer + 6} {cy - 38 + tilt} Q{cx} {cy - 50 + tilt} {inner - 2} {cy - 36 - tilt}" fill="none" stroke="{lash}" stroke-width="5" stroke-linecap="round"/>"""


def mouth_svg(c: dict) -> str:
    if c["mouth"] == "grin":
        return """
  <path d="M268 492 Q300 522 332 492 Q300 506 268 492 Z" fill="#8e3145"/>
  <path d="M272 493 Q300 512 328 493" fill="none" stroke="#5f2130" stroke-width="2"/>
  <path d="M300 500 V508" stroke="#8e3145" stroke-width="2" opacity=".5"/>"""
    if c["mouth"] == "smirk":
        return """
  <path d="M270 494 Q304 510 334 488" fill="none" stroke="#7a2c3d" stroke-width="4" stroke-linecap="round"/>
  <path d="M276 496 Q300 503 320 495" fill="none" stroke="#d98a98" stroke-opacity=".55" stroke-width="2"/>"""
    if c["mouth"] == "dry":
        return """
  <path d="M272 494 Q300 500 328 490" fill="none" stroke="#5f2130" stroke-width="3.5" stroke-linecap="round"/>"""
    return """
  <path d="M272 492 Q300 510 328 492" fill="none" stroke="#8e3145" stroke-width="4" stroke-linecap="round"/>
  <path d="M280 496 Q300 503 320 496" fill="none" stroke="#d98a98" stroke-opacity=".6" stroke-width="2"/>"""


def outfit_svg(c: dict) -> str:
    if c["outfit"] == "cardigan":
        return f"""
  <path d="M92 900 C104 704 190 636 300 614 C410 636 496 704 508 900 Z" fill="url(#cloth)"/>
  <path d="M300 614 C262 646 244 704 242 900 L358 900 C356 704 338 646 300 614 Z" fill="{c['inner']}"/>
  <path d="M300 614 C270 640 258 690 258 760 L300 780 L342 760 C342 690 330 640 300 614 Z" fill="#f8efe4"/>
  <path d="M258 620 C240 660 232 720 232 800" fill="none" stroke="#c9ae8a" stroke-width="3" opacity=".5"/>
  <path d="M342 620 C360 660 368 720 368 800" fill="none" stroke="#c9ae8a" stroke-width="3" opacity=".5"/>
  <circle cx="300" cy="790" r="4" fill="#c9ae8a" opacity=".7"/>
  <circle cx="300" cy="830" r="4" fill="#c9ae8a" opacity=".7"/>"""
    if c["outfit"] == "blazer":
        return f"""
  <path d="M86 900 C100 700 188 630 300 608 C412 630 500 700 514 900 Z" fill="url(#cloth)"/>
  <path d="M300 608 C272 640 262 700 262 900 L338 900 C338 700 328 640 300 608 Z" fill="{c['inner']}"/>
  <path d="M300 612 L238 700 L282 760 L300 730 Z" fill="#211f27"/>
  <path d="M300 612 L362 700 L318 760 L300 730 Z" fill="#211f27"/>
  <path d="M300 612 L282 760 L300 900 L318 760 Z" fill="#f6f1ea"/>
  <path d="M332 786 L348 792" stroke="#a99bd6" stroke-width="4" stroke-linecap="round"/>"""
    if c["outfit"] == "turtleneck":
        return f"""
  <path d="M82 900 C98 696 188 626 300 604 C412 626 502 696 518 900 Z" fill="url(#cloth)"/>
  <path d="M300 604 C246 604 224 650 224 690 L376 690 C376 650 354 604 300 604 Z" fill="{c['inner']}"/>
  <path d="M300 604 C258 616 238 650 232 700 C262 722 338 722 368 700 C362 650 342 616 300 604 Z" fill="#241f29"/>
  <path d="M300 720 C270 738 246 776 240 830" fill="none" stroke="#d9a441" stroke-opacity=".35" stroke-width="2"/>
  <path d="M300 720 C330 738 354 776 360 830" fill="none" stroke="#d9a441" stroke-opacity=".35" stroke-width="2"/>
  <path d="M300 606 C286 640 286 700 300 730 C314 700 314 640 300 606 Z" fill="{c['inner']}" opacity=".9"/>"""
    return f"""
  <path d="M88 900 C102 700 190 632 300 610 C410 632 498 700 512 900 Z" fill="url(#cloth)"/>
  <path d="M300 610 C262 644 250 704 250 900 L350 900 C350 704 338 644 300 610 Z" fill="{c['inner']}"/>
  <path d="M246 616 L214 900 L266 900 L278 660 Z" fill="#f7f0e2"/>
  <path d="M354 616 L386 900 L334 900 L322 660 Z" fill="#f7f0e2"/>
  <path d="M300 660 V900" stroke="#b57c22" stroke-width="2" opacity=".25"/>
  <rect x="268" y="780" width="64" height="44" rx="6" fill="#f7f0e2" opacity=".55"/>"""


def accessory_svg(c: dict) -> str:
    if c["accessory"] == "glasses_gold":
        return """
  <g fill="none" stroke="#d9a441" stroke-width="3" opacity=".9">
    <circle cx="245" cy="415" r="38"/><circle cx="355" cy="415" r="38"/>
    <path d="M283 415 Q300 405 317 415"/>
    <path d="M207 408 L184 398 M393 408 L416 398"/>
  </g>"""
    if c["accessory"] == "earrings_silver":
        return """
  <g fill="#e7e2f4" opacity=".9">
    <circle cx="166" cy="470" r="6"/><circle cx="434" cy="470" r="6"/>
  </g>"""
    if c["accessory"] == "freckles":
        return """
  <g fill="#b06a4a" opacity=".55">
    <circle cx="205" cy="462" r="3"/><circle cx="220" cy="470" r="2.4"/><circle cx="235" cy="460" r="2.8"/>
    <circle cx="395" cy="462" r="3"/><circle cx="380" cy="470" r="2.4"/><circle cx="365" cy="460" r="2.8"/>
  </g>"""
    return ""


def portrait(c: dict, avatar: bool = False) -> str:
    viewbox = "100 180 400 400" if avatar else "0 0 600 900"
    hair_back, hair_front = hair_svg(c)
    width = height = 600 if avatar else 600
    height = 600 if avatar else 900
    bg1, bg2 = {
        "bookshop": ("#2a1722", "#4a2a33"),
        "studio": ("#181527", "#302a44"),
        "office": ("#141217", "#2a222c"),
        "truck": ("#251a2e", "#4a2a33"),
    }[c["scene"]]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" width="{width}" height="{height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/>
    </linearGradient>
    <linearGradient id="skin" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{c['skin'][0]}"/><stop offset="1" stop-color="{c['skin'][1]}"/>
    </linearGradient>
    <linearGradient id="hair" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0" stop-color="{c['hair'][0]}"/><stop offset="1" stop-color="{c['hair'][1]}"/>
    </linearGradient>
    <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{c['cloth'][0]}"/><stop offset="1" stop-color="{c['cloth'][1]}"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="38%" r="55%">
      <stop offset="0" stop-color="{c['accent']}" stop-opacity=".45"/>
      <stop offset="1" stop-color="{c['accent']}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="iris" cx="50%" cy="32%" r="68%">
      <stop offset="0" stop-color="{c['eye']}"/><stop offset=".72" stop-color="{c['eye']}"/><stop offset="1" stop-color="#1b1016"/>
    </radialGradient>
    <radialGradient id="vignette" cx="50%" cy="45%" r="72%">
      <stop offset=".55" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity=".55"/>
    </radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="24"/></filter>
  </defs>
  <rect width="600" height="900" fill="url(#bg)"/>
  {scene_svg(c)}
  <circle cx="300" cy="340" r="250" fill="url(#glow)" filter="url(#blur)"/>
  <ellipse cx="300" cy="872" rx="230" ry="30" fill="#000" opacity=".35"/>
  {hair_back}
  <path d="M262 518 L262 612 Q300 634 338 612 L338 518 Z" fill="url(#skin)"/>
  <path d="M262 540 Q300 570 338 540 L338 612 Q300 634 262 612 Z" fill="#000" opacity=".09"/>
  <path d="M258 628 Q300 650 342 628" fill="none" stroke="#000" stroke-opacity=".12" stroke-width="3" stroke-linecap="round"/>
  <ellipse cx="174" cy="420" rx="22" ry="34" fill="url(#skin)"/>
  <ellipse cx="426" cy="420" rx="22" ry="34" fill="url(#skin)"/>
  <path d="M300 248 C374 248 418 306 418 396 C418 472 374 548 300 572 C226 548 182 472 182 396 C182 306 226 248 300 248 Z" fill="url(#skin)"/>
  <path d="M300 248 C374 248 418 306 418 396 C418 472 374 548 300 572 C226 548 182 472 182 396 C182 306 226 248 300 248 Z" fill="#fff" opacity=".05"/>
  <path d="M212 300 C196 366 198 448 220 516" fill="none" stroke="#fff" stroke-opacity=".08" stroke-width="12"/>
  {hair_front}
  <path d="M196 330 C184 410 190 500 208 556" fill="none" stroke="url(#hair)" stroke-width="15" stroke-linecap="round" opacity=".9"/>
  <path d="M404 330 C416 410 410 500 392 556" fill="none" stroke="url(#hair)" stroke-width="15" stroke-linecap="round" opacity=".9"/>
  {eye_svg(c, 240, -1)}
  {eye_svg(c, 360, 1)}
  <path d="M299 455 Q304 463 297 466" fill="none" stroke="#9c5f51" stroke-width="2.2" stroke-linecap="round" opacity=".55"/>
  {mouth_svg(c)}
  <ellipse cx="214" cy="468" rx="24" ry="10" fill="#e8798d" opacity="{c['blush']}"/>
  <ellipse cx="386" cy="468" rx="24" ry="10" fill="#e8798d" opacity="{c['blush']}"/>
  {accessory_svg(c)}
  {outfit_svg(c)}
  <rect width="600" height="900" fill="url(#vignette)"/>
  <rect x="0" y="0" width="600" height="6" fill="{c['accent']}" opacity=".55"/>
</svg>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for cid, c in CHARACTERS.items():
        (OUT / f"{cid}.svg").write_text(portrait(c))
        (OUT / f"{cid}-avatar.svg").write_text(portrait(c, avatar=True))
        print("wrote", OUT / f"{cid}.svg")


if __name__ == "__main__":
    main()
