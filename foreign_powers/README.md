# Foreign Powers

Updated foreign-power rules and data for *Northern Expedition*.

> **Implementation authority:** the running engine reads
> `data/foreign_powers.json`. An older target scale still appears in
> `cards/data/card_pool_rules.json`; it is not currently used for relation
> clamping or friendly/hostile bands and must not be treated as live rules.

## Files

- `data/foreign_powers.json` contains the current foreign-power rules, territories, relation keys, the relation scale, the June-1926 starting relations, removed assets, and punitive-war constraints.
- `relations.py` reads that file: the scale, the starting positions per faction, clamping, and the hostile/neutral/friendly band a value falls in. The engine imports this rather than hardcoding numbers.

## Current Rules

Foreign powers no longer use concession garrisons.

Foreign units that enter cities are ordinary foreign units. They do not transform into special concession troops, and old cards that add or strengthen `租界駐軍` need rewriting before final use.

Direct foreign military support is removed. Players should not borrow British, Japanese, French, or Soviet field formations as friendly auxiliaries. Foreign military action against a player only occurs through punitive expeditions.

Foreign relations use a **-10 to 10** scale. -4 and below is hostile, 6 and above is friendly and can unlock that power's function-card perks. These are the same cut points the loan tiers use, so a power that turns hostile stops lending in the same moment it turns hostile — see `economy/`.

Starting relations reflect June 1926 and live in `data/foreign_powers.json` under `initial_relations`:

| | 日 | 蘇 | 英 | 美 | 法 |
|---|---|---|---|---|---|
| 奉系 | +8 | -7 | +4 | +2 | +1 |
| 直系 | -3 | -8 | +6 | +5 | +2 |
| 五省聯軍 | +3 | -6 | +5 | +4 | +3 |
| 國民革命軍 | -1 | +9 | -8 | +1 | -4 |

Germany is deliberately absent from the relation track. After the 1921 Sino-German treaty it held no privileges in China, so it appears only as a neutral commercial lender (德華銀行).

Players may not attack foreign powers or enter foreign territory while not at war, even if relations are bad. Fighting foreign powers happens only when a punitive expedition is active.

Punitive expeditions:

- foreign side receives an independent turn
- opponent player controls the foreign side
- foreign occupation/attack reach is capped at three provinces
- mediation indemnity scales by foreign reach: 15, 30, or 45 money

## Scenario Changes

- Remove Philippines US forces.
- Remove Leonard Wood.
- Move 庫倫守軍 back under 外蒙古.
- Add 霍爾洛·喬巴山 as commander for 庫倫 and Outer Mongolian cavalry.
