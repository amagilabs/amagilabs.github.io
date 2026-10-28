# amagilabs.github.io

The public index of [AmagiLabs](https://github.com/amagilabs), the open-source lab of
Amagisolutionsgroup, Inc. One static page listing every public repo in the org with its
description, install line and GitHub link. Served by GitHub Pages from the root of `main`;
nothing builds on GitHub's side.

## Regenerate the list

```sh
python scripts/build.py            # fetch the org from GitHub, refresh the stills, render index.html + sitemap.xml
python scripts/build.py --offline  # re-render from data/repos.json without touching the network
```

The fetch step uses the `gh` CLI when it is logged in, otherwise the public REST API (set
`GH_TOKEN` for a higher rate limit). It needs Pillow for the demo stills. New repos land in
"More tools" until they are added to `GROUPS` in `scripts/build.py`. Commit the rendered output.

`python scripts/assets.py` rebuilds the fonts, icons and hero clip from the brand files in
`amagilabs_logo/` (fontTools, brotli, Pillow, ffmpeg). Run it only when the brand changes.

## Files

- `src/index.html`: the page template (edit this, not `index.html`)
- `assets/site.css`, `assets/site.js`: styles and the small script (copy buttons, list preview, type-to-find)
- `data/repos.json`: the last fetch
- `assets/shots/`: one frame from each repo's own `assets/demo.gif`
