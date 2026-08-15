# Map Overhaul Plan - China-Focused with Civ6 Unit Cycling

> **Archived design note.** The live game now uses the full playable hex map,
> click-to-command movement, land and naval pieces, fog of war, city control,
> railways, rivers, and shared multiplayer state. The mock schema and numbered
> implementation steps below are retained only as design history.

## Map Requirements

### 1. Simplified China Map
- **Remove**: Japan, Korea, Soviet Far East, Mongolia, Southeast Asia, Tibet
- **Keep**: China mainland provinces only (18-20 key provinces)
- **Key cities**: Guangzhou, Wuhan, Nanjing, Shanghai, Beijing, Tianjin, Xi'an, Chengdu
- **Simplified hex grid**: Focus on strategic movement, not detailed terrain
- **Province coloring**: Show faction control with transparent fills

### 2. Troop Markers (番號 System)
Instead of general names, show **unit designation numbers**:
- 第一軍 (1st Army) - Chiang Kai-shek's forces
- 第二軍 (2nd Army) - He Yingqin's forces  
- 第三軍 (3rd Army) - Bai Chongxi's forces
- 第四軍 (4th Army) - Tang Shengzhi's forces

Each marker shows:
- **番號** (army number)
- **Unit composition** on hover (步12 騎2 砲3 機4)
- **Faction color** border
- **Movement status** (halo if not moved this turn)

### 3. Civ6-Style Unit Cycling

**Auto-cycle through unmoved units:**
1. On turn start, build list of all armies that haven't moved
2. Auto-select first unmoved army
3. Show **glowing halo** around selected unmoved unit
4. **Pan camera** to center on that unit
5. Wait for player action:
   - **Move** → execute move, mark as moved, cycle to next
   - **Skip** → mark as skipped, cycle to next
   - **Attack** → show combat, mark as moved, cycle to next
   - **Rest** → mark as fortified, cycle to next
6. When all units processed → enable "End Turn" button

**Visual feedback:**
- Unmoved units: **Golden halo** (pulsing animation)
- Selected unit: **White highlight border**
- Moved units: **Dimmed** with checkmark
- Valid move destinations: **Highlighted hexes**

### 4. Backend Data Structure

```json
{
  "armies": {
    "army_1": {
      "id": "army_1",
      "designation": "第一軍",
      "general_id": "chiang_kai_shek",
      "faction": "N",
      "location": "guangzhou",
      "units": {"infantry": 18, "cavalry": 2, "artillery": 3, "machine_gun": 4},
      "movement_points": 2,
      "has_moved": false,
      "orders": null
    }
  },
  "provinces": {
    "guangzhou": {
      "id": "guangzhou",
      "name": "廣州",
      "controlled_by": "N",
      "adjacent": ["hunan", "jiangxi", "fujian"],
      "city_level": 3,
      "port": true
    }
  }
}
```

### 5. Implementation Steps
1. Create simplified SVG China map with 18-20 provinces
2. Add backend endpoints for army positions and movement
3. Render 番號 markers at army locations
4. Implement Civ6 unit cycling logic
5. Add movement validation and animation
6. Show combat resolution when attacking

This will transform the game from a passive board to an interactive HOI4/Civ6 hybrid.
