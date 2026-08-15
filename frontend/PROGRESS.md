# Frontend Progress

Updated 2026-08-15. This is the current implementation summary.

## Working

- China-focused historical hex map with opaque faction tiles, cities, province ownership, railways, rivers, ports, and near-coast water routes.
- Click-to-inspect plus explicit Move mode for armies and navies.
- Four player views with army and navy fog of war; intelligence cards temporarily reveal a province.
- Civ-style pending-unit cycle, synchronized multiplayer revisions, and localhost-only `DBG` turn forcing.
- Three-level player general trees, flat-command NPC exceptions, portraits, loyalty breakdown, captives, recruitment, and defection.
- Land battles with tactics, reinforcements, casualty reports, pursuit, and persistent multi-turn combat.
- Navy movement, transport, recruitment, repair, fog, naval duels, and army/navy contact reports.
- Optional function-card draws and one shared event/newspaper card every three turns.

## Active verification targets

- Exercise long-running multiplayer contacts after reconnect and snapshot restore.
- Continue balancing combat duration and naval retreat thresholds from playtest evidence.
- Add persistent database storage before treating Render as a durable production save host.
