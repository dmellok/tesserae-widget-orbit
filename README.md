# Orbit

Three Tesserae widgets for what passes over your place to-night, the station and the bright satellites, installed together as one bundle:

| widget | the page |
|---|---|
| **Orbit: Pass** | the best pass coming: the spacecraft painted in a ruled frame, a sky chart of its path with the rise and set times, and the particulars |
| **Orbit: To-night** | every visible pass in the next day, in order, each with its small painting and sky chart; or the objects packed on the page as a cluster, sized as they really are, the station a hundred metres across and a rocket stage ten |
| **Orbit: Scene** | one whole painting across the page, the pass written over it |

**Passes** are worked out on your server from CelesTrak's element sets (no key): the space stations, or the stations and the hundred-odd brightest objects. A bundled SGP4 propagator, checked against the reference implementation to within a tenth of a metre, carries each object across the next day and a half; a pass counts when the observer is in the dark, the object is in sunlight and it climbs above the elevation you choose. The work takes a couple of seconds in the background once every three hours; the first page after a start says it is working and fills within a minute. Times are local to the place, with the rise and set directions, how high, how long, and how bright: as bright as Venus for the station down to a faint moving star for a rocket body.

**Pictures** are silhouettes, or AI paintings: each object painted once through fal.ai, in a style, from a free picture on Wikimedia Commons where there is one (the stations, the telescopes, most of the observation satellites, the Tselina series and the stages that have one; thirty-three in all, each credited with its author and licence) and from its description otherwise, marked an impression on the page, on white paper so it cuts out cleanly, at about US$0.04 a painting. Twenty-five styles, from a space-age poster, engravings, watercolour, woodblock, linocut, Art Deco and mid-century flat to a magazine cutaway, a postage stamp, risograph, pixel art, a low-poly render, paper craft, toy bricks, charcoal, stained glass, an illuminated manuscript, a pulp cover, synthwave, a chalkboard and a celestial atlas, **Build my own** and **Your own prompt**. The Pass and the Scene take a **backdrop**: none, black space and stars, above the Earth's limb, over the Earth by day or by night, an orbital sunrise, or an ornate framed plate. Four views, from below as it passes over among them.

**The cluster** packs each object's cut-out from the middle out and then grows each into the room left. **Packing** can instead use one of the two packers from [Fugleramme](https://github.com/arnegiacomo/fugleramme), adapted from its code (MIT): *Spiral* sets each object, the largest first, on the first free spot out from the middle, for a round cluster, and *Voids* sets each on the emptiest paper it fits, so the page fills to the corners.

**Settings** live on Orbit Core (Settings › Widgets): the fal.ai key (or the one under Settings › Generative AI), a contact for CelesTrak and Wikimedia Commons, the daily painting budget. The paintings page is under Widgets › Orbit Core.

## Install

Needs Tesserae 0.463 or later for the paintings; an older server still shows the passes with silhouettes.

From the Tesserae catalog as the Orbit bundle, or by hand: copy the four folders (`orbit_core`, `orbit_pass`, `orbit_tonight`, `orbit_scene`) into your plugins folder together; the three widgets load their shared code from `orbit_core` by path.

## Development

```sh
PYTHONPATH=../tesserae python -m pytest orbit_core/tests -q    # offline: every call on the network is faked
python3 orbit_core/tools/manifests.py                           # rewrites the plugin.json files from one description
```

## Licence

AGPL-3.0-or-later, apart from the Spiral and Voids packing in `orbit_core/static/pack.js`, adapted from Fugleramme (MIT, copyright Arne Giacomo Munthe-Kaas; the notice is in that file). See `ATTRIBUTION.md`.
