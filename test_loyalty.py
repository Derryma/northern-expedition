"""
Test script to verify loyalty card functionality
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.card_engine import GameEngine

def test_loyalty_cards():
    print("\n" + "="*60)
    print("TESTING LOYALTY CARD SYSTEM")
    print("="*60)

    engine = GameEngine()

    # Setup tactical state with some generals
    engine._tactical = {
        "generalTrees": {
            "Z": {
                "generals": {
                    "z_cao_kun": {
                        "id": "z_cao_kun",
                        "name": "曹錕",
                        "loyalty": 3,
                        "loyalty_exempt": False
                    },
                    "z_wu_peifu": {
                        "id": "z_wu_peifu",
                        "name": "吳佩孚",
                        "loyalty": 4,
                        "loyalty_exempt": False
                    }
                }
            }
        },
        "generalOwners": {
            "z_cao_kun": "Z",
            "z_wu_peifu": "Z"
        },
        "loyaltyOverrides": {},
        "armies": {},
        "loyaltyBaselineArmyUnits": {}
    }

    print("\nTest 1: loyalty_all effect")
    print("-" * 40)
    effect = {"amount": 2}
    result = engine.resolve_loyalty_effect("loyalty_all", "Z", effect, engine._tactical)
    print(f"Picked generals: {result['picked']}")
    print(f"New overrides: {result['overrides']}")
    print(f"Amount: {result['amount']}")

    if result['picked'] and result['overrides']:
        print("✅ loyalty_all works")
    else:
        print("❌ loyalty_all FAILED - no generals picked or no overrides")
        return False

    print("\nTest 2: loyalty_random effect")
    print("-" * 40)
    effect = {"amount": -1, "count": 1}
    result = engine.resolve_loyalty_effect("loyalty_random", "Z", effect, engine._tactical)
    print(f"Picked generals: {result['picked']}")
    print(f"New overrides: {result['overrides']}")
    print(f"Amount: {result['amount']}")

    if len(result['picked']) == 1 and result['overrides']:
        print("✅ loyalty_random works")
    else:
        print("❌ loyalty_random FAILED")
        return False

    print("\nTest 3: apply_loyalty_deltas directly")
    print("-" * 40)
    deltas = [
        {"general_id": "z_cao_kun", "amount": 1},
        {"general_id": "z_wu_peifu", "amount": -2}
    ]
    result = engine.apply_loyalty_deltas(deltas, engine._tactical)
    print(f"Changed overrides: {result}")

    if result:
        print("✅ apply_loyalty_deltas works")
    else:
        print("❌ apply_loyalty_deltas FAILED")
        return False

    print("\nTest 4: mutable_loyalty_generals")
    print("-" * 40)
    generals = engine.mutable_loyalty_generals("Z", engine._tactical)
    print(f"Mutable loyalty generals: {generals}")

    if generals:
        print("✅ mutable_loyalty_generals works")
    else:
        print("❌ mutable_loyalty_generals FAILED - no generals found")
        return False

    print("\n" + "="*60)
    print("✅ ALL LOYALTY TESTS PASSED")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_loyalty_cards()
    sys.exit(0 if success else 1)
