# Manual Testing Guide for Bug Fixes

**Server Status**: ✅ Running on http://localhost:8766

All 6 bug fixes have been implemented. This guide provides step-by-step testing procedures for each fix.

---

## Test Environment Setup

1. **Server**: Already running at http://localhost:8766
2. **Browser**: Open http://localhost:8766 in your browser
3. **Test Save**: Recommend using a test save game or creating a new game

---

## Issue 1: NPC 勢力轉移後地格仍顯示舊勢力 ✅

### Test Procedure
1. Start a game and advance to a turn where NPC faction absorption/merger events are available
2. **For 15.13 馬家軍歸附 (Ma Family Absorption)**:
   - Trigger the event card
   - Check the map around Ma family territories (青海/甘肅 region)
   - **Expected**: ALL cells that were Ma family color should immediately change to the absorbing faction's color
   - **Previous bug**: Some cells would remain Ma family color despite the faction being absorbed

3. **For 15.14/15.27 NPC Faction Merger events**:
   - Trigger any NPC merger event
   - Check the entire map for the merged faction's territories
   - **Expected**: ALL cells transfer to winner faction immediately
   - **Previous bug**: Map would show patchwork of old and new faction colors

### Verification
- [ ] All Ma family cells change color when absorbed
- [ ] All merged faction cells transfer to winner
- [ ] No remnant cells of absorbed/merged factions remain
- [ ] City ownership AND surrounding cells both update

---

## Issue 2 & 3: 逾期貸款懲罰沒顯示且沒生效 ✅

### Test Procedure - Part A: Penalty Display (Issue 2)

1. **Take a loan perk card** (any of these three):
   - 橫濱正金墊款 (jp_yokohama_credit): 2 cities, 100% cash+factory, 5 turns
   - 匯豐墊款 (uk_hsbc_credit): 1 province, 15% cash+factory, permanent
   - 花旗墊款 (us_citibank_credit): 3 cities, 100% factory, 5 turns

2. **Let it go overdue**: 
   - Note the `due_turn` when taking the loan
   - Do NOT repay before that turn
   - Advance past the due turn

3. **Check affected cities**:
   - Open the city info panel for each affected city
   - **Expected**: City should show a penalty status tag with:
     - Loan name (e.g., "橫濱正金墊款")
     - Remaining duration (if time-limited)
     - Type of penalty
   - **Previous bug**: No penalty tag displayed, looked normal

### Test Procedure - Part B: Penalty Effect (Issue 3)

1. **Record baseline output**:
   - Before loan goes overdue, note the cash/factory output of affected cities
   - Example: City produces 100 cash, 50 factory

2. **After penalty activates**:
   - Check the same cities' actual income at turn end
   - **For 100% penalties**: City should produce 0 for affected resources
   - **For 15% penalties**: City should produce 85% of normal output
   - **Expected**: Real income reduction matches penalty percentage
   - **Previous bug**: Full output still awarded despite penalty

3. **For time-limited penalties**:
   - Wait until duration expires (e.g., 5 turns for jp_yokohama_credit)
   - Check city output after expiration
   - **Expected**: Output returns to normal, penalty tag disappears
   - **Previous bug**: N/A (penalty never applied in first place)

### Verification
- [ ] Penalty tags appear in city info panel
- [ ] Tags show correct loan name and remaining turns
- [ ] Actual city output is reduced by correct percentage
- [ ] Cash penalties reduce cash income
- [ ] Factory penalties reduce factory income
- [ ] Time-limited penalties expire and remove themselves
- [ ] Permanent penalties (UK HSBC) continue indefinitely until repaid

### Test Matrix

| Loan Card | Targets | Resources | Duration | Expected Behavior |
|-----------|---------|-----------|----------|-------------------|
| jp_yokohama_credit | 2 cities | 100% cash+factory | 5 turns | Zero output for 5 turns, then restore |
| uk_hsbc_credit | 1 province | 15% cash+factory | Permanent | 85% output until repaid |
| us_citibank_credit | 3 cities | 100% factory | 5 turns | Zero factory for 5 turns, cash unaffected |

---

## Issue 4: 城市升級事件卡沒有效果 ✅

### Test Procedure

1. **Trigger a city upgrade event card** (any of these):
   - 10.4 晏陽初辦學鄉村 (province-wide 2→3 upgrades)
   - 15.28 江西升級 (+1 level to Jiangxi cities)
   - 15.29 雲南升級 (+1 level to Yunnan cities)
   - 15.30 福建升級 (+1 level to Fujian cities)
   - 15.31 浙江升級 (+1 level to Zhejiang cities)
   - 15.32 湖南升級 (+1 level to Hunan cities)
   - 15.33 四川升級 (+1 level to Sichuan cities)

2. **Immediately after playing the card**:
   - Open the city info panel for affected cities
   - **Expected**: City level should increase immediately (e.g., 2→3)
   - **Previous bug**: City level stayed the same

3. **Check output changes**:
   - Higher level cities should produce more cash/factory
   - The increase should be visible immediately
   - **Expected**: Output recalculated based on new level
   - **Previous bug**: Output unchanged because level didn't update

4. **Verify persistence**:
   - Refresh the browser page (F5)
   - Check city levels again
   - **Expected**: Upgraded levels persist after refresh
   - **Previous bug**: N/A (level never upgraded in first place)

### Verification
- [ ] City level increases immediately when card played
- [ ] City info panel shows correct new level
- [ ] City output increases based on new level
- [ ] Level upgrade persists after page refresh
- [ ] Province-wide upgrades affect all eligible cities
- [ ] Regional upgrades only affect cities in that region

---

## Issue 5: 艦隊佔領城市後歸屬錯誤 ✅

### Test Procedure

**Prerequisites**: 
- Have a naval fleet ready to move
- Target enemy port city for capture
- Ensure you are at war with the target faction

1. **Naval City Capture**:
   - Select your naval fleet (e.g., 直系 fleet)
   - Move the fleet to an enemy port city
   - If enemy navy present, defeat it first
   - Fleet should occupy the port city

2. **Immediate Verification**:
   - Check the city ownership display on the map
   - **Expected**: City should show YOUR faction (直系)
   - **Previous bug**: City would show wrong faction (e.g., 五省聯軍)
   
3. **Check Backend State**:
   - Open city info panel
   - Verify city faction matches your fleet's faction
   - Check that the city cell color matches your faction

4. **Test Multiple Scenarios**:
   - Capture with different faction fleets (直系, 皖系, 奉系, etc.)
   - Verify each time the city shows correct capturing faction
   - Test both sea ports and river ports

5. **Refresh Test**:
   - After naval capture, refresh browser (F5)
   - **Expected**: City ownership persists correctly
   - Backend `state.city_owners` should match what map displays

### Verification
- [ ] Naval captured cities immediately show correct faction
- [ ] City cell color updates to capturing faction
- [ ] City info panel shows correct owner
- [ ] No race condition displays wrong faction temporarily
- [ ] Works for all faction fleets
- [ ] Works for both sea and river ports
- [ ] Ownership persists after browser refresh

### Technical Check (Advanced)
Open browser console (F12) and check:
```javascript
// After naval capture, verify:
console.log(state.city_owners['<city_id>']); // Should match your faction
console.log(bootstrap.strategic_map.cities.find(c => c.id === '<city_id>').faction); // Should match
```

---

## Issue 6: 重新整理後部隊數據丟失 ✅

### Test Procedure

**Critical Test - Data Persistence Across Server Restarts**

1. **Setup Game State**:
   - Start a new game or load a save
   - Create several armies with specific compositions
   - Assign generals to armies
   - Move armies to different map locations
   - Record details:
     - Army IDs and their general names
     - Army compositions (how many 步/騎/炮 units)
     - Army positions (cellKey/coordinates)
     - Cell ownership (which faction controls which cells)

2. **Refresh Browser (Soft Test)**:
   - Press F5 to reload the page
   - **Expected**: All armies still present with correct:
     - Generals assigned
     - Unit compositions
     - Map positions
     - Cell ownership
   - **Previous bug**: Armies might disappear or generals lose their armies

3. **Restart Server (Hard Test)**:
   - Stop the server (Ctrl+C in server terminal)
   - Restart the server: `python -m backend.server`
   - Refresh browser
   - **Expected**: All tactical state preserved:
     - All armies present
     - All generals still assigned
     - All positions maintained
     - Cell ownership intact
   - **Previous bug**: Complete data loss after server restart

4. **New Game Test**:
   - Start a new game
   - Check that `game_data/tactical_state.json` is cleared/reset
   - **Expected**: Old game data doesn't persist into new game
   - File should be empty or contain only new game state

### Verification
- [ ] Browser refresh preserves all army data
- [ ] Browser refresh preserves general assignments
- [ ] Browser refresh preserves cell ownership
- [ ] Server restart preserves all tactical state
- [ ] `game_data/tactical_state.json` file is created
- [ ] File contains armies, cellFactions, navyDivisions, etc.
- [ ] New game clears old tactical state file
- [ ] No "general without army" bugs after restart
- [ ] No army composition loss after restart

### File System Check
```bash
# Check that tactical state file exists and is updated
ls -la game_data/tactical_state.json
cat game_data/tactical_state.json | head -50

# After server restart, verify file still exists
# After new game, verify file is cleared/reset
```

---

## Cross-Issue Integration Tests

### Test 1: Full Gameplay Flow
1. Start new game
2. Take a loan (Issue 2/3)
3. Trigger NPC absorption event (Issue 1)
4. Play city upgrade card (Issue 4)
5. Naval city capture (Issue 5)
6. Let loan go overdue and verify penalties
7. Restart server (Issue 6)
8. Verify all changes persist

### Test 2: Race Condition Stress Test
For Issue 5 (naval capture), test rapid operations:
1. Naval fleet captures city
2. Immediately move another unit
3. Check city ownership displays correctly
4. Verify no temporary wrong-faction display

### Test 3: Multi-Faction Scenario
1. Play as multiple factions in multiplayer/hot-seat
2. Each faction captures cities (Issue 5)
3. Each faction takes loans and goes overdue (Issue 2/3)
4. Verify all faction-specific data displays correctly

---

## Known Limitations & Notes

1. **Issue 5 Fix**: Only fixes the race condition. Does not change naval combat mechanics themselves.

2. **Issue 6 Fix**: Tactical state persistence prevents data loss but doesn't replace proper save/load game functionality.

3. **Issue 2/3 Fix**: Loan penalties are retroactive - if you load a save with overdue loans, penalties may not apply until next turn calculation.

4. **Issue 4 Fix**: Frontend now syncs city levels from backend. City level can still be overridden by backend if server has different data.

---

## Bug Reporting Template

If you find any issues during testing, report with this format:

```
**Issue**: [Brief description]
**Which Fix**: [Issue 1-6]
**Steps to Reproduce**:
1. 
2. 
3. 

**Expected Behavior**: 
**Actual Behavior**: 
**Screenshots**: [If applicable]
**Browser Console Errors**: [F12 → Console tab]
```

---

## Success Criteria

All 6 issues are considered **FULLY FIXED** when:

- [ ] Issue 1: All NPC cells transfer on absorption/merger
- [ ] Issue 2: Loan penalty tags appear in UI
- [ ] Issue 3: Loan penalties actually reduce city output
- [ ] Issue 4: City level upgrades display immediately
- [ ] Issue 5: Naval captures show correct faction ownership
- [ ] Issue 6: Data survives browser refresh AND server restart

**Status**: Ready for manual testing
**Server**: Running at http://localhost:8766
**Next Step**: Open browser and begin testing
