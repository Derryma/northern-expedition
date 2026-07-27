# Frontend

Static playtest UI for Northern Expedition.

## Responsibilities

- Open on the playable PJ boardgame surface, with map/city/unit UI in the main stage.
- Switch between the integrated board, strategic map, faction operation board, and event-card board.
- Render compact turn state and function-card hands beside the board.
- Draw event/function cards through the backend API.
- Use function cards and display injected-event consequences.
- Run quick combat simulations through `/api/combat`.

The frontend shell does not own rules. It calls `backend/server.py` for turn/card/combat state and embeds the PJ boardgame HTML tools as the playable surface.
