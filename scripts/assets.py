"""Prepare the static brand assets the page uses. Run once, or after the brand files change.

    python scripts/assets.py [--brand-dir <path to amagilabs_logo>]

Writes:
  assets/fonts/*.woff2      Montserrat (text) and Playfair Display (display), Latin subset, trimmed weight axis
  assets/brand/*            icon PNG/WebP, wordmark SVG paths (inlined by build.py)
  favicon.svg / favicon.ico / apple-touch-icon.png
  assets/media/hero.mp4     the looping terminal clip in the hero, cut from one repo's demo.gif
  assets/media/hero.webp    its poster frame

Needs fontTools + brotli + Pillow, and ffmpeg for the clip. The demo GIFs come from build.py's fetch
step (assets/shots/_gif/), so run that first.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRAND = ROOT.parent.parent.parent / "amagilabs_logo"
LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,"
         "U+2074,U+20AC,U+2122,U+2190-2193,U+2212,U+2215,U+FEFF,U+FFFD")
CREAM = (246, 244, 241)
HERO_CLIP_FROM = "amagi-receipts-to-csv"


def fonts(brand: Path) -> None:
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    from fontTools import subset

    out = ROOT / "assets" / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for src, name, lo, hi in [("M.ttf", "montserrat", 400, 700),
                              ("P.ttf", "playfair-display", 600, 900)]:
        font = TTFont(brand / "work" / "fonts" / src)
        # Subset before trimming the axis: fontTools' gvar subsetting trips over the instanced font.
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga", "calt", "lnum", "tnum", "case"]
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=subset.parse_unicodes(LATIN))
        sub.subset(font)
        font = instancer.instantiateVariableFont(font, {"wght": (lo, hi)})
        dest = out / f"{name}-latin.woff2"
        font.flavor = "woff2"
        font.save(dest)
        print(f"  {dest.relative_to(ROOT)}  {dest.stat().st_size // 1024} KB  wght {lo}-{hi}")


def brand_files(brand: Path) -> None:
    final = brand / "final"
    out = ROOT / "assets" / "brand"
    out.mkdir(parents=True, exist_ok=True)

    with Image.open(final / "amagilabs-icon-transparent-1024.png") as im:
        im = im.convert("RGBA")
        for size in (96, 192):
            im.resize((size, size), Image.LANCZOS).save(out / f"amagilabs-icon-{size}.png", optimize=True)
        # favicon.ico: small sizes from the transparent mark
        im.save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    with Image.open(final / "amagilabs-icon-1024.png") as im:
        im = im.convert("RGB")
        im.resize((512, 512), Image.LANCZOS).save(out / "amagilabs-icon-512.png", optimize=True)
        im.resize((480, 480), Image.LANCZOS).save(out / "amagilabs-icon-480.webp", quality=88, method=6)
        im.resize((180, 180), Image.LANCZOS).save(ROOT / "apple-touch-icon.png", optimize=True)
    shutil.copyfile(final / "amagilabs-icon-transparent.svg", ROOT / "favicon.svg")

    # Wordmark: the lockup's "AMAGI", rule and "LABS", lifted out of the full lockup so the page can
    # colour it with currentColor (the header ink changes per section).
    svg = (final / "amagilabs-lockup.svg").read_text(encoding="utf-8")
    tail = svg[svg.rindex("</g>") + 4: svg.rindex("</svg>")]
    parts = re.findall(r"<(?:path|rect)[^>]*/>", tail)
    if len(parts) != 3:
        raise SystemExit(f"wordmark: expected 3 shapes after the icon group, found {len(parts)}")
    amagi, rule, labs = parts
    amagi = amagi.replace('fill="#161616"', 'fill="currentColor"')
    labs = labs.replace('fill="#161616"', 'fill="currentColor"')
    rule = rule.replace('fill="#D27A73"', 'fill="currentColor"')
    # The wordmark's box in lockup units: it starts where "AMAGI" starts (the first move-to of its
    # path) and runs to the lockup's own right and bottom edges.
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    x0 = float(re.search(r'd="M\s*(-?[\d.]+)', amagi).group(1)) - 6
    y0 = min(float(v) for v in re.findall(r"[ ,HL](\d+\.?\d*)", amagi[:400])) - 6
    x1, y1 = vb[0] + vb[2], vb[1] + vb[3]
    (out / "wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}">'
        f'{amagi}{rule}{labs}</svg>\n', encoding="utf-8")
    print(f"  assets/brand/ + favicons  (wordmark box {x1 - x0:.0f}x{y1 - y0:.0f})")


def hero_clip() -> None:
    gif = ROOT / "assets" / "shots" / "_gif" / f"{HERO_CLIP_FROM}.gif"
    if not gif.exists():
        raise SystemExit(f"{gif} missing: run scripts/build.py first")
    out = ROOT / "assets" / "media"
    out.mkdir(parents=True, exist_ok=True)
    # A 5:2 window on the terminal's upper left, where the command and the rows it prints appear.
    crop = "crop=iw*0.62:iw*0.62*0.4:0:0"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(gif), "-vf",
                    f"{crop},scale=640:-2:flags=lanczos,fps=12,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-an",
                    "-movflags", "+faststart", str(out / "hero.mp4")], check=True)
    with Image.open(gif) as im:
        im.seek(im.n_frames - 1)
        f = im.convert("RGB")
    w = int(f.width * 0.62)
    f = f.crop((0, 0, w, int(w * 0.4))).resize((640, 256), Image.LANCZOS)
    f.save(out / "hero.webp", quality=80, method=6)
    print(f"  assets/media/hero.mp4 {(out / 'hero.mp4').stat().st_size // 1024} KB, poster hero.webp")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-dir", type=Path, default=DEFAULT_BRAND)
    a = ap.parse_args()
    fonts(a.brand_dir)
    brand_files(a.brand_dir)
    hero_clip()


if __name__ == "__main__":
    main()
