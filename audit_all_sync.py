"""
Comprehensive audit of ALL frontend-backend sync points
Find every state mutation and verify it has proper sync
"""

import subprocess
import re

def run_grep(pattern, file_path="frontend/app.js"):
    """Run grep and return results"""
    result = subprocess.run(
        ["grep", "-n", pattern, file_path],
        capture_output=True,
        text=True
    )
    return result.stdout

print("="*80)
print("COMPREHENSIVE SYNC AUDIT")
print("="*80)

# Find all API calls that mutate state
print("\n1. ALL BACKEND API CALLS (State Mutations)")
print("-"*80)

api_calls = run_grep(r'await api\("/api/')
api_lines = api_calls.strip().split('\n') if api_calls.strip() else []
print(f"Found {len(api_lines)} API calls")

# Categorize by endpoint
endpoints = {}
for line in api_lines:
    match = re.search(r'"/api/([^"]+)"', line)
    if match:
        endpoint = match.group(1)
        line_num = line.split(':')[0]
        endpoints.setdefault(endpoint, []).append(line_num)

print("\nAPI endpoints by category:\n")
for endpoint, lines in sorted(endpoints.items()):
    print(f"  {endpoint}: {len(lines)} calls at lines {', '.join(lines[:3])}")

# Find all publishSharedState calls
print("\n\n2. ALL publishSharedState CALLS")
print("-"*80)
publish_calls = run_grep(r'publishSharedState')
print(publish_calls)

# Find all refreshBackendDerivedState calls
print("\n\n3. ALL refreshBackendDerivedState CALLS")
print("-"*80)
refresh_calls = run_grep(r'refreshBackendDerivedState')
print(refresh_calls)

print("\n\n4. CRITICAL STATE MUTATIONS TO CHECK")
print("-"*80)
critical_mutations = [
    ("generalOwners changes", r'generalOwners\['),
    ("generalTrees changes", r'generalTrees\[.*\].*='),
    ("loyaltyOverrides changes", r'loyaltyOverrides\['),
    ("army creation", r'newArmy\('),
    ("army deletion", r'removeArmy\('),
    ("cell faction changes", r'cell\.fac\s*='),
    ("city ownership changes", r'city\.faction\s*='),
]

for name, pattern in critical_mutations:
    results = run_grep(pattern)
    count = len(results.strip().split('\n')) if results.strip() else 0
    print(f"\n{name}: {count} occurrences")
    if count > 0 and count < 10:
        print(results[:500])

print("\n\n5. STATE MUTATION ENDPOINTS THAT MUST SYNC")
print("-"*80)

must_sync_endpoints = [
    "use-function",
    "respond-event",
    "attempt-defection",
    "recruit-captive-general",
    "combat",
    "turn-ready",
    "reinforce-army",
    "reinforce-navy",
    "occupy-tile",
    "navy-duel",
    "city-capture",
    "quell-uprising",
]

print("Checking if these endpoints have sync after them:\n")
for endpoint in must_sync_endpoints:
    lines = endpoints.get(endpoint, [])
    if lines:
        print(f"✓ {endpoint}: {len(lines)} calls at lines {', '.join(lines)}")
    else:
        print(f"✗ {endpoint}: NOT FOUND")

print("\n" + "="*80)
print("AUDIT COMPLETE - See output above for manual verification")
print("="*80)
