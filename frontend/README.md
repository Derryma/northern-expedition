# Frontend

Static playtest UI for Northern Expedition.

## Responsibilities

- Render the current turn state.
- Show playable factions and card hands.
- Draw event/function cards through the backend API.
- Use function cards and display injected-event consequences.
- Browse event/function/NPC/foreign-power data.
- Run quick combat simulations through `/api/combat`.

The frontend does not contain game rules. It calls `backend/server.py` for state changes.

