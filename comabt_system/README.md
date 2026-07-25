# Combat System

Army-level combat resolver for *Northern Expedition*.

This folder contains Owen's experimental battle mechanism. It resolves whole army pools by battalion count instead of individual tactical-board pieces.

## Files

- `combat.py` contains the callable combat function and experimental unit stats.
- `test_combat.py` contains regression tests for targeting priority, tactics, reinforcements, and cavalry pursuit.

## Basic Usage

```python
from combat import simulate_battle

army_a = {
    "name": "Army A",
    "units": {
        "infantry": 10,
        "cavalry": 3,
        "artillery": 2,
        "machine_gun": 3,
    },
    "tactic": "normal_advance",
}

army_b = {
    "name": "Army B",
    "units": {
        "infantry": 7,
        "cavalry": 0,
        "artillery": 1,
        "machine_gun": 2,
    },
    "tactic": "probing_attack",
}

result = simulate_battle(army_a, army_b, max_rounds=5)
```

The result includes:

- `winner`: `A`, `B`, `draw`, `stalemate`, or `undecided`.
- `rounds`: number of combat rounds resolved.
- `log`: per-round attacks, reinforcements, time-to-breakdown estimates, and pursuit.
- `remaining`: each side's remaining units, raw HP, and fighting/fleeing section states.

## Unit Types

Supported land units:

- `infantry`
- `cavalry`
- `artillery`
- `machine_gun`

Aliases such as `inf`, `cav`, `art`, `mg`, `步兵`, `騎兵`, `砲兵`, and `機槍` are accepted.

## Experimental Stats

Current coarse battalion stats:

| Unit | HP | Attack |
|---|---:|---:|
| infantry | 1 | 1 |
| cavalry | 2 | 1 |
| artillery | 1 | 4 |
| machine_gun | 1 | 3 |

These numbers are placeholders for playtesting. The core goal is to validate the logic before balancing values.

## Target Priority

Infantry and machine guns share the `line` section. Their HP is pooled for line-holding threshold checks, and incoming line casualties are spread by participating battalion ratio.

Attack priority:

| Source | Priority |
|---|---|
| infantry | line -> cavalry -> artillery |
| machine_gun | line -> cavalry -> artillery |
| cavalry | cavalry -> artillery -> line |
| artillery | artillery -> line -> cavalry |

If a target section reaches its casualty threshold and starts fleeing, attackers roll to the next valid priority.

## Casualty Threshold

Each section begins in `fighting` state. Once casualties reach the section threshold, that section becomes `fleeing` and no longer attacks or receives normal targeting priority.

Default threshold is `20%` casualties. Tactics and modifiers can change it.

## Tactics

Built-in tactics:

| Tactic | Attack | Harm Taken | Threshold |
|---|---:|---:|---:|
| `normal_advance` | 100% | 100% | 20% |
| `probing_attack` | 50% | 60% | 20% |
| `layered_delaying` | 70% | 75% | 25% |
| `all_out_offense` | 140% | 125% | 20% |
| `last_stand` | 100% | 150% | 40% |
| `pinning_attack` | 80% | 85% | 20% |

Example:

```python
army = {
    "units": {"infantry": 8, "machine_gun": 2},
    "tactic": "last_stand",
}
```

## Modifiers

Modifiers are designed for generals, terrain, tactics, events, and future special rules.

Examples:

```python
"modifiers": [
    {"stat": "attack", "unit": "infantry", "multiplier": 1.10},
    {"stat": "hp", "unit": "cavalry", "multiplier": 1.20},
    {"stat": "attack", "unit": "artillery", "target": "machine_gun", "multiplier": 1.25},
    {"stat": "harm_taken", "unit": "artillery", "multiplier": 0.75},
    {"stat": "threshold", "unit": "infantry", "add": 0.05},
]
```

Supported `stat` values:

- `attack`
- `hp`
- `harm_taken`
- `threshold`

Supported operations:

- `multiplier`: multiply the current value.
- `add`: add a flat amount.
- `add_pct`: add a percentage as decimal, such as `0.10` for +10%.

Use `unit: "all"` or omit `unit` to affect every unit. Use `target` for target-specific attack bonuses, such as artillery being better against machine guns.

## Reinforcements

Reinforcements join before attacks in their listed round.

```python
result = simulate_battle(
    army_a,
    army_b,
    reinforcements=[
        {"round": 3, "side": "A", "army": {"units": {"infantry": 2}}},
        {"round": 4, "side": "B", "army": {"units": {"cavalry": 1}}},
    ],
)
```

This allows allied armies to enter mid-battle, increase friendly HP, and add firepower from that round onward.

## Cavalry Pursuit

When one side collapses and the winner still has cavalry, pursuit casualties are applied to the loser:

```text
survivor multiplier = 1 - 0.05 * winning cavalry count
```

Remaining loser battalions are rounded with `.5` rounded down:

- `1.5 -> 1`
- `1.7 -> 2`

## Run Tests

From the repository root:

```bash
python3 -m unittest discover -s comabt_system -p 'test_*.py'
```

From this folder:

```bash
python3 -m unittest test_combat.py
```
