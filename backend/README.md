# Backend

Python standard-library server and authoritative economic/card state for the current playtest.

## Responsibilities

- Serve the frontend and JSON API on `0.0.0.0:$PORT` (local fallback `8766`).
- Own treasury, factory points, reserves, loans, cards, events, diplomacy, and city ownership.
- Store the latest shared tactical snapshot with optimistic revision checks for multiplayer synchronization.
- Expose land combat through `/api/combat` and snapshot/restore through the shared-state endpoints.

Army composition itself has one authority: `tactical.armies[army_id].units`. Reserve replenishment deducts the backend reserve and returns an accepted unit delta; the frontend immediately applies that delta to the tactical army and publishes it. The legacy `army_reinforcements` object remains only for old-save compatibility and is not added during combat.

## Main files

- `card_engine.py`: turns, economy, decks, cards, events, loans, reserves, and diplomacy.
- `server.py`: HTTP routes, static hosting, shared revisions, and snapshot restore.
- `combat_adapter.py`: adapter for `comabt_system/combat.py`.
- `data_store.py`: JSON loading and bootstrap assembly.

Run backend tests with `python3 -m unittest backend.test_backend`.
