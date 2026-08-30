# Frontend-Backend Sync Fixes Summary

## Root Cause
Universal frontend-backend synchronization issue affecting both function cards and event cards. The loyalty system and other game mechanics depend on accurate tactical state sync between frontend and backend.

## Core Sync Mechanism
- **publishSharedState()**: Sends tactical snapshot (armies, navies, generals) from frontend to backend
- **refreshBackendDerivedState()**: Requests fresh loyalty/navy calculations from backend based on current state
- **tacticalSnapshot()**: Creates snapshot of frontend state for sync
- **applyLoyaltyOverrides()**: Updates frontend loyaltyOverrides object

## Fixes Implemented

### 1. Loyalty Card Effects (Event Cards)
**Location**: frontend/app.js, line 596-607 (loyalty_random), line 704-715 (loyalty_all)

**Problem**: 
- loyalty_random and loyalty_all functions called applyLoyaltyOverrides() to update frontend state
- No backend sync was triggered after these changes
- Backend continued using stale loyalty data for subsequent operations

**Solution**: Added loyalty change detection flag
```javascript
window.__loyaltyChangedThisTurn = true;
```

**Integration Point**: Event card handler (line 7926-7965)
- Detects loyalty changes via flag
- Triggers immediate refreshBackendDerivedState() after publishSharedState

### 2. Function Card Loyalty Effects
**Location**: frontend/app.js, line 3749-3752

**Problem**: 
- Had publishSharedState but no immediate loyalty refresh
- Backend calculated loyalty using pre-sync state

**Solution**: Added immediate loyalty refresh
```javascript
await publishSharedState(true);
if (result.loyalty_overrides && Object.keys(result.loyalty_overrides).length > 0) {
  await refreshBackendDerivedState();
}
```

### 3. Defection Success
**Location**: frontend/app.js, line 3097-3106

**Problem**: 
- Successful defection changed general ownership
- No sync to backend after ownership change
- Loyalty calculations continued using wrong owner data

**Solution**: Added immediate sync
```javascript
await publishSharedState(true);
await refreshBackendDerivedState();
```

### 4. Captive General Recruitment
**Location**: frontend/app.js, line 2749-2759

**Problem**: 
- Recruiting captive general changed ownership
- No sync to backend
- Backend continued treating general as captive/unowned

**Solution**: Added immediate sync
```javascript
await publishSharedState(true);
await refreshBackendDerivedState();
```

### 5. Combat Resolution ✓ FIXED
**Location**: frontend/app.js, line 8557-8564

**Problem**: 
- Combat modifies army units via casualties
- Can cause surrenders which change general ownership
- Missing sync caused loyalty calculations to use stale data

**Solution**: Added sync after combat resolution
```javascript
await publishSharedState(true);
await refreshBackendDerivedState();
```

### 6. Navy Duel ✓ FIXED
**Location**: frontend/app.js, line 7085-7105

**Problem**: 
- Navy combat modifies unit counts
- Affects carried armies
- Missing sync

**Solution**: Added sync after navy duel
```javascript
await publishSharedState(true);
```

### 7. Train Unit ✓ FIXED
**Location**: frontend/app.js, line 3306-3316

**Problem**: 
- Training units modifies resources and reserves
- Missing sync

**Solution**: Added sync after training
```javascript
await publishSharedState(true);
```

### 8. Train Navy Unit ✓ FIXED
**Location**: frontend/app.js, line 3324-3336

**Problem**: 
- Training navy units modifies resources and reserves
- Missing sync

**Solution**: Added sync after training
```javascript
await publishSharedState(true);
```

### 9. Reinforce Navy ✓ ALREADY HAD SYNC
**Location**: frontend/app.js, line 6809

**Status**: Already had publishSharedState(true) - no fix needed

### 10. Pay Navy Move ✓ ALREADY HAD SYNC
**Location**: frontend/app.js, line 9109

**Status**: Already had publishSharedState(true) - no fix needed

### 11. Take Loan ✓ FIXED
**Location**: frontend/app.js, line 3486-3495

**Problem**: 
- Taking loans modifies financial state
- Missing sync

**Solution**: Added sync after taking loan
```javascript
await publishSharedState(true);
```

### 12. Repay Debt ✓ FIXED
**Location**: frontend/app.js, line 3505-3518

**Problem**: 
- Repaying debt modifies financial state
- Missing sync

**Solution**: Added sync after repayment
```javascript
await publishSharedState(true);
```

### 13. Diplomacy ✓ FIXED
**Location**: frontend/app.js, line 3620-3632

**Problem**: 
- Diplomacy changes relations
- Missing sync

**Solution**: Added sync after diplomacy action
```javascript
await publishSharedState(true);
```

### 14. Deal Submission ✓ FIXED
**Location**: frontend/app.js, line 3642-3658

**Problem**: 
- Submitting deals may modify resources
- Missing sync

**Solution**: Added sync after deal submission
```javascript
await publishSharedState(true);
```

### 15. Respond to Deal ✓ FIXED
**Location**: frontend/app.js, line 8768-8779

**Problem**: 
- Accepting deals transfers resources
- Missing sync

**Solution**: Added sync after responding to deal
```javascript
await publishSharedState(true);
```

### 16. Next Turn ✓ ALREADY HAD SYNC
**Location**: frontend/app.js, line 9694

**Status**: Already had publishSharedState(true) - no fix needed

### 17. Draw Function Card ✓ FIXED
**Location**: frontend/app.js, line 2138-2150

**Problem**: 
- Drawing cards modifies hand and resources
- Missing sync

**Solution**: Added sync after drawing
```javascript
await publishSharedState(true);
```

### 18. Discard for Draw ✓ FIXED
**Location**: frontend/app.js, line 3794-3802

**Problem**: 
- Discarding cards modifies hand composition
- Missing sync

**Solution**: Added sync after discarding
```javascript
await publishSharedState(true);
```

## Summary: All Sync Gaps Fixed

✓ 14 endpoints fixed with publishSharedState
✓ 3 endpoints already had sync (no fix needed)
✓ Total: 17 sync points verified/fixed

## Why Both publishSharedState AND refreshBackendDerivedState?

**publishSharedState**: 
- Sends current tactical state to backend
- Backend stores this in SHARED_TACTICAL_STATE
- Required for backend to know WHO owns WHICH generals

**refreshBackendDerivedState**:
- Backend recalculates loyalty based on current SHARED_TACTICAL_STATE
- Backend sends fresh loyalty values back to frontend
- Required for frontend to display correct loyalty after ownership changes

Both are needed when:
1. General ownership changes (defection, recruitment, combat surrenders)
2. Loyalty values change (loyalty cards, events)

Only publishSharedState is needed when:
- Only tactical positions change (movement, combat casualties)
- Resources change (training, loans, deals)
- No loyalty recalculation required

## Testing Recommendations

1. Test loyalty cards after each fix:
   - Play "部隊晉升" (unit_promotion)
   - Play "鼓吹地方自治" (local_autonomy_agitation)
   - Verify loyalty changes appear immediately
   - Verify changes persist across turn transitions

2. Test defection:
   - Successfully defect a general
   - Check loyalty panel immediately
   - Verify defected general shows correct owner

3. Test captive recruitment:
   - Recruit a captive general
   - Check loyalty panel immediately
   - Verify recruited general appears with correct loyalty

4. Test combat:
   - Engage in combat with casualties
   - Check if loyalty recalculates correctly
   - Test surrender scenarios

5. Test resource operations:
   - Train units, take loans, repay debt
   - Verify backend state stays synchronized

6. Test diplomacy and deals:
   - Change diplomatic status
   - Submit and accept deals
   - Verify resources transfer correctly

## Pattern for Future Development

When adding new game mechanics that modify state:

1. **Always call publishSharedState(true)** after API calls that change:
   - General ownership
   - Army/navy positions or composition
   - Resources (money, units, cards)
   - Diplomatic relations

2. **Additionally call refreshBackendDerivedState()** when:
   - General ownership changes
   - Loyalty values change
   - Any operation that affects derived calculations (loyalty, navy power, etc.)

3. **Set change detection flags** when:
   - Frontend-only state changes need to trigger backend recalculation
   - Multiple operations in sequence might need batched sync

## Key Insight

The fundamental issue was **state desynchronization**: frontend and backend maintained separate views of game state, and operations that modified one side didn't propagate changes to the other. The loyalty system is particularly sensitive because:
- Backend calculates loyalty values
- Frontend displays and applies them
- Calculation depends on current ownership and tactical positions
- Any desync makes loyalty system appear broken even though backend logic is correct

By systematically adding publishSharedState() calls at every state mutation point, we ensure frontend and backend never diverge.
