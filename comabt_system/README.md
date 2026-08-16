# Combat System

Army-level combat resolver for *Northern Expedition*.

This folder contains Owen's experimental battle mechanism. It resolves whole army pools by battalion count instead of individual tactical-board pieces.

## Files

- `combat.py` contains the callable combat function, experimental unit HP, attack matrix, and force points.
- `test_combat.py` contains regression tests for targeting priority, tactics, reinforcements, and cavalry pursuit.
- `examples/` contains sample army JSON files and a runnable JSON loading example.
- `data/` contains editable JSON references for unit stats, tactics, and general traits.

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

You can also run the bundled JSON example:

```bash
python3 comabt_system/examples/run_example.py
```

That example loads:

- `examples/a_1st_army.json`
- `examples/a_2nd_army.json`
- `examples/b_1st_army.json`

`A 1st Army` begins the battle, and `A 2nd Army` joins as an allied reinforcement on round 2.

The result includes:

- `winner`: `A`, `B`, `draw`, `stalemate`, or `undecided`.
- `rounds`: number of combat rounds resolved.
- `log`: per-round attacks, reinforcements, time-to-breakdown estimates, and pursuit.
- `remaining`: each side's aggregate remaining units plus each participating army's own remaining units, raw HP, tactic, focus target, and fighting/fleeing section states.

## Unit Types

Supported land units:

- `infantry`
- `cavalry`
- `artillery`
- `machine_gun`

Aliases such as `inf`, `cav`, `art`, `mg`, `步兵`, `騎兵`, `砲兵`, and `機槍` are accepted.

## Experimental Stats

Current coarse battalion HP and force points:

| Unit | HP | Force Points |
|---|---:|---:|
| infantry | 3 | 1 |
| cavalry | 3 | 1 |
| artillery | 2 | 4 |
| machine_gun | 3 | 2 |

Force points are not attack damage. They measure army size for later systems such as command caps, recruitment minimums, relative strength, logistics, and economy.

Current attack matrix, meaning damage dealt by one battalion of the source unit when harming each target unit type:

| Source / Target | infantry | cavalry | artillery | machine_gun |
|---|---:|---:|---:|---:|
| infantry | 1 | 1 | 1 | 1 |
| cavalry | 2 | 2 | 3 | 1 |
| artillery | 3 | 1 | 2 | 3 |
| machine_gun | 2 | 3 | 2 | 2 |

Design notes:

- Infantry is uniform into all targets.
- Machine guns are strongest into cavalry.
- Artillery is weak into cavalry, strong into enemy guns and static line targets.
- Cavalry is better at chasing cavalry and artillery than charging machine guns.
- Target priority still decides which section is attacked first. These matrix numbers are direct attack values, not damage-spread ratios.
- If damage is allocated across a mixed line, each allocated part uses its own source-vs-target value. For example, artillery harming a line uses artillery-to-infantry damage for the infantry share and artillery-to-machine-gun damage for the machine-gun share.
- There is no plain unit `attack` stat anymore. Every attack lookup uses this matrix.

These numbers are placeholders for playtesting. The core goal is to validate the logic before balancing values.

The same values are listed in `data/unit_stats.json` so they can later be loaded by a UI or external balancing tool. Python callers can use `calculate_force_strength(units)` to total force points for an army JSON unit block.

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

## Cavalry Artillery Contact

Cavalry can force artillery to protect itself.

At the start of each round, if a fighting cavalry unit's priority lets it reach enemy artillery, that enemy artillery army is marked as contacted. Contacted artillery must pour its fire into the contacting cavalry for that round instead of freely using its normal artillery -> line -> cavalry priority.

This means cavalry may fail to break enemy artillery, but still buy time:

- friendly cavalry contacts enemy artillery
- enemy artillery fires into that cavalry
- friendly artillery remains free to pound enemy artillery
- line troops can keep progressing without that enemy artillery choosing them first

Each round log includes `artillery_contacts`, and each attack records `forced_contact: true` when artillery was forced to fire at cavalry.

## Casualty Threshold

Each section begins in `fighting` state. Once casualties reach the section threshold, that section becomes `fleeing` and no longer attacks or receives normal targeting priority.

Default threshold is `30%` casualties. Tactics and modifiers can change it.

## Tactics

Built-in tactics:

| Tactic | Attack | Harm Taken | Threshold |
|---|---:|---:|---:|
| `normal_advance` | 100% | 100% | 30% |
| `probing_attack` | 35% | 45% | 25% |
| `layered_delaying` | 55% | 55% | 40% |
| `all_out_offense` | 170% | 145% | 25% |
| `last_stand` | 110% | 115% | 90% |
| `pinning_attack` | 90% | 70% | 20% |

Example:

```python
army = {
    "units": {"infantry": 8, "machine_gun": 2},
    "tactic": "last_stand",
}
```

The same tactic values are listed in `data/tactics.json`.

For simple holding-duration math, compare `threshold / harm_taken_multiplier`. `last_stand` is intentionally higher than `layered_delaying`, even though it takes more raw harm.

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

`data/general_traits.json` is the single source of truth for every general's
combat numbers. The frontend reads it through `/api/bootstrap` and only keeps the
Chinese label and description of its own; nothing multiplies these modifiers a
second time.

The 22 named generals each carry one signature skill (張宗昌 carries two):

| Trait | General | Effect |
|---|---|---|
| `northwest_overlord` 西北霸王 | 馮玉祥 | whole command HP +10% (aura, see below) |
| `dodging_drift` 閃躲漂 | 韓復榘 | harm taken -20%, attack -10% |
| `broadsword_corps` 大刀隊 | 宋哲元 | infantry harm taken +10%, infantry attack +15% |
| `northwest_vanguard` 西北先鋒 | 鹿鍾麟 | cavalry harm taken +10%, cavalry attack +15% |
| `shanxi_king` 山西王 | 閻錫山 | whole command HP +10% (aura) |
| `iron_bulwark` 銅牆鐵壁 | 傅作義 | harm taken -8%, artillery attack +8% |
| `chief_of_staff` 參謀長 | 徐永昌 | harm taken -8% |
| `xining_garrison` 西寧鎮守 | 馬麒 | whole command HP +10% (aura) |
| `desert_guard` 大漠衛隊 | 馬福祥 | infantry and cavalry harm taken -8% |
| `valiant_horse` 驍騎 | 馬鴻賓 | cavalry attack +10% |
| `marshal_zhang` 張大帥 | 張作霖 | whole command HP +10% (aura) |
| `young_marshal` 少帥 | 張學良 | cavalry and artillery attack +8% |
| `white_russian_mercenaries` 白俄傭兵 | 張宗昌 | infantry and cavalry attack +10%, cavalry HP +7%; disabled while the owning faction's Soviet relation is 6 or higher, and 張宗昌 loses 5 loyalty |
| `japanese_comprador` 日本買辦 | 張宗昌 | on joining a faction that faction's Japan relation +2; each Japanese condemnation card has a 10% chance of being blocked |
| `elite_artillery` 精銳砲兵 | 楊宇霆 | artillery attack +10% |
| `five_provinces_alliance` 五省聯軍 | 孫傳芳 | whole command HP +10% (aura) |
| `riverine_warfare` 水域作戰 | 周蔭人、盧香亭 | harm taken -10% while fighting in 廣西、廣東、福建、浙江、江蘇、安徽、江西 |
| `assault_breaker` 攻堅悍將 | 孟昭月 | infantry and artillery attack +7% |
| `wu_peifu_admired` 吾佩服 | 吳佩孚 | whole command HP +10% (aura) |
| `defensive_specialist` 防禦專家 | 靳雲鶚 | harm taken -12% |
| `central_plains_veteran` 中原宿將 | 寇英傑 | infantry and cavalry attack +7% |
| `wuchang_veteran` 武昌宿將 | 陳嘉謨 | infantry and artillery harm taken -7% |
| `advantage_is_ours` 優勢在我 | 蔣介石 | whole command HP +10% (aura) |
| `whampoa_spirit` 黃埔軍魂 | 何應欽 | infantry and machine gun harm taken +5%, their attack +15% |
| `precision_barrage` 精準砲擊 | 白崇禧 | artillery attack +25% vs machine guns, +15% vs infantry, +5% vs artillery |
| `mountain_division` 山地師 | 李宗仁、白崇禧、唐繼堯、龍雲、劉湘、楊森 | harm taken -10% while fighting in 廣東、廣西、雲南、貴州、四川、湖南 |
| `elite_mountain_division` 精銳山地師 | 劉文輝 | same provinces: harm taken -10% and attack +5% |
| `french_comprador` 法國買辦 | 唐繼堯 | on joining a faction that faction's France relation +3; each French condemnation card has a 30% chance of being blocked |
| `tianfu_land` 天府之國 | 劉湘 | every 四川 city his faction controls yields +1 cash and +1 factory per turn |
| `buddhist_general` 佛教將軍 | 唐生智 | harm taken -10%, attack -10%, and defection attempts against him lose 5 percentage points of success chance |
| `hunan_governor` 我才是省長 | 趙恒惕 | every 湖南 city his faction controls yields +1 cash and +1 factory per turn; attack +10% in any battle where 唐生智 is on the other side |
| `anticommunist_vanguard` 剿共先鋒 | 何鍵 | attack +10% against a faction whose Soviet relation is 6 or higher, and red army uprisings need only one garrison turn; disabled (and -5 loyalty) while his own faction's Soviet relation is 6 or higher |
| `former_overlord` 前代梟雄 | 段祺瑞 | infantry and artillery attack +12% |
| `anhui_veteran` 皖系舊部 | 盧永祥 | infantry and machine gun attack +8%; whole command HP +10% while 段祺瑞 is on the same side. 五省聯軍 cannot recruit him |
| `zhili_veteran` 直系宿將 | 王承斌 | cavalry and artillery attack +7% |
| `old_cantonese_army` 老粵軍 | 陳炯明 | artillery attack +12%; red army uprisings need only one garrison turn. 國民革命軍 cannot recruit him |
| `qilu_veteran` 齊魯宿將 | 田中玉 | cavalry harm taken -7%, artillery attack +7% |

Aura, province and relation conditions cannot be expressed as plain modifiers, so
they live in `frontend/app.js` (`AURA_TRAITS`, `PROVINCE_CONDITIONAL_TRAITS`,
`RELATION_DISABLED_TRAITS`) and are folded into the payload sent to
`simulate_battle`:

- An aura only fires when the named subordinate joins the **same side** of the
  **same battle** as its marshal; if they meet as enemies it does nothing. The
  bonus stacks across everyone present, so 吳佩孚 plus 靳雲鶚 plus 寇英傑 in one
  battle means all three commands get HP +10%. It lasts for that battle only.
- Aura partners: 馮玉祥 → 宋哲元、鹿鍾麟; 閻錫山 → 傅作義、徐永昌;
  馬麒 → 馬福祥、馬鴻賓; 張作霖 → 張學良; 孫傳芳 → 孟昭月、盧香亭;
  吳佩孚 → 靳雲鶚、寇英傑、陳嘉謨.
- Every unit in this game is a land unit, so "將領效果只對陸軍生效" needs no
  special handling.
- `ALLY_PRESENCE_TRAITS` is the mirror image of an aura: the bonus goes to the
  general who owns the trait, but only while a named ally is on his side
  (盧永祥 needs 段祺瑞). `ENEMY_PRESENCE_TRAITS` fires on a named general being
  on the *other* side (趙恒惕 vs 唐生智), and `ENEMY_RELATION_TRAITS` on the
  opposing faction's relation with a power (何鍵 vs anyone friendly to Moscow).

Effects that belong to a faction rather than to a battle live in the engine
(`backend/card_engine.py`): `COMPRADOR_TRAITS`, `PROVINCE_OUTPUT_TRAITS` and
`FAST_UPRISING_SUPPRESSION_TRAITS`. The engine tracks them in
`state["faction_general_traits"]` and moves them between factions in
`apply_general_join`, so a captured or defecting general takes his provincial
tax base and his foreign contacts with him.

The generic traits used by NPC and in-exile generals are unchanged:

- `steady_drillmaster`: infantry attack +10%.
- `fire_support_savant`: artillery hits infantry and machine guns harder.
- `cavalry_screen_commander`: cavalry HP +20%.
- `entrenched_warlord`: infantry and machine guns take 10% less harm.
- `shock_column_leader`: infantry and cavalry attack harder, but the army takes more harm.
- `local_supply_boss`: line troops hold longer before fleeing.
- `foreign_gunnery_advisor`: artillery is better at counter-battery fire.

## Focus Fire

By default, if a side is fighting multiple enemy armies, incoming damage is spread evenly across all valid enemy armies in the targeted section. This represents general battlefield pressure.

An army may instead focus its firepower on one named enemy army:

```python
army = {
    "name": "A First Army",
    "units": {"artillery": 2, "infantry": 8},
    "focus": "B Front Army",
}
```

Multiple friendly armies can choose the same focus:

```python
army_a = {
    "name": "A First Army",
    "units": {"artillery": 1},
    "focus": "B Front Army",
}

reinforcements = [
    {
        "round": 1,
        "side": "A",
        "army": {
            "name": "A Second Army",
            "units": {"artillery": 1},
            "focus": "B Front Army",
        },
    },
]
```

If the focused enemy army has already fled, is gone, or has no valid target for that attacking unit's priority, the attack falls back to normal spread against other valid enemy armies.

Each attack log records the actual target armies:

```python
result["log"][0]["attacks"][0]["target_armies"]
```

It also records per-target damage allocations:

```python
result["log"][0]["attacks"][0]["damage_by_target"]
```

## Reinforcements

Reinforcements are not merged into the original army. A reinforcement is another allied army joining the same side with its own commander/general modifiers, tactic, focus target, unit stats, HP pool, threshold state, and remaining casualties.

Reinforcements join before attacks in their listed round.

```python
result = simulate_battle(
    army_a,
    army_b,
    reinforcements=[
        {
            "round": 3,
            "side": "A",
            "army": {
                "name": "Allied 2nd Army",
                "units": {"infantry": 2, "machine_gun": 1},
                "tactic": "probing_attack",
                "focus": "B Front Army",
                "modifiers": [
                    {"stat": "attack", "unit": "machine_gun", "multiplier": 1.25}
                ],
            },
        },
        {
            "round": 4,
            "side": "B",
            "army": {
                "name": "Relief Cavalry Corps",
                "units": {"cavalry": 2},
                "tactic": "all_out_offense",
            },
        },
    ],
)
```

This allows allied armies to enter mid-battle, increase friendly HP, average out incoming damage across the side's live formations, and add their own firepower from that round onward.

The returned side snapshot keeps them separate:

```python
result["remaining"]["A"]["armies"]
```

Each entry in that list is one army's own remaining units and state. The top-level `result["remaining"]["A"]["units"]` is only the aggregate side total.

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
