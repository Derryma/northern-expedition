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

- NPC factions start with fixed armies and generals on their own major cities.
- NPC armies do not move, recruit, or grow by themselves.
- NPCs do not perform autonomous strategic actions.
- When attacked, NPCs passively fight.
- NPCs do not trigger total mobilization when attacked.
- NPCs do not become player-controlled just because they are attacked.
- Their purpose is to be occupied and to provide captive generals for player growth before the player-vs-player war deepens.

## Initial Armies

| Faction | Armies |
| --- | --- |
| 晉系 | 閻錫山 at 太原; 傅作義 at 大同 |
| 西北軍 | 馮玉祥 at 西安; 宋哲元 at 歸綏 |
| 西北馬家軍 | 馬麒 at 西寧; 馬福祥 at 西寧 |
| 湘軍 | 唐生智 at 長沙; 何鍵 at 衡陽 |
| 川軍 | 劉湘 at 成都; 劉文輝 at 重慶 |
| 滇系 | 唐繼堯 at 昆明; 龍雲 at 大理 |
| 黔軍 | 黔軍地方部隊 at 貴陽 |

This keeps smaller warlords present as pressure and opportunity without making them a full extra player.
