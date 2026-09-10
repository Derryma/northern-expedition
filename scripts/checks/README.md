# 驗證用的腳本

`backend/test_backend.py` 是單元測試，這裡是**單元測試之外**的那幾層——
真的把卡抽出來跑完、真的開瀏覽器點一遍、真的把程式改壞看測試會不會紅。

這些腳本原本住在 `/tmp/`。那是容器的暫存區，換一個 thread 就沒了，
於是交接文件會指到一堆不存在的路徑。搬進 repo 之後它們跟著同步走，
而且 repo 根目錄是**從腳本自己的位置推出來的**，不寫死路徑。

| 腳本 | 做什麼 |
| --- | --- |
| `event_replay.py` | 207 張事件卡逐張抽出來、逐張回應完，看有沒有炸掉或完全不動後端。判準是回應前後 snapshot 差在哪，不是「程式碼看起來有沒有處理」 |
| `npc_delta_replay.py` | 7 張 `npc_unit_delta` 卡走完整的抽卡→讀報→回應，看編制真的變了沒 |
| `npc_scale_replay.py` | 6 張 `npc_force_scale` 卡同上，看戰力點真的變了沒 |
| `npc_delta_e2e.py` | Playwright 開真前端跑 15.8，證明後端算完之後**畫面上那支部隊**真的多了兵 |
| `npc_scale_e2e.py` | 同上，跑 15.11，證明戰力點真的被砍了 |
| `mutate_safe.py` | 突變測試的骨架（安全版，見下） |
| `mutate_npc_unit_delta.py` | 批次一的 12 個突變體 |
| `mutate_npc_force_scale.py` | 批次二 A 的 10 個突變體 |
| `blocking_and_npc_transfer_e2e.py` | Playwright 開真前端 29 關：鐵路與急行軍被敵軍阻截、急行軍支援 2 格外的戰鬥、NPC 轉屬／招募／歸附重編番號與換將領樹、吞併類的城市與地格真的易主 |
| `mutate_blocking_and_npc_transfer.py` | 上面那一輪的 14 個突變體。**判定器是 e2e 不是單元測試**——前端行為靠讀原始碼的字串斷言擋不住 `if (false) {` |
| `card_effects_land_e2e.py` | 真前端 10 關：按真的按鈕打忠誠卡、跑城市等級事件卡、跑 NPC 吞併，檢查畫面真的跟著動 |
| `mutate_card_effects_land.py` | 上面那一輪的 7 個突變體（判定器＝單元測試 + e2e 兩者一起跑） |
| `mutate_sync_audit.py` | 前後端同步稽核那一輪的 7 個突變體 |
| `fingerprint.py` | 算「整體指紋」，用來確認 clone 與使用者本機完全一致 |

## 存檔目錄

伺服器會把戰術狀態存到 `game_data/` 並在啟動時載回來。**驗證腳本一律用
`NE_GAME_DATA_DIR` 指到自己的 tmp 目錄**，理由有兩個：不隔離的話每次起伺服器
都會接續玩家上一盤棋，檢查會安靜地變成空轉；而且跑一次測試就把玩家的存檔蓋掉。
`FrontendBackendSyncTests` 會守著這一點。

## 怎麼跑

```bash
cd <repo>

python3 scripts/checks/event_replay.py            # 期望 crashed 為 0
python3 scripts/checks/npc_delta_replay.py
python3 scripts/checks/npc_scale_replay.py

pkill -f "backend[.]server"                       # 這行必須自己一行
python3 scripts/checks/npc_delta_e2e.py
python3 scripts/checks/npc_scale_e2e.py
python3 scripts/checks/blocking_and_npc_transfer_e2e.py   # 期望 29/29

python3 scripts/checks/fingerprint.py .           # 整體指紋
```

## 突變測試

```bash
# 一輪約 90 秒 × 突變數，會超過 Bash 工具的 10 分鐘上限，所以丟背景再輪詢
nohup python3 scripts/checks/mutate_npc_force_scale.py > /tmp/mut.log 2>&1 &
```

`mutate_safe.py` 叫「安全版」是有原因的：**它的前身被外部逾時砍掉過三次，
每次都在 `card_engine.py` 裡留下一個突變體。** 其中一次更糟——重跑時腳本把
已經被污染的檔案當成基準讀進去，於是那一項顯示「目標字串找不到，跳過」，
看起來像設定問題而不是災難。

現在它會：

* 跑之前把基準 md5 與**乾淨副本**寫到 `/tmp/mutation_baseline.json`
  與 `/tmp/mutation_pristine.txt`；
* 每一輪結束**逐位元組**比對還原，對不上就 assert 掉；
* 啟動時先檢查上一次有沒有留下殘骸，有的話自動從乾淨副本還原。

**不要用 `grep "if False"` 之類的方式檢查有沒有殘骸**——不是每個突變體都長那樣，
以前就是這樣漏掉一個的。一律比 md5。

寫新的突變體時注意：`orig.count(old)` 必須剛好是 1，否則腳本會報
「目標出現 N 次，跳過」。**縮排要照抄檔案裡真正的縮排**，我為此白跑過一輪。

「逃掉的突變」幾乎都是**測試缺口**，不是死碼——目前六次全部都是真的漏驗，
例如測試挑的數字剛好讓兩種算法算出同一個答案；
最近兩次是「限時旗標到期了還算數」，以及「把常數寫回同樣的字面值」——
後者特別要注意：**比對數值的測試抓不到「又變成寫死的副本」**，
只有「改資料檔看數字跟不跟得動」才抓得到。

## 空轉機制稽核（這一輪新增）

```bash
# 16 個突變體，約 32 分鐘，一定要丟背景
nohup python3 -u scripts/checks/mutate_dead_mechanism_audit.py > /tmp/mut_audit.log 2>&1 &

# 真前端：非戰公約的宣戰鈕、治安期的暴動門檻、暴動進度顯示
python3 scripts/checks/dead_mechanism_e2e.py
```

守「寫進去了卻沒人讀」這一類缺陷的兩組單元測試在 `backend/test_backend.py`：

* `DeadMechanismAuditTests` —— 六條被修好的規則，每條都從 `next_turn` 跑完整條路。
* `OrphanedDataTests` / `SingleSourceOfTruthTests` —— 孤兒 mechanic／特質／技能的白名單，
  以及「同一條規則不准兩份」。

**資料檔的守門測試要做負向檢查**：把缺陷放回去一個，確認它真的會紅。
只看綠燈不算數——這種測試很容易寫成永遠成立的形狀。

## 第二輪稽核（黑幫暴動一致性＋沒人讀的資料檔）

```bash
# 11 個突變體，約 22 分鐘
nohup python3 -u scripts/checks/mutate_second_audit.py > /tmp/mut2.log 2>&1 &

# 真前端：宣戰鈕、暴動門檻、進度顯示、艦艇修理四關、三張暴動卡的標籤
python3 scripts/checks/dead_mechanism_e2e.py
```

對應的單元測試：

* `GangRiotCardsBehaveIdenticallyTests` —— 三張黑幫暴動卡**逐張跑**過每一條會碰到
  它們的機制。加第四張卡進來時，任何一條沒蓋到都會紅。
* `SecondSourceOfTruthTests` —— 那幾份「看起來是資料、其實沒人讀」的檔案
  （NPC 名冊、海軍規則、戰鬥數值、卡池規則、列強全域規則）與真源對死。

**掃描時不要只掃卡片資料檔。** 第一輪就是這樣漏掉 NPC 名冊、海軍規則、
戰鬥數值與列強全域規則的——而漏掉的那幾份恰好是 drift 最嚴重的。


## 省界與省級歸屬（第十七批）

```bash
# 真前端逐格量：四川、陝西南部、甘肅東南、察哈爾、青海，加上西北軍四個軍的駐地
python3 scripts/checks/province_ownership_e2e.py

# 8 個突變體，約半分鐘（判定器裡的 e2e 跑得很快）
python3 scripts/checks/mutate_province_ownership.py

# 存證截圖（不判定，只出圖）：_shots/province_map_*.png
python3 scripts/checks/province_map_screenshots.py
```

對應的單元測試是 `backend/test_backend.py` 的 `ProvinceBordersAndOwnershipTests`。

這一輪的設計重點：**省界只有一份**。地圖上的省界、城市的省籍、
「某省全境歸某陣營」這三件事全部從 `frontend/data/provinces_1926.geojson`
推出來——前者由 `scripts/build_provinces_1926.py` 產生，後兩者分別由
`scenario/data/strategic_map.json` 與 `frontend/map.js` 的
`PROVINCE_OWNERSHIP_CLAIMS` 引用。**不要**為了讓某一省整片變色，
去手改 `FACTION_TERRITORIES` 那些手描的控制圈：那會讓省界變成兩份，
改一邊另一邊就歪。

`province_ownership_e2e.py` 裡最值錢的一關是「條款以外全圖一格都沒動」——
它拿 `factionAt()`（套用歸屬保證**之前**的歸屬）當基準逐格比，
所以測試裡不必寫死「奉系應該有幾格」這種會過期的數字，
而且任何一條條款不小心擴權，都會在別的省份被抓到。

改地格歸屬的時候順手看一眼城市：城市是先篩同陣營的格子再取最近的，
所以顏色一動，城市就可能跳一格（大同踩過：它是山西的城，腳下那一格卻在
察哈爾境內）。三層防線分別是套用條款時的城市護欄、名冊上的 `cell_key` 釘選、
以及 `CELL_OWNERSHIP_OVERRIDES` 逐格例外表，e2e 三層都有守。

## 陣營吞併／歸屬轉移（第十八批）

```bash
# 21 張卡逐張打真的 HTTP，並且刻意在 next-turn 與 respond-event 中間換一份新快照
python3 scripts/checks/faction_transfer_e2e.py

# 8 個突變體，約兩分鐘
python3 scripts/checks/mutate_faction_transfer.py
```

對應的單元測試是 `backend/test_backend.py` 的 `FactionTransferTacticalTests`。

**這一輪修的缺陷值得記住，因為它的形狀會再出現。**
所有吞併與歸屬轉移的卡都在 `respond_event()` 裡結算（卡片的 `apply` 要等每一家
都回應完才跑），而 `self._tactical` 先前只有 `next_turn()` 會設。前端每推一次
共享狀態，`SHARED_TACTICAL_STATE` 就換成一份新的 dict，引擎手上那個變成孤兒：
黔軍的地格、部隊、城市確實都轉給了川軍——轉在一份再也沒有人看的字典上。
`applied` 回報成功，地圖一格沒動，而且**時好時壞**，端看那一輪前端有沒有剛好
在中間推過一次。

所以：

* 「伺服器現在手上那份戰術快照」只有 `backend/server.py` 的 `current_tactical()`
  一個定義，`_run_route()` 在每個路由跑之前都重新綁一次。不要把它存起來重複用。
* 拿不到快照時一律記 `*_skipped` 並附 `reason`，不准靜靜跳過——
  `_transfer_all_faction_cells()` 現在回傳「轉了幾格」，`None` 和 `0` 意思不同。
* `faction_transfer_e2e.py` 是照 `KEYS` 自己去卡池撈的，新增一張同類的卡會自動
  被涵蓋；驗的也不只是「有東西變了」，而是**照機制該變的那幾個部分都變了**
  （吞併沒轉地格、招募沒換旗，都會被單獨抓出來）。

## 排空競態與腳本埠號（第十九批）

```bash
# 6 個突變體，約一分半
python3 scripts/checks/mutate_drain_race.py

# 隨機挑三張吞併／轉移卡在真前端實際觸發並截圖（不判定）
python3 scripts/checks/faction_transfer_screenshots.py [種子] [張數]
```

對應的單元測試是 `DrainRaceTests` 與 `CheckScriptPortTests`。

**寫新的檢查腳本時，這三件事別再犯：**

1. **一支腳本一個埠。** 共用埠會製造假紅與假綠——前一支的伺服器還沒收乾淨，
   後一支就可能整份量測都對著上一盤棋做。
2. **啟動的埠要就是輪詢的埠。** 別用 `python3 -m backend.server`，
   那綁的是預設的 8766。
3. **檢查 `proc.poll()`。** 綁不上埠時子程序立刻死掉，而輪詢仍可能連上
   別人那一台。要出聲，不要默默量錯的那一台。

另外：**斷言字串時先把註解剝掉。** 這個專案已經踩過兩次——
要守的旗標或函式名，在解釋它的註解裡也有一份，把程式碼那一行刪掉測試照樣綠。
`DrainRaceTests._no_comments()` 就是為此而生。

## NPC 那一半的世界（第二十批）

```bash
# 5 個突變體，約十分鐘（判定器是單元測試 + 真前端 e2e）
python3 scripts/checks/mutate_npc_visible_state.py

# 指定卡逐張跑並截圖（不判定，只存證）
python3 scripts/checks/card_effect_screenshots.py 卡ref[,卡ref...] [輸出.json]
```

對應的單元測試是 `NpcVisibleStateTests`；真前端那三關在
`card_effects_land_e2e.py` 裡（現在 18 關）。

**這一輪的缺陷形狀：畫面只更新玩家自己那一半的世界。**

* `syncStrategicCitiesFromState()` 先前只讀各玩家的 `city_economy`。
  〈黔軍整頓茅台酒造〉把遵義升到 3 級，後端的 `city_level_overrides` 有寫，
  畫面卻永遠停在 2 級——因為遵義不屬於任何玩家，沒有人的 `city_economy`
  會提到它。現在等級的權威來源是後端覆寫表，覆寫解除時回到開局基準
  （`baseCityLevels`），`city_economy` 只在沒有覆寫時當備援。
* 鐵路停擺的**理由**先前只有後端知道，前端一律寫「搶修中」。
  〈閻錫山封鎖窄軌鐵路〉是永久封鎖、無法搶修，看起來卻像修得好。
  後端的 `railway_access()` 現在多回一份 `disabled_detail`
  （`permanent` / `no_repair` / `until_general_leaves`），前端只負責翻成字。

寫新測試時的判準：**挑一個不屬於任何玩家的目標**。
`card_effects_land_e2e.py` 特地加了一關去斷言「遵義確實不在任何玩家的
`city_economy` 裡」——沒有那一關，這關驗不到東西，會是假綠。

## 後端知道、玩家看不到（第二十一批）

```bash
# 真前端 25 關，埠 8794
python3 scripts/checks/world_visibility_e2e.py

# 14 個突變體（判定器＝上面那支 e2e ＋ WorldVisibilityTests）
python3 scripts/checks/mutate_world_visibility.py
```

對應的單元測試是 `WorldVisibilityTests`（13 項）。

**三個缺陷，同一個家族：後端算出來了，玩家在畫面上看不到。**

1. **`remaining_turns` 為 null＝無限期，不是過期。** 前端先前在八個地方各寫
   一份 `Number(remaining_turns || 0) > 0`，於是每一種永久效果都被當成已經結束
   ——〈閻錫山封鎖窄軌鐵路〉兩條線全停，「持續效果」清單一筆都不列。
   現在後端在 `snapshot()` 裡替每一筆蓋 `active`，前端只讀 `effectActive()`。
   **不要再在前端寫任何一條 `remaining_turns` 的判斷**，測試會擋。
2. **擋得住就要說。** `blocked_cards`（被事件按住的功能卡）與
   `blocked_actions`（被禁掉的訓練／造船／補兵）現在隨 snapshot 送出來，
   前端把按鈕關掉並寫出擋住它的是什麼。判準仍然只在後端——前端不准自己
   翻 `perk_suspensions` / `action_bans` 那兩張原始表。
3. **無主城市。** 列強佔領解除時記成 `city_owners[id] = None`
   （**不是** `pop`：引擎裡到處都是 `.get(id, city["faction"])`，鍵一不見
   就把城市悄悄還給 1926 劇本的原主）。`ownerless_cities()` 由它算出來，
   解除時開一筆 `cities_became_ownerless` 交辦讓畫面中立化。

**下次怎麼做同一份稽核：** 把後端 `state` 的每一個鍵列出來，數它在引擎、
測試、前端各出現幾次。

* 只出現在寫入處 → 空轉（這次抓到 `npc_accounts`，已移除）。
* 只出現在後端、但「玩家理當要看到」→ 就是這一類缺陷。
* 前端零引用但**刻意**的：`comprador_deflections`、`assassination_log`
  是查帳用的紀錄，不要順手刪。

## 卡面 vs 實作 vs 畫面（第二十二批）

```bash
# 真前端 38 關（含佔領／演習、戰鬥加成、卡片改寫、銀行停貸）
python3 scripts/checks/world_visibility_e2e.py

# 25 個突變體
python3 scripts/checks/mutate_world_visibility.py
```

單元測試：`EffectsReachThePlayerTests`、`OccupationVersusDrillStateTests`。

**這一批的稽核方法，下次照做：**

1. 把每張事件卡的 `apply`（含 `resolution.options[].apply`）套進一局乾淨的引擎，
   比對前後的 `snapshot()`，列出它**真正改了哪些鍵**。
2. 把那些鍵拿去 `frontend/app.js` 裡找（記得先剝註解）——沒人讀的就是
   「後端算了、玩家看不到」。
3. 逐一判斷：這件事玩家理當要看到嗎？看不到的話他會不會按下去才知道？

207 張裡有 36 張的改動全部落在前端讀不到的鍵上。其中真的會咬到玩家的四類
已經修掉（戰鬥加成、卡片數字改寫、單一銀行停貸、鐵路「沿線」範圍）；
剩下的是 `event_locks` / `scheduled_event_effects` / `unlocks` 這種
「改的是未來抽牌機率」的機制，當下沒有東西可以畫。

**數字對不對也量過**：把 `effect` 文字裡的數字（含百分比轉成倍率）與 payload
裡的數字對照，207＋90 張全掃。殘留的不一致只有三張鐵路交涉卡
（12.58／12.59／12.60），已修；其餘都是文字寫百分比、資料存倍率之類的假警報。

### 全卡池稽核工具

```bash
# 三軸全跑（數字、具名實體、效果有沒有出現在畫面上）
python3 scripts/checks/card_effect_audit.py

# 只跑一軸
python3 scripts/checks/card_effect_audit.py 畫面
```

**不判定成敗，離開碼一律 0**——它只做候選篩選，結論要人看。假警報很多是正常的：
軸一初篩 127 張，真正的不一致只有 3 張。

軸三有一張 `DERIVED_OUTLETS` 對照表：有些原始狀態鍵前端本來就不該直接讀
（後端會解算成另一個欄位送出去，例如 `perk_suspensions` → `blocked_cards`）。
**新增這種「後端解算、前端只讀結果」的欄位時，記得補一行**，否則報告會一直
對著已經修好的東西喊狼來了。

## 港口水域與地形（第二十七批）

```bash
# 真前端 23 關，埠 8819
python3 scripts/checks/port_terrain_e2e.py

# 13 個突變體（判定器＝上面那支 e2e ＋ PortWaterRosterTests ＋ CityRosterTests）
python3 scripts/checks/mutate_port_terrain.py
```

單元測試：`PortWaterRosterTests`（9 項）、`CityRosterTests`（6 項）。

**抓到的真缺陷：成都與襄陽是「地圖上的長江河港、後端不屬於任何水系」。**
水域名單 `foreign_punishment.RIVER_PORTS` 是手維護的，這兩座從來沒被寫進去，
於是 `waters_for_city()` 回傳空陣列——長江水患／封鎖挑港市時挑不到它們。
可是前端 `markRiverPortWater()` 另外拿 `nearestRiverName()` 量最近的河，
把它們標成「河港・長江」，連封鎖的斜紋都照塗。**畫面說被淹、結算說沒事。**

修法照專案的老規矩：**規則只留一份，在後端。**
`_strategic_map_snapshot()` 現在對每座港市送出 `city["waters"]`，
前端 `portWaterName()` 只讀；名單漏掉時前端**大聲丟例外**，不再悄悄補一個河名。
`nearestRiverName()` 與 `pointSegmentDistance()` 隨之刪除（前端已無人使用）。

**加港口城市的檢查清單**（照做，不要憑印象）：

1. `scenario/data/strategic_map.json` 加 `"port": "river"` 或 `"sea"`；
2. 河港**一定要**在 `RIVER_PORTS` 裡選一條幹流（支流掛幹流：漢水、岷江
   都歸長江）。海港不用，`coastal_sea_name()` 照經緯度自己分；
3. 開真前端量三件事——地格有沒有變成水域、河名等不等於後端給的水系、
   鄰格有沒有同一條河（沒有的話艦隊到不了，那是一座孤港）；
4. 海港的地格必須至少貼著一格近海，否則艦隊一樣進不去。

**對照組不能省。** 「河港放陸軍通行」這一關單獨看是假綠——`riverStepAllowed()`
整條 return true 也會過。所以 e2e 另外掃全圖沒有城市的河道格，斷言它們照樣
攔得住陸軍；突變體 P9 就是靠這一關抓到的。

**把港口改回普通城市時要改兩邊。** 名冊拿掉 `"port"`、`RIVER_PORTS` 撤掉 id，
缺一不可——`_select_cities` 是先看 waters 再看 port，只回退一半會出現
「不是港口卻被長江水患挑到」。突變體 P7／P7b 分別咬這兩半（自貢就是這樣改回去的）。

**等價突變體的處理方式**（P11）：`portWaterName()` 裡那個 throw 在資料完整時
永遠跑不到，把它改成「回傳內河」的突變體與原始碼等價，任何判定器都看不出差別。
解法不是刪掉那個突變體，而是替那條路徑補一關——e2e 直接拿一座假的港市去問
`portWaterName()`，斷言它拋例外。補完之後 11/11 全抓。

## 存檔歸存檔、開局地圖歸開局地圖（第二十八批）

```bash
# 真前端 16 關，埠 8822
python3 scripts/checks/save_vs_opening_map_e2e.py

# 10 個突變體（判定器＝上面那支 e2e ＋ province_ownership_e2e）
python3 scripts/checks/mutate_save_vs_opening_map.py
```

單元測試：`NewGameAndProvinceNamingTests`（新增 4 項）。

**抓到的真缺陷：舊存檔會把整張地圖蓋回舊版本。** `applyTacticalSnapshot()`
先前是無條件 `cells[k].fac = snapshot.cellFactions[k]`。開局地圖一改，
連玩家從來沒打過的格子都跟著倒退——使用者本機那兩份存檔與乾淨新局差 40 格。

現在：開局地圖只有 `applyOpeningMap()` 一份定義；存檔帶著
`openingMap: { revision, cells }`（revision ＝開局歸屬的雜湊，**不是手寫版本號**）；
還原分三條路——版本一樣照舊全套、版本不一樣先歸零再只疊玩家的戰果、
沒有版本就整層不套。三條都有守門，包含「同版本不能有提示」（多人同步是常態）。

**改地圖之後要跑這一支。** 任何動到 `map.js`、省界檔、`strategic_map.json`
的改動都會讓 revision 變，也就是讓所有舊存檔走上第二條路——那條路的行為
必須是對的。

### 兩個測試設計上的坑（這一輪各踩一次）

* **e2e 要走玩家會走的那條路。** 第一版直接叫 `applyCellFactionsFromSnapshot()`，
  於是「把入口改回無條件全套」的突變體完全看不到。測入口，不要測規則。
* **驗「先歸零」要先把狀態弄髒。** 呼叫前地圖已經是開局地圖的話，
  歸不歸零看不出差別，突變體會逃掉。現在測試會先塗髒 60 格。

### 不要 kill 掉正在跑的 mutate_safe

它靠 finally 還原原始碼，被 SIGTERM 就會把突變體留在檔案裡；更糟的是
`/tmp/mutation_pristine/` 那份基準會在**下一次**跑的時候把你後來的修改一起蓋掉。
真的必須中斷，事後三件事：比對 md5、確認每個突變體的「原始字串」都還在、
`rm -rf /tmp/mutation_pristine`。
