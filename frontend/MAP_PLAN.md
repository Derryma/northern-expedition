# Map Integration Plan

> **Archived design note.** This predates the current interactive hex map and is
> not a current implementation plan. The live map is implemented by
> `frontend/map.js`, `frontend/app.js`, and `scenario/data/strategic_map.json`.
> See `frontend/STATUS.md` and the main rulebook for current behavior.

## Current Map Issues
The existing map in `PJ Boardgame/北伐風雲_地圖.html` is overwhelming because:
1. Shows ALL of East Asia (Japan, Korea, Soviet Far East, Mongolia, Tibet, Southeast Asia)
2. Hex grid with detailed province borders and rail lines
3. Too much information for core gameplay

## Simplified Map Requirements

### Focus Area
**China mainland only** (no foreign territories):
- 4 major player factions: F (張), W (吳), S (孫), N (蔣)
- Key NPC factions: Y (晉系), G (西北軍), H (湘軍), D (滇系), C (川軍)
- Major cities and strategic railways only
- Remove: Japan, Korea, Soviet territories, detailed hex numbers

### Troop Display
Each general should appear on map as a **movable unit marker**:
- Stack generals at their HQ city
- Show: General name + unit composition (步12 騎2 砲2 機3)
- Clickable to see details
- Draggable to move between cities

### Next Steps for Map
1. Create simplified China-only SVG map
2. Add general position data to game state
3. Render general markers on map
4. Implement click-to-select, drag-to-move
5. Connect movement to general tree data

## Current Backend State
- General tree data available via `/api/general-tree`
- Need to add general positions to game state
- Need movement validation (adjacent provinces, movement points)

Would you like me to:
1. **Create a simplified China-focused map** (remove foreign territories, clean up detail)
2. **Add general positions to backend** (track which city each general is at)
3. **Implement troop markers on map** (render generals as movable pieces)
