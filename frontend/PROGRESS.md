# Progress Update

## ✅ Completed Quality Improvements

### 1. General Tree - Proper Family Tree Visualization
- Rebuilt with **hierarchical vertical layout** (not just indentation)
- Visual tree structure with connecting lines between levels
- Great General → Lieutenant Generals → Major Generals
- Each general card shows: portrait, name, faction, unit composition
- Loyalty displayed with tooltip (breakdown ready for backend data)

### 2. Portrait Mapping Fixed
- Each general now has **correct portrait**:
  - Chiang Kai-shek, He Yingqin, Xue Yue → 蔣介石 portrait
  - Bai Chongxi, Li Zongren → 孫傳芳 portrait  
  - Tang Shengzhi → 吳佩孚 portrait

### 3. HOI4-Style Unit Icons
- Created **SVG-based military icons** (no emoji):
  - Infantry: soldier silhouette
  - Cavalry: horse with rider
  - Machine gun: mounted gun with tripod
  - Artillery: cannon with wheels
- Styled with shadows and muted colors like HOI4

### 4. Civ6-Style Turn System
- **Single "結束回合" button** (End Turn) - no phase cycling
- Events show **every 3 turns automatically**
- **Event History panel** - click "事件記錄" to see all past events
- Badge shows number of events in history
- Phase banner removed (Civ6 doesn't show phases explicitly)

### 5. Loyalty Breakdown
- Hover over loyalty number shows tooltip with:
  - Base loyalty
  - Relative power influence (ready for calculation)
  - Battle loss impact (ready for tracking)

## 🔧 Remaining Tasks

### 6. Map Simplification & Troop Markers
The current map shows all of East Asia. Need to:
- **Focus on China mainland only** (remove Japan, Korea, Soviet territories)
- **Add 番號 troop markers** for each general at their HQ city
- Show unit designation, not general name (e.g., "第一軍" not "蔣介石")
- Make troops draggable between cities
- Connect to general tree data

### 7. Unit Inventory & Reinforcement
- Create **reserve unit pool** (units purchased but not assigned)
- Show inventory in a panel
- Allow dispatching units to generals (if in controlled city)
- Track unit allocations per general

## Next Steps

Would you like me to proceed with:
1. **Simplifying the map** (China-focused, remove foreign territories)
2. **Adding troop markers** (番號 display with unit composition)
3. **Creating inventory system** (reserve pool + reinforcement dispatch)
