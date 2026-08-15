# Northern Expedition / 北伐風雲

Current playtest workspace for the map-based, multiplayer Northern Expedition strategy game.

## Run locally

```bash
python3 scripts/run_playtest_server.py
```

Open `http://127.0.0.1:8766`. Localhost enables the red `DBG` button; the deployed Render build does not expose it.

## Current game

- Four players: 張、吳、孫、蔣. Other Chinese factions are stationary NPC warlords.
- Shared hex map with cities, provinces, railways, rivers, fog of war, armies, navies, and synchronized turns.
- Land armies use infantry, cavalry, machine guns, and artillery with a 100-force cap.
- Each playable faction starts with a gunboat/cargo-boat division. Naval and army/navy contacts persist by shared turn state.
- Function cards are optional purchases: `$5 + 5 factory`, at most two draws per turn, six-card hand limit.
- One shared event card is drawn every three turns; only its selected faction must acknowledge or choose.
- The active game is held in server memory. Save `/api/shared-state` before restarting or deploying; see `REMOTE_PLAY.md` for the exact commands.

## Source of truth

- `PJ Boardgame/北伐風雲_規則書.md`: implemented rules and player flow.
- `cards/README.md`: every active card and pool rule.
- `comabt_system/README.md`: land combat formula and examples.
- `navy_system/README.md`: navy movement, transport, repair, and combat.
- `general_tree/README.md`: hierarchy, loyalty, capture, defection, and recruitment.
- `NPC/README.md`, `economy/README.md`, `foreign_powers/README.md`: strategic subsystems.

Folders named `事件卡工作日誌` and the frontend planning documents are historical records, not live rules.
