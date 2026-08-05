# Old Map (archived)

These files are the map surfaces this project used before the June-1926 revision.
They are kept for reference only: `index.html` does not load any of them, and each
carries its own outdated copy of the province and city data.

- `map_config.js`, `map_renderer.js` — earlier canvas renderer, 20 provinces as
  lon/lat rectangles, pre-rename city names.
- `china_map.html`, `china_map.js`, `china_map_data.js` — an earlier standalone
  China map experiment.
- `map_data.html` — a copy of the PJ boardgame hex map.

The live map is `frontend/data/provinces_1926.geojson`, drawn by `frontend/app.js`
and `frontend/map.js`.
