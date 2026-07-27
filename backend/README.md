# Backend

Python backend for the Northern Expedition playtest app.

## Responsibilities

- Load JSON data from `cards/`, `NPC/`, `foreign_powers/`, `general_tree/`, and `comabt_system/`.
- Own temporary playtest state in memory.
- Draw automatic event cards.
- Draw and use per-player function cards.
- Inject consequence event cards into the event pool.
- Expose the combat simulator through `/api/combat`.

## Main Files

- `data_store.py`: JSON loading and indexing.
- `card_engine.py`: turn flow, decks, hands, injected events.
- `combat_adapter.py`: wrapper around `comabt_system/combat.py`.
- `server.py`: stdlib HTTP API and static frontend server.

The backend intentionally uses only the Python standard library so collaborators can run it without installing packages.

