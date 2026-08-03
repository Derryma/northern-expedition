# NPC

NPC faction data for *Northern Expedition*.

The four major playable factions are:

- 孫 / 孫傳芳
- 吳 / 吳佩孚
- 張 / 張作霖
- 蔣 / 蔣中正

All other Chinese-side factions are organized as NPC factions.

## Files

- `data/npc_factions.json` lists the playable majors, NPC rules, and NPC faction records.

Each NPC faction keeps only 1-2 representative figures. Smaller named officers can return later as event text, local modifiers, or function-card results, but they should not clutter the primary NPC faction roster.

## NPC Rules

- Every three turns, all NPC generals add 1 infantry to their HQ.
- NPCs are event-driven only.
- NPCs do not perform autonomous strategic actions.
- When attacked, NPCs passively fight.
- NPCs do not trigger total mobilization when attacked.
- NPCs do not become player-controlled just because they are attacked.

This keeps smaller warlords present as pressure and opportunity without making them a full extra player.
