"""Regenerate the AmagiLabs site from the live GitHub org.

    python scripts/build.py            # fetch repos from GitHub, refresh media, render the site
    python scripts/build.py --offline  # render from the cached data/repos.json only

Fetch step: lists public, non-fork, non-archived repos in github.com/amagilabs (gh CLI if it is
logged in, else the public REST API; set GH_TOKEN/GITHUB_TOKEN for higher limits), reads each
README, checks PyPI for the package name, and pulls a still frame of each repo's assets/demo.gif
(needs ffmpeg; skipped if missing). Writes data/repos.json.

Render step: fills src/index.html into ./index.html, and writes sitemap.xml. Nothing on GitHub's
side builds anything; commit the output.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ORG = "amagilabs"
SITE = "https://amagilabs.github.io"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "repos.json"
SHOTS = ROOT / "assets" / "shots"
SKIP = {f"{ORG}.github.io", ".github"}

# Group order on the page. A repo lands in the first group whose names list it; anything new
# falls through to "More tools" until someone adds it here.
GROUPS = [
    ("legal", "Law firm work", ["amagi-legal-review-skills", "amagi-contract-deadlines",
                                "amagi-litigation-deadlines", "amagi-federal-compliance-matrix"]),
    ("office", "Back office", ["amagi-crm", "amagi-receipts-to-csv"]),
    ("media", "Video, audio and notes for Claude", ["amagi-watch", "amagi-listen", "amagi-screen",
                                                    "amagi-vaultgraph"]),
    ("dev", "Checks before you ship", ["amagi-staleref", "amagi-skill-lint", "amagi-mcp-probe",
                                       "amagi-env-check", "amagi-site-diff", "amagi-name-check"]),
]
OTHER = ("more", "More tools")


# ---------------------------------------------------------------- fetch

def _gh_ok() -> bool:
    if not shutil.which("gh"):
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


USE_GH = None


def api(path: str, raw: bool = False):
    """GET https://api.github.com/<path>. Returns parsed JSON, or text when raw=True; None on 404."""
    global USE_GH
    if USE_GH is None:
        USE_GH = _gh_ok()
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    if USE_GH:
        p = subprocess.run(["gh", "api", path, "-H", f"Accept: {accept}"], capture_output=True,
                           text=True, encoding="utf-8")
        if p.returncode != 0:
            if "404" in p.stderr or "Not Found" in p.stderr:
                return None
            raise RuntimeError(f"gh api {path}: {p.stderr.strip()}")
        return p.stdout if raw else json.loads(p.stdout)
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": accept})
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return body if raw else json.loads(body)


def http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError:
        return 0


def first_sentence(md: str) -> str:
    """First prose sentence of a README, for repos with an empty GitHub description."""
    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if not b or b[0] in "#!>|-*`<[" or b.startswith("⭐"):
            continue
        b = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(b.split()))
        b = b.replace("**", "").replace("`", "")
        m = re.match(r"(.+?[.!?])(\s|$)", b)
        return (m.group(1) if m else b)[:240]
    return ""


def install_line(name: str, md: str) -> tuple[str, bool]:
    """(command, on_pypi). Uses the README's pipx line when the package really is on PyPI."""
    on_pypi = http_status(f"https://pypi.org/pypi/{name}/json") == 200
    if on_pypi:
        m = re.search(r"pipx install ([A-Za-z0-9_.\-\[\]]+)", md)
        pkg = m.group(1) if m and m.group(1).split("[")[0] == name else name
        return f"pipx install {pkg}", True
    return f"pipx install git+https://github.com/{ORG}/{name}", False


def demo_still(name: str, branch: str) -> str | None:
    """Download assets/demo.gif and keep one frame as assets/shots/<name>.webp."""
    from PIL import Image
    url = f"https://raw.githubusercontent.com/{ORG}/{name}/{branch}/assets/demo.gif"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            gif = r.read()
    except urllib.error.URLError:
        return None
    SHOTS.mkdir(parents=True, exist_ok=True)
    (SHOTS / "_gif").mkdir(exist_ok=True)
    src = SHOTS / "_gif" / f"{name}.gif"  # gitignored; scripts/media.py cuts the looping clip from it
    src.write_bytes(gif)
    out = SHOTS / f"{name}.webp"
    with Image.open(src) as im:
        # Keep the busiest frame: the demos are terminal recordings, and the frame with the most
        # ink on it is the one that shows the result rather than a half-typed prompt.
        n = getattr(im, "n_frames", 1)
        step = max(1, n // 60)
        best, best_score = None, -1
        for i in range(0, n, step):
            im.seek(i)
            f = im.convert("RGB")
            small = f.resize((160, max(1, round(f.height * 160 / f.width))))
            bg = small.getpixel((small.width - 1, small.height - 1))
            score = sum(1 for px in small.getdata() if sum(abs(a - b) for a, b in zip(px, bg)) > 60)
            if score >= best_score:
                best, best_score = f, score
        frame = best
    if frame.width > 1200:
        frame = frame.resize((1200, round(frame.height * 1200 / frame.width)), Image.LANCZOS)
    frame.save(out, "WEBP", quality=82, method=6)
    return f"assets/shots/{name}.webp"


def image_size(path: Path) -> list[int]:
    from PIL import Image
    with Image.open(path) as im:
        return list(im.size)


def fetch() -> list[dict]:
    repos = api(f"orgs/{ORG}/repos?type=public&per_page=100&sort=full_name")
    out = []
    for r in repos:
        if r["fork"] or r["archived"] or r["private"] or r["name"] in SKIP:
            continue
        name, branch = r["name"], r["default_branch"]
        md = api(f"repos/{ORG}/{name}/readme", raw=True) or ""
        cmd, on_pypi = install_line(name, md)
        tree = api(f"repos/{ORG}/{name}/git/trees/{branch}?recursive=1") or {}
        has_skill = any(t["path"].endswith("SKILL.md") for t in tree.get("tree", []))
        shot = demo_still(name, branch)
        item = {
            "name": name,
            "description": (r.get("description") or "").strip() or first_sentence(md),
            "url": r["html_url"],
            "homepage": r.get("homepage") or "",
            "license": (r.get("license") or {}).get("spdx_id") or "",
            "language": r.get("language") or "",
            "topics": r.get("topics") or [],
            "stars": r.get("stargazers_count", 0),
            "created": r["created_at"][:10],
            "pushed": r["pushed_at"][:10],
            "branch": branch,
            "install": cmd,
            "on_pypi": on_pypi,
            "pypi": f"https://pypi.org/project/{name}/" if on_pypi else "",
            "has_skill": has_skill,
            "shot": shot,
        }
        if shot:
            item["shot_size"] = image_size(ROOT / shot)
        out.append(item)
        print(f"  {name:36} pypi={'yes' if on_pypi else 'NO '} skill={'yes' if has_skill else 'no '} "
              f"shot={'yes' if shot else 'no'}")
    out.sort(key=lambda x: x["name"])
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"org": ORG, "fetched": dt.datetime.now(dt.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"), "repos": out}, indent=2),
                    encoding="utf-8")
    return out


# ---------------------------------------------------------------- render

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def group_of(name: str) -> tuple[str, str]:
    for key, label, names in GROUPS:
        if name in names:
            return key, label
    return OTHER


def words(n: int) -> str:
    small = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
             "fourteen fifteen sixteen seventeen eighteen nineteen twenty").split()
    return small[n] if n < len(small) else str(n)


def render_rows(repos: list[dict]) -> str:
    order = [g[0] for g in GROUPS] + [OTHER[0]]
    by = {k: [] for k in order}
    labels = {g[0]: g[1] for g in GROUPS} | {OTHER[0]: OTHER[1]}
    for r in repos:
        by[group_of(r["name"])[0]].append(r)
    parts = []
    for key in order:
        items = by[key]
        if not items:
            continue
        parts.append(f'<section class="group" aria-labelledby="g-{key}">'
                     f'<h3 id="g-{key}" class="group-name">{esc(labels[key])}</h3><ul class="rows">')
        for r in items:
            short = r["name"].removeprefix("amagi-")
            shot = f' data-shot="{esc(r["shot"])}"' if r.get("shot") else ""
            skill = '<span class="tag">Claude skill included</span>' if r["has_skill"] else ""
            note = "" if r["on_pypi"] else '<span class="tag">installs from GitHub</span>'
            parts.append(
                f'<li class="row" id="{esc(r["name"])}"{shot}>'
                f'<h4 class="row-name"><a href="{esc(r["url"])}">'
                f'<span class="pre">amagi-</span>{esc(short)}</a></h4>'
                f'<p class="row-desc">{esc(r["description"])}</p>'
                f'<div class="row-meta"><code class="cmd">{esc(r["install"])}</code>'
                f'<button class="copy" type="button" data-copy="{esc(r["install"])}" '
                f'aria-label="Copy install command for {esc(r["name"])}">Copy</button>'
                f'{skill}{note}<a class="gh" href="{esc(r["url"])}" '
                f'aria-label="{esc(r["name"])} on GitHub">GitHub</a></div></li>')
        parts.append("</ul></section>")
    return "\n".join(parts)


def render(repos: list[dict], fetched: str) -> None:
    tpl = (ROOT / "src" / "index.html").read_text(encoding="utf-8")
    n = len(repos)
    lic = sorted({r["license"] for r in repos if r["license"]})
    data_js = json.dumps([{k: r[k] for k in ("name", "description", "url", "install", "topics",
                                              "has_skill", "shot")} | {"group": group_of(r["name"])[1]}
                          for r in repos], ensure_ascii=False).replace("</", "<\\/")
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": f"{SITE}/#org", "name": "AmagiLabs",
             "legalName": "Amagisolutionsgroup, Inc.", "url": f"{SITE}/",
             "logo": f"{SITE}/assets/brand/amagilabs-icon-512.png",
             "email": "dev@amagisolutionsgroup.com",
             "sameAs": [f"https://github.com/{ORG}", "https://amagilabs.ai"]},
            {"@type": "WebSite", "@id": f"{SITE}/#site", "url": f"{SITE}/", "name": "AmagiLabs",
             "publisher": {"@id": f"{SITE}/#org"}},
            {"@type": "ItemList", "name": "AmagiLabs open-source tools", "numberOfItems": n,
             "itemListElement": [
                 {"@type": "ListItem", "position": i + 1, "item": {
                     "@type": "SoftwareSourceCode", "name": r["name"], "description": r["description"],
                     "codeRepository": r["url"], "programmingLanguage": r["language"] or "Python",
                     "license": f"https://spdx.org/licenses/{r['license']}.html" if r["license"] else None,
                     "author": {"@id": f"{SITE}/#org"}}}
                 for i, r in enumerate(repos)]},
        ],
    }
    for el in ld["@graph"][2]["itemListElement"]:
        el["item"] = {k: v for k, v in el["item"].items() if v is not None}
    first = min((r["created"] for r in repos), default="")
    subs = {
        "{{COUNT}}": str(n),
        "{{COUNT_WORD}}": words(n),
        "{{COUNT_WORD_CAP}}": words(n).capitalize(),
        "{{LICENSES}}": " and ".join(lic) or "open source",
        "{{FIRST_MONTH}}": dt.date.fromisoformat(first).strftime("%B %Y") if first else "",
        "{{FETCHED}}": fetched[:10],
        "{{ROWS}}": render_rows(repos),
        "{{DATA}}": data_js,
        "{{JSONLD}}": json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", tpl)
    if left:
        sys.exit(f"unfilled placeholders: {left}")
    (ROOT / "index.html").write_text(tpl, encoding="utf-8")
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE}/</loc><lastmod>{fetched[:10]}</lastmod></url>\n"
        "</urlset>\n", encoding="utf-8")
    print(f"rendered index.html with {n} repos (data fetched {fetched})")


def main() -> None:
    if "--offline" in sys.argv:
        d = json.loads(DATA.read_text(encoding="utf-8"))
    else:
        print(f"fetching github.com/{ORG} ...")
        fetch()
        d = json.loads(DATA.read_text(encoding="utf-8"))
    render(d["repos"], d["fetched"])


if __name__ == "__main__":
    main()
