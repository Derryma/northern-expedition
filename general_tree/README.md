# General Tree

Hierarchy, loyalty, recruitment, and troop-allocation model for *Northern Expedition*.

This folder is separate from `comabt_system` because combat resolves battles, while the general tree owns who commands each army, how much force each commander can hold, and whether non-core commanders may defect.

## Files

- `general_tree.py` exports helper functions for hierarchy and loyalty state.
- `data/general_tree_template.json` is a save-file style template for one great general, lieutenants, and majors.
- `data/skill_catalog.json` lists special promotion-only skills.
- `data/generals_in_exile.json` is the 在野將領 pool: commanders who are out of office at the
  start of the game. They sit on no faction's tree, hold no faction, and are not on the map.
  The function card 〈在野名將投效〉 (`exile_recruit`) buys one of them out of retirement for the
  full `recruit_value` in cash; the general then joins the recruiting faction's tree with the
  troops listed in `units`, appearing where that faction's great general stands. Each pool general
  can be recruited once per game — the engine tracks this in `state.recruited_exiles`. Once the
  pool is empty the card falls back to a unit top-up (2 infantry, 1 machine gun) charged at half
  the faction's recruitment cash and no factory points.
- `test_general_tree.py` contains small regression tests for the core rules.

## Hierarchy

Default hierarchy:

| Role | Normal Subordinate Slots |
|---|---:|
| `great_general` | 3 lieutenant generals |
| `lieutenant_general` | 2 major generals |
| `major_general` | 0 |

Two NPC factions are exceptions. 川軍 and 湘軍 have no marshal at all: every
general sits at the same level, nobody is anybody's subordinate, and capturing
one of them brings over only that one command. Their tree files set
`"flat_command": true` with `"great_general_id": null`, and `validate_tree`
accepts that shape while still rejecting a stray `great_general` or `parent_id`
inside it.

Ranked NPC factions hang lower commanders from a leader. Capturing that leader
drops those subordinates to loyalty 1 but does not capture them immediately.
Only after the leader is recruited do the still-active subordinates enter the
recruiting faction's captive list. Their old links expire and each must be
assigned separately to an open lieutenant slot. Flat-command 川軍 and 湘軍 do
not perform any of these subordinate transitions.

Events can increase slots with:

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

In the live game, a defeated captive costs five infantry reserves to recruit.
He enters as a major general under an open lieutenant slot, receives the next
available army designator, and returns with exactly five infantry battalions;
his pre-capture army is not restored. If no slot exists, he remains captive.

The helper library also exposes a generic data-construction function:

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

The generic helper may create either rank, but the live captive workflow always
installs the recruited commander as a major general.

## Affiliation Events

If a lieutenant general is killed:

```python
from general_tree import kill_general

kill_general(tree, "he_yingqin")
```

All major generals under him immediately drop to `loyalty: 0`.

The standalone model still provides a branch-defection helper:

```python
from general_tree import defect_general

defect_general(tree, "bai_chongxi", "桂系獨立")
```

The live map's paid defection action transfers only the selected general and
army. It requires one open major-general slot; old subordinate links do not
create a fourth hierarchy layer.

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
