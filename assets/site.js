// AmagiLabs site: copy buttons, list preview, type-to-find, header colour by chapter, entrances.
// The page works without this file: the list, the default find results and every link are in the HTML.
(() => {
  const doc = document.documentElement;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  let repos = [];
  try { repos = JSON.parse($("#repo-data").textContent); } catch (e) { repos = []; }

  // ------------------------------------------------------------ copy the install line
  const status = $("#copy-status");
  function fallbackCopy(text) {
    const t = document.createElement("textarea");
    t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    t.remove();
    return ok;
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("button.copy");
    if (!b) return;
    const text = b.dataset.copy;
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (err) { ok = fallbackCopy(text); }
    b.textContent = ok ? "Copied" : "Select it";
    b.classList.toggle("done", ok);
    status.textContent = ok ? "Copied: " + text : "Could not copy. Select the command and copy it.";
    clearTimeout(b._t);
    b._t = setTimeout(() => { b.textContent = "Copy"; b.classList.remove("done"); }, 1800);
  });

  // ------------------------------------------------------------ the preview follows the row you point at
  const pimg = $(".preview-img");
  const pcap = $(".preview-cap");
  const table = $(".tools .table");
  let shown = null;
  function preview(row) {
    if (!row || row === shown || !pimg) return;
    $$(".row.on").forEach((r) => r.classList.remove("on"));
    row.classList.add("on");
    if (!row.dataset.shot) return;
    shown = row;
    const name = row.id;
    const next = new Image();
    next.src = row.dataset.shot;
    pimg.classList.add("swap");
    const swap = () => {
      if (shown !== row) return;
      pimg.src = next.src;
      pimg.width = +row.dataset.w;
      pimg.height = +row.dataset.h;
      pimg.alt = "Terminal frame from the " + name + " demo recording";
      pcap.textContent = name + ", a frame from its README demo";
      pimg.classList.remove("swap");
    };
    (next.decode ? next.decode() : Promise.resolve()).then(swap, swap);
  }
  if (table) {
    table.addEventListener("pointerover", (e) => preview(e.target.closest(".row")));
    table.addEventListener("focusin", (e) => preview(e.target.closest(".row")));
  }

  // ------------------------------------------------------------ type-to-find (same scoring as scripts/build.py)
  const STOP = new Set(("a an the for to of and or my our your before after in on with from into i me it is " +
    "this that by at as be can do get how what want need").split(" "));
  const tokens = (text) => String(text).toLowerCase().split(/[^a-z0-9]+/)
    .filter((t) => t.length >= 2 && !STOP.has(t))
    .map((t) => (t.length > 3 && t.endsWith("s") && !t.endsWith("ss") ? t.slice(0, -1) : t));
  function score(r, q) {
    const name = tokens(r.name.replace(/^amagi-/, ""));
    const topics = (r.topics || []).flatMap(tokens);
    const desc = tokens(r.description);
    let total = 0;
    for (const t of q) {
      const hit = (ws) => ws.some((w) => w.startsWith(t) || (w.length >= 3 && t.startsWith(w)));
      total += 3 * hit(name) + 2 * hit(topics) + (hit(desc) ? 1 : 0);
    }
    return total;
  }
  function find(query, k = 3) {
    const q = tokens(query);
    const ranked = repos.map((r) => [score(r, q), r.name, r])
      .sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
    const top = ranked.length ? ranked[0][0] : 0;
    return ranked.slice(0, k).filter(([s]) => s > 0 && s * 3 >= top).map(([, , r]) => r);
  }
  function hitHtml(r, i) {
    const short = r.name.replace(/^amagi-/, "");
    const [w, h] = r.shot_size || [1200, 750];
    const pic = r.shot ? `<img class="hit-pic" src="${esc(r.shot)}" width="${w}" height="${h}" alt="Terminal frame from the ${esc(r.name)} demo" decoding="async">` : "";
    const tags = (r.has_skill ? '<span class="tag">Claude skill</span>' : "") +
      (r.on_pypi === false ? '<span class="tag">installs from GitHub</span>' : "");
    return `<li class="hit fresh" style="--d:${i * 70}ms">${pic}<div class="row-body">` +
      `<h3 class="row-name"><a href="${esc(r.url)}"><span class="pre">amagi-</span>${esc(short)}</a></h3>` +
      `<p class="row-desc">${esc(r.description)}</p>` +
      `<div class="row-meta"><code class="cmd">${esc(r.install)}</code>` +
      `<button class="copy" type="button" data-copy="${esc(r.install)}" aria-label="Copy the install command for ${esc(r.name)}">Copy</button>` +
      `${tags}<a class="gh" href="${esc(r.url)}">GitHub<span class="sr-only">: ${esc(r.name)}</span></a></div></div></li>`;
  }
  const input = $("#find-q");
  const out = $("#find-out");
  const tries = $$(".find-try button");
  let last = input ? input.value.trim().toLowerCase() : "";
  function run() {
    const q = input.value.trim();
    if (q.toLowerCase() === last) return;
    last = q.toLowerCase();
    tries.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.q.toLowerCase() === last)));
    if (!q) {
      out.innerHTML = '<li class="find-none">Type the job above, or pick one of the examples below.</li>';
      return;
    }
    const hits = find(q);
    out.innerHTML = hits.length ? hits.map(hitHtml).join("")
      : '<li class="find-none">Nothing matched that. Try other words, or <a href="#tools">browse all the tools</a>.</li>';
  }
  if (input && out && repos.length) {
    let t;
    input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 120); });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); clearTimeout(t); run(); } });
    tries.forEach((b) => {
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => { input.value = b.dataset.q; run(); });
    });
  }

  // ------------------------------------------------------------ the header takes the colour of the chapter beneath it
  const bar = $(".bar");
  const chapters = $$("[data-chapter]");
  let chapterIO;
  function watchChapters() {
    if (chapterIO) chapterIO.disconnect();
    const y = Math.round(bar.offsetHeight / 2);
    chapterIO = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) bar.dataset.ink = e.target.dataset.chapter;
    }, { rootMargin: `-${y}px 0px -${Math.max(0, window.innerHeight - y - 1)}px 0px` });
    chapters.forEach((c) => chapterIO.observe(c));
  }
  if (bar && "IntersectionObserver" in window) {
    watchChapters();
    let rt;
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(watchChapters, 150); });
  }

  // small screens: close the menu after a jump
  const menu = $(".menu");
  if (menu) menu.addEventListener("click", (e) => { if (e.target.closest("a")) menu.open = false; });

  // ------------------------------------------------------------ entrances: each part of a section rises in turn
  if ("IntersectionObserver" in window) {
    doc.classList.add("rv");
    const io = new IntersectionObserver((entries) => {
      let i = 0;
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.style.setProperty("--d", Math.min(i++, 6) * 75 + "ms");
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    $$("[data-reveal]").forEach((el) => io.observe(el));
  }

  // ------------------------------------------------------------ the hero clip: still under reduced motion, paused off screen
  const clip = $(".slot-clip");
  if (clip) {
    const setMotion = () => {
      if (reduce.matches) { clip.pause(); clip.removeAttribute("autoplay"); }
      else if (clip.paused && clip.offsetParent !== null) clip.play().catch(() => {});
    };
    setMotion();
    if (reduce.addEventListener) reduce.addEventListener("change", setMotion);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([e]) => {
        if (reduce.matches) return;
        if (e.isIntersecting) clip.play().catch(() => {}); else clip.pause();
      }).observe(clip);
    }
  }
})();
