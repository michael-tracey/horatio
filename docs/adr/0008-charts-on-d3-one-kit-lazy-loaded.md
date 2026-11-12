# Charts on d3, through one kit, loaded only where they are drawn

Horatio's charts (#713: boon statistics, sire lines, the web of blood bonds, influence, the court over time, the chronicle timeline) are drawn with **d3's modules**, rendered as SVG from React, through **one shared kit** in `frontend/src/charts` (#706). No chart reaches for d3 or picks colours on its own.

We chose d3 over a ready-made React chart library because the charts we want are not the stock ones: force-laid networks, family trees, chord diagrams and long, uneven timelines, which those libraries either lack or bury. We use d3 for scales, shapes, layouts and zoom, and let React draw the SVG, so charts follow the app's own components, tokens and accessibility.

## Consequences

- **Only the modules a chart needs**, never the `d3` bundle, each pinned to an exact version in `package.json`, with `overrides` holding the modules they pull in. In November 2026 every d3 module was republished at once; we pinned the releases before that (2021–2026) until a newer one has a reason and a track record.
- **Lazy, and not offline.** d3 goes into a chunk of its own (`vite.config.ts`), loaded only by pages imported with `lazy()`. The service worker leaves it out, so the Play View's offline copy doesn't grow: charts are staff pages that need a connection anyway. `npm run build` fails if d3 reaches the first load or the offline cache (`frontend/scripts/check-chart-chunks.mjs`).
- **One look.** Colours come from the kit by the job they do (identity, magnitude, polarity), using the dataviz method's validated palette, checked against Horatio's own surfaces; each theme sets them as CSS custom properties. A clan keeps one colour across a troupe's charts (`clanSlots`). Past eight things, or three where any two marks can meet, the rest fold into Other.
- **Every chart has its table**, for screen readers always and for anyone on request, and its tooltips work by hover, tap and keyboard focus.
