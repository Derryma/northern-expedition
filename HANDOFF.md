# 交接說明 — NPC 事件卡機制

> 最後更新：2026-08-29。這份檔案給**接手的另一個 thread** 看的，
> 目的是讓你在讀完之後就能直接動工，不必重新摸索。
> 每做完一批就回來更新這份檔案的「目前進度」與「還沒做的」兩節。

---

## 一、這是什麼專案

《北伐風雲》——1926 年軍閥割據為背景的桌遊，有可以真的玩的網頁版原型。

* **後端**：Python，`backend/`。規則的唯一權威。
* **前端**：單檔 `frontend/app.js`（約 9,500 行）。負責地圖、部隊擺位、呈現。
* **測試**：`backend/test_backend.py`，目前 **1,122 項**，用
  `python3 -m unittest backend.test_backend` 跑（**不要**直接 `python3 backend/test_backend.py`）。

四家玩家勢力：`F` 奉系、`W` 直系、`S` 孫傳芳、`N` 國民革命軍。
七家 NPC 勢力：`Y` 晉系、`G` 西北軍、`M` 馬家軍、`H` 湘軍、`C` 川軍、`D` 滇系、`Q` 黔軍。

---

## 二、不可違反的規矩

這些是使用者反覆強調過的，違反等於白做：

1. **絕不直接推 main。** 一律開 feature branch 走 PR。
2. **絕不在使用者本機那份 repo 裡跑任何 git 指令。** 每跑一次就留下一個刪不掉的
   `.lock`。所有 git 動作只在 clone（`/tmp/ne`）裡做。
3. **`PJ Boardgame/` 底下的檔案一律不碰**，除非使用者另外交代。
4. **`CLAUDE.md` 不適用於本專案**（那是別人的共享專案）。
5. **誠實回報，嚴禁捏造進度。** 讀程式碼不算驗證——每一句宣稱都要有實跑的輸出撐著。
6. **「我不要再看到應該自動化的機制還要『玩家自主遵守』」。** 規則要嘛程式強制，
   要嘛就別說它存在。
7. **所有列強 perk 卡門檻一律是 6**，文字說明與實作必須一致，沒有例外。
8. **所有將領在所有 UI 呈現上一律用中文名。**
9. **架構原則**：本質上屬於後端的系統，計算**只能在後端**。前端剩下的職責是
   接收玩家指令、呈現戰鬥與結算結果、以及地圖狀態。
   → 實務上這代表：**同一個常數／同一條規則不准在前後端各寫一份。**
     後端要嘛在 bootstrap 裡把值發給前端，要嘛把算好的結果送過去。
     已經因此收拾過兩次：`FOREIGN_RAILWAY_RELATION_MIN`、`EXILE_RECRUIT_SURCHARGE`。
10. **「控制 a、b 或 c 者本回合獲得 $xx」這類事件，收益以控制一個地區發一次，可疊加。**
11. **clone 與使用者本機必須永遠同步。** 每批收尾都要比對整體指紋（見第六節）。

`device_bash` 無法刪檔（`rm` 會失敗）。要刪的話搬進同一個掛載資料夾下的
`_to_delete/`，然後告訴使用者。

---

## 三、目前進度

事件卡共 **207 張**。第 15 區塊（`ref` 以 `15.` 開頭）是 NPC 事件卡，共 33 張。

| 狀態 | 張數 | 說明 |
| --- | ---: | --- |
| 已上線 | **33（全部）** | 機制建好、`not_in_pool` 已清空、全部會被抽到 |
| 仍缺機制 | **0** | — |

**`apply.pending` 已經清空，NPC 事件卡這條線做完了。**
下面五套機制加上批次四的四項結構變動就是全部的成果；
接手的人多半是來改規則或修 bug，不是來補新機制的。

### 五套 NPC 機制

**1. 觸發條件閘門 `entry_condition.npc_requires`**

判定「某某將領是否仍屬某陣營」「某陣營是否還有將領／還有幾營」「某城是否仍歸誰」。
判定全在後端，資料來自伺服器手上的 `SHARED_TACTICAL_STATE`。
**沒有戰術快照時一律判為不合格（fail closed）**——寧可卡不出現，
也不要發一張「馮玉祥誓師」而馮玉祥早就陣亡的報紙。純城市條件不需要快照。

卡片點名了查無此人的將領、或名字對得上但陣營寫錯，**當場拋錯**，
不會安靜地判成「條件不成立」。資料寫錯與條件不成立是兩回事。

**2. `apply.npc_unit_delta` — 絕對增減兵**（15.3、15.6、15.8、15.12、15.19、15.25、15.26）

```json
"npc_unit_delta": [
  {"general": "馮玉祥", "units": {"infantry": 1, "machine_gun": 1, "artillery": 1}},
  {"faction": "G", "except_generals": ["馮玉祥"], "units": {"infantry": 1}}
]
```

同一支部隊被多條規則點到時**先累加、最後才寫一次**。
先扣後補：減損一律生效（最低 0），增援只補得進去的部分——
滿編的部隊不會為了塞新兵而裁掉老兵。補的順序由**卡片寫的順序**決定。

**3. `apply.npc_force_scale` — 按比例增減戰力**（15.4、15.7、15.9、15.11、15.15、15.17、15.24）

```json
"npc_force_scale": [
  {"faction": "G", "multiplier": 0.85},
  {"faction": "Y", "multiplier": 0.80}
]
```

**「戰力」就是那個每支部隊 100 點上限的兵力值**（步兵／騎兵每營 1 點、
機槍 2 點、砲兵 4 點）——這是使用者定的，所以「戰力 −50%」是**真的裁兵**，
不是戰鬥時打折。目標戰力點 = `min(100, floor(現值 × 倍率 + 0.5))`。

* **四捨五入，不是無條件捨去。** NPC 部隊小，捨去的話一張寫 −15% 的卡
  打在 7 點的部隊上會變成實際 −29%。
* 用 `floor(x + 0.5)`，**不要用 Python 的 `round()`**——後者是銀行家捨入。
* **減損從最貴的兵種裁起，但不裁過頭**：每一步只裁「裁下去還不會低於目標」的
  最貴兵種，沒有就停手，並誠實報實際的數。（`_cut_down_to_force`）
* **增益補步兵**（1 點，補得最精準），補不出一整營就什麼都不動。
* 多條規則點到同一支部隊時**倍率相乘**，不是相加。
* 一次性、永久，不會自己回復。

兩套機制的點名方式完全共用（`general` / `generals` / `faction` / `except_generals`），
落地邏輯也共用（`_land_npc_army_patch`）。

**4. `apply.npc_combat_modifier` — NPC 的限時戰鬥修正**（15.2、15.20、15.22、15.23）

```json
"npc_combat_modifier": [
  {"general": "傅作義", "modifiers": [{"stat": "hp", "multiplier": 1.08}],
   "until_general_leaves": true},
  {"faction": "Y", "modifiers": [{"stat": "attack", "multiplier": 1.05}], "turns": 5}
]
```

「生命」是 `hp`、「攻擊」是 `attack`。效果存在 `state["npc_combat_effects"]`——
玩家的限時修正掛在 `player["timed_effects"]`，但 NPC 陣營不在 `state["players"]` 裡。
讀取端是 `CombatModifierBuilder.npc_combat_modifiers()`，由 `build()` 掛上去；
`build()` 拿得到 NPC 側的陣營代號與將領代號（前端 `combatBattleFacts()` 送的
`sides.{A,B}.faction` 就是），前端一行都不用改。

`until_general_leaves` 的離場判定用 **`npc_situation(self._tactical)`**，
也就是戰術快照上的現況。**不要**去讀將領樹檔案的 `status`——那是唯讀的靜態資料，
永遠不會變，這條效期會因此永遠不到期。

抽到的那一回合不倒數，否則寫 5 回合的效果只會活 4 回合。

**5. `apply.contested_npc_recruit` — 付費招募**（15.7、15.10、15.18、15.21）

```json
"contested_npc_recruit": {"general": "龍雲", "cost": 25, "option_id": "recruit"}
```

**結算點只能在卡片層級的 `apply`。** 選項的 `apply` 是在每個人各自回應的當下就跑的，
那時只看得到他一個人的選擇，算不出「參與人數」。卡片層級的 `apply` 等所有人回應完
才跑一次，用 `_event_responses(card)` 讀全部表態。

付了就扣、沒抽中也不退（卡片這樣寫）；成功率 1/n；表態但錢不夠的算棄權，
不扣成負數也不算進分母。抽籤用 `self.random`（有種子，可重播）。

### 資料怎麼流動（這是整套的關鍵）

```
事件卡結算（後端）
   ↓ 算出每支部隊「調整後的絕對編制」
   ├─→ 直接改寫 SHARED_TACTICAL_STATE（伺服器手上那份）
   │     ← 同一個事件週期裡後面幾張卡的 npc_requires 要看改完的現況
   └─→ 掛一筆 pending_frontend_effects（kind: "npc_army_units"）
         ↓ 前端 consumePendingFrontendEffects() 消費
         army.units = { ...entry.units }   ← 照抄，不准自己加減
         ↓ /api/ack-frontend-effects 銷帳
```

**只掛在一位玩家的佇列上**（`sorted(state["players"])[0]`）：這是全場共通的事，
掛給每個人會讓提示重複四次。內容是絕對編制，所以重複套用結果相同。

---

## 四、批次四做了什麼（陣營級結構變動）

15.1、15.5、15.13、15.14、15.27。這一批動的不只是編制，還有**地盤歸屬**與
**陣營是否還在地圖上**，所以多了一個共用概念：`state["retired_npc_factions"]`。

**退出地圖**＝`npc_situation()`、`_living_npc_armies()` 與 `npc_reinforcements()`
三處都把它當成空的。三處缺一不可——少了第三處，被併吞的黔軍會每三回合
自己長出一營步兵，一路長回來（這是突變測試挖出來的真漏洞，不是假警報）。

* **`railway_permanent_block`（15.1）**：`railway_effects` 的 `remaining_turns`
  是 `None`。既有程式都拿 `int(remaining_turns)` 去比大小，所以抽出了
  `_railway_effect_active()` 共用判定。沒有搶修攤派（修不好），
  解除條件是閻錫山離場，判定用 `_npc_general_still_here()`。
* **`npc_general_transfer` ＋ `npc_army_relocate`（15.5）**：換陣營在後端；
  **移防只有前端做得到**——後端沒有座標，它只說「搬到哪座城周邊幾格」，
  格子由 `relocationCellNear()` 挑。前端不決定目的地，只決定哪一格。
* **`npc_faction_absorb` ＋ `player_rank`（15.13）**：`player_force_ranking()`
  掃戰術快照算各家總戰力，並列最高用 `self.random` 擇一。
  沒有快照、或全場戰力為 0 就不發這張卡。
* **`npc_faction_merge`（15.14／15.27）**：兵一營一營併進去，
  **戰力上限不因為併吞而放寬**，塞不下的記在 `overflow` 如實回報。

## 五、關鍵檔案與位置

行號是 2026-08-27 當下的，會漂——用函式名搜尋比較可靠。

### 後端

| 檔案 | 你要看的東西 |
| --- | --- |
| `backend/card_engine.py`（約 7,300 行） | 引擎本體 |
| └ `_trim_to_force` / `_cut_down_to_force`（約 1332 / 1353） | 裁兵的兩套規則，差別在「裁不裁過頭」 |
| └ `npc_reinforcements`（約 1387） | NPC 每回合例行補兵。**新機制的形狀都照它抄** |
| └ `_npc_general_index`（約 4703） | 將領中文姓名 → (陣營, 將領代號) |
| └ `npc_situation`（約 4713） | 各 NPC 陣營現況：還在的將領、還剩幾營 |
| └ `_living_npc_armies`（約 4749） | 還在場、還算自家人的 NPC 部隊 |
| └ `_npc_delta_targets`（約 4767） | 解析 general/generals/faction/except_generals |
| └ `npc_unit_delta_patch`（約 4811） | 絕對增減兵 |
| └ `npc_force_scale_patch`（約 4863） | 按比例增減戰力 |
| └ `_land_npc_army_patch`（約 4921） | 補丁落地：改後端那份＋掛前端佇列 |
| └ `_npc_requires_met`（約 4948） | NPC 進入條件判定 |
| └ `_event_eligible_players`（約 5011） | 這張卡現在誰抽得到；`known_conditions` 在這裡 |
| └ `_apply_event_payload`（約 5317） | **所有 `apply.*` 機制的分派點**，新機制加在這裡 |
| `backend/combat_modifiers.py` | 戰鬥加成的組裝。批次二 B 的主場 |
| `backend/server.py` | HTTP 端點；`SHARED_TACTICAL_STATE` 住這裡 |
| `backend/data_store.py` | 載入所有資料檔，含七份 NPC 將領樹 |
| `navy_system/navy.py` → `settle_carried_army` | 運輸船被擊沉時的兵力減損，減損類機制的參考 |

### 資料

| 檔案 | 內容 |
| --- | --- |
| `cards/data/event_cards.json` | 207 張事件卡。**唯一的卡片權威** |
| `general_tree/data/general_tree_npc_*.json` | 七份 NPC 將領樹（Y/G/M/H/C/D/Q） |
| `general_tree/data/general_tree_template.json` | **是測試夾具，不是遊戲資料**，別把它當將領池讀 |
| `comabt_system/data/general_traits.json` | 技能的基礎 modifiers（`hp` / `attack` / `harm_taken`） |

### 前端

| 位置 | 內容 |
| --- | --- |
| `frontend/app.js` `PENDING_EFFECT_HANDLERS`（約 521） | 後端交辦事項的**唯一消費點**。新 kind 一定要在這裡登記 |
| └ `npc_army_units`（約 556） | NPC 編制補丁：只做 `army.units = { ...entry.units }` |
| └ `consumePendingFrontendEffects`（約 583） | 消費＋銷帳 |
| `window.__neDebug`（檔尾） | 自動化檢查的掛勾。要驗什麼就從這裡挖 |

### 測試與文件

| 檔案 | 內容 |
| --- | --- |
| `backend/test_backend.py` | 1,049 項。`NpcConditionGateTests` / `NpcUnitDeltaTests` / `NpcForceScaleTests` 是這三批的 |
| └ `TestFileStructureTests` | 守著「檔案中段不准有 `unittest.main()`」——它已經抓到過我一次 |
| `cards/README.md` | **產生檔，不要手改**。改完卡要跑 `python3 scripts/build_event_card_table.py` |
| `scripts/build_event_card_table.py` | 上面那份的產生器 |
| `事件卡工作日誌/事件卡系統重建工作紀錄.md` | **完整的工作紀錄**。每批的決策理由、突變結果、踩過的坑都在裡面 |
| `scripts/checks/` | 單元測試之外的驗證層：重播、瀏覽器實跑、突變測試、指紋。有自己的 README |

---

## 六、每一批的收尾流程

少一步就不算做完。

所有非單元測試的驗證腳本都在 **`scripts/checks/`**（有自己的 README）。
它們原本住在 `/tmp/`，但那是容器暫存區、換個 thread 就沒了，所以搬進 repo，
而且 repo 根目錄是從腳本自己的位置推出來的，不寫死路徑。

```bash
cd <repo>

# 1. 卡片資料改完 → 重建 README（有測試守著同步）
python3 scripts/build_event_card_table.py

# 2. 全套測試（一定要用 -m unittest）
rm -rf backend/__pycache__          # 舊 bytecode 會餵你上一版的程式
python3 -m unittest backend.test_backend

# 3. 事件卡重播：逐張真的抽出來、真的回應完
python3 scripts/checks/event_replay.py        # 期望 crashed 為 0

# 4. 帶戰術快照的重播（NPC 卡要有快照才抽得到）
python3 scripts/checks/npc_delta_replay.py
python3 scripts/checks/npc_scale_replay.py
python3 scripts/checks/npc_batch3_replay.py
python3 scripts/checks/npc_batch4_replay.py

# 5. 真前端實跑（Playwright，證明前端那一段交接沒斷）
pkill -f "backend[.]server"         # 這行必須自己一行
python3 scripts/checks/npc_delta_e2e.py
python3 scripts/checks/npc_scale_e2e.py
python3 scripts/checks/garrison_report_e2e.py
python3 scripts/checks/npc_batch4_e2e.py

# 6. 突變測試（在背景跑，一輪約 90 秒 × 突變數）
nohup python3 scripts/checks/mutate_npc_force_scale.py > /tmp/mut.log 2>&1 &
```

### 突變測試務必注意

`scripts/checks/mutate_safe.py` 是安全版。**已經被外部逾時砍掉過三次**，
每次都在 `card_engine.py` 裡留下突變體。它現在會：

* 跑之前把基準 md5 與乾淨副本寫到 `/tmp/mutation_baseline.json`
  與 `/tmp/mutation_pristine.txt`；
* 每一輪結束**逐位元組**比對還原；
* 啟動時先檢查上一次有沒有留下殘骸，有的話自動從乾淨副本還原。

**不要用 `grep "if False"` 檢查有沒有殘骸**——不是每個突變體都長那樣，
以前就是這樣漏掉一個的。一律比 md5。

突變體預設打在 `backend/card_engine.py`。要打別的檔（例如 `combat_modifiers.py`）
就寫成四元組 `(名稱, 原字串, 新字串, 相對路徑)`，基準與乾淨副本會各檔各存一份。

**Bash 工具上限是 10 分鐘**，突變跑會超過。用 `nohup ... &` 丟到背景再輪詢，
不要讓它被逾時砍掉。

「逃掉的突變」幾乎都是**測試缺口**，不是死碼。已經發生四次，每次都是真的漏驗：
挑的測試數字剛好讓兩種算法撞在一起、或那條路徑根本沒有卡片走到。

### 同步到使用者本機

```bash
python3 scripts/checks/fingerprint.py .      # 產生整體指紋
```

`fingerprint.py` 會把每個檔案正規化行尾（CRLF→LF）後取 md5、排序、
再對整份清單取一次 md5，得到一個「整體指紋」。做法：

1. 在 clone 與裝置兩邊各跑一次，比對差異檔清單；
2. `SendUserFile` 送出異動檔 → `mcp__remote-devices__device_commit_files` 寫回
   `C:\Users\derry\OneDrive\Desktop\northern-expedition\...`；
3. 再算一次裝置指紋，**必須與 clone 完全相同**；
4. 最好在裝置上實跑一次新測試類別，證明送過去的檔案是活的。

裝置端路徑：`device_bash` 看到的是 `$HOME/mnt/northern-expedition`，
但 `device_commit_files` 要用 Windows 路徑。

---

## 七、踩過的坑（別再踩一次）

* **兩條線同時改同一份 repo，會安靜地互相蓋掉。** 曾經有另一個 thread 從
  批次零之前的版本分岔出去做批次二 B，寫回使用者本機時把批次零、一、二 A 的
  11 個函式整批抹掉——而工作紀錄沒有任何一筆提到這件事，
  只有逐檔比對才看得出來。**接手時先比對，不要假設本機一定比 clone 新。**
  比對方式：`scripts/checks/fingerprint.py` 兩邊各跑一次，
  差異檔用 `sed 's/\r$//'` 正規化行尾之後再 diff（本機是 Windows，CRLF 會讓整份檔案看起來全變了）。
* **不要對著想像中的資料形狀寫程式。** 那條線的批次三讀
  `state["shared_tactical_state"]` 裡的 `npc_armies` / `player_armies` / `army["city"]`——
  這四個鍵一個都不存在，所以招募會扣錢、會抽出贏家，但**部隊永遠不會轉手**，
  而且不會報錯。真正的形狀是 `self._tactical["armies"][部隊編號]`，位置欄位叫 `cellKey`。

* **讀程式碼不算驗證。** 每一句宣稱都要有實跑輸出。
  我曾經因為讀到一份還沒套用完的資料檔，就指控自己前一批的文件是捏造的——
  那份文件是對的，而我為了「修正」它跑了一支腳本，反而讓 5 張卡的報導縮水。
* **突變腳本污染原始碼**：見上一節。第二次還更糟——重跑時腳本把**已經被污染的檔案**
  當成基準讀進去，於是那一項變成「目標字串找不到，跳過」，看起來像設定問題。
* **`never_drawn` 與 `not_in_pool` 是兩回事。** 前者是「這張卡完全沒有效果」
  （保留給日蘇戰況報導），後者是「機制還沒建好，暫不進牌堆」。混用會打壞四條既有不變量。
* **舊的 `__pycache__` 會餵你上一版的 bytecode**，突變跑之前一定要清。
* **`/mnt/user-data/uploads/` 的快取可能是舊的**，要用 `device_bash` 的 md5 對過才算數。
* **`comabt_system/test_combat.py` 從 repo 根目錄跑會 `ModuleNotFoundError`**，
  要進到那個資料夾裡跑（14 項）。這是既有的路徑怪癖，不是你弄壞的。
* **「旗標寫進去了」不等於「機制存在」。** 這是這個專案最常見的缺陷形狀：
  `oil_price_immunity`、`npc_general_recruited`、`blocks_declaration`、
  `suppression_turn_bonus()`、`recover_battalions`、`lost_on_defection`
  ——全都是寫進去了、沒有任何讀取者。**grep 抓不準**（tuple、
  `LOYALTY_FUNCTION_CARD_IDS` 這種反推、JS 物件鍵都會製造誤報），
  **測試也不一定守得住**（`ContestedNpcRecruitTests` 整批綠燈，
  卻掩護著一條實戰永遠跑不到的多方競標規則，因為它手工塞好了 `responses`）。
  唯一可靠的判準是**跑一次真實情境，看那個數字有沒有變**。
  現在有兩組守門測試在防這一類：`OrphanedDataTests`（孤兒 mechanic／特質／技能）
  與 `SingleSourceOfTruthTests`（同一條規則兩份、只有測試在叫的公開方法）。
* **測試綠燈不等於規則可達。** 用手工塞好的狀態測結算邏輯，證明的是
  「餵它這個輸入會算對」，不是「玩家有辦法走到這個輸入」。
  牽涉到回應佇列、抽卡資格、卡池組成的規則，一定要從 `next_turn` 開始跑完整條路。
* **`_adjusted_city_output` 用的是 `int(round())`，也就是銀行家捨入**，
  所以 5 級城市在學潮下掉的是 60% 而不是 50%。
  **已回報、刻意沒改**——那是規則決定，等使用者裁示。

---

## 八、給接手 agent 的起手 prompt

把下面整段貼給新的 thread：

```
接手《北伐風雲》的 NPC 事件卡機制開發。clone 在 /tmp/ne，
使用者本機那份在 C:\Users\derry\OneDrive\Desktop\northern-expedition
（device_bash 看到的是 $HOME/mnt/northern-expedition）。

動工前先照順序讀完這些，讀完再說你打算怎麼做：

1. /tmp/ne/HANDOFF.md
   ——整份讀完。規矩、進度、下一步、收尾流程都在裡面。

2. /tmp/ne/事件卡工作日誌/事件卡系統重建工作紀錄.md
   ——至少讀最後三節（NPC 條件閘門、批次一 npc_unit_delta、
     批次二 A npc_force_scale）。每個決定的理由與突變結果都在那裡，
     不讀會重新發明已經被否決過的作法。

3. /tmp/ne/backend/card_engine.py
   ——搜這幾個函式讀懂現有的 NPC 機制：
     npc_reinforcements、npc_situation、_living_npc_armies、
     _npc_delta_targets、npc_unit_delta_patch、npc_force_scale_patch、
     _land_npc_army_patch、_npc_requires_met、_event_eligible_players。
     還有 _apply_event_payload——所有 apply.* 機制的分派點，新機制加在那裡。

4. /tmp/ne/backend/combat_modifiers.py
   ——整份讀完。下一批（15.2 / 15.20 / 15.22 / 15.23）的主場。
     特別看 CombatModifierBuilder.timed_modifiers() 與 build()。

5. /tmp/ne/frontend/app.js 的 PENDING_EFFECT_HANDLERS 區塊
   ——搜 "PENDING_EFFECT_HANDLERS"，讀到 consumePendingFrontendEffects 結束。
     這是後端交辦事項的唯一消費點。

6. /tmp/ne/backend/test_backend.py 的 NpcUnitDeltaTests 與 NpcForceScaleTests
   ——搜類別名。看驗到什麼程度才算過關。

7. /tmp/ne/scripts/checks/README.md
   ——單元測試之外的驗證層怎麼跑。每一批收尾都要跑完那幾支。

8. /tmp/ne/cards/data/event_cards.json
   ——別整份讀（很大）。用腳本把 ref 開頭是 15. 的卡連同
     effect / entry_condition / apply 印出來就好。

這一輪（空轉機制稽核）新增的驗證腳本：
* `scripts/checks/mutate_dead_mechanism_audit.py`（16 個突變體）
* `scripts/checks/dead_mechanism_e2e.py`（真前端：宣戰鈕、暴動門檻、進度顯示）

四條底線，違反等於白做：
* 絕不推 main，一律 feature branch + PR。
* 絕不在使用者本機那份 repo 裡跑任何 git 指令。
* 誠實回報，嚴禁捏造進度——讀程式碼不算驗證，每句宣稱都要有實跑輸出撐著。
* 本質屬於後端的計算只能在後端，同一條規則不准前後端各寫一份。

NPC 事件卡這條線**已經做完了**：33 張全部上線，apply.pending 清空，
後端 1182 項測試全綠。所以你多半是來改規則或修 bug 的，不是來補新機制的。

改任何東西之前先跑一次收尾流程（HANDOFF.md 第六節），確認現況真的是綠的；
改完也照那份流程走一遍，尤其別跳過突變測試——這個專案裡它挖出過真漏洞，
不只是形式。

另外：動工前務必先比對 clone 與使用者本機。曾經有另一條線從舊版分岔出去，
把三個批次的工作安靜地蓋掉了——細節在 HANDOFF.md 第七節第一條。
```
