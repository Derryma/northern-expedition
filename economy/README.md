# Economy

City output, factory points, and the bank loan book.

## Files

- `output.py` — how a city's raw `cash`/`factory` figures become per-turn income: the `ECONOMY_SCALE` reduction, and the concession/port bonus that settles every third turn.
- `loans.py` — the loan book: tiers, credit limits, interest accrual, overdue seizure, and oldest-first repayment.
- `data/banks.json` — the banks, their limits per tier, and the tier definitions.
- `test_economy.py` — one test per rule below.

## Lending tiers

A bank's terms come from the borrower's relation with that bank's power, on the -10..10 scale defined in `foreign_powers/`.

| Relation | Tier | Term | Interest | Effect |
|---|---|---|---|---|
| -10 … -4 | 不可借貸 | — | — | No new loans; existing loans from that bank fall due at the start of the next turn |
| -3 … 5 | 普通借貸 | 3 turns | 5% per turn | Lower limit |
| 6 … 10 | 優惠借貸 | 6 turns | 3% per turn | Higher limit |

| Bank | Power | 普通 | 優惠 |
|---|---|---|---|
| 香港上海匯豐銀行 | 英 | $30 | $65 |
| 花旗（萬國寶通）銀行 | 美 | $30 | $58 |
| 橫濱正金銀行 | 日 | $26 | $52 |
| 東方匯理銀行 | 法 | $23 | $42 |
| 德華銀行 | 德（中立） | $20 | — |

德華銀行 is neutral: Germany is not on the relation track, so it always lends $20 over 3 turns at 3%. 蘇聯 does not lend commercially and has no bank.

## Turn order

At the start of every turn, for each player:

1. One turn of interest is added to every outstanding loan. That accrued figure is the debt for the rest of the turn.
2. Any bank whose power has fallen into the hostile band calls its loans in.
3. Loans past their due turn are flagged overdue.
4. If anything is overdue, cash on hand is taken first, then that turn's income. Arrears that survive keep taking income every following turn until they clear.
5. Whatever income is left reaches the treasury.

Income is **not** otherwise touched. Outside of arrears, how much to repay each turn is the player's decision, through `/api/repay-debt`.

Repayment always clears the oldest loan first. A bank's available credit is its tier limit minus what the player still owes it, so an unpaid loan blocks new borrowing from that bank.

Loans issued by function cards join the same list, with the issuing bank's current terms.
