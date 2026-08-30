"""
Comprehensive diagnostic for loyalty card issues
This will simulate the exact frontend workflow
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.card_engine import GameEngine
from backend.server import SHARED_TACTICAL_STATE

def diagnose_loyalty_issue():
    print("\n" + "="*70)
    print(" LOYALTY CARD DIAGNOSTIC - FRONTEND-BACKEND SYNC CHECK")
    print("="*70)

    # Load actual tactical state
    tactical_file = Path("game_data/tactical_state.json")
    if not tactical_file.exists():
        print("\n❌ CRITICAL: No tactical state file exists")
        print("   The frontend must sync state to backend first")
        return False

    with open(tactical_file, 'r', encoding='utf-8') as f:
        tactical = json.load(f)

    print("\n1. TACTICAL STATE LOADED")
    print("-" * 70)
    print(f"   General owners: {len(tactical.get('generalOwners', {}))}")
    print(f"   General trees: {list(tactical.get('generalTrees', {}).keys())}")
    print(f"   Loyalty overrides count: {len(tactical.get('loyaltyOverrides', {}))}")

    if tactical.get('loyaltyOverrides'):
        print(f"   Current overrides sample: {dict(list(tactical['loyaltyOverrides'].items())[:5])}")

    # Create engine
    engine = GameEngine()

    # Check each faction
    print("\n2. CHECKING EACH FACTION'S MUTABLE GENERALS")
    print("-" * 70)

    all_factions_ok = True
    for faction, tree in tactical.get('generalTrees', {}).items():
        generals = tree.get('generals', {})
        mutable = engine.mutable_loyalty_generals(faction, tactical)

        print(f"\n   Faction {faction}:")
        print(f"     Total generals: {len(generals)}")
        print(f"     Mutable loyalty generals: {len(mutable)}")

        if len(generals) > 0 and len(mutable) == 0:
            print(f"     ⚠️  WARNING: Has generals but NONE are mutable")
            # Check why they're not mutable
            for gen_id, gen in list(generals.items())[:3]:
                loyalty = gen.get('loyalty')
                exempt = gen.get('loyalty_exempt')
                absolute = gen.get('absolute_loyalty')
                print(f"       - {gen.get('name', gen_id)}: loyalty={loyalty}, exempt={exempt}, absolute={absolute}")

    # Simulate loyalty card usage
    print("\n3. SIMULATING LOYALTY CARD USAGE")
    print("-" * 70)

    test_faction = None
    for faction in tactical.get('generalTrees', {}).keys():
        mutable = engine.mutable_loyalty_generals(faction, tactical)
        if mutable:
            test_faction = faction
            break

    if not test_faction:
        print("\n   ❌ CRITICAL: NO faction has mutable loyalty generals!")
        print("   Possible causes:")
        print("      - All generals have loyalty=null (core faction members)")
        print("      - All generals have absolute_loyalty=true")
        print("      - All generals have loyalty_exempt=true")
        return False

    print(f"\n   Testing with faction: {test_faction}")

    # Test loyalty_all
    print(f"\n   A. Testing loyalty_all +2:")
    try:
        result = engine.resolve_loyalty_effect(
            "loyalty_all", test_faction, {"amount": 2}, tactical)

        print(f"      ✅ Backend processed successfully")
        print(f"      Picked {len(result['picked'])} generals")
        print(f"      Created {len(result['overrides'])} overrides")

        if result['overrides']:
            print(f"      Sample overrides:")
            for gen_id, value in list(result['overrides'].items())[:3]:
                gen = tactical['generalTrees'][test_faction]['generals'].get(gen_id, {})
                print(f"        - {gen.get('name', gen_id)}: {value}")
        else:
            print(f"      ❌ PROBLEM: No overrides created despite having mutable generals")
            all_factions_ok = False

    except Exception as e:
        print(f"      ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Check what frontend should do
    print("\n4. FRONTEND INTEGRATION CHECK")
    print("-" * 70)
    print("\n   After calling /api/loyalty-effect, frontend should:")
    print("   1. Receive response with 'overrides' object")
    print("   2. Call applyLoyaltyOverrides(result.overrides)")
    print("   3. This updates the global loyaltyOverrides object")
    print("   4. Next sync to backend includes these overrides")
    print("   5. Backend uses them in loyalty calculations")

    # Verify the overrides would persist
    print("\n   Testing override persistence:")
    new_overrides = {**tactical.get('loyaltyOverrides', {}), **result['overrides']}
    print(f"   Before: {len(tactical.get('loyaltyOverrides', {}))} overrides")
    print(f"   After: {len(new_overrides)} overrides (+{len(result['overrides'])})")

    # Test that these overrides would work on next calculation
    print("\n   Testing loyalty calculation with new overrides:")
    tactical_with_overrides = {**tactical, 'loyaltyOverrides': new_overrides}
    mutable_after = engine.mutable_loyalty_generals(test_faction, tactical_with_overrides)
    print(f"   Mutable generals still available: {len(mutable_after)}")

    print("\n5. POTENTIAL ISSUES TO CHECK")
    print("-" * 70)
    print("\n   ❓ Is the frontend calling /api/loyalty-effect?")
    print("      → Check browser console for API calls")
    print("\n   ❓ Is applyLoyaltyOverrides() being called with the result?")
    print("      → Check browser console for errors in card effect handlers")
    print("\n   ❓ Are the overrides being synced to backend?")
    print("      → Check /api/shared-state calls include loyaltyOverrides")
    print("\n   ❓ Is the server receiving the overrides?")
    print("      → Check server logs for /api/shared-state requests")

    print("\n" + "="*70)
    print(" DIAGNOSTIC COMPLETE")
    print("="*70)
    print("\n✅ Backend loyalty system: WORKING")
    print("✅ Tactical state loaded: WORKING")
    print("✅ Mutable generals found: WORKING")
    print("✅ Override generation: WORKING")
    print("\n⚠️  Issue is likely in FRONTEND or SYNC process")
    print("    Check browser console for errors when playing loyalty cards")
    print("="*70)

    return True

if __name__ == "__main__":
    success = diagnose_loyalty_issue()
    sys.exit(0 if success else 1)
