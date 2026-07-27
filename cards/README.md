# Cards

Card data for *Northern Expedition*.

There are two card types:

- `event` cards are drawn automatically each turn and represent China-wide or world events that may affect all sides.
- `function` cards are drawn by each player and kept in hand until used. They represent a right to act, such as sabotage, intelligence, black-gold operations, political agitation, or foreign-credit deals.

## Files

- `data/event_cards.json` contains the cleaned automatic event deck. Old direct foreign attack cards were removed.
- `data/function_cards.json` contains player-held action cards, including many cards migrated out of the old event deck.
- `data/injected_event_cards.json` contains consequence event cards that enter the event pool later due to player choices.
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

The source HTML still contains old direct foreign military support, foreign punitive attack, and concession-garrison wording. The cleaned `event_cards.json` discards those direct foreign attack cards instead of keeping them in the automatic deck.

Cards that are really player choices, such as loans, advisor missions, arms-purchase opportunities, defections, and recruitment actions, belong in `function_cards.json`.
