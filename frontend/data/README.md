# Map Data

`provinces_1926.geojson` is the map the running game reads, and the only one.
It holds the 24 top-level administrative units of June 1926, clipped to the playable
silhouette that `frontend/map.js` defines. `app.js` fetches it at
`/data/provinces_1926.geojson`.

It is generated. Edit `scripts/build_provinces_1926.py` and re-run it rather than
editing this file by hand.

`china_provinces.geojson` is the generator's input: the modern China provincial
boundary dataset published by DataV GeoAtlas
(`https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json`), retrieved on
2026-07-28. Nothing fetches it at runtime, and it still covers regions the game map
deliberately excludes, so it must not be wired back into the renderer.

Superseded map files are kept under `frontend/old map/` for reference. Nothing loads
them and their data predates the 1926 revision.
