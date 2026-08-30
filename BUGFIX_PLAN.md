# Bug Fix Plan - 6 Issues

## Issue 1: NPC 勢力轉移後地格仍顯示舊勢力
**問題**: NPC 被併吞/歸附後，地格(cells)仍顯示被併吞的舊勢力標記，而非接管方

**根本原因**: 
- Backend 更新了 `city_owners` (城市歸屬)
- Backend 更新了部隊的 `faction`
- **但沒有更新 SHARED_TACTICAL_STATE 中的 `cellFactions`**
- Frontend 的地格顯示(`cell.fac`)來自 tactical snapshot，而這部分沒被更新

**修復方案**:
1. 在 `_hand_over_npc_armies()` 和 `npc_faction_merge` 中，當部隊轉屬時更新 `self._tactical["cellFactions"]`
2. 將被併吞陣營控制的所有地格改為接管方陣營
3. Frontend 已經會從 snapshot.cellFactions 同步，無需改動

**涉及文件**: `backend/card_engine.py`

---

## Issue 2 & 3: 逾期貸款懲罰沒顯示 & 完全沒生效
**問題**: 三張列強專項貸款逾期後:
- 產出不會被扣減 (Issue 3)
- 受影響城市沒有狀態標籤 (Issue 2)

**根本原因分析**:
檢查 `_apply_loan_penalties()`:
- 計算邏輯看起來正確
- **但這只是計算，沒有真正扣除產出**
- `_adjusted_city_output()` 需要讀取 `loan_penalties` 並扣除
- `city_output_effects` 需要記錄受影響的城市供前端顯示

**修復方案**:
1. 在 `_apply_loan_penalties()` 中，為每個受影響城市添加 `city_output_effects` 記錄
2. 在 `_adjusted_city_output()` 中，檢查該城市是否在活躍的 loan_penalties 範圍內，如果是則扣除相應產出
3. Frontend 的 `city_disruption_report()` 應該已經會顯示，確認即可

**涉及文件**: `backend/card_engine.py`

---

## Issue 4: 城市升級事件卡沒有效果
**問題**: city_level_upgrade 類事件卡完全無效

**需要檢查**:
1. `_apply_event_payload()` 中的 city_level_upgrade 處理
2. `city_level_overrides` 是否正確寫入
3. Frontend 是否消費 pending_frontend_effects

**修復方案**: 待調查後確定

---

## Issue 5: 艦隊佔領城市後歸屬錯誤
**問題**: 直系艦隊佔領城市後顯示歸屬五省聯軍

**需要檢查**:
1. Navy system 的城市佔領邏輯
2. `city_owners` 更新時機
3. 陸軍佔領是否也有問題

**修復方案**: 待調查後確定

---

## Issue 6: 重新整理後部隊數據丟失
**問題**: 網頁重新整理後部隊兵力消失或將領無部隊

**需要檢查**:
1. SHARED_TACTICAL_STATE 持久化
2. applyTacticalSnapshot() 邏輯
3. 前後端同步機制

**修復方案**: 待調查後確定

---

## 修復順序
1. Issue 1 (最明確)
2. Issue 2 & 3 (相關，一起修)
3. Issue 4, 5, 6 (需要更多調查)
