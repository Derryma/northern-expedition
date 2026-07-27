# Northern Expedition

Playtest workspace for *北伐風雲*.

## Run The Playtest App

```bash
python3 scripts/run_playtest_server.py
```

Open:

```text
http://127.0.0.1:8765
```

## Structure

- `backend/`: Python API, data loading, turn/card engine, combat adapter.
- `frontend/`: static playtest interface.
- `cards/`: event cards, function cards, injected event cards, card-pool rules.
- `NPC/`: NPC faction data.
- `foreign_powers/`: foreign-power rules and data.
- `general_tree/`: hierarchy, loyalty, body guard, recruitment, troop allocation.
- `comabt_system/`: combat simulator.
- `PJ Boardgame/`: legacy/source HTML tools and original boardgame materials.

