"""
Comprehensive Frontend-Backend Sync Investigation
This script analyzes all sync points and identifies potential issues
"""

SYNC_ANALYSIS = """
=============================================================================
FRONTEND-BACKEND SYNC INVESTIGATION
=============================================================================

1. SYNC MECHANISMS
-----------------

A. publishSharedState(force = false)
   - Sends tactical snapshot to backend
   - Returns: loyalty, navy_outlook, railway_access, engine_state
   - Called from: ~20 locations
   - Issue: Only syncs if signature changed (unless force=true)

B. refreshBackendDerivedState()
   - Requests fresh loyalty/navy_outlook from backend
   - Calls /api/full-sync endpoint
   - Re-renders after receiving data
   - Issue: May not be called after all state changes

C. syncStrategicCitiesFromState()
   - Syncs city ownership from engine state to map display
   - Local operation, no backend call

D. applyLoyaltyOverrides(overrides)
   - Updates frontend loyaltyOverrides object
   - Does NOT sync to backend automatically
   - Backend only sees it on next publishSharedState()

2. STATE MUTATION POINTS
------------------------

Function Cards (/api/use-function):
  ✅ Line 3749: await publishSharedState(true)
  ✅ NEW: Force loyalty refresh if loyalty_overrides present

Event Cards (/api/respond-event):
  ✅ Line 7959: await publishSharedState(true)
  ✅ NEW: Force loyalty refresh if loyalty effects present

Turn Actions (/api/turn-ready):
  ? Need to verify sync after turn advance

Combat (/api/combat):
  ? Need to verify sync after battle

Defection (/api/defection):
  ? Need to verify sync after defection

Naval Operations:
  ? occupyTile, naval capture, navy duel

City Capture:
  ? Need to verify sync after city ownership changes

Reinforcement:
  ? Need to verify sync after army/navy reinforcement

3. POTENTIAL SYNC GAPS
----------------------

Gap 1: loyalty_all / loyalty_random effects
  - Called via /api/loyalty-effect
  - Updates loyaltyOverrides in frontend
  - BUT: No immediate publishSharedState() call after
  - RESULT: Backend tactical state stays stale until next sync

Gap 2: Event card frontend_effects
  - Some effects mutate tactical state directly
  - publishSharedState() called at END of event handler
  - BUT: If multiple effects run, intermediate states not synced

Gap 3: Army/Navy movements
  - Armies/navies moved on frontend first
  - Sync happens later via publishSharedState()
  - ISSUE: Race conditions if actions happen too fast

Gap 4: General recruitment/jail/exile
  - Changes generalOwners and generalTrees
  - May not trigger immediate backend sync

Gap 5: City ownership changes
  - syncStrategicCitiesFromState() is LOCAL only
  - Backend state may be out of sync with display

Gap 6: Defection success
  - Changes general ownership and loyalty
  - Need to verify loyalty recalculation happens

4. CRITICAL OPERATIONS THAT MUST SYNC IMMEDIATELY
-------------------------------------------------

1. Loyalty changes (function cards, event cards, defection)
2. General ownership changes (recruitment, capture, defection)
3. City ownership changes (capture, events)
4. Army/Navy creation or destruction
5. Cell/province ownership changes
6. Combat results (casualties, captures)
7. Turn advancement
8. Economic changes that affect display

5. RECOMMENDED FIXES
-------------------

Fix 1: Add sync flag to track what needs backend refresh
  const needsBackendRefresh = {
    loyalty: false,
    navyOutlook: false,
    complete: false  // Full state change
  };

Fix 2: Ensure publishSharedState() is awaited everywhere
  - Some calls use .catch() without await
  - This can cause race conditions

Fix 3: Add automatic sync after loyalty_all/loyalty_random
  - Currently only updates local loyaltyOverrides
  - Should trigger publishSharedState() + refreshBackendDerivedState()

Fix 4: Verify all combat handlers sync properly
  - Check applyArmyDuel, applyNavyDuel, etc.

Fix 5: Add sync verification logging
  - Log when sync happens vs when state changes
  - Detect gaps where state changed but no sync occurred

=============================================================================
"""

print(SYNC_ANALYSIS)
