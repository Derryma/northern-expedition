# Cards

Card data for *Northern Expedition*.

There are two card types:

- `event` cards are drawn automatically each turn and represent China-wide or world events that may affect all sides.
- `function` cards are optionally purchased by each player at turn start for ¥10, at most once per turn, and kept in hand until used. They represent a right to act, such as intelligence, counter-intelligence, sabotage, political agitation, reserve gain, or foreign-credit deals.

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

## Live Function Deck

Only the cards below are placed into live player decks by `backend/card_engine.py`. Initial deck sizes are 張 53, 吳 50, 孫 50, 蔣 53. The draw rate is the chance of drawing that card from a fresh eligible deck before any purchases or discards.

| Scope | Card | Copies | Draw rate | Current implemented effect |
| --- | --- | ---: | --- | --- |
| Common | 部隊晉升 | 4 | 張/蔣 7.5%; 吳/孫 8.0% | One own mutable-loyalty general gains loyalty +1. Absolute-loyalty generals ignore this. |
| Common | 鼓吹地方自治 | 4 | 張/蔣 7.5%; 吳/孫 8.0% | One opposing non-core, mutable-loyalty general loses loyalty -1. Absolute-loyalty generals ignore this. |
| Common | 步槍補給 | 4 | 張/蔣 7.5%; 吳/孫 8.0% | Gain infantry reserves +2 to +5 battalions. |
| Common | 馬隊徵發 | 2 | 張/蔣 3.8%; 吳/孫 4.0% | Gain cavalry reserves +1 to +3 battalions. |
| Common | 機槍到貨 | 2 | 張/蔣 3.8%; 吳/孫 4.0% | Gain machine-gun reserves +1 to +2 battalions. |
| Common | 火砲撥補 | 1 | 張/蔣 1.9%; 吳/孫 2.0% | Gain artillery reserves +1 to +2 battalions. |
| Common | 城市建設 | 4 | 張/蔣 7.5%; 吳/孫 8.0% | Choose one controlled city; permanent city output increases by cash +1 to +3 and factory +1 to +2. |
| Common | 情報網 | 6 | 張/蔣 11.3%; 吳/孫 12.0% | Choose one playable 民國 province; for 1 turn, reveal enemy army icons and compositions in that province unless protected by `警政系統`. |
| Common | 警政系統 | 4 | 張/蔣 7.5%; 吳/孫 8.0% | For 3 turns, your armies outside normal enemy sight are immune to enemy province intel reveals. Visible or battling armies are still visible. |
| Common | 共黨暴動 | 3 | 張/蔣 5.7%; 吳/孫 6.0% | Choose one opponent; two random target cities have cash and factory output set to 0 for 3 turns. Target receives a message. |
| Common | 反戰演講：步兵逃散 | 5 | 張/蔣 9.4%; 吳/孫 10.0% | Choose one opponent; remove infantry reserves -3 to -5 battalions, capped by available reserves. |
| Common | 反戰演講：馬隊離營 | 2 | 張/蔣 3.8%; 吳/孫 4.0% | Choose one opponent; remove cavalry reserves -1 to -3 battalions, capped by available reserves. |
| Common | 反戰演講：火力排抗命 | 2 | 張/蔣 3.8%; 吳/孫 4.0% | Choose one opponent; remove machine-gun reserves -1 to -2 battalions, capped by available reserves. |
| Common | 反戰演講：砲兵厭戰 | 1 | 張/蔣 1.9%; 吳/孫 2.0% | Choose one opponent; remove artillery reserves -1 to -2 battalions, capped by available reserves. |
| 吳/孫 only | 直系步兵操練 | 2 | 吳/孫 4.0% | Usable only while 吳 and 孫 are not at war; both gain infantry reserves +5. |
| 吳/孫 only | 討奉反正 | 2 | 吳/孫 4.0% | Usable only while 吳 and 孫 are not at war; both gain all-unit attack +5% against 張 for 3 turns. |
| 吳/孫 only | 大帥恩情還不完 | 2 | 吳/孫 4.0% | Usable only while 吳 and 孫 are not at war; 孫 cash -5 per turn and 吳 cash +10 per turn for 5 turns. |
| 蔣 only | 蘇聯援助 | 2 | 蔣 3.8% | 蔣 debt +20; reserves gain infantry +5, cavalry +5, machine gun +2. |
| 蔣 only | 黃埔精神 | 2 | 蔣 3.8% | All 蔣 mutable-loyalty generals gain loyalty +2. Absolute-loyalty generals ignore this. |
| 蔣 only | 誓師北伐 | 2 | 蔣 3.8% | 蔣 all-unit attack +10% for 3 turns. |
| 蔣 only | 僑胞匯款 | 2 | 蔣 3.8% | 蔣 cash +20. |
| 蔣 only | 國共合作 | 1 | 蔣 1.9% | 蔣 infantry reserves +20. One copy per deck. |
| 張 only | 東北軍整武 | 2 | 張 3.8% | 張 infantry harm taken -5% for 3 turns. |
| 張 only | 關東軍演習 | 2 | 張 3.8% | 張 infantry attack +5% for 3 turns. |
| 張 only | 日本墾殖團 | 1 | 張 1.9% | 張-controlled cities in 奉天, 吉林, 黑龍江 permanently gain cash +1 and factory +1. One copy per deck. |
| 張 only | 日本借款 | 2 | 張 3.8% | 張 debt +100 and cash +90. |
| 張 only | 滿洲鐵路特許權 | 2 | 張 3.8% | 張 railroad movement limit increases from 3 tiles to 4 tiles for 2 turns. |

## War Fog And Intelligence

- Enemy army icons are normally visible only when inside sight range of one of your armies, or while they are in an active battle.
- Seeing an enemy icon does not reveal its unit composition.
- Enemy composition is revealed only in battle or through `情報網`.
- `情報網` reveals one province for 1 turn and is private to the player using it.
- `警政系統` blocks enemy `情報網` reveals against protected armies that are outside normal sight. It does not hide armies already visible by ordinary army sight or battle contact.
