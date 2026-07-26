# Cards

Card data for *Northern Expedition*.

There are two card types:

- `event` cards are drawn automatically each turn and represent China-wide or world events that may affect all sides.
- `function` cards are drawn by each player and kept in hand until used. They represent a right to act, such as sabotage, intelligence, black-gold operations, political agitation, or foreign-credit deals.

## Files

- `data/event_cards.json` contains extracted event cards from `PJ Boardgame/北伐風雲_整合遊戲介面.html`.
- `data/function_cards.json` contains the updated function-card list from `北伐風雲遊戲修改.md`.
- `data/injected_event_cards.json` contains event cards that enter the event pool later due to player choices.
- `data/card_pool_rules.json` describes draw timing and dynamic pool mutation.

## Dynamic Event Pool

Function cards can inject event cards into the event pool.

Example:

```json
{
  "id": "japanese_debt_for_firearms",
  "name": "日本債款換械",
  "generated_event_cards": [
    {
      "id": "north_manchuria_railway_concession_demand",
      "name": "要求北滿鐵路特許權",
      "copies": 1
    }
  ]
}
```

So if 張作霖 uses Japanese debt for firearms, `要求北滿鐵路特許權` can be inserted into the future event deck.

## Body Guards

Body guards should not be represented as redundant unit/card state such as extra `機槍營` or separate `菁英衛隊` records.

Use the general-tree field instead:

```json
{
  "body_guard_level": null
}
```

Valid levels are `null`, `low`, and `high`.

Function cards `特勤衛隊：普通` and `特勤衛隊：菁英` simply set that field on a selected general.

## Cleanup Notes

The source HTML still contains old direct foreign military support and concession-garrison wording. The extracted `event_cards.json` marks those records with `status: "needs_rewrite"` when detected. Direct military support cards such as `英軍借調`, `日軍借調`, `法軍借調`, and `蘇軍借調` were intentionally excluded from the new event JSON.
