# Attribution

- **Element sets**: CelesTrak (https://celestrak.org), the `stations` and `visual` groups, fetched at most once every four hours per group, as CelesTrak asks.
- **Propagation**: the bundled `orbit_core/lib/sgp4.py`, a port of the Vallado 2006 SGP4 for near-Earth objects with the WGS-72 constants, checked against the reference `sgp4` package to within a tenth of a metre over two days.
- **Reference pictures** for the painter: NASA photographs of the International Space Station (STS-134) and the Hubble Space Telescope (SM4) from Wikimedia Commons, public domain; every other object is painted from its description.
- **Paintings**: fal.ai models, named on the page; the prompts are in `orbit_core/lib/paint.py`.
- **Fonts**: IM Fell English and IM Fell English SC (Igino Marini, SIL Open Font License), Archivo Narrow (Omnibus-Type, SIL Open Font License); licences in `orbit_core/lib/fonts/`.
