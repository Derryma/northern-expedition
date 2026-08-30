"""
Debug script to check current SHARED_TACTICAL_STATE
"""
import json
import sys
from pathlib import Path

# Check if tactical state file exists
tactical_file = Path("game_data/tactical_state.json")

print("\n" + "="*60)
print("TACTICAL STATE DIAGNOSTIC")
print("="*60)

if tactical_file.exists():
    print(f"\n✅ Tactical state file exists: {tactical_file}")
    with open(tactical_file, 'r', encoding='utf-8') as f:
        state = json.load(f)

    print(f"\nFile size: {tactical_file.stat().st_size} bytes")
    print(f"\nKeys in tactical state: {list(state.keys())}")

    if "generalTrees" in state:
        print(f"\nGeneral trees factions: {list(state['generalTrees'].keys())}")
        for faction, tree in state['generalTrees'].items():
            generals = tree.get('generals', {})
            print(f"  {faction}: {len(generals)} generals")
    else:
        print("\n❌ NO generalTrees in tactical state!")

    if "loyaltyOverrides" in state:
        print(f"\nLoyalty overrides count: {len(state['loyaltyOverrides'])}")
        if state['loyaltyOverrides']:
            print(f"  Sample: {dict(list(state['loyaltyOverrides'].items())[:5])}")
    else:
        print("\n❌ NO loyaltyOverrides in tactical state!")

    if "generalOwners" in state:
        print(f"\nGeneral owners count: {len(state['generalOwners'])}")
    else:
        print("\n❌ NO generalOwners in tactical state!")

    print(f"\n📄 Full tactical state structure:")
    print(json.dumps({k: f"<{type(v).__name__}>" for k, v in state.items()}, indent=2))

else:
    print(f"\n❌ Tactical state file does NOT exist: {tactical_file}")
    print("\nThis means:")
    print("  1. No game has been started yet, OR")
    print("  2. Frontend hasn't synced tactical state to backend yet")
    print("\n💡 To fix: Start a game and make at least one action that syncs state")

print("\n" + "="*60)
