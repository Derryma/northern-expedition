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
* **前端把「加減」加在畫面顯示值上，是這個專案最貴的一種錯。** 忠誠加減先前
  `override = 顯示值 + 幅度`，而 override 是後端 compute_loyalty 的**基礎值**輸入；
  後端拿它再套一次相對實力與戰損，於是「+2」在弱軍身上實際變成 **+0**。
  凡是「某個值 + 幅度」的規則，加的是哪一個量必須講清楚，而且只能在後端加。
* **摘要寫不出來 ≠ 卡沒有效果。** 出牌摘要少一個描述分支，畫面就會說
  「無效果，浪費一次出牌」——後端其實已經扣過錢、效果也生效了。
  現在有測試逐一比對「後端回傳的每個欄位都有描述分支」，而且檢查的是**判斷式本身**
  （只檢查字串會被 `if (false) {` 騙過去）。
* **「只在還沒收到後端結果時當過渡值」＝第二套規則。** 忠誠、策反成本與成功率、
  技能失效判準、每一個規則數字的「退路值」——這些全都掛著這種註解，
  而且全都會在後端還沒答話時安靜地端出自己算的答案。
  現在的規矩是：拿不到後端的值就顯示「—」，不猜、不自己算。
  守門的是 `BackendIsTheOnlyEngineTests`（全檔搜字串：公式片段、表名、裸數字）
  與 `scripts/checks/backend_drives_ui_e2e.py`（隨機調後端數字看畫面跟不跟得動）。
* **驗這一類不要比對兩邊算出同一個值。** 那不是單一來源，那是兩份規則加一個看門的。
  要驗就把後端的數字改成一個前端猜不到的怪值，看畫面跟不跟得動。
* **e2e 之前先確認埠是空的。** 上一輪沒收掉的伺服器還佔著 8766 時，
  新的綁不上就死了，而輪詢對著舊的立刻成功——整份量測都是對舊伺服器做的，
  看起來像產品壞了。
* **量法錯了會讓對的程式看起來是錯的。** 「每家表態」的事件卡會被
  `pending_event_view` 回傳好幾次（一次一個回應者）；把每次回傳都當成一次抽卡，
  抽卡順序的報告就會出現一堆假的不符。量之前先想清楚一次到底代表什麼。
* **沒人讀的資料檔會安靜地變成假的，而它看起來仍然像規則書。**
  `NPC/data/npc_factions.json` 的起始部隊少了 7 支、川軍兩支的駐地是舊的；
  `card_pool_rules.json` 的親衛隊那一節描述的是一個從未實作過的設計；
  `foreign_powers.json` 有五條沒有實作的「懲戒戰爭」規則。
  **掃空轉機制時不要只掃卡片資料檔**——第一輪就是這樣漏掉這四份的。
* **同一個數字出現三次也不會有人發現。** 每營 HP／戰力點／攻擊矩陣曾經在
  `unit_stats.json`、`combat.py`、`card_engine.py` 各一份，三份剛好相同。
  驗這一類只能用「改資料檔看數字跟不跟得動」——**比對數值的測試抓不到**，
  突變測試就是這樣逃掉一項的。
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

空轉機制稽核新增的驗證腳本：
* `scripts/checks/mutate_dead_mechanism_audit.py`（16 個突變體）
* `scripts/checks/mutate_second_audit.py`（11 個突變體，第二輪）
* `scripts/checks/mutate_draw_order.py`（8 個突變體，NPC 卡優先抽）
* `scripts/checks/mutate_backend_only_engine.py`（8 個突變體，後端唯一計算引擎）
* `scripts/checks/backend_drives_ui_e2e.py`（隨機調後端數字，驗畫面即時跟動；
  搭配測試用啟動器 `_probe_server.py`）
* `scripts/checks/mutate_loyalty_and_tags.py`（11 個突變體：忠誠加減、地格標籤、偵查、摘要）
* `scripts/checks/loyalty_and_tags_e2e.py`（真前端：忠誠加減、崩鐵玩家摘要、
  地格癱瘓標籤、情報局擋情報網）
* `scripts/checks/dead_mechanism_e2e.py`（真前端：宣戰鈕、暴動門檻、進度顯示、
  艦艇修理四關、三張黑幫暴動卡的標籤）
* `scripts/checks/blocking_and_npc_transfer_e2e.py`（真前端 29 關：鐵路與急行軍
  被敵軍阻截、急行軍支援 2 格外的戰鬥、NPC 轉屬／招募／歸附重編番號與換將領樹、
  吞併類的城市與地格真的易主）
* `scripts/checks/mutate_blocking_and_npc_transfer.py`（14 個突變體。這一輪改的
  幾乎全在前端，所以判定器不是單元測試而是上面那支 e2e——`mutate_safe.main()`
  現在收 `runner=` 參數就是為了這個。讀原始碼的字串斷言擋不住 `if (false) {`，
  跑瀏覽器的擋得住。）

這一輪（卡的效果落到畫面上）新增的驗證：
* `scripts/checks/card_effects_land_e2e.py`（真前端 10 關：**按真的按鈕**打忠誠卡、
  跑城市等級事件卡、跑 NPC 吞併，檢查畫面數字真的動了、而且提示不是例外訊息）
* `scripts/checks/mutate_card_effects_land.py`（7 個突變體。判定器同時跑
  `EveryCalledFunctionExistsTests` 與上面那支 e2e——只跑其中一個會有突變體逃掉）
* `backend/test_backend.py` 的 `EveryCalledFunctionExistsTests`——守「**叫了但沒人定義**」。
  這是「寫了但沒人讀」的雙胞胎，而且更兇：ReferenceError 會把整段處理器打斷，
  後面的重畫全部不跑，於是卡明明生效了、畫面卻停在原地。合併兩條開發線之後
  一次就出現兩個（refreshBackendDerivedState、renderMapUnits）。

前後端同步稽核（第十六批）新增的驗證：
* `scripts/checks/mutate_sync_audit.py`（7 個突變體：交辦流水號、逐筆銷帳、
  重複套用、版本推進、存檔目錄隔離、重畫函式）
* `backend/test_backend.py` 的 `FrontendBackendSyncTests`——守四件事：
  後端每條路由都要有人呼叫；交辦一定要蓋流水號並逐筆銷帳；伺服器改動共享
  狀態時要推進版本；**驗證腳本不准寫進玩家的存檔目錄**（用 NE_GAME_DATA_DIR）。

  最後一條是實跑的：設環境變數、reload 模組、確認路徑真的跟著換。
  先前只斷言原始碼裡有那個字串——註解裡也有，所以永遠通過。

省界與省級歸屬（第十七批）新增的驗證：
* `scripts/checks/province_ownership_e2e.py`（真前端 14 關：逐格量四川、
  陝西南部、甘肅東南、察哈爾、青海的歸屬，量西北軍四個軍的駐地，
  再把地圖推上後端確認 `cellFactions` 一致）
* `scripts/checks/mutate_province_ownership.py`（8 個突變體）
* `scripts/checks/province_map_screenshots.py`（存證截圖，不判定）
* `backend/test_backend.py` 的 `ProvinceBordersAndOwnershipTests`

  這一輪把「某省全境歸某陣營」從手描的控制圈裡抽出來，寫成 `frontend/map.js`
  的 `PROVINCE_OWNERSHIP_CLAIMS`，開局時拿真正的省界幾何逐格判定。
  省界因此只剩一份（`frontend/data/provinces_1926.geojson`），
  不會出現「省界改了、勢力界沒跟上」這種兩份幾何互相打架的情況。

  e2e 裡「條款以外全圖一格都沒動」那一關拿 `factionAt()` 當基準，
  所以不必在測試裡寫死任何一個會過期的格數。

  城市落點對地格歸屬很敏感：`indexScenarioCells()` 是先篩同陣營的格子再取最近的，
  所以地格一改色，城市就可能在畫面上跳一格。防線有三層——套用條款時護著別家
  城市腳下那一格、城市名冊的 `cell_key` 釘選、以及 `CELL_OWNERSHIP_OVERRIDES`
  這張逐格例外表。改地格歸屬之前先看一眼這三層。

陣營吞併／歸屬轉移（第十八批）新增的驗證：
* `scripts/checks/faction_transfer_e2e.py`（21 張卡逐張打真的 HTTP，
  而且刻意在 next-turn 與 respond-event 中間換一份新快照上去——那正是競態）
* `scripts/checks/mutate_faction_transfer.py`（8 個突變體）
* `backend/test_backend.py` 的 `FactionTransferTacticalTests`

  修的是一個一直在跑的缺陷：這些卡全部在 `respond_event()` 裡結算（卡片的
  `apply` 要等每一家都回應完才跑），而 `self._tactical` 先前只有 `next_turn()`
  會設。前端每推一次共享狀態，`SHARED_TACTICAL_STATE` 就換成新的一份，
  引擎手上那個變成孤兒——卡片回報吞併成功、地圖一格沒動，而且時好時壞。

  現在「伺服器現在手上那一份」只有 `current_tactical()` 一個定義，
  `_run_route()` 在每個路由跑之前都重新綁一次。**不要把它存起來重複用。**
  拿不到快照時一律記 `*_skipped` 並附 `reason`，不准靜靜跳過。

排空競態與腳本埠號（第十九批）新增的驗證：
* `scripts/checks/mutate_drain_race.py`（6 個突變體）
* `backend/test_backend.py` 的 `DrainRaceTests`、`CheckScriptPortTests`
* `scripts/checks/faction_transfer_screenshots.py`（隨機觸發吞併／轉移卡並截圖）

  排空（`consumePendingFrontendEffects`）中間全是 await，而背景同步每 1.2 秒
  跑一次。它只要在那些空檔裡 pull 一次，就會把「已經套用、還沒推上去」的
  結果蓋掉——而流水號已經記進 `appliedFrontendEffectIds`，下一次只會補銷帳、
  不會重做，效果永久消失。現在排空期間背景同步讓路（`drainInFlight`），
  而且排空做完自己發佈一次。

  同時修掉驗證腳本互相踩埠：一支一個埠、啟動的埠就是輪詢的埠、綁不上要出聲。
  共用埠會製造假紅與假綠，那比壞掉更難查。

NPC 那一半的世界（第二十批）新增的驗證：
* `scripts/checks/mutate_npc_visible_state.py`（5 個突變體）
* `backend/test_backend.py` 的 `NpcVisibleStateTests`
* `scripts/checks/card_effect_screenshots.py`（指定卡逐張跑並截圖，含地格、
  城市浮窗與鐵路狀態；不判定，只存證）
* `scripts/checks/card_effects_land_e2e.py` 長到 18 關（多了 NPC 城市等級三關）

  這一輪的缺陷是同一個形狀的兩個實例：**畫面只更新玩家自己那一半的世界**。
  `syncStrategicCitiesFromState()` 先前只讀各玩家的 `city_economy`，所以
  〈黔軍整頓茅台酒造〉把遵義升到 3 級之後，後端的 `city_level_overrides`
  有寫、畫面永遠停在 2 級——因為遵義不屬於任何玩家。現在等級的權威來源是
  後端的覆寫表，覆寫解除時回到開局基準（`baseCityLevels`），
  `city_economy` 只在沒有覆寫時當備援。

  第二個：鐵路停擺的**理由**先前只有後端知道，前端一律寫「搶修中」，
  於是〈閻錫山封鎖窄軌鐵路〉這種永久封鎖看起來像是修得好的。
  後端的 `railway_access()` 現在多回一份 `disabled_detail`
  （`permanent` / `no_repair` / `until_general_leaves`），
  前端只負責把它翻成字——判斷仍然只在後端。

  留給下一個人的判準：改任何後端狀態之前先問一句「這東西**不屬於玩家**的時候，
  畫面靠什麼知道它變了？」。答不出來就是又一個這種 bug。

後端知道、玩家看不到（第二十一批）新增的驗證：
* `scripts/checks/world_visibility_e2e.py`（真前端 25 關，埠 8794）
* `scripts/checks/mutate_world_visibility.py`（14 個突變體）
* `backend/test_backend.py` 的 `WorldVisibilityTests`（13 項）

  上一批修完之後做的全面稽核，又挖出三個同一家族的缺陷：

  **一、`remaining_turns` 為 null 在後端是「無限期」，前端當成「已結束」。**
  前端在八個地方各寫一份 `Number(remaining_turns || 0) > 0`，於是每一種永久
  效果在畫面上一律被當成過期：〈閻錫山封鎖窄軌鐵路〉兩條線全停，「持續效果」
  清單一筆都不列；廢兩改元的永久免疫同理。現在判準只有一份——後端在
  `snapshot()` 裡替每一筆限時效果蓋 `active`，前端只讀 `effectActive()`。
  **不要再在前端寫任何一條 `remaining_turns` 的判斷。**

  **二、擋得住卻不說。** 被事件按住的功能卡（`perk_suspensions`）與被禁掉的
  行動（`action_bans`），後端本來就會在路由上擋下來，但畫面按鈕照樣亮著，
  玩家按下去才收到例外訊息。後端現在送 `blocked_cards` / `blocked_actions`
  （判準仍只在後端），前端負責把按鈕關掉並寫出理由。

  **三、變無主卻沒人知道。** 列強「地面部隊佔領」的懲戒解除時，後端把城市從
  `city_owners` **移除**——可是引擎裡到處都是 `.get(id, city["faction"])`，
  鍵一不見，回退值就把城市悄悄還給 1926 劇本的原主（很可能是別家玩家），
  而那份 `ownerless_cities` 名單全專案沒有人讀，地圖一格都沒動。現在記成
  `city_owners[id] = None`（＝沒有主人），`ownerless_cities()` 由它算出來，
  解除時開一筆 `cities_became_ownerless` 交辦讓畫面中立化，無主之地任何一家
  都可以直接進去佔領。

  順帶清掉兩個「存了沒人讀」：`npc_accounts`（整份死狀態，已移除，
  `WorldVisibilityTests` 有守門）與前端自己重算的 `cityPunishmentStatus`
  （改讀後端的 `city_punishment_status`）。

  稽核方法留在這裡，下次照做：把後端 `state` 的每一個鍵列出來，數它在
  引擎、測試、前端各出現幾次；只出現在寫入處的就是空轉，只出現在後端而
  「玩家理當要看到」的就是這一類缺陷。`comprador_deflections` 與
  `assassination_log` 前端零引用是**刻意**的（查帳用），不要順手刪。

卡面 vs 實作 vs 畫面（第二十二批）新增的驗證：
* `scripts/checks/world_visibility_e2e.py` 長到 38 關
* `scripts/checks/mutate_world_visibility.py` 長到 25 個突變體
* `backend/test_backend.py` 的 `EffectsReachThePlayerTests`（10 項）、
  `OccupationVersusDrillStateTests`（8 項）

  **稽核方法（下次照做）**：把每張事件卡的 payload（含 resolution 每個選項）
  套進一局乾淨的引擎，比對前後的 `snapshot()`，列出它真正改了哪些鍵，
  再問前端有沒有讀那個鍵。207 張裡有 36 張的改動**全部**落在前端讀不到的地方。
  腳本留在 `/tmp` 不進 repo，但方法就是這三步，很容易重寫。

  修掉的四件：

  1. **戰鬥加成算了一整套，畫面一個字都沒有。** `combat_adapter` 回傳
     `applied_modifiers`，註解還寫著「讓前端照著顯示」——而 `app.js` 只把它存進
     `battle.appliedModifiers` 之後**再也沒有人讀**。技能、光環、限時效果、
     要塞、NPC 事件（15.2 傅作義加固城防那一類）全部在暗地裡改數字。
     現在後端替每一項貼上中文說明（`CombatModifierBuilder._modifier_label`），
     前端在戰鬥面板列出來。**新增修正項來源時記得補 `_modifier_source`。**
  2. **事件卡改寫功能卡的數字，手上那張卡還印著舊數字。** 卡面 `effect` 是靜態
     文字，〈飛鳥非鳥案〉把〈盜賣文物〉收益永久改成 $30～60 之後畫面照舊。
     後端新增 `card_field_changes`（解算後的卡 vs 資料檔原卡），前端在卡片下面
     補一行「事件改寫：收益下限 $20 → $30」。
  3. **單一銀行被事件停貸，借款面板照樣印「可借」。** `take_loan()` 會擋，
     但 `loan_offers()` 只處理玩家層級的 `loan_ban_until_turn`，漏了
     `bank_bans`。現在 offer 上帶 `bank_ban`，面板寫理由、收掉借款鈕。
  4. **鐵路交涉的代價寫「沿線每座城市」，實作卻是整個省。** 12.58／12.59／12.60
     的 `city_output.select` 從 `provinces` 改成新的 `railways` 選擇器
     （`cities_along_railways()`，門檻 0.9 度是量出來的，落選者最近 1.08 度）。

  還沒動、但已經知道的：`event_locks`、`scheduled_event_effects`、
  `function_card_freezes`、`perk_copy_bonuses`、`student_unrest_relief`、
  `unlocks` 這幾類改的是**未來的抽牌機率與卡池組成**，當下畫面沒有東西可以動。
  要補的話是加一塊「全場效果」清單，不是改這些機制本身。

佔領與演習是兩種狀態（第二十二批）：

  先前兩者共用 `kind: "ground_occupation"` 加一個 `drill` 布林，於是**演習也算進
  「先來後到」的爭奪**：一場日方演習就能把蘇聯的真佔領擋在門外，範圍重疊時還會
  照日蘇開戰規則打一仗、把戰損算在玩家頭上——而卡面白紙黑字寫著
  「演習不是懲戒：不造成任何傷害」。

  現在 `mode` 是明白的欄位（`punishment` / `drill`），另有 `release_rule`
  （`becomes_ownerless` / `returns_to_owner`）：

  * `occupied_provinces()` 只算真的佔領（先來後到與日蘇開戰用它）；
  * `drilled_provinces()` 是另一層；
  * `ground_controlled_provinces()` 是兩者的聯集，收入歸零、部隊被鎖、
    地圖換色用它（卡面兩種都寫了「期間金錢與工廠收入歸零」）；
  * 前端 `punishmentIsDrill()` / `punishmentReleaseNote()` 把差別寫在地格資訊上，
    佔領區是實線、演習區是虛線。

  **不要再用 `entry["drill"]`**：`is_drill(entry)` 是唯一的判準（舊存檔才回退看
  那個布林）。

**絕對不要在這份 clone 裡跑 `git checkout <檔案>`。** repo 的 HEAD 落後工作區
很多（這條線從來不 commit，改動是直接同步到使用者本機的），`git checkout` 會把
檔案還原成好幾個批次以前的版本——這次就把 207 張的 `event_cards.json` 還原成
59 張，靠使用者本機那份救回來的。要比對就跟本機比指紋，不要動 git。

**改了地圖或駐防之後，使用者說「我這邊沒更新」——先看存檔，不是先看同步。**

`game_data/tactical_state.json` 存著 `cellFactions`、`armies`、`cityFactions`。
前端開機時先照 `map.js` 建一張新地圖，接著 `pullSharedState()` 會用存檔**整個蓋掉**
地格歸屬與部隊位置。所以任何動到 `map.js`／`strategic_map.json`／省界的改動，
對**進行中的舊存檔一律看不到**——檔案同步得再乾淨也一樣。

判斷方法（實測過，不要用猜的）：拿一份乾淨存檔目錄開個 server、無頭開一次頁面，
把 `cells` 的各家格數與四個軍的 `cellKey` 印出來，跟使用者的存檔比。
差很多就是存檔太舊，讓他開新局（或把 `game_data/tactical_state.json` 搬走）。

`device_bash` 刪不掉檔案，所以要搬到 `_to_delete/`，不是 `rm`。

新局與省份命名（第二十三批）：使用者回報「開了新局，除了駐軍以外地格還是沒變」
以及「甘青省界出來了，但青海境內還是屬於甘肅」。兩個獨立的病根，
形狀一樣——**一份在權威計算之前拍的快照／清單，蓋掉了正確答案**：

* `INITIAL_CELL_FACTIONS`（已改名 `SCENARIO_CELL_FACTIONS`）是 **module load**
  時抓的，而 `applyProvinceOwnershipClaims()` 是 `boot()` 裡才跑的。
  `resetGame()` 把 `cell.fac` 寫回那份快照，等於把整套省級歸屬保證抹掉：
  實測按一次新局，川軍 64→52、西北軍 140→124、馬家軍 69→75、直系 57→69，
  **正好回到條款套用之前的樣子**。部隊照樣重新入城，所以症狀是
  「駐軍變了、地格沒變」。現在還原之後一定要再跑一次 `indexProvinceCells()`。
* `strategicProvinceForCell()` 拿 `provinceOptions()`（＝**有城市的**省份）
  當判準。青海整省一座城都沒有（西寧照舊民國地圖歸甘肅），於是
  `provinceAt()` 明明答對了「青海」也不算數，一路掉到「最近的城市是哪一省」
  → 西寧 → 甘肅。**有沒有城市不是省份存在與否的判準**，改讀省界檔
  （`mapProvinceNames()`）。

守門在 `NewGameAndProvinceNamingTests` 與 `province_ownership_e2e.py`
（新增 4 關，其中一關專門斷言「青海真的一座城都沒有」——沒有那一關，
另外兩關驗不到東西）。

**教訓照抄**：`const X = 從 cells 算出來的東西` 寫在檔案頂層，就是一顆定時炸彈——
它抓的是 map.js 剛建完的樣子，不是 boot() 跑完的樣子。要「回到開局」就重跑
boot 的那段順序，不要還原快照。

產能、戰力與規則歸屬（第二十四批）：

* **城市升級了，產能沒跟上。** 等級讀 `city_level_overrides`（全圖都有）、
  產出卻只讀 `city_economy`（只有玩家自己的城），於是升級卡打在 NPC 手上的城，
  標籤變成「3 級城市」、產出還印著 2 級的數字。後端新增
  `city_output_report()`（全圖每一座城的等級＋產出，與 `_strategic_map_snapshot`
  同源），前端只讀 `state.city_output`。
* **削兵的規則前後端各寫一套，答案不一樣。** 列強懲戒的「範圍內部隊戰力一次性
  −40%」由前端動手（部隊住在前端），但**怎麼裁**是規則：後端的
  `_cut_down_to_force` 每一步只裁「裁下去還不會低於 target」的最貴兵種，
  前端卻是「從最貴的裁到不超過目標為止」——37 點打 −40%，後端 22、前端 21，
  砲兵多的部隊差更多。那正是後端那支函式的註解一開始就在警告的事。
  現在開了 `/api/cut-force`，前端改打那條路由。**部隊住在前端不代表裁法也在前端。**
* **將領直屬名額（大將 3、中將 2、少將 0、中將上限 3）只寫在 app.js。**
  後端連〈擴編直屬〉的上限都無從把關。搬進 `FEATURES["general_slots"]`，
  `use_function` 收前端送上來的 `current_slots`（將領樹住在前端，只有它數得出來）
  並在後端判上限——**前端送事實，後端判規則**。
* 技能中文名在 `general_traits.json` 與 `app.js` 各有一份（目前一致）。
  加了一條測試，等它們哪天開始不一致就會叫。

**省級歸屬保證只在開局播種一次**（`boot()` 與 `resetGame()`，只有這兩處）。
它**不是**每次重畫都跑的規則——跑第二次會把玩家打下來的地盤還給原主。
`province_ownership_e2e` 現在有一組「佔領之後走完一輪（推回後端／換回合／重畫）
歸屬沒有被還回去、同省其他格一格沒動、地格屬性沒被弄壞」的驗證守著。

兵力復活、解鎖鏈、免疫／封鎖（第二十五批）：

* **12.49〈國際紅十字救護團〉只補 1 營，卡面寫的是 2。** 資料檔寫了
  `timed_flags[].units: 2`，但 `_field_hospital_battalions()` 只認功能卡的
  `recover_battalions`，那個欄位**從來沒有人讀**。現在事件卡開的全軍醫院讀旗標上的
  `units`，與盤尼西林同時在場時取多的那一份。畫面的「+N 營」也改成讀後端送的
  `picked`（先前一律寫 +1，補兩營也寫 1）。
* **綁省份的免疫（10.8 復興儒學）擋得住卻不說。** `use_function()` 會擋，
  但「指定將領」的下拉照樣把免疫的目標列出來。後端新增 `immune_targets()`
  （判定仍只有 `province_card_immunity()` 一份），畫面把那些選項關掉並標
  「✕ 復興儒學免疫」。
* 解鎖鏈**六條全通**（3.1/3.2/6.2/7.1/7.4/8.4）：事件給旗標 → 功能卡洗進牌庫 →
  解鎖前打出去會被擋，訊息寫得出是哪一張事件卡。`event_goddard_rocket` 沒有
  功能卡在等它是**刻意的**（它是要塞砲戰的修正開關，`situational_modifiers` 讀），
  守門測試把它列為例外。

**一個給自己的提醒**：`conditional_branch`（9.5／10.1／10.3）的 `if_active`
需要 `drawn AND active`，而 `drawn` 看的是 `event_history`——那是
`respond_event()` 才會寫的。**繞過抽卡流程直接 `_apply_event_payload` 會讓它
走 `otherwise`**，看起來像 bug 其實不是。驗這三張卡一定要走真的抽卡路徑
（`RevivalUnlockAndImmunityTests._draw`）。我這一輪差點把它報成缺陷。

四條底線，違反等於白做：
* 絕不推 main，一律 feature branch + PR。
* 絕不在使用者本機那份 repo 裡跑任何 git 指令。
* 誠實回報，嚴禁捏造進度——讀程式碼不算驗證，每句宣稱都要有實跑輸出撐著。
* 本質屬於後端的計算只能在後端，同一條規則不准前後端各寫一份。

NPC 事件卡這條線**已經做完了**：33 張全部上線，apply.pending 清空，
後端 1332 項測試全綠。所以你多半是來改規則或修 bug 的，不是來補新機制的。

改任何東西之前先跑一次收尾流程（HANDOFF.md 第六節），確認現況真的是綠的；
改完也照那份流程走一遍，尤其別跳過突變測試——這個專案裡它挖出過真漏洞，
不只是形式。

另外：動工前務必先比對 clone 與使用者本機。曾經有另一條線從舊版分岔出去，
把三個批次的工作安靜地蓋掉了——細節在 HANDOFF.md 第七節第一條。
```
