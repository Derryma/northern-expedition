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
- NPC armies do not move or recruit by themselves, but they do grow on a fixed timer (see 自動增兵 below).
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

## 自動增兵（NPC 專屬）

NPC 勢力會隨時間自己長兵，玩家勢力不會。這是為了讓「先打弱的、慢慢啃」有時間成本：
拖得越久，中西部那幾家越難啃。

- **每 3 回合**（第 3、6、9⋯回合），**每一支** NPC 部隊 **+1 營步兵**。
- **每 5 回合**（第 5、10、15⋯回合），**每家 NPC 大帥的部隊** 隨機 **+1 營機槍、騎兵或砲兵**。
  大帥是各勢力將領樹的 `great_general_id`：晉系閻錫山、西北軍馮玉祥、馬家軍馬麒、
  滇系唐繼堯。**川軍、湘軍與黔軍沒有大帥**（將領樹是 `flat_command`、`great_general_id` 為
  null），所以這三家只有三回合的步兵成長，沒有五回合的重武器。
- 成長**不因交戰而中斷**——正在打仗的 NPC 部隊照樣補進來。
- 成長**受 100 戰力上限限制**，規則與玩家一致。滿載的部隊停止成長；五回合的重武器若因為
  點數（機槍 2、騎兵 1、砲兵 4）放不下，就只從放得下的兵種裡抽。
- 一支 NPC 部隊只要**被玩家策反或招降過，它的成長就永久停止**，直到遊戲結束為止，
  之後不論怎麼易手都不會恢復。判定看兩件事：將領歸屬換人，或部隊本身改掛別家旗。

實作在 `frontend/app.js` 的 `applyNpcReinforcements()`，掛在回合推進裡（跟工事進度同一個
位置），成長結果寫進共享快照的 `armies`，永久除名的印記存成 `army.npcGrowthEnded`。

## 黔軍沒有俘虜機制

黔軍是地方民團，不是某位督軍的班底，所以**沒有可俘可招的人**。其他勢力的部隊兵力打到 5 戰力
點以下會投降並被收押、將領進俘虜區等待招降；黔軍部隊在同樣情況下**直接就地消滅**：

- 不產生俘虜紀錄，招不到將領，將領樹的被俘區不會出現黔軍。
- 不觸發「上級被俘、麾下忠誠歸零」的連帶效果——黔軍本來就只有一支平行部隊。
- 部隊標記從地圖上消失（`army.status = "destroyed"`），不再參與任何判定，也不會再自動增兵。
- 戰場照常判給勝方、地格照常占領，戰報上寫的是「遭殲滅」而不是「投降並被俘」。

程式上由 `frontend/app.js` 的 `NO_CAPTURE_FACTIONS` 控制，`surrenderArmy()` 一進來就先分流到
`annihilateArmy()`，所以八個投降呼叫點都吃得到這條規則。
