# Frontend

The live map-first client is `index.html` + `app.js` + `map.js` + `navy.js`.

It renders the shared hex map, army/navy markers, fog of war, pending-unit panel, battle reports, general tree, recruitment, loans, diplomacy, cards, and the single shared newspaper event. Movement is explicit: select a unit, press Move, then left-click the destination; ordinary left-click remains inspection.

`app.js` owns tactical state and publishes revisioned snapshots. `map.js` owns map geometry, cities, railways, rivers, and starting armies. `navy.js` contains isolated boat state and exchange helpers. Economic/card authority remains in the backend.

The current client supports multiplayer polling. Conflicting revisions are pulled and rendered instead of silently overwriting another device. Debug-only force-next-turn is available only from localhost.

Historical plans in this folder are retained for design history and are labeled archived; they are not implementation instructions.
