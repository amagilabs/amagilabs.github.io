"""Verify the built site in a real browser before publishing.

Serves the repo root on a local port (inside this process), then with Playwright:
  - screenshots desktop 1440, mobile 390 and dark mode into ../_screens/
  - fails on console errors, page errors and failed local requests
  - checks the live parts: type-to-find, the example buttons, copy, the header colour by chapter
  - checks every link: in-page anchors exist, local files return 200, external URLs answer < 400
  - basic accessibility and weight checks (one h1, alt text, labels, lang, page weight)

Run with a Python that has playwright:  python scripts/verify.py [--no-external]
Exit code 0 when every check passes.
"""
import functools
import http.server
import json
import socketserver
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT.parent / "_screens"
SITE = "https://amagilabs.github.io/"
UA = "Mozilla/5.0 (amagilabs.github.io link check)"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = functools.partial(Quiet, directory=str(ROOT))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def check_url(url):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if method == "GET" or e.code not in (403, 405, 429):
                return e.code
        except Exception as e:  # noqa: BLE001
            if method == "GET":
                return f"error: {e.__class__.__name__}"
    return "error"


def settle(page):
    """Scroll the whole page so every entrance runs, then return to the top."""
    h = page.evaluate("document.documentElement.scrollHeight")
    vh = page.viewport_size["height"]
    y = 0
    while y < h:
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(120)
        y += vh // 2
    page.wait_for_timeout(600)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)


def main():
    external = "--no-external" not in sys.argv
    SHOTS.mkdir(parents=True, exist_ok=True)
    httpd, base = serve()
    problems, notes, shots = [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        runs = [
            ("desktop", {"width": 1440, "height": 900}, "light", False),
            ("mobile", {"width": 390, "height": 844}, "light", True),
            ("desktop-dark", {"width": 1440, "height": 900}, "dark", False),
            ("mobile-dark", {"width": 390, "height": 844}, "dark", True),
        ]
        for name, vp, scheme, mobile in runs:
            ctx = browser.new_context(viewport=vp, color_scheme=scheme, is_mobile=mobile, has_touch=mobile,
                                      device_scale_factor=2 if mobile else 1)
            page = ctx.new_page()
            errors, failed = [], []
            page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda ex, e=errors: e.append(str(ex)))
            page.on("requestfailed", lambda r, f=failed: f.append(r.url) if r.url.startswith(base) else None)
            page.on("response", lambda r, f=failed: f.append(f"{r.status} {r.url}")
                    if r.url.startswith(base) and r.status >= 400 else None)
            page.goto(base, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            fold = SHOTS / f"{name}-fold.png"
            page.wait_for_timeout(900)
            page.screenshot(path=str(fold))
            settle(page)
            full = SHOTS / f"{name}-full.png"
            # a full-page capture repeats fixed elements mid-page; pin the header to the top for this picture only
            page.add_style_tag(content=".bar { position: absolute !important; } .skip { display: none; }")
            page.screenshot(path=str(full), full_page=True)
            shots += [fold, full]
            if errors:
                problems.append(f"{name}: console/page errors: {errors}")
            if failed:
                problems.append(f"{name}: failed local requests: {failed}")
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if overflow > 0:
                problems.append(f"{name}: page scrolls sideways by {overflow}px")
            ctx.close()

        # ---- interactions and structure (desktop, light)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base.rstrip("/"))
        page = ctx.new_page()
        page.goto(base, wait_until="networkidle")
        s = page.evaluate("""() => ({
            h1: document.querySelectorAll('h1').length,
            lang: document.documentElement.lang,
            imgsNoAlt: [...document.images].filter(i => !i.hasAttribute('alt')).map(i => i.src),
            unlabelled: [...document.querySelectorAll('input, button')].filter(el => {
                const id = el.id && document.querySelector(`label[for="${el.id}"]`);
                return !(id || el.getAttribute('aria-label') || el.textContent.trim());
            }).length,
            rows: document.querySelectorAll('.tools .row').length,
            repoData: JSON.parse(document.getElementById('repo-data').textContent).length,
            title: document.title, desc: document.querySelector('meta[name=description]').content,
        })""")
        if s["h1"] != 1:
            problems.append(f"expected one h1, found {s['h1']}")
        if s["lang"] != "en":
            problems.append("html lang missing")
        if s["imgsNoAlt"]:
            problems.append(f"images without alt: {s['imgsNoAlt']}")
        if s["unlabelled"]:
            problems.append(f"{s['unlabelled']} unlabelled controls")
        if s["rows"] != s["repoData"]:
            problems.append(f"list shows {s['rows']} rows but data has {s['repoData']} repos")
        notes.append(f"{s['rows']} repo rows; title {len(s['title'])} chars; description {len(s['desc'])} chars")

        # type-to-find
        page.fill("#find-q", "receipts to csv")
        page.wait_for_timeout(400)
        first = page.locator("#find-out .hit .row-name a").first.get_attribute("href")
        if not first or not first.endswith("amagi-receipts-to-csv"):
            problems.append(f"find 'receipts to csv' led with {first}")
        page.fill("#find-q", "zzqx")
        page.wait_for_timeout(400)
        if page.locator("#find-out .find-none").count() != 1:
            problems.append("find: no-match state missing")
        page.locator(".find-try button").nth(1).click()
        page.wait_for_timeout(300)
        if page.locator(".find-try button").nth(1).get_attribute("aria-pressed") != "true":
            problems.append("find: example button not pressed")
        hits = page.locator("#find-out .hit .row-name a").evaluate_all("as => as.map(a => a.href.split('/').pop())")
        notes.append(f"find 'a video for Claude' -> {hits}")

        # copy
        btn = page.locator(".tools .row button.copy").first
        want = btn.get_attribute("data-copy")
        btn.click()
        page.wait_for_timeout(200)
        got = page.evaluate("navigator.clipboard.readText()")
        if got != want or btn.text_content().strip() != "Copied":
            problems.append(f"copy: clipboard {got!r} vs {want!r}, label {btn.text_content()!r}")

        # header colour by chapter
        inks = []
        for sel in (".hero", "#tools", "#find", "#about", ".foot"):
            page.evaluate(f"window.scrollTo({{top: document.querySelector('{sel}').getBoundingClientRect().top"
                          f" + scrollY + 40, behavior: 'instant'}})")
            page.wait_for_timeout(350)
            inks.append(page.get_attribute(".bar", "data-ink"))
        notes.append(f"header ink by section: {inks}")
        # the footer is shorter than a screen, so at the bottom the bar may still sit over the about section
        if inks[:4] != ["paper", "paper", "ink", "sand"] or inks[4] not in ("sand", "clay"):
            problems.append(f"header ink sequence unexpected: {inks}")

        # links
        hrefs = page.evaluate("[...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))")
        srcs = page.evaluate("""[...document.querySelectorAll('[src], link[href]')]
            .map(e => e.getAttribute('src') || e.getAttribute('href'))""")
        weight = page.evaluate("""performance.getEntriesByType('resource')
            .reduce((n, r) => n + (r.transferSize || r.encodedBodySize || 0), 0)""")
        notes.append(f"first-load transfer about {round(weight / 1024)} KB (local, uncompressed)")
        ctx.close()
        browser.close()

    seen, bad, ext = set(), [], []
    for h in hrefs + srcs:
        if not h or h in seen or h.startswith("mailto:"):
            continue
        seen.add(h)
        if h.startswith("#"):
            continue  # checked below
        url = urljoin(base, h.replace(SITE, "/", 1) if h.startswith(SITE) else h)  # own domain: not live yet
        if url.startswith(base):
            st = check_url(url)
            if st != 200:
                bad.append(f"{st} {h}")
        elif urlparse(url).scheme in ("http", "https"):
            ext.append(url)
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for h in {x for x in hrefs if x.startswith("#") and len(x) > 1}:
        if f'id="{h[1:]}"' not in html:
            bad.append(f"missing anchor {h}")
    if external:
        for url in sorted(set(ext)):
            st = check_url(url)
            if not (isinstance(st, int) and st < 400):
                bad.append(f"{st} {url}")
        notes.append(f"{len(set(ext))} external links checked")
    if bad:
        problems.append(f"links: {bad}")
    httpd.shutdown()

    for p_ in shots:
        print("screenshot", p_)
    for n in notes:
        print("note", n)
    for pr in problems:
        print("PROBLEM", pr)
    print("RESULT", "PASS" if not problems else f"{len(problems)} problem(s)")
    (SHOTS / "verify.json").write_text(json.dumps({"problems": problems, "notes": notes,
                                                   "shots": [str(x) for x in shots]}, indent=2),
                                       encoding="utf-8", newline="\n")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
