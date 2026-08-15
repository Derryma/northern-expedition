# UI Reorganization Summary

> **Archived UI milestone.** The iframe/tab prototype described below has been
> replaced by the map-first interface on port `8766`. Current UI ownership is in
> `frontend/app.js`, `frontend/map.js`, `frontend/navy.js`, and
> `frontend/styles.css`; see `frontend/STATUS.md`.

## What Changed

The UI has been reorganized from iframe-based HTML views to a proper **tabbed management interface** that surfaces your game logic directly.

## New Structure

### Navigation Sidebar (Left)

**遊戲階段 (Game Phases)**
- **事件階段** (Event Phase) - Draw and display event cards
- **準備階段** (Preparation Phase) - Purchase troops, build economy, manage debt
- **軍事行動** (Military Operations) - Move armies and engage in combat

**管理面板 (Management Panels)**
- **將領樹** (General Tree) - Hierarchy, loyalty system, command structure
- **募兵徵將** (Recruitment) - Recruit units and generals with force points
- **經濟建設** (Economy) - Income, construction, debt management
- **列強外交** (Foreign Powers) - Relations with Japan, UK, USSR, France
- **手牌管理** (Cards) - Function cards for each player faction

**戰略地圖 (Strategic Map)**
- **戰略地圖** (Map View) - Embedded map interface
- **戰鬥計算器** (Combat Calculator) - HOI4-style combat simulation

## Design System

Following your requirements for HOI4 realism + CIV6 UI simplicity:

### Visual Style
- **Warm, editorial palette**: Cream backgrounds (#F7F4EF), terracotta accents (#C4612F)
- **Typography**: Fraunces serif for headings (with italicized keywords), Inter for UI
- **Layout**: Single column, centered panels with soft shadows
- **Components**: Fully rounded pill buttons, loyalty meters, general portraits

### Game Logic Integration

**General Tree** (from `general_tree/`)
- Displays hierarchy: Great General → Lieutenant Generals → Major Generals
- Shows loyalty values (0-10 scale)
- Highlights non-core factions (桂系, 湘系) vs core faction (中央軍)
- Force strength calculation (infantry=1, cavalry=1, MG=2, artillery=4 FP)

**Recruitment** (from `general_tree/README.md`)
- Unit cards showing cost and force points
- Minimum 5 FP required for new generals
- Command cap enforcement

**Foreign Powers** (from `foreign_powers/`)
- No concession garrisons (removed)
- No direct military support (removed)
- Punitive expedition system (opponent controls foreign side)
- Relation tracking: JP, UK, SU, FR

**Cards System** (from `cards/`)
- Player hands displayed by faction
- Function cards with categories (black_gold, etc.)
- Event injection mechanics visible

## To Run

```bash
python3 scripts/run_playtest_server.py
```

Open: http://127.0.0.1:8766

## Next Steps

The UI framework is ready. You can now:

1. **Connect real data**: Replace mock generals with actual `general_tree` API calls
2. **Wire recruitment**: Connect unit purchase buttons to backend
3. **Economy system**: Build the debt/income tracker
4. **Foreign relations API**: Create endpoints for diplomatic actions
5. **Map integration**: Connect army movement from map to general tree
6. **Phase enforcement**: Lock/unlock actions based on current phase

The old PJ Boardgame HTML files are still accessible via the map tabs for reference, but the new UI gives you organized access to all your redesigned systems.
