# Cards

Card data for *Northern Expedition*.

There are two card types:

- `event` cards are drawn automatically each turn and represent China-wide or world events that may affect all sides.
- `function` cards are optionally purchased by each player at turn start for ¥5, at most twice per turn, and kept in hand until used. Playing a drawn function card has no additional cash cost.

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

Only the cards below are placed into live player decks by `backend/card_engine.py`. Function cards cost money only when drawn: ¥5 per draw, up to 2 draws per turn, with a 6-card hand limit. Playing a function card has no extra cash cost.

Initial deck sizes, including hostile foreign condemnation fillers, are 張 88, 吳 88, 孫 85, 蔣 85. Foreign relations use a 0-10 scale: below 3 is hostile, 8+ is friendly.

| Scope | Card | Copies | Initial draw rate | Current implemented effect |
| --- | --- | ---: | --- | --- |
| Common | 部隊晉升 | 4 | 張/吳 4.5%; 孫/蔣 4.7% | One own mutable-loyalty general gains loyalty +1. Absolute-loyalty generals ignore this. |
| Common | 鼓吹地方自治 | 4 | 張/吳 4.5%; 孫/蔣 4.7% | One opposing non-core, mutable-loyalty general loses loyalty -1. Absolute-loyalty generals ignore this. |
| Common | 步槍補給 | 4 | 張/吳 4.5%; 孫/蔣 4.7% | Gain infantry reserves +2 to +5 battalions. |
| Common | 馬隊徵發 | 2 | 張/吳 2.3%; 孫/蔣 2.4% | Gain cavalry reserves +1 to +3 battalions. |
| Common | 機槍到貨 | 2 | 張/吳 2.3%; 孫/蔣 2.4% | Gain machine-gun reserves +1 to +2 battalions. |
| Common | 火砲撥補 | 1 | 張/吳 1.1%; 孫/蔣 1.2% | Gain artillery reserves +1 to +2 battalions. |
| Common | 城市建設 | 8 | 張/吳 9.1%; 孫/蔣 9.4% | Choose one controlled city; permanent city output increases by cash +1 to +3 and factory +1 to +2. |
| Common | 情報網 | 6 | 張/吳 6.8%; 孫/蔣 7.1% | Choose one playable 民國 province; for 1 turn, reveal enemy army icons and compositions in that province unless protected by `警政系統`. |
| Common | 警政系統 | 4 | 張/吳 4.5%; 孫/蔣 4.7% | For 3 turns, armies outside normal enemy sight are immune to enemy province intel reveals. |
| Common | 共黨暴動 | 3 | 張/吳 3.4%; 孫/蔣 3.5% | Choose one opponent; two random target cities have cash and factory output set to 0 for 3 turns. |
| Common | 青幫暴動 | 3 | 張/吳 3.4%; 孫/蔣 3.5% | Choose one enemy province; all target-owned cities there halt output indefinitely. Initiator receives half halted cash and factory each turn. Target suppresses with 15+ force in province for 3 consecutive turns. |
| Common | 反戰演講：步兵逃散 | 5 | 張/吳 5.7%; 孫/蔣 5.9% | Choose one opponent; remove infantry reserves -3 to -5 battalions, capped by available reserves. |
| Common | 反戰演講：馬隊離營 | 2 | 張/吳 2.3%; 孫/蔣 2.4% | Choose one opponent; remove cavalry reserves -1 to -3 battalions, capped by available reserves. |
| Common | 反戰演講：火力排抗命 | 2 | 張/吳 2.3%; 孫/蔣 2.4% | Choose one opponent; remove machine-gun reserves -1 to -2 battalions, capped by available reserves. |
| Common | 反戰演講：砲兵厭戰 | 1 | 張/吳 1.1%; 孫/蔣 1.2% | Choose one opponent; remove artillery reserves -1 to -2 battalions, capped by available reserves. |
| Common | 急行軍 | 4 | 張/吳 4.5%; 孫/蔣 4.7% | For 3 turns, armies may move 2 rural tiles per turn outside rail movement; rivers still need bridge/pontoon access. |
| Common foreign relation | 對日/對蘇/對英/對法/對美交涉 | 4 each | 張/吳 4.5%; 孫/蔣 4.7% each | Chosen power relation +2, capped to 0-10. Relation 8+ unlocks that power's friendly perk cards. |
| Foreign filler | 日本/蘇聯/英國/法國/美國的譴責 | 3 if relation <3 | depends on faction relation | No effect. Wastes a draw while relations are hostile; undrawn copies are removed once relation recovers. |
| 吳/孫 only | 直系步兵操練 | 2 | 吳 2.3%; 孫 2.4% | Usable only while 吳 and 孫 are not at war; both gain infantry reserves +5. |
| 吳/孫 only | 討奉反正 | 2 | 吳 2.3%; 孫 2.4% | Usable only while 吳 and 孫 are not at war; both gain all-unit attack +5% against 張 for 3 turns. |
| 吳/孫 only | 大帥恩情還不完 | 2 | 吳 2.3%; 孫 2.4% | Usable only while 吳 and 孫 are not at war; 孫 cash -5 per turn and 吳 cash +10 per turn for 5 turns. |
| 吳/孫 only | 聯合反共宣言 | 1 | 吳 1.1%; 孫 1.2% | Usable only while 吳 and 孫 are not at war; 吳/孫 mutable-loyalty generals +3, 張/蔣 mutable-loyalty generals -1. |
| 蔣 only | 黃埔精神 | 2 | 蔣 2.4% | All 蔣 mutable-loyalty generals gain loyalty +2. |
| 蔣 only | 誓師北伐 | 2 | 蔣 2.4% | 蔣 all-unit attack +10% for 3 turns. |
| 蔣 only | 僑胞匯款 | 2 | 蔣 2.4% | 蔣 cash +20. |
| 蔣 only | 國共合作 | 1 | 蔣 1.2% | 蔣 infantry reserves +20, but 蔣 mutable-loyalty generals loyalty -3. |
| 張 only | 東北軍整武 | 2 | 張 2.3% | 張 infantry harm taken -5% for 3 turns. |
| 張 only | 少帥崛起 | 1 | 張 1.1% | If 張學良 is not captive, add infantry +10, cavalry +5, machine gun +2, artillery +1 to 張學良's army. |
| 張 only | 王永江金融改革 | 1 | 張 1.1% | 張 permanent income +¥5 and factory income +2 per turn. |

## Foreign Relation Cards

Relation values 8+ unlock one copy of each friendly perk card for that power. Relation values below 3 add three `...的譴責` filler cards for that power.

| Power | Unit perk | Money perk | Combat perk | Production perk |
| --- | --- | --- | --- | --- |
| 日本 | 三井步槍機槍轉運: 步兵 +4, 機槍 +1 | 橫濱正金短貸: cash +45, debt +55 | 關東軍步兵教範: infantry attack +8% for 3 turns | 南滿鐵路工程隊: controlled 奉天/吉林/黑龍江 cities cash +1, factory +2 |
| 蘇聯 | 蘇式步槍船運: 步兵 +6, 機槍 +1 | 盧布秘密補助: cash +25 | 加倫顧問團: infantry and cavalry attack +6% for 3 turns | 蘇聯軍校教官: one city cash +1-2, factory +3-4 |
| 英國 | 維克斯機槍合約: 機槍 +3 | 匯豐周轉授信: cash +60, debt +70 | 英械火力教官: machine-gun attack +14% for 2 turns | 海關稅務顧問: one city cash +3-4, factory +1-2 |
| 法國 | 法式山砲軍援: 砲兵 +2 | 東方匯理墊款: cash +30, debt +25 | 法國砲兵學校: artillery attack +12% for 3 turns | 法租界工程師: one city cash +2-3, factory +2-3 |
| 美國 | 白朗寧樣品槍: 步兵 +2, 機槍 +1, 砲兵 +1 | 美商現金信貸: cash +40 | 美式火力編組: machine-gun attack +10%, artillery attack +7% for 2 turns | 美國工業技師: one city cash +2, factory +4 |

## War Fog And Intelligence

- Enemy army icons are normally visible only when inside sight range of one of your armies, or while they are in an active battle.
- Seeing an enemy icon does not reveal its unit composition.
- Enemy composition is revealed only in battle or through `情報網`.
- `情報網` reveals one province for 1 turn and is private to the player using it.
- `警政系統` blocks enemy `情報網` reveals against protected armies that are outside normal sight. It does not hide armies already visible by ordinary army sight or battle contact.
