# Navy System

Current river and near-coast naval layer. The code is isolated in `frontend/navy.js`; `data/navy_rules.json` is the editable rule source.

## Division and movement

- Each player starts with one division: two gunboats and one cargo boat, with no general.
- Navies may use water, river/sea ports, navigable railway bridges, and marked naval routes.
- One order moves at most two connected tiles.
- Movement costs 5 factory points for every surviving gunboat in the division. Cargo boats add no movement cost.
- A cargo boat carries one land army up to 20 force points. Embarkation and disembarkation require a controlled port.
- Naval sight range is two tiles and obeys fog of war.

## Units

| Unit | HP | Active | Attack | Other |
|---|---:|---|---|---|
| Gunboat | 30 | HP 15 or more | 5 vs gunboat; 2 vs artillery | Only artillery can damage it |
| Cargo boat | 10 | Never fires | 0 | 20-force transport capacity |

Zero-HP ships sink and are removed. Damage spills from gunboats into cargo boats. Repair is available only in a controlled port and costs 2 factory points per restored HP.

## Exchange and retreat

Fire eligibility is fixed at the start of each exchange:

1. A division with no active gunboat still receives the enemy salvo, cannot return fire, and retreats afterward.
2. A division with at least one active gunboat exchanges fire normally.
3. A fleet crosses its retreat line at 50% or less of its original total gunboat HP, or when no active gunboat remains.
4. If both fleets cross the line in the same exchange, the fleet with more remaining gunboat HP holds the tile. Equal HP makes both retreat one tile.
5. A player may voluntarily retreat from the battle report.

## Army against navy

- Only artillery participates. Each artillery battalion deals 1 HP to the navy; each active gunboat deals 2 damage to artillery.
- A navy with no active gunboat takes the artillery attack without retaliation and then retreats.
- The army stays on the contact tile while at least one artillery battalion remains. It withdraws automatically only when all artillery is gone; the player may move it away voluntarily on a later order.
- A naval screen is resolved before any land army sharing that tile can be attacked.
- There are no tactics, cavalry pursuit, or combined land/naval damage pools.
