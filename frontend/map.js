// Strategic map geometry for the 1926 Northern Expedition scenario.

const MIN_LON = 95;
const MAX_LON = 135;
const MIN_LAT = 18;
const MAX_LAT = 54;
// Keep longitude and latitude on the same visual scale. The old 38:28
// projection compressed north-south distances and starved southern China of
// strategic hexes.
const KX = 36;
const KY = 36;

export function px(lon, lat) {
  return [(lon - MIN_LON) * KX, (MAX_LAT - lat) * KY];
}

export function unpx(x, y) {
  return [MIN_LON + x / KX, MAX_LAT - y / KY];
}

export const MAPW = (MAX_LON - MIN_LON) * KX;
export const MAPH = (MAX_LAT - MIN_LAT) * KY;

export const FACTIONS = {
  F: { name: '奉系', shortName: '奉系', type: 'player', color: '#546e7a' },
  W: { name: '直系', shortName: '直系', type: 'player', color: '#6a1b9a' },
  S: { name: '五省聯軍', shortName: '五省聯軍', type: 'player', color: '#2e7d32' },
  N: { name: '國民革命軍', shortName: '國民革命軍', type: 'player', color: '#d89b1d' },
  Y: { name: '晉系（閻錫山）', shortName: '晉', type: 'npc', color: '#6d4c41' },
  G: { name: '西北軍（馮玉祥）', shortName: '西北軍', type: 'npc', color: '#ad496f' },
  M: { name: '西北馬家軍', shortName: '馬', type: 'npc', color: '#16877b' },
  // 湘軍改為平行編制之後沒有大帥，名稱不再掛唐生智。
  H: { name: '湘軍', shortName: '湘', type: 'npc', color: '#88a84e' },
  D: { name: '滇系（唐繼堯）', shortName: '滇', type: 'npc', color: '#7254a8' },
  C: { name: '川軍（防區制）', shortName: '川', type: 'npc', color: '#d8732b' },
  Q: { name: '黔（貴州·中立）', shortName: '黔', type: 'npc', color: '#aaa13d' },
};

// Playable China only. Xinjiang, Tibet, Outer Mongolia, Korea, and foreign
// territories are intentionally outside this silhouette.
export const CHINA_PROPER = [
  [96.1, 39.8], [98.4, 41.5], [103.4, 42.6], [108.6, 42.5], [112.2, 43.8],
  [116.3, 45.3], [119.5, 47.6], [122.6, 53.0], [128.0, 50.1], [134.0, 48.0],
  [134.5, 45.5], [132.5, 44.5], [131.9, 43.1], [130.6, 42.9], [130.2, 42.3],
  [128.6, 41.5], [126.8, 41.2], [125.2, 40.1], [123.0, 39.9], [121.6, 38.9],
  [122.0, 40.2], [121.2, 40.9], [120.9, 40.7], [119.9, 40.0], [119.0, 39.4],
  [118.4, 39.0], [117.6, 38.4], [119.0, 37.9], [120.8, 37.9], [122.7, 37.4],
  [121.1, 36.6], [119.4, 35.4], [120.3, 34.0], [120.9, 32.3], [121.8, 31.4],
  [121.7, 30.8], [122.0, 30.3], [121.1, 29.4], [120.4, 27.5], [119.6, 25.9],
  [118.1, 24.6], [116.8, 23.5], [114.5, 22.8], [113.6, 22.2], [112.0, 21.6],
  [110.4, 21.1], [109.9, 21.0], [108.4, 21.6], [106.5, 20.3], [104.3, 21.5],
  [100.0, 21.7], [98.2, 24.0], [98.8, 27.3], [101.4, 29.5], [100.2, 32.0],
  [98.5, 34.4], [96.4, 36.5],
];

export const HAINAN = [
  [110.0, 20.1], [111.0, 19.9], [110.6, 18.4], [109.2, 18.5], [108.8, 19.8],
];

export const RIVERS = [
  { name: '黃河', pts: [[103.8, 36.1], [106.0, 37.3], [109.0, 40.3], [110.5, 40.4], [110.7, 37.6], [110.4, 34.9], [112.5, 34.8], [114.3, 34.8], [116.5, 35.5], [118.0, 37.0], [119.0, 37.9]] },
  // 蕪湖 (118.4, 31.3) 本來就在長江邊，補上這個控制點之後，原本蕪湖那一格會落在河道上。
  { name: '長江', pts: [[104.1, 30.7], [106.5, 29.6], [108.4, 30.7], [111.3, 30.7], [114.3, 30.6], [116.5, 30.2], [117.0, 30.5], [118.4, 31.3], [118.8, 32.1], [120.4, 32.0], [121.8, 31.4]] },
  { name: '珠江', pts: [[108.3, 22.8], [111.3, 23.5], [112.5, 23.2], [113.3, 23.1], [113.6, 22.4]] },
];

// Approximate 1926 control polygons. Their shared edges are deliberately
// irregular so the strategic layer follows geography instead of rectangles.
const FACTION_TERRITORIES = [
  ['M', [[96.2, 36.4], [98.5, 34.4], [100.2, 32.0], [103.6, 33.0], [103.6, 36.2], [102.2, 37.3], [102.2, 40.0], [98.5, 41.5]]],
  ['D', [[100.0, 21.7], [104.3, 21.5], [105.0, 24.2], [105.0, 27.1], [104.5, 28.8], [101.4, 29.5], [98.8, 27.3], [98.2, 24.0]]],
  ['N', [[104.3, 21.5], [108.4, 21.6], [109.9, 21.0], [113.6, 22.2], [116.8, 23.5], [116.8, 25.2], [113.8, 25.8], [110.8, 25.7], [107.2, 25.8], [106.7, 24.2]]],
  ['Q', [[104.5, 28.8], [105.0, 27.1], [105.0, 25.4], [110.0, 25.8], [110.3, 28.4], [108.2, 28.7], [106.0, 28.7]]],
  ['H', [[110.0, 25.8], [113.8, 25.8], [114.3, 28.7], [113.8, 30.5], [110.7, 30.8], [108.6, 30.0], [110.3, 28.8]]],
  ['C', [[101.4, 29.5], [104.8, 29.0], [106.5, 29.6], [108.6, 30.0], [110.7, 30.8], [110.2, 33.6], [106.0, 34.0], [104.2, 32.4], [100.2, 32.0]]],
  ['Y', [[110.3, 35.2], [112.0, 35.2], [114.5, 35.4], [114.1, 40.3], [111.3, 40.8], [110.0, 38.0]]],
  ['G', [[102.2, 40.0], [102.2, 37.3], [103.6, 36.2], [104.2, 32.4], [106.0, 34.0], [111.0, 34.0], [110.0, 38.0], [111.3, 40.8], [116.3, 42.5], [112.2, 43.8], [108.6, 42.5]]],
  ['W', [[108.6, 30.0], [110.7, 30.8], [110.2, 33.6], [110.2, 34.2], [112.0, 34.6], [114.5, 35.0], [117.0, 34.0], [116.7, 31.0], [114.3, 28.7], [113.8, 30.5]]],
  ['S', [[113.8, 25.8], [116.8, 23.5], [118.1, 24.6], [119.6, 25.9], [120.4, 27.5], [121.1, 29.4], [122.0, 30.3], [121.8, 31.4], [120.9, 32.3], [120.3, 34.0], [119.4, 35.4], [117.0, 34.0], [116.7, 31.0], [114.3, 28.7]]],
  ['F', [[114.5, 35.0], [117.0, 34.0], [119.4, 35.4], [121.1, 36.6], [122.7, 37.4], [120.8, 37.9], [117.6, 38.4], [119.9, 40.0], [120.9, 40.7], [121.6, 38.9], [123.0, 39.9], [125.2, 40.1], [128.6, 41.5], [131.9, 43.1], [134.5, 45.5], [134.0, 48.0], [128.0, 50.1], [122.6, 53.0], [119.5, 47.6], [116.3, 45.3], [112.2, 43.8], [116.3, 42.5], [114.1, 40.3]]],
];

export function pointInPolygon(lon, lat, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const crosses = ((yi > lat) !== (yj > lat))
      && (lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi);
    if (crosses) inside = !inside;
  }
  return inside;
}

export function factionAt(lon, lat) {
  if (pointInPolygon(lon, lat, HAINAN)) return 'N';
  // Province-level guarantees for the core 1926 setup.
  if (lon >= 110.7 && lon <= 116.7 && lat >= 33.2 && lat <= 35.3) return 'W'; // 河南
  if (lon >= 108.3 && lon <= 115.4 && lat >= 29.9 && lat < 33.2) return 'W'; // 湖北
  if (lon >= 102.0 && lon <= 104.0 && lat >= 37.2 && lat <= 40.2) return 'G'; // 甘肅北部
  for (const [faction, polygon] of FACTION_TERRITORIES) {
    if (pointInPolygon(lon, lat, polygon)) return faction;
  }
  return null;
}

export const HEX_SPACING = 0.86;
export const s = 18;
// hexPts() creates flat-top hexes. Their columns are 1.5 radii apart and
// their rows are sqrt(3) radii apart; the previous pointy-top spacing made
// adjacent tiles overlap.
const dx = s * 1.5;
const dy = Math.sqrt(3) * s;

export const COLS = Math.ceil(MAPW / dx) + 1;
export const ROWS = Math.ceil(MAPH / dy) + 1;

export function hcx(c) { return dx * (c + 0.5); }
export function hcy(c, r) { return dy * (r + 0.666) + (c % 2) * (dy / 2); }

export const cells = {};
for (let c = 0; c < COLS; c++) {
  for (let r = 0; r < ROWS; r++) {
    const x = hcx(c);
    const y = hcy(c, r);
    const [lon, lat] = unpx(x, y);
    if (!pointInPolygon(lon, lat, CHINA_PROPER) && !pointInPolygon(lon, lat, HAINAN)) continue;
    const key = `${c},${r}`;
    cells[key] = { key, c, r, lon, lat, land: true, fac: factionAt(lon, lat), river: null };
  }
}

function neighborCoordKeys(c, r) {
  const diagonalRows = c % 2 ? [r, r + 1] : [r - 1, r];
  return [
    `${c},${r - 1}`,
    `${c},${r + 1}`,
    `${c - 1},${diagonalRows[0]}`,
    `${c - 1},${diagonalRows[1]}`,
    `${c + 1},${diagonalRows[0]}`,
    `${c + 1},${diagonalRows[1]}`,
  ];
}

function coastalWaterAllowed(lon, lat) {
  const northernCoast = lon >= 116.1 && lon <= 123.4 && lat >= 36.0 && lat <= 42.8;
  const easternCoast = lon >= 118.0 && lat >= 27.5 && lat <= 36.6;
  const southernCoast = lon >= 108.0 && lat >= 18.2 && lat <= 27.8;
  return northernCoast || easternCoast || southernCoast;
}

const FORCED_COASTAL_WATER = new Set([
  // 天津、渤海灣缺口：讓天津港真正貼近可航行水域，並補掉水面中的陸地洞。
  '30,16', '30,17', '31,18', '32,18',
  // 渤海灣中央的兩個空洞：一圈近海水域繞不到，補上才連得成一片海。
  '33,16', '34,16',
  // 青島右下方：膠州灣外的一格，補上讓青島港南面也連得出去。
  '34,21',
  // 香港外側繞行水道：租借地本身不可通過，旁邊多給兩格讓艦隊繞行。
  '25,37', '26,37',
]);

// 海南島南側多生出來的三格近海：正下方兩格與最南端陸地格的右下一格，
// 都在南海深處，海圖上不該有格子。
const REMOVED_COASTAL_WATER = new Set(['18,40', '19,40', '21,40']);

const FORCED_LAND_CELLS = new Set([
  // 膠濟鐵路沿線：濟南往青島改走陸上路廊，不再把鐵路橋畫進海格。
  '31,19', '32,19', '33,20',
]);

function markCoastalWaterCell(key) {
  const [c, r] = key.split(',').map(Number);
  const [lon, lat] = unpx(hcx(c), hcy(c, r));
  cells[key] = {
    ...(cells[key] || {}),
    key,
    c,
    r,
    lon,
    lat,
    land: false,
    fac: null,
    river: '近海',
    coastalWater: true,
    coastalWaterDepth: 1,
  };
}

function markForcedLandCell(key) {
  const [c, r] = key.split(',').map(Number);
  const [lon, lat] = unpx(hcx(c), hcy(c, r));
  cells[key] = {
    ...(cells[key] || {}),
    key,
    c,
    r,
    lon,
    lat,
    land: true,
    fac: cells[key]?.fac ?? factionAt(lon, lat),
    river: null,
    coastalWater: false,
    coastalWaterDepth: 0,
  };
}

for (const cell of Object.values({ ...cells })) {
  for (const key of neighborCoordKeys(cell.c, cell.r)) {
    if (cells[key]) continue;
    const [c, r] = key.split(',').map(Number);
    const [lon, lat] = unpx(hcx(c), hcy(c, r));
    if (!coastalWaterAllowed(lon, lat)) continue;
    if (pointInPolygon(lon, lat, CHINA_PROPER) || pointInPolygon(lon, lat, HAINAN)) continue;
    cells[key] = {
      key,
      c,
      r,
      lon,
      lat,
      land: false,
      fac: null,
      river: '近海',
      coastalWater: true,
      coastalWaterDepth: 1,
    };
  }
}
for (const key of FORCED_COASTAL_WATER) markCoastalWaterCell(key);
for (const key of FORCED_LAND_CELLS) markForcedLandCell(key);
for (const key of REMOVED_COASTAL_WATER) delete cells[key];

// 多邊形之外、但規則上需要的額外地格。
// 香港在珠江口右下（英國屬地）；瓊州海峽是連接海南島與大陸的水道。
export const EXTRA_CELLS = [
  { key: '25,36' },
  { key: '20,38', river: '瓊州海峽' },
];
for (const spec of EXTRA_CELLS) {
  const [c, r] = spec.key.split(',').map(Number);
  const [lon, lat] = unpx(hcx(c), hcy(c, r));
  const existing = cells[spec.key] || {};
  cells[spec.key] = {
    ...existing,
    key: spec.key,
    c,
    r,
    lon,
    lat,
    land: existing.land ?? true,
    fac: existing.fac ?? null,
    river: spec.navalRoute ? null : (spec.river || existing.river || null),
    coastalWater: spec.navalRoute ? false : Boolean(spec.coastalWater || existing.coastalWater),
    navalRoute: Boolean(spec.navalRoute || existing.navalRoute),
    navalRouteName: spec.navalRouteName || existing.navalRouteName || (spec.navalRoute ? '近海航道' : null),
  };
}

// Hand-drawn control polygons can leave narrow seams. Fill only those seams
// from the nearest assigned land cell so every playable hex has an owner.
const assignedCells = Object.values(cells).filter((cell) => cell.fac);
for (const cell of Object.values(cells)) {
  if (!cell.land || cell.fac) continue;
  let nearest = null;
  let nearestDistance = Infinity;
  for (const candidate of assignedCells) {
    const distance = (candidate.lon - cell.lon) ** 2 + (candidate.lat - cell.lat) ** 2;
    if (distance < nearestDistance) {
      nearest = candidate;
      nearestDistance = distance;
    }
  }
  cell.fac = nearest?.fac || null;
}

// 列強在中國的租借地與屬地。這些地格不屬於任何中國勢力，
// 中國各勢力（含 NPC）都不得進入或通過，也不列入任何省分。
export const FOREIGN_CITIES = [
  { id: 'hongkong', name: '香港', power: 'uk', level: 5, cellKey: '25,36' },
  { id: 'lushun', name: '旅順', power: 'jp', level: 5, cellKey: '36,16' },
  { id: 'vladivostok', name: '海參崴', power: 'su', level: 5, cellKey: '48,12' },
];
for (const city of FOREIGN_CITIES) {
  const cell = cells[city.cellKey];
  if (!cell) continue;
  cell.power = city.power;
  cell.foreignCity = city;
  cell.fac = null;
  cell.river = null;   // 列強城市一律是陸地
}

export function cellAt(lon, lat, requiredFaction = null, excludedKeys = null) {
  let nearest = null;
  let nearestDistance = Infinity;
  for (const cell of Object.values(cells)) {
    if (requiredFaction && cell.fac !== requiredFaction) continue;
    if (excludedKeys?.has(cell.key)) continue;
    const distance = (cell.lon - lon) ** 2 + (cell.lat - lat) ** 2;
    if (distance < nearestDistance) {
      nearest = cell;
      nearestDistance = distance;
    }
  }
  return nearest;
}

function startingCellAt(lon, lat, faction, occupied) {
  const blocked = new Set(occupied);
  for (const cell of Object.values(cells)) {
    if (cell.fac === faction && cell.river) blocked.add(cell.key);
  }
  return cellAt(lon, lat, faction, blocked) || cellAt(lon, lat, faction, occupied);
}

export function cellNeighbors(cellOrKey) {
  const cell = typeof cellOrKey === 'string' ? cells[cellOrKey] : cellOrKey;
  if (!cell) return [];
  const diagonalRows = cell.c % 2 ? [cell.r, cell.r + 1] : [cell.r - 1, cell.r];
  const keys = [
    `${cell.c},${cell.r - 1}`,
    `${cell.c},${cell.r + 1}`,
    `${cell.c - 1},${diagonalRows[0]}`,
    `${cell.c - 1},${diagonalRows[1]}`,
    `${cell.c + 1},${diagonalRows[0]}`,
    `${cell.c + 1},${diagonalRows[1]}`,
  ];
  return keys.map((key) => cells[key]).filter(Boolean);
}

// Sample every river segment densely enough that adjacent river hexes never
// contain gaps, including between widely spaced polyline control points.
for (const river of RIVERS) {
  for (let i = 0; i < river.pts.length - 1; i++) {
    const [fromLon, fromLat] = river.pts[i];
    const [toLon, toLat] = river.pts[i + 1];
    const length = Math.hypot(toLon - fromLon, toLat - fromLat);
    const steps = Math.max(1, Math.ceil(length / (HEX_SPACING * 0.25)));
    for (let step = 0; step <= steps; step++) {
      const progress = step / steps;
      const cell = cellAt(
        fromLon + (toLon - fromLon) * progress,
        fromLat + (toLat - fromLat) * progress,
      );
      if (cell) cell.river = river.name;
    }
  }
}

// 折線之外另外指定為水域的地格：地形上是水面，但不在河道折線的取樣路徑上。
const EXTRA_WATER = [
  // 鄭州正上方一格。黃河主槽在鄭州以北，這一格就是河道本身。
  { name: '黃河', lon: 113.38, lat: 35.24 },
];
for (const spot of EXTRA_WATER) {
  const cell = cellAt(spot.lon, spot.lat);
  if (cell) cell.river = spot.name;
}

for (const cell of Object.values(cells)) {
  if (!cell.navalRoute) continue;
  cell.river = null;
  cell.coastalWater = false;
}

export const ARMY_POSITIONS = {
  N: [
    { id: 'N-1', generalId: 'chiang_kai_shek', general: '蔣介石', designator: '第一軍', startCityId: 'guangzhou', lon: 113.3, lat: 23.1, units: { infantry: 15, cavalry: 2, artillery: 3, machine_gun: 4 } },
    { id: 'N-2', generalId: 'he_yingqin', general: '何應欽', designator: '第二軍', startCityId: 'shantou', lon: 116.7, lat: 23.4, units: { infantry: 12, cavalry: 2, artillery: 2, machine_gun: 4 } },
    { id: 'N-3', generalId: 'bai_chongxi', general: '白崇禧', designator: '第三軍', startCityId: 'nanning', lon: 108.3, lat: 22.8, units: { infantry: 11, cavalry: 2, artillery: 2, machine_gun: 3 } },
    { id: 'N-4', generalId: 'li_zongren', general: '李宗仁', designator: '第四軍', startCityId: 'guilin', lon: 110.3, lat: 25.3, units: { infantry: 9, cavalry: 3, artillery: 1, machine_gun: 2 } },
  ],
  F: [
    { id: 'F-1', generalId: 'zhang_zuolin', general: '張作霖', designator: '第一軍', startCityId: 'fengtian', lon: 123.4, lat: 41.8, units: { infantry: 16, cavalry: 6, artillery: 3, machine_gun: 3 } },
    { id: 'F-2', generalId: 'zhang_xueliang', general: '張學良', designator: '第二軍', startCityId: 'tianjin', lon: 117.2, lat: 39.1, units: { infantry: 12, cavalry: 3, artillery: 2, machine_gun: 2 } },
    { id: 'F-3', generalId: 'yang_yuting', general: '楊宇霆', designator: '第三軍', startCityId: 'beijing', lon: 116.4, lat: 39.9, units: { infantry: 11, cavalry: 2, artillery: 2, machine_gun: 3 } },
    { id: 'F-4', generalId: 'zhang_zongchang', general: '張宗昌', designator: '第四軍', startCityId: 'jinan', lon: 117.0, lat: 36.7, units: { infantry: 14, cavalry: 4, artillery: 1, machine_gun: 2 } },
  ],
  W: [
    { id: 'W-1', generalId: 'wu_peifu', general: '吳佩孚', designator: '第一軍', startCityId: 'hankou', lon: 114.3, lat: 30.6, units: { infantry: 20, cavalry: 2, artillery: 3, machine_gun: 3 } },
    { id: 'W-2', generalId: 'jin_yun_e', general: '靳雲鶚', designator: '第二軍', startCityId: 'zhengzhou', lon: 113.6, lat: 34.7, units: { infantry: 15, cavalry: 1, artillery: 2, machine_gun: 3 } },
    { id: 'W-3', generalId: 'kou_yingjie', general: '寇英傑', designator: '第三軍', startCityId: 'luoyang', lon: 112.4, lat: 34.6, units: { infantry: 12, cavalry: 4, artillery: 2, machine_gun: 3 } },
    { id: 'W-4', generalId: 'chen_jiamo', general: '陳嘉謨', designator: '第四軍', startCityId: 'yichang', lon: 111.3, lat: 30.7, units: { infantry: 12, cavalry: 2, artillery: 1, machine_gun: 2 } },
  ],
  S: [
    { id: 'S-1', generalId: 'sun_chuanfang', general: '孫傳芳', designator: '第一軍', startCityId: 'nanjing', lon: 118.8, lat: 32.1, units: { infantry: 18, cavalry: 1, artillery: 2, machine_gun: 5 } },
    { id: 'S-2', generalId: 'lu_xiangting', general: '盧香亭', designator: '第二軍', startCityId: 'shanghai', lon: 121.5, lat: 31.2, units: { infantry: 15, cavalry: 1, artillery: 2, machine_gun: 3 } },
    { id: 'S-3', generalId: 'zhou_yinren', general: '周蔭人', designator: '第三軍', startCityId: 'fuzhou', lon: 119.3, lat: 26.1, units: { infantry: 12, cavalry: 1, artillery: 1, machine_gun: 3 } },
    { id: 'S-4', generalId: 'meng_zhaoyue', general: '孟昭月', designator: '第四軍', startCityId: 'nanchang', lon: 115.9, lat: 28.7, units: { infantry: 11, cavalry: 2, artillery: 1, machine_gun: 2 } },
  ],
  Y: [
    { id: 'Y-1', generalId: 'yan_xishan', general: '閻錫山', designator: '第一軍', startCityId: 'taiyuan', lon: 112.5, lat: 37.9, units: { infantry: 11, cavalry: 3, artillery: 2, machine_gun: 2 } },
    { id: 'Y-2', generalId: 'fu_zuoyi', general: '傅作義', designator: '第二軍', startCityId: 'datong', lon: 113.3, lat: 40.1, units: { infantry: 7, cavalry: 4, artillery: 0, machine_gun: 2 } },
    { id: 'Y-3', generalId: 'xu_yongchang', general: '徐永昌', designator: '第三軍', startCityId: 'taiyuan', lon: 112.5, lat: 37.9, units: { infantry: 6, cavalry: 4, artillery: 0, machine_gun: 1 } },
  ],
  G: [
    { id: 'G-1', generalId: 'feng_yuxiang', general: '馮玉祥', designator: '第一軍', startCityId: 'xian', lon: 108.9, lat: 34.3, units: { infantry: 10, cavalry: 5, artillery: 1, machine_gun: 2 } },
    { id: 'G-2', generalId: 'song_zheyuan', general: '宋哲元', designator: '第二軍', startCityId: 'guisui', lon: 111.7, lat: 40.8, units: { infantry: 7, cavalry: 4, artillery: 0, machine_gun: 1 } },
    { id: 'G-3', generalId: 'han_fuqu', general: '韓復榘', designator: '第三軍', startCityId: 'xian', lon: 108.9, lat: 34.3, units: { infantry: 8, cavalry: 4, artillery: 1, machine_gun: 2 } },
    { id: 'G-4', generalId: 'lu_zhonglin', general: '鹿鍾麟', designator: '第四軍', startCityId: 'xian', lon: 108.9, lat: 34.3, units: { infantry: 7, cavalry: 3, artillery: 1, machine_gun: 1 } },
  ],
  M: [
    { id: 'M-1', generalId: 'ma_qi', general: '馬麒', designator: '第一軍', startCityId: 'xining', lon: 101.8, lat: 36.6, units: { infantry: 7, cavalry: 5, artillery: 0, machine_gun: 1 } },
    { id: 'M-2', generalId: 'ma_fuxiang', general: '馬福祥', designator: '第二軍', startCityId: 'xining', lon: 101.8, lat: 36.6, units: { infantry: 6, cavalry: 4, artillery: 0, machine_gun: 1 } },
    { id: 'M-3', generalId: 'ma_hongbin', general: '馬鴻賓', designator: '第三軍', startCityId: 'xining', lon: 101.8, lat: 36.6, units: { infantry: 5, cavalry: 4, artillery: 0, machine_gun: 1 } },
  ],
  H: [
    { id: 'H-1', generalId: 'tang_shengzhi', general: '唐生智', designator: '第一軍', startCityId: 'changsha', lon: 112.9, lat: 28.2, units: { infantry: 9, cavalry: 3, artillery: 1, machine_gun: 2 } },
    { id: 'H-2', generalId: 'he_jian', general: '何鍵', designator: '第二軍', startCityId: 'hengyang', lon: 112.6, lat: 26.9, units: { infantry: 7, cavalry: 3, artillery: 0, machine_gun: 1 } },
    { id: 'H-3', generalId: 'zhao_hengti', general: '趙恒惕', designator: '第三軍', startCityId: 'yueyang', lon: 113.1, lat: 29.4, units: { infantry: 7, cavalry: 2, artillery: 1, machine_gun: 1 } },
  ],
  C: [
    { id: 'C-1', generalId: 'liu_xiang', general: '劉湘', designator: '第一軍', startCityId: 'chengdu', lon: 104.1, lat: 30.7, units: { infantry: 9, cavalry: 3, artillery: 1, machine_gun: 1 } },
    { id: 'C-2', generalId: 'liu_wenhui', general: '劉文輝', designator: '第二軍', startCityId: 'chongqing', lon: 106.5, lat: 29.6, units: { infantry: 8, cavalry: 3, artillery: 1, machine_gun: 1 } },
    // 楊森與劉文輝同以重慶為起點，重慶只有一格；楊森指定落在萬縣一帶的陸地格，
    // 免得被擠到長江的水域格上。
    { id: 'C-3', generalId: 'yang_sen', general: '楊森', designator: '第三軍', startCityId: 'chongqing', startCellKey: '16,26', lon: 107.4, lat: 30.9, units: { infantry: 7, cavalry: 2, artillery: 1, machine_gun: 1 } },
  ],
  D: [
    { id: 'D-1', generalId: 'tang_jiyao', general: '唐繼堯', designator: '第一軍', startCityId: 'kunming', lon: 102.7, lat: 25.0, units: { infantry: 8, cavalry: 4, artillery: 1, machine_gun: 1 } },
    { id: 'D-2', generalId: 'long_yun', general: '龍雲', designator: '第二軍', startCityId: 'dali', lon: 100.2, lat: 25.6, units: { infantry: 6, cavalry: 3, artillery: 0, machine_gun: 1 } },
  ],
  Q: [
    { id: 'Q-1', generalId: 'qian_local_militia', general: '黔軍地方部隊', designator: '第一軍', startCityId: 'guiyang', lon: 106.7, lat: 26.6, units: { infantry: 5, cavalry: 3, artillery: 0, machine_gun: 0 } },
  ],
};

// Scenario-load validation: snap every army to the nearest unoccupied hex its
// faction controls. This also protects future data edits from invalid starts.
for (const [faction, armies] of Object.entries(ARMY_POSITIONS)) {
  const occupied = new Set();
  for (const army of armies) {
    const cell = startingCellAt(army.lon, army.lat, faction, occupied);
    if (!cell) throw new Error(`No controlled starting hex available for ${army.id}`);
    army.lon = cell.lon;
    army.lat = cell.lat;
    army.cellKey = cell.key;
    occupied.add(cell.key);
  }
}

export function hexPts(x, y) {
  const points = [];
  for (let i = 0; i < 6; i++) {
    const angle = Math.PI / 180 * (60 * i);
    points.push([x + s * Math.cos(angle), y + s * Math.sin(angle)]);
  }
  return points;
}
