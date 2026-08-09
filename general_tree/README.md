# General Tree

Hierarchy, loyalty, recruitment, and troop-allocation model for *Northern Expedition*.

This folder is separate from `comabt_system` because combat resolves battles, while the general tree owns who commands each army, how much force each commander can hold, and whether non-core commanders may defect.

## Files

- `general_tree.py` exports helper functions for hierarchy and loyalty state.
- `data/general_tree_template.json` is a save-file style template for one great general, lieutenants, and majors.
- `data/skill_catalog.json` lists special promotion-only skills.
- `test_general_tree.py` contains small regression tests for the core rules.

## Hierarchy

Default hierarchy:

| Role | Normal Subordinate Slots |
|---|---:|
| `great_general` | 3 lieutenant generals |
| `lieutenant_general` | 2 major generals |
| `major_general` | 0 |

The common function card 「擴編直屬」 can increase a lieutenant general from 2 to 3 major-general slots. Three is the cap.

Scripts can apply the same effect with:

```python
from general_tree import increase_affiliation_slots

increase_affiliation_slots(tree, "he_yingqin", amount=1)
```

## General JSON Shape

Each general is keyed by id:

```json
{
  "id": "bai_chongxi",
  "name": "Bai Chongxi",
  "role": "lieutenant_general",
  "faction": "桂系",
  "core_faction": false,
  "loyalty": 6,
  "loyalty_exempt": false,
  "body_guard_level": null,
  "command_cap": 40,
  "traits": ["fire_support_savant"],
  "skills": [],
  "units": {
    "infantry": 12,
    "cavalry": 2,
    "artillery": 2,
    "machine_gun": 3
  },
  "parent_id": "chiang_kai_shek",
  "subordinate_slots": 2,
  "subordinates": ["li_zongren"],
  "status": "active"
}
```

Traits are normal general modifiers and can appear on multiple generals. Skills are special promotion-only powers. Only one starting general should begin with the engineering skill if the scenario wants that rarity.

`body_guard_level` replaces older separate guard-state ideas such as tracking extra machine-gun camps or elite-guard labels. It defaults to `null`; valid values are `null`, `low`, and `high`.

```python
from general_tree import set_body_guard_level

set_body_guard_level(tree, "bai_chongxi", "low")
set_body_guard_level(tree, "bai_chongxi", "high")
set_body_guard_level(tree, "bai_chongxi", None)
```

## Force Points

Force points measure army strength for command caps, recruitment, relative strength, and later economy/logistics systems:

| Unit | Force Points |
|---|---:|
| infantry | 1 |
| cavalry | 1 |
| machine_gun | 2 |
| artillery | 4 |

Use:

```python
from general_tree import calculate_force_strength

calculate_force_strength({"infantry": 5, "cavalry": 3})
```

## Loyalty

Loyalty runs from `0` to `10`.

- Great generals normally use `loyalty: null` and `loyalty_exempt: true`.
- Some exceptional generals can also be exempt.
- Non-core generals care about relative strength.
- Most generals lose loyalty from battle losses.
- Events can directly add loyalty.

Relative strength is calculated as:

```text
non-core command branch force / all force belonging to the great general's faction
```

This means a non-core lieutenant who controls a large branch becomes politically dangerous even if his displayed loyalty is not terrible.

Use:

```python
from general_tree import loyalty_report

report = loyalty_report(tree)
```

Each report entry includes `command_strength`, `relative_strength`, `loyalty`, and a simple `rebellion_pressure` score.

## Battle Loss Dissent

When a general loses troops, record the lost units:

```python
from general_tree import record_battle_loss

record_battle_loss(
    tree,
    "bai_chongxi",
    {"infantry": 3, "machine_gun": 1},
    loyalty_loss_per_force_point=0.1,
)
```

The function removes the lost units and subtracts loyalty based on lost force points.

## Direct Loyalty Effects

Other systems can directly modify loyalty:

```python
from general_tree import add_loyalty

add_loyalty(tree, "bai_chongxi", 2)
add_loyalty(tree, "bai_chongxi", -1)
```

Values are clamped between `0` and `10`.

## Recruitment

Recruiting a new general creates a new army and must assign at least `5` force strength:

```python
from general_tree import recruit_general

recruit_general(
    tree,
    parent_id="he_yingqin",
    general={
        "id": "new_major",
        "name": "New Major",
        "faction": "中央軍",
        "loyalty": 5,
        "command_cap": 12
    },
    starting_units={"infantry": 5}
)
```

If recruited under the great general, the new commander defaults to `lieutenant_general`. If recruited under a lieutenant general, he defaults to `major_general`.

## Affiliation Events

If a lieutenant general is killed:

```python
from general_tree import kill_general

kill_general(tree, "he_yingqin")
```

All major generals under him immediately drop to `loyalty: 0`.

If a general defects:

```python
from general_tree import defect_general

defect_general(tree, "bai_chongxi", "桂系獨立")
```

All subordinates in that branch defect with him and reset to `loyalty: 1`, so the branch remains unstable.

## Promotion

Promotion effects can append traits or special skills:

```python
from general_tree import add_trait, add_skill

add_trait(tree, "bai_chongxi", "steady_drillmaster")
add_skill(tree, "engineer_major", "pontoon_bridge")
```

Promotion-only skills currently planned:

| Skill | Effect Hook |
|---|---|
| `pontoon_bridge` | Build a temporary bridge over a river so an army can cross. |
| `fortress_builder` | Build a fortress that gives shelter and reduces incoming harm. |
| `fortress_buster` | Ignore the defender's fortress harm-reduction multiplier. |

## Troop Allocation

Newly conscripted troops can reinforce a general's army:

```python
from general_tree import allocate_troops

allocate_troops(tree, "li_zongren", {"infantry": 5, "cavalry": 3})
```

This only adds troops and checks the general's `command_cap`. There is intentionally no normal troop-transfer helper because allocated troops should not be moved out freely unless a future event explicitly grants that effect.
