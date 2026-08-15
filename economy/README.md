# Economy

Current city production, reserves, construction spending, and loans.

## City output

City level is the baseline: a level 1 city produces `$1` and 1 factory point per turn; every level adds one of each.

| Level | Cash | Factory |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 3 | 3 |
| 4 | 4 | 4 |
| 5 | 5 | 5 |

Permanent card effects and disruptions are applied on top of this baseline. A captured city immediately uses its new owner for production and replenishment checks. Army reserve transfer requires a controlled city of level 3 or higher; navy reserve transfer requires a controlled river or sea port.

Army composition is stored directly in the tactical army. Replenishment deducts the reserve and adds the accepted battalion once; no separate reinforcement ledger participates in combat.

## Debt

- Debt accrues the rate defined by its loan record each turn and is rounded to an integer.
- While debt exists, half of cash income is automatically applied to repayment.
- Players may repay any additional amount up to their current cash through the loan panel.
- Bank offers depend on relation tier, current credit use, temporary lockouts, and the individual bank's terms.
- `軍閥公債` blocks new bank borrowing for five turns while existing debts remain repayable.

Implementation: `output.py`, `loans.py`, `data/banks.json`, and backend `card_engine.py`.
