#!/usr/bin/env python3
"""Render the demo manifest, store web assets, and delete each studio output.

Reads world/demo-assets.json (prompt, size, seed, static_url), submits one render at a
time, writes the PNG and a web JPEG where declared, then calls
DELETE /api/v1/library/image/<name> and verifies the file is gone from the studio list.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("castart", ROOT / "scripts" / "generate-cast-art.py")
castart = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(castart)

STUDIO = castart.STUDIO
MANIFEST = ROOT / "world" / "demo-assets.json"


def delete_studio(url: str) -> str:
    name = Path(urllib.parse.urlparse(url).path).name
    if not name:
        return "no-url"
    endpoint = f"{STUDIO}/api/v1/library/image/{urllib.parse.quote(name)}"
    request = urllib.request.Request(endpoint, method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except Exception as exc:
        return f"delete failed: {exc}"
    try:
        library = castart._req(f"{STUDIO}/api/v1/library/image")
        names = {item.get("file") for item in library} if isinstance(library, list) else set()
    except Exception as exc:
        return f"verify failed: {exc}"
    return "deleted" if name not in names else "STILL PRESENT"


def render(item: dict) -> None:
    static_url = item["static_url"]
    rel = static_url.removeprefix("/static/assets/")
    png = ROOT / "web" / "assets" / (rel[:-4] + ".png")
    jpg = ROOT / "web" / "assets" / rel if rel.endswith(".jpg") else None
    png.parent.mkdir(parents=True, exist_ok=True)
    print(f"{item['id']}:")
    result = castart.generate(item["prompt"], item["size"], int(item["seed"]), studio=STUDIO)
    castart._download(f"{STUDIO}{result['url']}", png)
    if jpg:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(png),
                "-vf", "crop=iw:ih-66:0:0,scale=832:1150:flags=lanczos",
                "-q:v", "3", str(jpg),
            ],
            check=True,
        )
        print(f"  -> {jpg.relative_to(ROOT)} ({jpg.stat().st_size // 1024} KB)")
    else:
        print(f"  -> {png.relative_to(ROOT)} ({png.stat().st_size // 1024} KB)")
    print(f"  studio: {delete_studio(result['url'])}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    items = json.loads(MANIFEST.read_text())["items"]
    wanted = {part.strip() for part in args.ids.split(",") if part.strip()}
    for item in items:
        if not args.all and wanted and item["id"] not in wanted:
            continue
        if not args.all and not wanted and item.get("priority") != "P0":
            continue
        rel = item["static_url"].removeprefix("/static/assets/")
        target = ROOT / "web" / "assets" / (rel if rel.endswith(".jpg") else rel)
        if target.exists() and not args.force:
            print(f"{item['id']}: exists, skipping (use --force)")
            continue
        render(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
