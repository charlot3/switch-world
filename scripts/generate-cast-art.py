#!/usr/bin/env python3
"""Generate the cast art set from one shared visual-novel template.

The four characters used to be generated one prompt at a time, which gave four
different cameras, light temperatures and crops. This script fixes the *set*:

  * one shared composition/lighting scaffold, with only the character block and
    the background hint changing;
  * one sampler seed per shot type, so the camera and head size stay aligned;
  * a bust (832x1216) for cards/scene and a full-body (768x1344) for the
    character sheet, plus a 512x512 avatar crop from the bust.

It talks to the local rin-studio API (proxy-studio) and downloads the result
into web/assets/portraits/. The prompts are written to PROMPTS.md next to the
images, so a judge can reproduce the exact set.

Usage:
    python3 scripts/generate-cast-art.py --kind bust
    python3 scripts/generate-cast-art.py --kind both --force
    python3 scripts/generate-cast-art.py --only alice,emily --kind full
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "assets" / "portraits"
STUDIO = "http://127.0.0.1:8899"

# The shared half of every prompt. Keep this stable: it is what makes the four
# images read as one set rather than four separate commissions.
BUST_SCAFFOLD = (
    "visual novel character key visual, character sheet, solo, waist-up portrait, "
    "centered composition, eye level, looking at viewer, head in the upper third, "
    "same camera distance, same head size, soft warm late-afternoon key light, "
    "muted plum and gold palette, soft cel shading, clean lineart, detailed eyes, "
    "{character}, {background} softly blurred bokeh, "
    "no text, no watermark, adult woman, fully clothed, modest clothing, tasteful"
)

FULL_SCAFFOLD = (
    "visual novel character sheet, solo, full body, standing, front view, head to toe, "
    "entire figure including shoes, small figure centered with space above the head and "
    "below the feet, neutral relaxed pose, arms at sides, feet visible, same camera distance, "
    "soft warm late-afternoon key light, muted plum and gold palette, soft cel shading, "
    "clean lineart, detailed eyes, {character}, plain muted plum studio backdrop with "
    "soft vignette, no text, no watermark, adult woman, fully clothed, modest clothing, tasteful"
)

# One seed per shot type. The prompt does the character differentiation; the
# seed holds the camera, crop and lighting constant across the four.
SEED_BUST = 424242
SEED_FULL = 515151

CHARACTERS = {
    "alice": {
        "character": (
            "a woman in her early thirties with chestnut brown hair in a loose bun, "
            "warm amber eyes, round gold glasses, a soft knowing smile, ink-stained fingers, "
            "cream knit cardigan over a burgundy blouse, tailored beige trousers, "
            "black leather ankle boots"
        ),
        "background": "warm second-hand bookshop interior, shelves and an autumn window",
    },
    "emily": {
        "character": (
            "a woman in her late twenties with a sharp black bob and blunt bangs, "
            "dark brown eyes, silver drop earrings, a small scar through one eyebrow, "
            "a composed expression, charcoal blazer over a white silk blouse, black trousers, "
            "black leather loafers"
        ),
        "background": "muted design studio with pinned prints and a tall window",
    },
    "sophia": {
        "character": (
            "a woman in her early thirties with warm brown skin, dark curls in a low bun, "
            "amber eyes, thin gold glasses, a calm half-smile, black turtleneck, "
            "a thin gold necklace, a long charcoal coat, black ankle boots"
        ),
        "background": "university office with books and a warm brass lamp",
    },
    "mia": {
        "character": (
            "a woman in her mid-twenties with auburn hair in a messy ponytail, green eyes, "
            "freckles, a burn scar on one wrist, a bright grin, "
            "mustard yellow sweater under a white canvas apron, dark jeans, "
            "black canvas sneakers"
        ),
        "background": "food truck with warm string lights at golden hour",
    },
}


def _req(url: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as fh:
        while chunk := response.read(1 << 20):
            fh.write(chunk)
    tmp.replace(dest)


def generate(prompt: str, size: str, seed: int, studio: str = STUDIO) -> dict:
    job = _req(
        f"{studio}/api/v1/image?wait=0",
        {"prompt": prompt, "style": "anime", "size": size, "seed": seed},
        method="POST",
    )
    job_id = job.get("id") or job.get("job_id")
    if not job_id:
        raise RuntimeError(f"no job id in {job}")
    print(f"  queued {job_id} ({size}, seed {seed})", flush=True)

    last = None
    while True:
        info = _req(f"{studio}/api/v1/jobs/{job_id}")
        status = str(info.get("status") or info.get("state") or "").lower()
        position = info.get("queue_position")
        label = status + (f" · {position}" if position is not None else "")
        if label != last:
            print(f"  {label}", flush=True)
            last = label
        if status in {"done", "completed", "succeeded", "finished", "success"}:
            result = info.get("result") or info
            if not result.get("url"):
                raise RuntimeError(f"job {job_id} finished without a url: {info}")
            return result
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise RuntimeError(f"job {job_id} {status}: {info.get('error') or info}")
        time.sleep(4)


def avatar(bust: Path) -> Path:
    """Crop the head/shoulders from the bust, centred on the composition."""
    dest = bust.with_name(bust.stem.replace("-bust", "-avatar") + ".png")
    # 832x1216 → 640x640 at x=96, y=88 → 512x512.
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(bust),
            "-vf", "crop=640:640:96:88,scale=512:512:flags=lanczos",
            str(dest),
        ],
        check=True,
    )
    return dest


def contact(paths: list[Path], dest: Path) -> None:
    if len(paths) < 2:
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for path in paths:
        cmd += ["-i", str(path)]
    cmd += [
        "-filter_complex",
        "".join(f"[{i}:v]" for i in range(len(paths))) + f"hstack=inputs={len(paths)}",
        str(dest),
    ]
    subprocess.run(cmd, check=True)


def write_prompts(entries: list[dict]) -> None:
    lines = [
        "# Cast art prompts",
        "",
        "Generated by `scripts/generate-cast-art.py` against the local rin-studio / ComfyUI.",
        "The shared scaffold is the contract: only the character block and background hint",
        "change between the four. The seed is fixed per shot type.",
        "",
    ]
    for entry in entries:
        lines += [
            f"## {entry['id']} · {entry['kind']}",
            "",
            f"- size: `{entry['size']}`",
            f"- seed: `{entry['seed']}`",
            f"- file: `{entry['file']}`",
            "",
            "```text",
            entry["prompt"],
            "```",
            "",
        ]
    (OUT / "PROMPTS.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["bust", "full", "both"], default="both")
    parser.add_argument("--only", default=",".join(CHARACTERS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--studio", default=STUDIO)
    parser.add_argument("--prompts-only", action="store_true",
                        help="write PROMPTS.md for the selected set without rendering")
    args = parser.parse_args()

    studio = args.studio
    OUT.mkdir(parents=True, exist_ok=True)
    ids = [part.strip() for part in args.only.split(",") if part.strip()]
    unknown = [part for part in ids if part not in CHARACTERS]
    if unknown:
        parser.error(f"unknown character(s): {', '.join(unknown)}")

    kinds = ["bust", "full"] if args.kind == "both" else [args.kind]
    entries: list[dict] = []
    made: dict[str, list[Path]] = {"bust": [], "full": []}

    for kind in kinds:
        for cid in ids:
            config = CHARACTERS[cid]
            prompt = (BUST_SCAFFOLD if kind == "bust" else FULL_SCAFFOLD).format(**config)
            size = "portrait" if kind == "bust" else "tall"
            seed = SEED_BUST if kind == "bust" else SEED_FULL
            dest = OUT / f"{cid}-{kind}.png"
            entries.append(
                {"id": cid, "kind": kind, "size": size, "seed": seed,
                 "file": dest.name, "prompt": prompt}
            )

    write_prompts(entries)
    if args.prompts_only:
        print(f"wrote {OUT / 'PROMPTS.md'}")
        return 0

    for entry in entries:
        kind, cid, prompt, size, seed = (
            entry["kind"], entry["id"], entry["prompt"], entry["size"], entry["seed"]
        )
        dest = OUT / entry["file"]
        if dest.exists() and not args.force:
            print(f"{cid} {kind}: exists, skipping (use --force)")
            made[kind].append(dest)
            continue
        print(f"{cid} {kind}:")
        result = generate(prompt, size, seed, studio=studio)
        _download(f"{studio}{result['url']}", dest)
        print(f"  -> {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")
        made[kind].append(dest)
        if kind == "bust":
            crop = avatar(dest)
            print(f"  -> {crop.relative_to(ROOT)}")

    for kind, paths in made.items():
        if len(paths) == len(ids) and paths:
            contact(paths, OUT / f"contact-{kind}.png")
            print(f"contact sheet -> web/assets/portraits/contact-{kind}.png")
    print("done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
