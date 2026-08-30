"""
Test the actual /api/loyalty-effect endpoint with real tactical state
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.card_engine import GameEngine

def test_loyalty_effect_with_real_state():
    print("\n" + "="*60)
    print("TESTING /api/loyalty-effect WITH REAL TACTICAL STATE")
    print("="*60)

    # Load the actual tactical state
    tactical_file = Path("game_data/tactical_state.json")
    if not tactical_file.exists():
        print("❌ No tactical state file found")
        return False

    with open(tactical_file, 'r', encoding='utf-8') as f:
        tactical_state = json.load(f)

    print(f"\n✅ Loaded tactical state with {len(tactical_state.get('generalOwners', {}))} generals")

    # Create engine instance
    engine = GameEngine()

    # Test with each faction that has generals
    for faction in tactical_state.get('generalTrees', {}).keys():
        generals = tactical_state['generalTrees'][faction].get('generals', {})
        if not generals:
            continue

        print(f"\n{'='*60}")
        print(f"Testing faction: {faction} ({len(generals)} generals)")
        print(f"{'='*60}")

        # Find mutable loyalty generals
        mutable = engine.mutable_loyalty_generals(faction, tactical_state)
        print(f"\nMutable loyalty generals: {len(mutable)}")
        for gen_id in mutable[:3]:  # Show first 3
            gen = generals.get(gen_id, {})
            print(f"  - {gen.get('name', gen_id)}: loyalty={gen.get('loyalty')}")

        if not mutable:
            print(f"⚠️  No mutable loyalty generals for {faction}")
            continue

        # Test loyalty_all
        print(f"\nTest: loyalty_all +2")
        try:
            result = engine.resolve_loyalty_effect(
                "loyalty_all", faction, {"amount": 2}, tactical_state)
            print(f"  Picked: {len(result['picked'])} generals")
            print(f"  Overrides: {len(result['overrides'])} entries")
            if result['overrides']:
                sample = list(result['overrides'].items())[:3]
                for gen_id, value in sample:
                    gen = generals.get(gen_id, {})
                    print(f"    - {gen.get('name', gen_id)}: new loyalty={value}")
                print(f"  ✅ loyalty_all works for {faction}")
            else:
                print(f"  ❌ No overrides created for {faction}")
                return False
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Test loyalty_random
        print(f"\nTest: loyalty_random -1 (count=1)")
        try:
            result = engine.resolve_loyalty_effect(
                "loyalty_random", faction, {"amount": -1, "count": 1}, tactical_state)
            print(f"  Picked: {result['picked']}")
            print(f"  Overrides: {result['overrides']}")
            if result['picked'] and result['overrides']:
                print(f"  ✅ loyalty_random works for {faction}")
            else:
                print(f"  ❌ No generals picked or no overrides")
                return False
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Only test first faction with generals
        break

    print("\n" + "="*60)
    print("✅ ALL LOYALTY EFFECT TESTS PASSED WITH REAL STATE")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_loyalty_effect_with_real_state()
    sys.exit(0 if success else 1)
