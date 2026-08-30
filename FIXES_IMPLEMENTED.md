# Bug Fixes Implemented

## Issue 1: NPC 勢力轉移後地格仍顯示舊勢力 ✅ FIXED

**Problem**: After NPC faction absorption/merger, map cells still showed old NPC faction colors.

**Root Cause**: Backend updated `city_owners` and army `faction`, but did NOT update `cellFactions` in SHARED_TACTICAL_STATE.

**Fixes Applied**:
1. Modified `_hand_over_npc_armies()` to update `cellFactions` for each army's cell when transferring
2. Added new helper function `_transfer_all_faction_cells()` to transfer all cells from old faction to new faction
3. Updated `npc_faction_absorb` to call `_transfer_all_faction_cells(faction, winner)` after city transfers
4. Updated `npc_faction_merge` to call `_transfer_all_faction_cells(source, winner_faction)` after city transfers

**Files Modified**: `backend/card_engine.py`

---

## Issue 2 & 3: 逾期貸款懲罰沒顯示且沒生效 ✅ FIXED

**Problem**: 
- Loan penalties not deducted from city output (Issue 3)
- Affected cities not showing status tags (Issue 2)

**Root Cause**: 
- `_apply_loan_penalties()` calculated penalties but didn't add them to `city_output_effects`
- `_adjusted_city_output()` reads from `city_output_effects` to apply multipliers
- Without entries in `city_output_effects`, penalties were neither applied nor displayed

**Fixes Applied**:
1. Modified `_apply_loan_penalties()` to add `city_output_effects` entries for each affected city
2. Each entry includes:
   - `kind: "loan_penalty"`
   - `city_ids`: list of affected city IDs
   - `cash_multiplier` and `factory_multiplier` based on penalty share
   - `remaining_turns` for timed penalties
   - `loan_id` for tracking
3. When penalties expire, corresponding `city_output_effects` entries are removed

**How It Works**:
- `_adjusted_city_output()` already processes `city_output_effects` and applies multipliers ✓
- `city_disruption_report()` already reads from `city_output_effects` to show tags ✓
- Frontend already displays disruption tags from backend report ✓

**Files Modified**: `backend/card_engine.py`

---

## Issue 4: 城市升級事件卡沒有效果 ⚠️ NEEDS INVESTIGATION

**Current Status**: Backend logic is CORRECT
- Backend writes to `city_level_overrides` ✓
- Backend calls `_refresh_city_income()` ✓
- `_strategic_map_snapshot()` applies level overrides to cities ✓ (line 994)
- Bootstrap sends updated city levels to frontend ✓

**Possible Issues**:
1. Frontend may not be refreshing after turn/event resolution
2. `syncStrategicCitiesFromState()` only syncs cash/factory, not level
3. City level from bootstrap may not be syncing to cells

**Needs**: Testing to confirm if issue still exists after backend sends correct data

---

## Issue 5: 艦隊佔領城市後歸屬錯誤 ⚠️ NEEDS INVESTIGATION

**Status**: Requires detailed investigation of naval combat city capture logic

**Files to Check**:
- `navy_system/navy.py` - naval combat and city capture
- `backend/server.py` - naval combat endpoints  
- Frontend naval combat handlers

**Questions**:
- Does naval city capture properly update `state["city_owners"]`?
- Does it update `cellFactions` in tactical state?
- Is there special handling for port cities?

---

## Issue 6: 重新整理後部隊數據丟失 ⚠️ CRITICAL ISSUE

**Problem**: Page refresh causes army data loss or generals without armies

**Root Cause Analysis**:
- `SHARED_TACTICAL_STATE` in `backend/server.py` is a **global in-memory variable** (line 27)
- It is NOT persisted to disk
- Server restart = data loss
- Page refresh triggers `pullSharedState()` which gets empty tactical state

**Current Architecture**:
```python
# backend/server.py line 27
SHARED_TACTICAL_STATE: Optional[Dict[str, Any]] = None  # IN MEMORY ONLY!
```

**Why This Happens**:
1. User plays game, tactical state builds up in memory
2. Server restarts (or gets recycled)
3. `SHARED_TACTICAL_STATE = None`
4. Frontend pulls state, gets `None`
5. Armies disappear because there's no tactical snapshot

**Potential Fixes** (NEEDS USER DECISION):

**Option A**: Save tactical state to disk
- Persist `SHARED_TACTICAL_STATE` to a JSON file on each update
- Load from disk on server startup
- Pro: Simple, preserves data across restarts
- Con: File I/O on every tactical update

**Option B**: Include tactical state in engine snapshot
- Make tactical state part of `ENGINE.state`
- Save/restore with engine state
- Pro: Single source of truth
- Con: Larger refactor

**Option C**: Auto-recover from frontend
- Frontend keeps tactical snapshot in localStorage
- On missing server state, re-publish from localStorage
- Pro: No server-side persistence needed
- Con: Client-side must be source of truth

**Recommended**: Option A - persist to disk, simplest and most reliable

---

## Summary

**Completed**: Issues 1, 2, 3 ✅
**Needs Testing**: Issue 4 ⚠️
**Needs Investigation**: Issue 5 ⚠️  
**Critical Architecture Issue**: Issue 6 ⚠️

**Files Modified**:
- `backend/card_engine.py` - Issues 1, 2, 3

**Next Steps**:
1. Test Issue 4 to confirm if backend fixes are sufficient
2. Investigate Issue 5 naval city capture logic
3. Decide on persistence strategy for Issue 6
