# 6 Issues - Comprehensive Fix Plan

## Issue 1: NPC 勢力轉移後地格仍顯示舊勢力
**Root Cause**: 
- Backend updates `city_owners` (cities) and army `faction`
- Backend does NOT update `cellFactions` in SHARED_TACTICAL_STATE
- Frontend's `cell.fac` comes from tactical snapshot, which is not updated
- Result: Map tiles still show old NPC faction colors even after absorption/merger

**Fix**:
1. In `_hand_over_npc_armies()`: Update `self._tactical["cellFactions"]` for all cells where transferred armies are located
2. In `npc_faction_absorb` (line ~6531): After transferring cities, update all non-city cells in that faction's territory
3. In `npc_faction_merge` (line ~6593): After transferring cities, update all non-city cells from source faction to winner faction

**Implementation Details**:
```python
# In _hand_over_npc_armies(), after line 5578:
if isinstance(self._tactical, dict):
    cell_key = army.get("cellKey")
    if cell_key:
        self._tactical.setdefault("cellFactions", {})[cell_key] = str(new_owner)

# After city transfers in npc_faction_absorb/merge:
# Update all cells that belonged to the old faction
if isinstance(self._tactical, dict):
    cell_factions = self._tactical.setdefault("cellFactions", {})
    for cell_key, fac in list(cell_factions.items()):
        if fac == faction:  # old faction
            cell_factions[cell_key] = winner  # new owner
```

---

## Issue 2 & 3: 逾期貸款懲罰沒顯示且沒生效
**Root Cause**:
- `_apply_loan_penalties()` calculates penalties correctly
- BUT penalties are NOT actually deducted from city output
- `_adjusted_city_output()` does NOT read loan_penalties
- `city_output_effects` does NOT include loan penalty entries for UI display

**Fix**:
1. Modify `_apply_loan_penalties()` to add entries to `city_output_effects` for each affected city
2. Modify `_adjusted_city_output()` to check active loan penalties and deduct accordingly
3. Ensure `city_disruption_report()` includes loan penalties (should work automatically if in city_output_effects)

**Implementation Details**:
```python
# In _apply_loan_penalties() after line 3920:
# Add city_output_effects entries for affected cities
city_effects = self.state.setdefault("city_output_effects", [])
for clause in remaining:
    targets = self._penalty_targets(player, clause)
    share = float(clause.get("share", 1.0))
    take = set(clause.get("take") or ["cash", "factory"])
    
    for city in targets:
        # Check if effect already exists for this loan+city
        effect_id = f"loan_penalty_{clause.get('loan_id')}_{city['id']}"
        if not any(e.get("id") == effect_id for e in city_effects):
            city_effects.append({
                "id": effect_id,
                "kind": "loan_penalty",
                "label": clause.get("label", "貸款違約條款"),
                "city_ids": [city["id"]],
                "cash_multiplier": 0.0 if "cash" in take else 1.0,
                "factory_multiplier": 0.0 if "factory" in take else 1.0,
                "remaining_turns": clause.get("remaining_turns"),
                "loan_id": clause.get("loan_id"),
                "power": clause.get("power"),
            })
```

---

## Issue 4: 城市升級事件卡沒有效果
**Root Cause Investigation**:
- Backend code (lines 6664-6706) DOES write to `city_level_overrides` ✓
- Backend code DOES call `_refresh_city_income()` ✓
- Backend creates `applied` entry with `kind: "city_level_upgrade"` ✓
- `_with_level()` correctly reads from `city_level_overrides` ✓
- `_strategic_map_snapshot()` (line 994) applies level overrides to city snapshots ✓
- Frontend: **NO handler for city_level_upgrade in PENDING_EFFECT_HANDLERS** ✗

**Fix**:
Frontend needs to add a handler for `city_level_upgrade` in PENDING_EFFECT_HANDLERS to sync city levels from the backend snapshot.

Actually - the frontend gets updated city levels through `_strategic_map_snapshot()` which is sent with every turn. The issue might be:
1. Frontend not refreshing city display after receiving snapshot
2. Or frontend caching old city data

**Need to check**: Does `syncStrategicCitiesFromState()` get called after turn updates?

---

## Issue 5: 艦隊佔領城市後歸屬錯誤
**Root Cause**: Unknown - needs investigation
**Files to check**:
- `navy_system/navy.py` - naval city capture logic
- `backend/server.py` - naval combat endpoints
- Frontend naval combat handlers

**Investigation needed**: 
- How does naval city capture work?
- Does it properly update `state["city_owners"]`?
- Does it call the same city transfer logic as land armies?

---

## Issue 6: 重新整理後部隊數據丟失
**Root Cause**: Unknown - needs investigation
**Possible causes**:
- SHARED_TACTICAL_STATE not persisted properly between requests
- `applyTacticalSnapshot()` missing data
- Race condition in frontend/backend sync

**Investigation needed**:
- How is SHARED_TACTICAL_STATE stored in `backend/server.py`?
- Is it per-session or in-memory only?
- Does page refresh lose the tactical state?

---

## Implementation Order
1. **Issue 1** - Clear fix, well understood ✓
2. **Issue 2 & 3** - Clear fix, well understood ✓  
3. **Issue 4** - Mostly understood, small frontend fix needed
4. **Issue 5** - Needs more investigation
5. **Issue 6** - Needs more investigation

## Files to Modify
- `backend/card_engine.py` - Issues 1, 2, 3
- `frontend/app.js` - Issue 4 (maybe already working?)
- `navy_system/navy.py` - Issue 5 (TBD)
- `backend/server.py` - Issue 6 (TBD)
