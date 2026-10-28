"""Render assets/og.png (1200x630 social card) from scripts/og.html with Playwright.

Run with a Python that has playwright installed:  python scripts/og.py
The wordmark SVG and the tool count are filled in from assets/brand/wordmark.svg and data/repos.json.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
         "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def main():
    n = len(json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))["repos"])
    count = (WORDS[n] if n < len(WORDS) else str(n)).capitalize()
    svg = (ROOT / "assets" / "brand" / "wordmark.svg").read_text(encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page.goto((ROOT / "scripts" / "og.html").as_uri())
        page.evaluate("([svg, text]) => { document.getElementById('wm').innerHTML = svg;"
                      " document.getElementById('count').textContent = text; }",
                      [svg, f"{count} open-source CLI tools and Claude skills"])
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(200)
        page.locator(".card").screenshot(path=str(ROOT / "assets" / "og.png"))
        b.close()
    print("wrote assets/og.png")


if __name__ == "__main__":
    main()
