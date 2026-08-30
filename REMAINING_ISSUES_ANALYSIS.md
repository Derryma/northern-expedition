# Remaining Issues Analysis and Fixes

## Issue 4: 城市升級事件卡沒有效果 - ANALYSIS COMPLETE

### Current Findings:
1. ✅ Backend logic is 100% correct:
   - Writes to `city_level_overrides` 
   - Calls `_refresh_city_income()` to recalculate output
   - `_strategic_map_snapshot()` line 994 applies level to cities
   - Bootstrap sends updated city.level to frontend

2. ✅ Frontend receives data correctly:
   - `boot()` loads bootstrap with updated city levels
   - `indexScenarioCells()` processes cities from bootstrap
   - Cities are assigned to cells with their properties

3. ❓ Potential Issue: **Bootstrap is only loaded ONCE at startup**
   - When city levels change mid-game via event cards, the bootstrap.strategic_map doesn't update
   - Frontend needs to refresh city data from somewhere other than initial bootstrap

### The Real Problem:
After investigating the flow:
- Bootstrap is loaded once at page load (line 4142-4143)
- City levels change during gameplay via event cards
- But frontend never re-reads the updated city levels from backend!
- `syncStrategicCitiesFromState()` only syncs cash/factory, NOT level

### Fix Required:
The backend DOES send updated levels via `_strategic_map_snapshot()` which is part of the engine state.
We need to ensure frontend reads and applies city levels from the engine state, not just from initial bootstrap.

**Solution**: Modify `syncStrategicCitiesFromState()` to also sync city levels from state.

---

## Issue 5: 艦隊佔領城市後歸屬錯誤 - INVESTIGATION NEEDED

### What We Know:
- Problem: 直系艦隊佔領城市後顯示歸屬五省聯軍
- This suggests either:
  1. City owner update logic has faction mapping bug
  2. Naval city capture doesn't update city_owners correctly
  3. Frontend displays wrong faction after naval capture

### Investigation Approach:
1. Find naval city capture code in navy_system/
2. Check if it calls same city transfer logic as land armies
3. Verify city_owners state update
4. Check if cellFactions also updated for naval captures

### Files to Investigate:
- `navy_system/navy.py` - naval combat and city capture
- `backend/server.py` - naval combat endpoints
- Frontend naval combat handlers

---

## Issue 6: 重新整理後部隊數據丟失 - CRITICAL ARCHITECTURAL ISSUE

### Root Cause (CONFIRMED):
```python
# backend/server.py line 27
SHARED_TACTICAL_STATE: Optional[Dict[str, Any]] = None  # IN-MEMORY ONLY!
```

This is a **global variable** that is:
- ❌ NOT persisted to disk
- ❌ NOT included in engine state snapshots
- ❌ Lost on server restart
- ❌ Lost when process is recycled

### Why Data Loss Happens:
1. User plays game → tactical state builds up in memory
2. Server process restarts (manual restart, crash, or auto-recycle)
3. `SHARED_TACTICAL_STATE = None`
4. Frontend calls `/api/shared-state`
5. Gets `{"tactical": None, ...}`
6. Frontend applies None tactical snapshot → all armies disappear

### Current Save/Restore:
- Engine state CAN be saved/restored via `/api/restore-shared-state`
- But tactical state is separate and NOT included
- Line 226-227 in server.py: tactical is passed separately but not persisted

### Fix Options:

#### Option A: Persist Tactical State to Disk (RECOMMENDED)
**Pros:**
- Simple to implement
- Survives server restarts
- Single source of truth on server

**Cons:**
- File I/O on every tactical update
- Need to handle concurrent access

**Implementation:**
```python
import json
from pathlib import Path

TACTICAL_STATE_FILE = Path("game_data/tactical_state.json")

def save_tactical_state():
    TACTICAL_STATE_FILE.parent.mkdir(exist_ok=True)
    with open(TACTICAL_STATE_FILE, 'w') as f:
        json.dump(SHARED_TACTICAL_STATE, f)

def load_tactical_state():
    global SHARED_TACTICAL_STATE
    if TACTICAL_STATE_FILE.exists():
        with open(TACTICAL_STATE_FILE, 'r') as f:
            SHARED_TACTICAL_STATE = json.load(f)

# Call load_tactical_state() on server startup
# Call save_tactical_state() in _shared_state() after updating
```

#### Option B: Include in Engine Snapshot
**Pros:**
- Single unified save/load mechanism
- No separate tactical state file

**Cons:**
- Larger refactor
- Engine state includes tactical state (coupling)

#### Option C: Frontend localStorage Fallback
**Pros:**
- No server-side changes
- Works even with ephemeral servers

**Cons:**
- Client becomes source of truth (risky)
- Doesn't work across devices
- Can get out of sync

---

## Priority Order:

1. **Issue 6** - CRITICAL: Data loss breaks the game
2. **Issue 4** - HIGH: City upgrades don't work
3. **Issue 5** - MEDIUM: Naval capture bug (less common scenario)

---

## Recommended Action Plan:

### Step 1: Fix Issue 6 (Data Loss)
Implement Option A - persist tactical state to disk:
- Add save/load functions in `backend/server.py`
- Save on every `_shared_state()` update
- Load on server startup
- Test server restart scenario

### Step 2: Fix Issue 4 (City Levels)
Modify `syncStrategicCitiesFromState()` to sync city levels:
```javascript
for (const city of bootstrap.strategic_map.cities) {
  const economy = economyByCity.get(city.id);
  if (economy) {
    city.cash = economy.cash;
    city.factory = economy.factory;
    // ADD THIS: Sync level from backend if available
    if (economy.level !== undefined) {
      city.level = economy.level;
    }
  }
  const cell = cells[city.cellKey];
  if (cell) cell.city = city;
}
```

### Step 3: Investigate Issue 5 (Naval Capture)
- Search for naval city capture logic
- Compare with land capture logic
- Test and fix

