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
| `fingerprint.py` | 算「整體指紋」，用來確認 clone 與使用者本機完全一致 |

## 怎麼跑

```bash
cd <repo>

python3 scripts/checks/event_replay.py            # 期望 crashed 為 0
python3 scripts/checks/npc_delta_replay.py
python3 scripts/checks/npc_scale_replay.py

pkill -f "backend[.]server"                       # 這行必須自己一行
python3 scripts/checks/npc_delta_e2e.py
python3 scripts/checks/npc_scale_e2e.py

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

「逃掉的突變」幾乎都是**測試缺口**，不是死碼——目前五次全部都是真的漏驗，
例如測試挑的數字剛好讓兩種算法算出同一個答案；
最近一次是「限時旗標到期了還算數」沒有任何測試在守。

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
