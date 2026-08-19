import { FLAG, factionFlagMarkup, flagMarkup, powerFlagMarkup, POWER_NAME } from './flags.js';
import { RIVERS } from './map.js';
import { px, unpx, MAPW, MAPH, FACTIONS, CHINA_PROPER, HAINAN, pointInPolygon, hexPts, cells, cellAt, cellNeighbors, ARMY_POSITIONS, COLS, ROWS, hcx, hcy, s, FOREIGN_CITIES } from './map.js';
import {
  NAVY_UNIT_META,
  activeGunBoats,
  createInitialNavies,
  maxGunBoatHp,
  maxCargoBoatHp,
  navyCanEnterCell,
  navyCapacity,
  navyFaction,
  navyPath,
  normalizeNavyDivision,
  resolveArmyNavyContact,
  resolveNavyDuel,
  retreatBaselineGunBoatHp,
  restoreHpToFloor,
  totalCargoBoatHp,
  totalGunBoatHp,
} from './navy.js';

const portraits = {
  F: "/assets/portraits/張作霖.jpg",
  W: "/assets/portraits/吳佩孚.jpg",
  S: "/assets/portraits/孫傳芳.jpg",
  N: "/assets/portraits/蔣介石.jpg",
};

const PORTRAIT_BY_ID = {
  chiang_kai_shek: "/assets/portraits/蔣介石.jpg",
  he_yingqin: "/assets/portraits/何應欽.jpg",
  bai_chongxi: "/assets/portraits/白崇禧.jpg",
  tang_shengzhi: "/assets/portraits/唐生智.jpg",
  zhang_zuolin: "/assets/portraits/張作霖.jpg",
  zhang_xueliang: "/assets/portraits/張學良.jpg",
  yang_yuting: "/assets/portraits/楊宇霆.jpg",
  zhang_zongchang: "/assets/portraits/張宗昌.jpg",
  wu_peifu: "/assets/portraits/吳佩孚.jpg",
  jin_yun_e: "/assets/portraits/靳雲鶚.jpg",
  feng_yuxiang: "/assets/portraits/馮玉祥.jpg",
  chen_jiamo: "/assets/portraits/陳嘉謨.jpg",
  kou_yingjie: "/assets/portraits/寇英傑.jpg",
  sun_chuanfang: "/assets/portraits/孫傳芳.jpg",
  zhou_yinren: "/assets/portraits/周蔭人.jpg",
  lu_xiangting: "/assets/portraits/盧香亭.jpg",
  meng_zhaoyue: "/assets/portraits/孟昭月.jpg",
  li_zongren: "/assets/portraits/李宗仁.jpg",
  yan_xishan: "/assets/portraits/閻錫山.jpg",
  fu_zuoyi: "/assets/portraits/傅作義.jpg",
  song_zheyuan: "/assets/portraits/宋哲元.jpg",
  ma_qi: "/assets/portraits/馬麒.jpg",
  ma_fuxiang: "/assets/portraits/馬福祥.jpg",
  he_jian: "/assets/portraits/何鍵.jpg",
  liu_xiang: "/assets/portraits/劉湘.jpg",
  liu_wenhui: "/assets/portraits/劉文輝.jpg",
  tang_jiyao: "/assets/portraits/唐繼堯.jpg",
  long_yun: "/assets/portraits/龍雲.jpg",
  han_fuqu: "/assets/portraits/韓復榘.jpg",
  lu_zhonglin: "/assets/portraits/鹿鍾麟.jpg",
  xu_yongchang: "/assets/portraits/徐永昌.jpg",
  yang_sen: "/assets/portraits/楊森.jpg",
  zhao_hengti: "/assets/portraits/趙恒惕.jpg",
  ma_hongbin: "/assets/portraits/馬鴻賓.jpg",
  // 在野將領
  duan_qirui: "/assets/portraits/段祺瑞.jpg",
  chen_jiongming: "/assets/portraits/陳炯明.jpg",
  tian_zhongyu: "/assets/portraits/田中玉.jpg",
  wang_chengbin: "/assets/portraits/王承斌.jpg",
  li_houji: "/assets/portraits/李厚基.jpg",
  lu_yongxiang: "/assets/portraits/盧永祥.jpg",
};

let bootstrap = null;
let state = null;
let provinceGeoJson = null;
let cardIndex = {};
let generalTreeData = null;
const generalTrees = {};
const initialGeneralTrees = {};
const generalOwners = {};
const initialGeneralOwners = {};
const loyaltyOverrides = {};
let currentPhase = "event"; // event, preparation, military
let currentPlayer = null;
let selectedArmyId = null;
let selectedNavyId = null;
const resolvedArmyIds = new Set();
const resolvedNavyIds = new Set();
const MAX_HAND_SIZE = 6;
const DEFAULT_FUNCTION_CARD_DRAW_COST = 5;
const DEFAULT_FUNCTION_CARD_DRAW_FACTORY_COST = 5;
let foreignTab = "warlords";
let dealTarget = null;
let moveMode = false;
let navyMoveMode = false;
let engineeringMode = null;
let uiNotice = null;
const armyOrderHistory = [];
const navyOrderHistory = [];
let navyDivisions = [];
let initialNavyDivisions = [];
const navyBattleReports = [];
const hiddenNavyBattleReportIds = new Set();
// 瓊州海峽開局就架著浮橋，海南島才連得上大陸。
const PREBUILT_PONTOONS = ['20,38'];
const LAND_ONLY_CITY_IDS = new Set(["hangzhou", "yueyang", "nanchang", "hefei"]);
const completedPontoons = new Set(PREBUILT_PONTOONS);
const completedFortresses = new Set();
const activeBattles = [];
const battleReports = [];
const pendingProvinceClaims = [];
const collapsedBattleIds = new Set();
const hiddenBattleReportIds = new Set();
const retreatConfirmations = new Map();
const RETREAT_CONFIRMATION_MS = 3000;
const TURN_PLAYERS = ["F", "W", "S", "N"];
const turnReady = {};
let selectedBattleId = null;
let selectedTileKey = null;
let mapZoom = 1;
let mapPanX = 0;
let mapPanY = 0;
let suppressMapClick = false;
let cityEconomySync = Promise.resolve();
const jailedGenerals = { F: [], W: [], S: [], N: [] };
const recruitedGenerals = { F: [], W: [], S: [], N: [] };
const INITIAL_ARMY_UNITS = {};
const LOYALTY_BASELINE_ARMY_UNITS = {};
const INITIAL_ARMY_FACTIONS = {};
let sharedRevision = 0;
let sharedSnapshotHash = "";
let sharedEngineHash = "";
let sharedSyncInFlight = false;
let sharedReady = false;
const skippedFunctionPurchasePrompts = new Set();
// 後端寫給某一勢力的通知（紅軍起義、鐵路搶修等），已讀的記在這裡。
const readNotifications = new Set();
const DEBUG_MODE = ["localhost", "127.0.0.1"].includes(window.location.hostname);
// 底圖：《中華民國全圖》掃描件，已依本作的等距圓柱投影（東經 95–135、北緯 18–54）
// 重新取樣，所以圖上的海岸線、省界會和可遊玩區域大致吻合。
const outsideMapArt = new Image();
outsideMapArt.src = "/assets/republic-map-1926.jpg";
// 最底層：舊的列強瓜分中國圖。全圖掃描件是張長方形的紙，套到等距圓柱投影後
// 右下角會缺一塊楔形，那塊就讓瓜分圖透出來填滿。
const underlayMapArt = new Image();
underlayMapArt.src = "/assets/shiju-border.png";
underlayMapArt.addEventListener("load", () => {
  if (state) initMap();
});
// 掃描件圖框在畫布上的範圍：上下是水平線，右緣是一條微彎的線（經線收斂造成）。
// 這組點是用配準參數把原圖右框取樣回畫布座標算出來的，用來裁切上層底圖，
// 邊緣保持銳利、不做羽化。
const SCAN_TOP_Y = 29.5;
// 地圖上緣（北緯 52.5 度以北）掃描件沒有畫到。那條窄帶不讓瓜分圖露出來，
// 改填掃描件自己刻度帶的黃色，接上去才不突兀。
const SCAN_MARGIN_COLOR = '#efd4a8';
const SCAN_BOTTOM_Y = 1296.1;
const SCAN_RIGHT_EDGE = [
  [1632.9, 29.5], [1598.3, 108.7], [1565.5, 187.9], [1534.5, 267.0], [1505.0, 346.2],
  [1477.0, 425.4], [1450.3, 504.5], [1424.8, 583.7], [1400.5, 662.8], [1377.4, 742.0],
  [1355.2, 821.2], [1334.0, 900.3], [1313.6, 979.5], [1294.1, 1058.6], [1275.4, 1137.8],
  [1257.5, 1217.0], [1240.2, 1296.1],
];
// 可遊玩區域的陸地與六角格透明度：留一點讓底圖透出來，好看出兩者的對位。
const PLAYABLE_LAYER_ALPHA = 0.86;

// 列強租借地的顏色，與列強鐵路（南滿、中東、滇越）同一個紅。
const FOREIGN_TERRITORY_FILL = 'rgba(176, 34, 34, 0.34)';

// ── 列強懲戒在地圖上的樣子 ──────────────────────────────────────────────
// 佔領區換成該列強的領土色、城市換成列強紅、區域中央插旗；水域封鎖畫成
// 帶斜紋的同色水面；被轟炸的城市在下方標紅字「轟炸中」並掛上施暴國國旗，
// 解除後轉成「重建中」。全部的判定資料來自後端 state.foreign_punishments，
// 前端只負責畫。
const POWER_TERRITORY_COLORS = {
  jp: '#d8cfa8',   // 淺卡其
  su: '#a3242b',   // 紅色，比西北軍更深
  uk: '#9fc4de',   // 淺藍
  fr: '#3f6fb5',   // 藍
};
// 列強旗幟一律走 flags.js 的 FLAG，與租借地標記、陣營操作板同一套：
// 日本是**旭日旗**、蘇聯是鐮刀錘子紅旗。不要用 emoji——emoji 的日本是日章旗、
// 蘇聯是現代俄羅斯三色旗，放在 1926 年的盤面上兩個都不對。
const powerFlagImageCache = {};

function powerFlagDataUrl(power) {
  const svg = FLAG[power];
  if (!svg) return null;
  // flags.js 的 SVG 是要內嵌進 HTML 的，沒有帶 xmlns；當成獨立圖片載入時
  // 少了這個宣告瀏覽器一律當作壞圖，得補上去。
  const standalone = svg.includes('xmlns=')
    ? svg
    : svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(standalone)}`;
}

// canvas 不能直接畫 SVG 字串，得先做成 Image。圖是非同步載入的，
// 載好之後補畫一次，否則第一輪的佔領旗會是空的。
function powerFlagImage(power) {
  const url = powerFlagDataUrl(power);
  if (!url) return null;
  let img = powerFlagImageCache[power];
  if (!img) {
    img = new Image();
    img.addEventListener('load', () => { if (state) initMap(); });
    img.src = url;
    powerFlagImageCache[power] = img;
  }
  return img.complete && img.naturalWidth ? img : null;
}

// 在 canvas 上畫一面小旗（含深色細框，免得白底旗糊在淺色地形上）。
function drawPowerFlag(ctx, power, cx, cy, width) {
  const img = powerFlagImage(power);
  const height = width * 2 / 3;
  if (!img) return false;
  ctx.save();
  ctx.drawImage(img, cx - width / 2, cy - height / 2, width, height);
  ctx.strokeStyle = 'rgba(24, 20, 16, 0.9)';
  ctx.lineWidth = 1;
  ctx.strokeRect(cx - width / 2, cy - height / 2, width, height);
  ctx.restore();
  return true;
}
const POWER_LABELS = { jp: '日本', su: '蘇聯', uk: '英國', fr: '法國', us: '美國' };
const OCCUPIED_CITY_FILL = 'rgba(140, 31, 28, 0.92)';
const BOMBING_MARK = '#e2483c';
const REBUILD_MARK = '#d9a441';

// 把 #rrggbb 加上透明度。佔領區要蓋住底下的勢力色但不能完全遮死地形。
function withAlpha(hex, alpha) {
  const value = String(hex).replace('#', '');
  const full = value.length === 3
    ? value.split('').map((ch) => ch + ch).join('')
    : value;
  const n = parseInt(full, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function foreignPunishments() {
  return state?.foreign_punishments || [];
}

function occupiedProvinces() {
  const out = {};
  for (const entry of foreignPunishments()) {
    if (entry.kind !== 'ground_occupation') continue;
    for (const province of entry.provinces || []) {
      if (!out[province]) out[province] = entry;   // 先來後到
    }
  }
  return out;
}

function blockadedWaters() {
  const out = {};
  for (const entry of foreignPunishments()) {
    if (entry.kind !== 'water_blockade') continue;
    for (const water of entry.waters || []) {
      if (!out[water]) out[water] = entry;
    }
  }
  return out;
}

function bombedCities() {
  const out = {};
  for (const entry of foreignPunishments()) {
    if (entry.kind !== 'air_raid') continue;
    for (const cityId of entry.city_ids || []) {
      if (!out[cityId]) out[cityId] = entry;
    }
  }
  return out;
}

// 城市現在的狀態：轟炸中 / 重建中 / 沒事。後端也算一份同樣的東西
// （PunishmentBook.city_status），兩邊必須說一樣的話。
function cityPunishmentStatus(cityId) {
  const bombed = bombedCities()[cityId];
  if (bombed) return { status: 'bombing', label: '轟炸中', power: bombed.power };
  const remaining = (state?.city_rebuilding || {})[cityId];
  if (remaining) return { status: 'rebuilding', label: '重建中', remaining_turns: remaining };
  return null;
}

function occupationForCell(cell) {
  if (!cell) return null;
  const province = strategicProvinceForCell(cell);
  if (province && occupiedProvinces()[province] && cell.land) {
    return occupiedProvinces()[province];
  }
  // cell.river 同時放海域名（近海格）與河名（河道格）——map.js 兩邊都寫這個欄位。
  if (cell.river) {
    const entry = blockadedWaters()[cell.river];
    if (entry) return entry;
  }
  return null;
}

// ── 懲戒對部隊與艦隊的實際作用 ─────────────────────────────────────────
// 設計稿寫的是「部隊被鎖在原地」「艦隊被鎖在原地」「城內駐軍被驅趕至鄰近
// 鄉野地格」以及一次性的戰力／艦體損失。部隊與艦隊都住在前端，後端只能把
// 待辦掛在 state.players[x].pending_frontend_effects 上；真正執行的地方是
// 這裡。做完之後打 /api/ack-frontend-effects 銷帳，避免重複扣。

// 這支部隊此刻是否被地面佔領鎖在原地？回傳鎖住它的那筆懲戒，或 null。
// 事件卡造成的「該區部隊本回合／N 回合不可移動」（蘇聯遠東調兵、南滿護路隊擴編）。
// 走 timed_effects 的 movement_freeze，範圍以省份指定；沒指定省份就是全境。
function movementFreezeForArmy(army) {
  const faction = factionForArmy(army);
  const province = strategicProvinceForCell(cells[army?.cellKey]);
  for (const effect of activeTimedEffects(faction, "movement_freeze")) {
    const provinces = effect.provinces || [];
    if (!provinces.length || (province && provinces.includes(province))) return effect;
  }
  return null;
}

function punishmentLockForArmy(army) {
  const cell = cells[army?.cellKey];
  if (!cell) return null;
  const entry = occupationForCell(cell);
  if (!entry || entry.kind !== 'ground_occupation') return null;
  // 懲戒只鎖被罰的那一家；同一塊地上別家的部隊不受影響。
  return entry.owner && entry.owner !== factionForArmy(army) ? null : entry;
}

// 艦隊在封鎖水域或被佔領的沿岸／河道上，一樣被鎖在原地。
function punishmentLockForNavy(navy) {
  const cell = cells[navy?.cellKey];
  if (!cell) return null;
  const entry = occupationForCell(cell);
  if (!entry || !['water_blockade', 'ground_occupation'].includes(entry.kind)) return null;
  return entry.owner && entry.owner !== navyFaction(navy) ? null : entry;
}

function punishmentLockLabel(entry) {
  const power = POWER_LABELS[entry?.power] || entry?.power || '列強';
  return entry?.kind === 'water_blockade' ? `${power}封鎖水域` : `${power}佔領區`;
}

// 一次性戰力損失：照現有的 clampUnitsToForceCap 往下削，削到目標戰力為止。
function scaleArmyForce(army, multiplier) {
  const before = forcePoints(armyUnits(army));
  if (before <= 0) return 0;
  army.units = clampUnitsToForceCap(armyUnits(army), Math.max(0, Math.floor(before * multiplier)));
  const general = generalById(army.generalId);
  if (general) general.units = { ...army.units };
  return before - forcePoints(armyUnits(army));
}

// 艦體損失按比例攤在每艘船上，船數不變（沉船交給既有的正規化流程）。
function scaleNavyHp(navy, multiplier) {
  normalizeNavyDivision(navy, navyRules());
  let lost = 0;
  for (const boat of [...(navy.gunBoats || []), ...(navy.cargoBoatHp || [])]) {
    const before = Math.max(0, Number(boat.hp || 0));
    const after = Math.max(0, Math.round(before * multiplier));
    lost += before - after;
    boat.hp = after;
  }
  normalizeNavyDivision(navy, navyRules());
  return lost;
}

// 把城內駐軍趕到鄰近的鄉野地格：不進城、不進租借地、不疊在別支部隊上。
function evictArmyFromCity(army) {
  const cell = cells[army?.cellKey];
  if (!cell?.city) return null;
  const target = cellNeighbors(cell).find((next) => next.land && !next.city && !next.power
    && !allArmies().some((other) => other.id !== army.id && other.cellKey === next.key));
  if (!target) return null;
  moveArmyToCell(army, target);
  return target;
}

// 執行一筆 foreign_punishment_damage。範圍判定與後端同一套：
// 省份（地面佔領）、水域（封鎖）、城市清單（空襲）。
function applyForeignPunishmentDamage(faction, effect) {
  const notes = [];
  const provinces = new Set(effect.provinces || []);
  const waters = new Set(effect.waters || []);
  const cityIds = new Set(effect.city_ids || []);
  const power = POWER_LABELS[effect.power] || effect.power || '列強';

  const inZone = (cell) => {
    if (!cell) return false;
    if (cityIds.size && cell.city && cityIds.has(cell.city.id)) return true;
    if (provinces.size && cell.land && provinces.has(strategicProvinceForCell(cell))) return true;
    if (waters.size && cell.river && waters.has(cell.river)) return true;
    return false;
  };
  // 「鄰接港口」：封鎖水域旁邊的港市。
  const nextToZone = (cell) => Boolean(cell) && cellNeighbors(cell).some(inZone);

  // 日蘇重疊區的三重傷害是**以初始值為基準相加**的（−40%−10%−40% → 剩 10%），
  // 不是逐次相乘（那會得到 32.4%）。所以後端送來的是「累計損失率」，前端要記住
  // 這條鏈開始前的初始值，每次都從初始值重算，而不是在現值上再乘一次。
  const chain = effect.chain || null;
  const cumulativeForce = Number(effect.cumulative_army_force || 0);
  const cumulativeHull = Number(effect.cumulative_harbor_gunboat_hp || 0);

  let forceLost = 0;
  let evicted = 0;
  for (const army of allArmies()) {
    if (factionForArmy(army) !== faction) continue;
    const cell = cells[army.cellKey];
    const here = inZone(cell);
    if (chain && here && cumulativeForce) {
      forceLost += setArmyForceFromBaseline(army, `${chain}`, 1 - cumulativeForce);
      continue;
    }
    const harbor = Boolean(effect.harbor_army_force) && cell?.city && nextToZone(cell);
    const rate = here ? Number(effect.army_force || 0) : (harbor ? Number(effect.harbor_army_force || 0) : 0);
    if (rate) forceLost += scaleArmyForce(army, 1 + rate);
    if (here && effect.evict_from_city && evictArmyFromCity(army)) evicted += 1;
  }

  let hullLost = 0;
  for (const navy of allNavies()) {
    if (navyFaction(navy) !== faction) continue;
    const cell = cells[navy.cellKey];
    if (!inZone(cell) && !(cell?.city && nextToZone(cell))) continue;
    if (chain && cumulativeHull) {
      hullLost += setNavyHpFromBaseline(navy, `${chain}`, 1 - cumulativeHull);
      continue;
    }
    const rate = Number(effect.fleet_hp || effect.harbor_gunboat_hp || 0);
    if (rate) hullLost += scaleNavyHp(navy, 1 + rate);
  }

  const headline = effect.punishment_kind === 'power_war'
    ? `日蘇${(effect.provinces || []).join('、')}之戰`
    : `${power}懲戒`;
  if (forceLost) notes.push(`${headline}：部隊戰力共 −${forceLost}`);
  if (hullLost) notes.push(`${headline}：艦隊生命共 −${hullLost}`);
  if (evicted) notes.push(`${evicted} 支駐軍被逐出城`);
  return notes;
}

// 三重傷害用的「初始值」帳本：鍵是 部隊/艦隊 id ＋ 這條傷害鏈（通常是省份）。
// 第一次被打到時記下當時的值，之後每一段都從這個值重算。
const punishmentBaselines = new Map();

function setArmyForceFromBaseline(army, chain, remaining) {
  const key = `${army.id}:${chain}`;
  const current = forcePoints(armyUnits(army));
  if (!punishmentBaselines.has(key)) punishmentBaselines.set(key, current);
  const baseline = punishmentBaselines.get(key);
  const target = Math.max(0, Math.floor(baseline * remaining));
  if (target >= current) return 0;
  army.units = clampUnitsToForceCap(armyUnits(army), target);
  const general = generalById(army.generalId);
  if (general) general.units = { ...army.units };
  return current - forcePoints(armyUnits(army));
}

function setNavyHpFromBaseline(navy, chain, remaining) {
  normalizeNavyDivision(navy, navyRules());
  const key = `${navy.id}:${chain}`;
  const boats = [...(navy.gunBoats || []), ...(navy.cargoBoatHp || [])];
  const current = boats.reduce((sum, boat) => sum + Math.max(0, Number(boat.hp || 0)), 0);
  if (!punishmentBaselines.has(key)) punishmentBaselines.set(key, current);
  const baseline = punishmentBaselines.get(key);
  if (!current) return 0;
  const target = Math.max(0, baseline * remaining);
  if (target >= current) return 0;
  const lost = scaleNavyHp(navy, target / current);
  return lost;
}

// 最後通牒：回報每家「哪些指定城市的周邊一格有我方部隊」。
// 旅順、香港、海參崴是列強城市（住在 map.js 的 FOREIGN_CITIES），
// 通牒指定的正是它們，所以兩種城市都要算進去。
function ultimatumGarrisons() {
  const adjacency = new Map();
  for (const cell of Object.values(cells)) {
    const city = cell.city || cell.foreignCity;
    if (!city) continue;
    for (const neighbour of cellNeighbors(cell)) {
      if (!adjacency.has(neighbour.key)) adjacency.set(neighbour.key, new Set());
      adjacency.get(neighbour.key).add(city.id);
    }
  }
  const out = {};
  for (const army of allArmies()) {
    const faction = factionForArmy(army);
    if (!TURN_PLAYERS.includes(faction)) continue;
    const near = adjacency.get(army.cellKey);
    if (!near) continue;
    const list = out[faction] || (out[faction] = []);
    for (const cityId of near) if (!list.includes(cityId)) list.push(cityId);
  }
  return out;
}

// ── 前端待辦的總處理台 ────────────────────────────────────────────────
// 後端把「只有前端做得到的事」掛在 state.players[x].pending_frontend_effects
// 上。這裡是唯一的消費點：每個 kind 都要在 PENDING_EFFECT_HANDLERS 裡登記，
// 做完打 /api/ack-frontend-effects 銷帳。沒登記的 kind 會在主控台叫出來——
// 先前 loyalty_all 就是因為沒人消費而靜靜失效了半年，不要再發生第二次。
const PENDING_EFFECT_HANDLERS = {
  foreign_punishment_damage: (faction, effect) => applyForeignPunishmentDamage(faction, effect),

  // 全體可變忠誠將領加減忠誠。1.8 日本承認北京政府、10.8 復興儒學走這條，
  // 幅度可能已被〈成立官辦廣播電台〉放大（後端算好了，這裡照數字執行）。
  // 列強派來的刺客得手：真的把人從將領樹上抹掉（部屬少將忠誠一併歸零）。
  general_death: (faction, effect) => {
    const owner = effect.owner || faction;
    const general = generalTrees[owner]?.generals?.[effect.general_id];
    if (!applyGeneralDeath(effect.general_id, owner)) return [];
    const who = general?.name || effect.general_id;
    return [`${factionLabel(owner, owner === currentPlayer)}${effect.marshal ? '大帥' : ''}${who}遇刺身亡`];
  },

  loyalty_all: (faction, effect) => {
    const amount = Number(effect.amount || 0);
    if (!amount) return [];
    const ids = mutableGeneralIdsForOwner(faction);
    if (!ids.length) return [];
    ids.forEach((generalId) => adjustGeneralLoyalty(generalId, amount));
    const sign = amount > 0 ? `+${amount}` : `${amount}`;
    const amplified = effect.amplified_by === 'radio_station' ? '（廣播電台放大）' : '';
    return [`${factionLabel(faction, faction === currentPlayer)}全體可變忠誠將領 ${ids.length} 位忠誠 ${sign}${amplified}`];
  },
};

async function consumePendingFrontendEffects() {
  const notes = [];
  const drained = [];
  for (const faction of TURN_PLAYERS) {
    const queue = state?.players?.[faction]?.pending_frontend_effects || [];
    if (!queue.length) continue;
    let handled = false;
    for (const effect of queue) {
      const handler = PENDING_EFFECT_HANDLERS[effect.kind];
      if (!handler) {
        console.warn(`[pending_frontend_effects] 沒有處理器的 kind：${effect.kind}`, effect);
        continue;
      }
      notes.push(...(handler(faction, effect) || []));
      handled = true;
    }
    if (handled) drained.push(faction);
  }
  for (const faction of drained) {
    // 不指定 kind：整個佇列清掉。沒有處理器的項目也一併清，免得無限累積；
    // 上面的 console.warn 已經把它們喊出來了。
    const result = await api('/api/ack-frontend-effects', { player: faction });
    state = result.state;
  }
  if (drained.length) {
    renderArmyMarkers(currentPlayer);
    renderPendingActions();
  }
  return notes;
}

const FOREIGN_CITY_OUTLINE = '#b02222';
outsideMapArt.addEventListener("load", () => {
  if (state) initMap();
});

const UNIT_META = {
  infantry: { name: "步兵", short: "步", symbol: "infantry" },
  cavalry: { name: "騎兵", short: "騎", symbol: "cavalry" },
  machine_gun: { name: "機槍", short: "機", symbol: "machine-gun" },
  artillery: { name: "砲兵", short: "砲", symbol: "artillery" },
};

const UNIT_DISPLAY_SCALE = {
  infantry: { multiplier: 1000, suffix: "人" },
  cavalry: { multiplier: 1000, suffix: "人" },
  machine_gun: { multiplier: 50, suffix: "挺" },
  artillery: { multiplier: 10, suffix: "門" },
};

const GENERAL_SLOT_DEFAULTS = {
  great_general: 3,
  lieutenant_general: 2,
  major_general: 0,
};
const LIEUTENANT_SLOT_CAP = 3;


const TRAIT_LABELS = {
  // 國民革命軍、滇系、川軍、湘軍與在野將領的專屬技能
  advantage_is_ours: "優勢在我",
  whampoa_spirit: "黃埔軍魂",
  precision_barrage: "精準砲擊",
  mountain_division: "山地師",
  elite_mountain_division: "精銳山地師",
  french_comprador: "法國買辦",
  tianfu_land: "天府之國",
  buddhist_general: "佛教將軍",
  hunan_governor: "我才是省長",
  anticommunist_vanguard: "剿共先鋒",
  former_overlord: "前代梟雄",
  anhui_veteran: "皖系舊部",
  zhili_veteran: "直系宿將",
  old_cantonese_army: "老粵軍",
  qilu_veteran: "齊魯宿將",
  // 北洋各系主要將領的專屬技能
  northwest_overlord: "西北霸王",
  dodging_drift: "閃躲漂",
  broadsword_corps: "大刀隊",
  northwest_vanguard: "西北先鋒",
  shanxi_king: "山西王",
  iron_bulwark: "銅牆鐵壁",
  chief_of_staff: "參謀長",
  xining_garrison: "西寧鎮守",
  desert_guard: "大漠衛隊",
  valiant_horse: "驍騎",
  marshal_zhang: "張大帥",
  young_marshal: "少帥",
  white_russian_mercenaries: "白俄傭兵",
  japanese_comprador: "日本買辦",
  elite_artillery: "精銳砲兵",
  five_provinces_alliance: "五省聯軍",
  riverine_warfare: "水域作戰",
  assault_breaker: "攻堅悍將",
  wu_peifu_admired: "吾佩服",
  defensive_specialist: "防禦專家",
  central_plains_veteran: "中原宿將",
  wuchang_veteran: "武昌宿將",
  // 其他 NPC、在野將領沿用的通用特質
  warlord_supremacy: "軍閥統御",
  industrial_organizer: "工業組織者",
  confucian_general: "儒將",
  christian_general: "基督將軍",
  soviet_trained: "蘇式訓練",
  yangzi_defender: "長江守備",
  fujian_garrison: "福建守備",
  jiangxi_commander: "江西統帥",
  layered_defender: "縱深防禦",
  shock_column_leader: "突擊縱隊",
  steady_drillmaster: "練兵能手",
  fire_support_savant: "火力協同",
  local_supply_boss: "地方補給",
  entrenched_warlord: "固守軍閥",
  cavalry_screen_commander: "騎兵屏護",
  foreign_gunnery_advisor: "外籍砲術顧問",
};

// 何應欽的光環說明，兩個版本的技能說明共用同一句。
const CHIANG_AURA_NOTE = "何應欽在同一場戰鬥中作為友軍出現時，他的部隊生命也 +10%（戰鬥結束即恢復）。";

const TRAIT_DESCRIPTIONS = {
  advantage_is_ours: `八十萬對六十萬，優勢在我。${CHIANG_AURA_NOTE}`,
  whampoa_spirit: "何應欽的黃埔部隊。步兵與機槍攻擊 +15%，代價是這兩種兵承傷 +5%。",
  precision_barrage: "白崇禧的砲兵指揮。彈著點算得極準，對各兵種都吃得開。",
  mountain_division: "擅長南方山地作戰。於廣東、廣西、雲南、貴州、四川、湖南境內任何地格作戰時，所部全體承傷 -10%。",
  elite_mountain_division: "劉文輝的川康精銳。於廣東、廣西、雲南、貴州、四川、湖南境內任何地格作戰時，所部全體承傷 -10%、攻擊 +5%。",
  french_comprador: "唐繼堯與法方的往來。加入某陣營時，該陣營對法關係 +3；該陣營遭遇法國譴責時有 30% 機率免疫。",
  tianfu_land: "劉湘握著四川的錢袋。他所屬陣營控制的每座四川城市每回合現金 +1、工業 +1。",
  buddhist_general: "唐生智心中有佛。所部全體承傷 -10%、攻擊 -10%，且被策反時對方成功率額外 -5%。",
  hunan_governor: "趙恒惕的湖南省憲。他所屬陣營控制的每座湖南城市每回合現金 +1、工業 +1；戰場上遇到唐生智時所部全體攻擊 +10%（戰鬥結束即恢復）。",
  anticommunist_vanguard: "何鍵的剿共招牌。與對蘇關係 6 以上的勢力交戰時所部全體攻擊 +10%，鎮壓紅軍起義只需一回合；但自己所屬陣營對蘇關係達 6 以上時本技能失效，且何鍵忠誠 -5。",
  former_overlord: "段祺瑞帶得動北洋最正統的步砲部隊。",
  anhui_veteran: "盧永祥的皖系舊部。步兵與機槍攻擊 +8%；與段祺瑞同一場戰鬥的同一邊時，所部全體生命 +10%（戰鬥結束即恢復）。五省聯軍不可延攬。",
  zhili_veteran: "王承斌的直系班底。騎兵與砲兵攻擊 +7%。",
  old_cantonese_army: "陳炯明的粵軍元老。砲兵攻擊 +12%，鎮壓紅軍起義只需一回合。國民革命軍不可延攬。",
  qilu_veteran: "田中玉的山東舊部。騎兵承傷 -7%、砲兵攻擊 +7%。",
  northwest_overlord: "馮玉祥的統御。所部全體生命 +10%；宋哲元或鹿鍾麟在同一場戰鬥中作為友軍出現時，他們的部隊生命也 +10%（戰鬥結束即恢復）。",
  dodging_drift: "韓復榘的看家本領。部隊極難被咬住，但也不願打硬仗。",
  broadsword_corps: "宋哲元的大刀隊。步兵近身突擊凌厲，代價是挨得更多。",
  northwest_vanguard: "鹿鍾麟的騎兵前導。衝得最前，也最先承受反擊。",
  shanxi_king: "閻錫山的山西體系。所部全體生命 +10%；傅作義或徐永昌同場作為友軍時，他們的部隊生命也 +10%。",
  iron_bulwark: "傅作義的守勢經營。陣地紮實，砲兵配置得宜。",
  chief_of_staff: "徐永昌的參謀作業。作戰計畫周密，少犯無謂損失。",
  xining_garrison: "馬麒的青海根基。所部全體生命 +10%；馬福祥或馬鴻賓同場作為友軍時，他們的部隊生命也 +10%。",
  desert_guard: "馬福祥的沙漠行軍經驗。步騎兵在惡地中仍能保存實力。",
  valiant_horse: "馬鴻賓的騎兵衝擊。",
  marshal_zhang: "張作霖的東北基業。所部全體生命 +10%；張學良同場作為友軍時，少帥的部隊生命也 +10%。",
  young_marshal: "張學良的新式軍事教育。善於運用騎兵與砲兵的協同機動。",
  white_russian_mercenaries: "張宗昌收容的白俄軍官與士兵。所屬陣營對蘇關係達 6 以上時本技能失效，且張宗昌忠誠 -5。",
  japanese_comprador: "張宗昌與日方的往來。加入某陣營時，該陣營對日關係 +2；該陣營遭遇日本譴責時有 10% 機率免疫。",
  elite_artillery: "楊宇霆主持的奉天兵工廠。砲兵器材與訓練均屬一流。",
  five_provinces_alliance: "孫傳芳的五省聯軍。所部全體生命 +10%；孟昭月或盧香亭同場作為友軍時，他們的部隊生命也 +10%。",
  riverine_warfare: "熟悉東南水網。於廣西、廣東、福建、浙江、江蘇、安徽、江西境內任何地格作戰時，所部全體承傷 -10%。",
  assault_breaker: "孟昭月的攻堅打法。步砲協同砸開對方陣地。",
  wu_peifu_admired: "吳佩孚的威望。所部全體生命 +10%；靳雲鶚、寇英傑或陳嘉謨同場作為友軍時，他們的部隊生命也 +10%。",
  defensive_specialist: "靳雲鶚擅長利用地形和縱深防禦，適合固守重要城市與交通線。",
  central_plains_veteran: "寇英傑久經中原戰陣，熟悉當地地形與軍閥打法。",
  wuchang_veteran: "陳嘉謨的武昌城防經驗。步兵與砲兵陣位安排老練，部隊耐打。",
  warlord_supremacy: "以個人威望維繫全軍，適合統率大型軍團與地方派系。",
  industrial_organizer: "擅長兵工、補給與軍需組織，提高重裝部隊的持續作戰能力。",
  confucian_general: "重視軍紀與傳統威望，有利於穩定部隊忠誠。",
  christian_general: "依靠教會與地方人脈組織軍隊和補給。",
  soviet_trained: "接受蘇式參謀與協同作戰訓練。",
  yangzi_defender: "熟悉長江沿線防禦、渡口與水陸交通。",
  fujian_garrison: "熟悉福建山地、港口與地方守備體系。",
  jiangxi_commander: "熟悉江西交通、補給與地方部隊動員。",
  layered_defender: "以層層陣地遲滯對手，換取時間與空間。",
  shock_column_leader: "把步兵與騎兵直接推進對方弱點。",
  steady_drillmaster: "能把生兵帶成可靠正規步兵的練兵者。",
  fire_support_savant: "懂得把砲火集中在對方支撐點上。",
  local_supply_boss: "把糧秣、彈藥與補充兵源撐到最後一刻。",
  entrenched_warlord: "以既設塹壕與地方防務固守防區。",
  cavalry_screen_commander: "以騎兵幕掩護主力調動、追擊潰兵。",
  foreign_gunnery_advisor: "外籍砲術教官帶來的反砲兵射法。",
};

// 光環技能：大帥與名單上的部屬「同戰場」（同一場戰鬥、同一邊）時，
// 部屬的部隊也吃到同一份加成。互為敵軍時不生效（規則 42）。
// 加成是「且」的關係，大帥與每位在場部屬各自都拿到（規則 43）。
const AURA_TRAITS = {
  advantage_is_ours: { partners: ["he_yingqin"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  northwest_overlord: { partners: ["song_zheyuan", "lu_zhonglin"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  shanxi_king: { partners: ["fu_zuoyi", "xu_yongchang"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  xining_garrison: { partners: ["ma_fuxiang", "ma_hongbin"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  marshal_zhang: { partners: ["zhang_xueliang"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  five_provinces_alliance: { partners: ["meng_zhaoyue", "lu_xiangting"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
  wu_peifu_admired: { partners: ["jin_yun_e", "kou_yingjie", "chen_jiamo"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
};

// 自己這邊有指定友軍同戰場時，才給自己加成（盧永祥要段祺瑞在場）。
// 和 AURA_TRAITS 方向相反：光環是「我加給別人」，這個是「別人在場我才強」。
const ALLY_PRESENCE_TRAITS = {
  anhui_veteran: { allies: ["duan_qirui"], modifiers: [{ stat: "hp", multiplier: 1.10 }] },
};

// 對面出現指定將領時才生效（趙恒惕碰上唐生智）。
const ENEMY_PRESENCE_TRAITS = {
  hunan_governor: { enemies: ["tang_shengzhi"], modifiers: [{ stat: "attack", multiplier: 1.10 }] },
};

// 敵方陣營與某列強關係到達門檻時才生效（何鍵打親蘇勢力）。
const ENEMY_RELATION_TRAITS = {
  anticommunist_vanguard: { power: "su", min: 6, modifiers: [{ stat: "attack", multiplier: 1.10 }] },
};

// 只在特定省份生效的技能。
const SOUTHERN_MOUNTAIN_PROVINCES = ["廣東", "廣西", "雲南", "貴州", "四川", "湖南"];
const SOUTHEAST_WATER_PROVINCES = ["廣西", "廣東", "福建", "浙江", "江蘇", "安徽", "江西"];
const PROVINCE_CONDITIONAL_TRAITS = {
  riverine_warfare: {
    provinces: new Set(SOUTHEAST_WATER_PROVINCES),
    modifiers: [{ stat: "harm_taken", multiplier: 0.90 }],
  },
  mountain_division: {
    provinces: new Set(SOUTHERN_MOUNTAIN_PROVINCES),
    modifiers: [{ stat: "harm_taken", multiplier: 0.90 }],
  },
  elite_mountain_division: {
    provinces: new Set(SOUTHERN_MOUNTAIN_PROVINCES),
    modifiers: [{ stat: "harm_taken", multiplier: 0.90 }, { stat: "attack", multiplier: 1.05 }],
  },
};

// 所屬陣營與列強關係太好／太差時會失效的技能。
const RELATION_DISABLED_TRAITS = {
  white_russian_mercenaries: { power: "su", min: 6, loyalty_penalty: 5 },
  anticommunist_vanguard: { power: "su", min: 6, loyalty_penalty: 5 },
};

// 同陣營有指定將領時忠誠 +1。
// 被策反時對方成功率的額外修正（唐生智的〈佛教將軍〉）。
const DEFECTION_RESISTANCE_TRAITS = { buddhist_general: 0.05 };

// 買辦技能：帶著它的將領轉投某陣營時，該陣營對該國關係上升；
// 該陣營被塞那一國的譴責時每張有一定機率被擋下（後端 card_engine 處理）。
const COMPRADOR_TRAITS = {
  japanese_comprador: { power: "jp", gain: 2, immunity: 0.10 },
  french_comprador: { power: "fr", gain: 3, immunity: 0.30 },
};

// 戰鬥數值只有一份來源：comabt_system/data/general_traits.json。
// 之前這裡把 JSON 的 modifiers 和前端表格的 modifiers 相加，
// 兩邊都有的特質會被套用兩次，現在改成只讀 JSON。
function traitModifiers(trait) {
  return bootstrap?.general_traits?.traits?.[trait]?.modifiers || [];
}

// 蔣介石不再屬於國民革命軍時，〈優勢在我〉改個名字與說明，效果一字不動。
const CHIANG_LOST_CAUSE_TRAIT = {
  trait: "advantage_is_ours",
  general: "chiang_kai_shek",
  faction: "N",
  label: "我不明白",
  description: `我不明白，為什麼大家都在談論著項羽被困垓下，仿佛這中原古戰場對於我們注定了凶多吉少。${CHIANG_AURA_NOTE}`,
};

function chiangLostCause(trait, generalId) {
  if (trait !== CHIANG_LOST_CAUSE_TRAIT.trait || generalId !== CHIANG_LOST_CAUSE_TRAIT.general) return false;
  const owner = factionHoldingGeneral(CHIANG_LOST_CAUSE_TRAIT.general);
  return Boolean(owner) && owner !== CHIANG_LOST_CAUSE_TRAIT.faction;
}

function traitLabel(trait, generalId = null) {
  if (chiangLostCause(trait, generalId)) return CHIANG_LOST_CAUSE_TRAIT.label;
  return TRAIT_LABELS[trait] || trait;
}

function traitDescription(trait, generalId = null) {
  const base = chiangLostCause(trait, generalId)
    ? CHIANG_LOST_CAUSE_TRAIT.description
    : TRAIT_DESCRIPTIONS[trait]
    || bootstrap?.general_traits?.traits?.[trait]?.background
    || "此特質目前沒有補充說明。";
  // 光環與省份條件加成不列進「戰鬥效果」，因為說明文字已經寫清楚
  // 生效條件了，重複列出只會讓人以為會疊加兩次。
  const modifiers = traitModifiers(trait);
  const engineering = Object.entries(ENGINEERING_TRAIT_SKILLS || {})
    .filter(([, traits]) => traits.has(trait))
    .map(([skill]) => ENGINEERING_OPERATIONS[skill]?.label)
    .filter(Boolean);
  const effects = [];
  if (modifiers.length) effects.push(`戰鬥效果：${modifiers.map(modifierDescription).join("、")}`);
  if (engineering.length) effects.push(`工程能力：${engineering.join("、")}`);
  return effects.length ? `${base}\n${effects.join("\n")}` : base;
}

function modifierDescription(modifier) {
  const unit = modifier.unit ? `${UNIT_META[modifier.unit]?.name || modifier.unit}` : "全軍";
  const target = modifier.target ? `對${UNIT_META[modifier.target]?.name || modifier.target}` : "";
  const statLabels = {
    attack: "攻擊",
    hp: "生命",
    threshold: "崩潰門檻",
    harm_taken: "承傷",
  };
  const stat = statLabels[modifier.stat] || modifier.stat || "效果";
  if (modifier.multiplier !== undefined) {
    const delta = (Number(modifier.multiplier) - 1) * 100;
    return `${unit}${target}${stat} ${delta >= 0 ? "+" : ""}${Math.round(delta)}%`;
  }
  if (modifier.add !== undefined) {
    const delta = Number(modifier.add) * 100;
    return `${unit}${target}${stat} ${delta >= 0 ? "+" : ""}${Math.round(delta)}%`;
  }
  return `${unit}${target}${stat}`;
}

function traitChip(trait, generalId = null) {
  const description = traitDescription(trait, generalId);
  return `<span class="trait-chip" tabindex="0" data-tooltip="${description}">${traitLabel(trait, generalId)}</span>`;
}

const ENGINEERING_OPERATIONS = {
  pontoon_bridge: { label: "架設浮橋", turns: 2, factoryCost: 10 },
  fortress_builder: { label: "構築要塞", turns: 3, factoryCost: 10 },
};
// 工程能力除了將領檔案裡的 skills 之外，也可以由特質帶出來。
// 22 名主要將領的浮橋／要塞是寫在各自的 skills 欄位，這裡保留的是
// 其他 NPC 與在野將領沿用的通用特質對應。
const ENGINEERING_TRAIT_SKILLS = {
  pontoon_bridge: new Set([
    "young_marshal", "riverine_warfare", "dodging_drift", "central_plains_veteran",
    "whampoa_spirit", "anhui_veteran", "old_cantonese_army",
    "christian_general", "yangzi_defender", "local_supply_boss",
  ]),
  fortress_builder: new Set([
    "broadsword_corps", "iron_bulwark", "marshal_zhang", "elite_artillery", "assault_breaker",
    "defensive_specialist", "advantage_is_ours", "elite_mountain_division", "hunan_governor",
    "former_overlord", "zhili_veteran", "qilu_veteran",
    "industrial_organizer", "fujian_garrison", "warlord_supremacy", "shock_column_leader",
  ]),
};

const TACTIC_LABELS = {
  normal_advance: "穩健推進",
  probing_attack: "試探攻擊",
  layered_delaying: "層次遲滯",
  all_out_offense: "全力進攻",
  last_stand: "死守陣地",
  pinning_attack: "牽制攻擊",
};
const OFFENSIVE_TACTICS = ["normal_advance", "probing_attack", "all_out_offense", "pinning_attack"];
const DEFENSIVE_TACTICS = ["normal_advance", "layered_delaying", "last_stand"];
const NPC_TACTIC_CHOICES = ["normal_advance", "layered_delaying"];
const COMBAT_ESTIMATE_CALIBRATION = 0.45;
const CHINESE_ARMY_NUMERALS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
const CHINESE_ARMY_NUMERAL_VALUES = Object.fromEntries(CHINESE_ARMY_NUMERALS.map((char, index) => [char, index]));
const OVERRUN_SURRENDER_FORCE = 8;
const OVERRUN_FORCE_RATIO = 2.5;

const INITIAL_ARMY_CELLS = Object.fromEntries(
  Object.values(ARMY_POSITIONS).flat().map((army) => [army.id, {
    cellKey: army.cellKey,
    lon: army.lon,
    lat: army.lat,
  }])
);
const INITIAL_CELL_FACTIONS = Object.fromEntries(
  Object.values(cells).map((cell) => [cell.key, cell.fac])
);
const INITIAL_CITY_FACTIONS = {};

const $ = (id) => document.getElementById(id);

function formatUnitQuantity(type, count, compact = false) {
  const display = UNIT_DISPLAY_SCALE[type];
  const amount = Math.max(0, Number(count) || 0) * display.multiplier;
  if (compact && amount >= 1000) return `${new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 1, notation: "compact" }).format(amount)}${display.suffix}`;
  return `${amount.toLocaleString("zh-TW", { maximumFractionDigits: 1 })}${display.suffix}`;
}

function armyCombatLabel(army) {
  if (!army) return "未知軍隊";
  const faction = factionForArmy(army);
  return `${FACTIONS[faction]?.shortName || faction} ${army.designator}`;
}

function hexToRgb(hex) {
  const clean = String(hex || "").replace("#", "");
  const value = parseInt(clean.length === 3
    ? clean.split("").map((char) => char + char).join("")
    : clean, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

function mixColor(hex, base = "#e7dcbe", weight = 0.52) {
  const source = hexToRgb(hex);
  const backdrop = hexToRgb(base);
  const channel = (name) => Math.round(source[name] * weight + backdrop[name] * (1 - weight));
  return `rgb(${channel("r")}, ${channel("g")}, ${channel("b")})`;
}

function armyCompositionVisible(army, observer = currentPlayer) {
  if (!army) return false;
  if (factionForArmy(army) === observer) return true;
  return Boolean(activeBattleForArmy(army) || armyRevealedByIntel(army, observer));
}

function tacticData(tacticId) {
  return bootstrap?.tactics?.tactics?.[tacticId] || {
    attack_multiplier: 1,
    harm_taken_multiplier: 1,
    threshold: 0.3,
  };
}

function rawUnitTotalsForArmy(army) {
  return army.units || {};
}

function tacticOptionLabel(tacticId) {
  const tactic = tacticData(tacticId);
  return `${TACTIC_LABELS[tacticId] || tacticId} · 攻×${Number(tactic.attack_multiplier).toFixed(2)} / 承傷×${Number(tactic.harm_taken_multiplier).toFixed(2)} / 退卻${Math.round(Number(tactic.threshold) * 100)}%`;
}

function tacticOptionsMarkup(selectedId, side = null) {
  const allowed = side === "A" ? OFFENSIVE_TACTICS
    : side === "B" ? DEFENSIVE_TACTICS
    : Object.keys(bootstrap.tactics?.tactics || TACTIC_LABELS);
  return allowed
    .map((id) => `<option value="${id}" ${selectedId === id ? "selected" : ""}>${tacticOptionLabel(id)}</option>`)
    .join("");
}

function factionIsNpc(faction) {
  return FACTIONS[faction]?.type === "npc";
}

function npcTacticForSide(battle, side) {
  if (!battle || !factionIsNpc(side === "A" ? battle.attackerFaction : battle.defenderFaction)) return null;
  if (side === "B") return "layered_delaying";
  return "normal_advance";
}

function applyNpcBattleDefaults(battle) {
  if (!battle) return;
  battle.tactics ||= { A: "normal_advance", B: "normal_advance" };
  battle.confirmed ||= { A: false, B: false };
  battle.tacticRevision ||= { A: true, B: true };
  for (const side of ["A", "B"]) {
    const tactic = npcTacticForSide(battle, side);
    if (!tactic) continue;
    battle.tactics[side] = tactic;
    battle.confirmed[side] = true;
    battle.tacticRevision[side] = false;
  }
}

function chineseNumber(value) {
  const number = Math.max(1, Math.floor(Number(value) || 1));
  if (number <= 10) return CHINESE_ARMY_NUMERALS[number];
  if (number < 20) return `十${CHINESE_ARMY_NUMERALS[number - 10]}`;
  const tens = Math.floor(number / 10);
  const ones = number % 10;
  return `${CHINESE_ARMY_NUMERALS[tens]}十${ones ? CHINESE_ARMY_NUMERALS[ones] : ""}`;
}

function parseChineseNumber(text) {
  if (!text) return 0;
  if (Object.hasOwn(CHINESE_ARMY_NUMERAL_VALUES, text)) return CHINESE_ARMY_NUMERAL_VALUES[text];
  if (text === "十") return 10;
  if (text.startsWith("十")) return 10 + (CHINESE_ARMY_NUMERAL_VALUES[text.slice(1)] || 0);
  const match = text.match(/^(.+)十(.+)?$/);
  if (!match) return 0;
  const tens = CHINESE_ARMY_NUMERAL_VALUES[match[1]] || 0;
  const ones = match[2] ? CHINESE_ARMY_NUMERAL_VALUES[match[2]] : 0;
  return tens > 0 && ones >= 0 ? tens * 10 + ones : 0;
}

function parseArmyDesignatorNumber(designator) {
  const text = String(designator || "");
  const arabic = text.match(/第(\d+)軍/);
  if (arabic) return Number(arabic[1]) || 0;
  const chinese = text.match(/第([一二三四五六七八九十]+)軍/);
  return chinese ? parseChineseNumber(chinese[1]) : 0;
}

function nextAvailableArmyNumber(faction, excludedArmyId = null) {
  const used = new Set(allArmies(true)
    .filter((item) => factionForArmy(item) === faction && item.id !== excludedArmyId)
    .map((item) => parseArmyDesignatorNumber(item.designator))
    .filter(Boolean));
  let candidate = 1;
  while (used.has(candidate)) candidate += 1;
  return candidate;
}

function formatArmyDesignator(number) {
  return `第${chineseNumber(number)}軍`;
}

function setupUiTooltip() {
  const tooltip = $("uiTooltip");
  const show = (chip) => {
    const message = chip?.dataset.tooltip;
    if (!message) return;
    tooltip.textContent = message;
    tooltip.hidden = false;
    const chipRect = chip.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const left = Math.min(
      window.innerWidth - tooltipRect.width - 10,
      Math.max(10, chipRect.left + chipRect.width / 2 - tooltipRect.width / 2),
    );
    const above = chipRect.top - tooltipRect.height - 8;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${above >= 10 ? above : chipRect.bottom + 8}px`;
  };
  const hide = () => {
    tooltip.hidden = true;
  };
  document.addEventListener("pointerover", (event) => {
    const chip = event.target.closest?.(".trait-chip");
    if (chip) show(chip);
  });
  document.addEventListener("pointerout", (event) => {
    const chip = event.target.closest?.(".trait-chip");
    if (chip && !chip.contains(event.relatedTarget)) hide();
  });
  document.addEventListener("focusin", (event) => {
    const chip = event.target.closest?.(".trait-chip");
    if (chip) show(chip);
  });
  document.addEventListener("focusout", (event) => {
    if (event.target.closest?.(".trait-chip")) hide();
  });
}

async function loadGeneralTreeForFaction(factionCode) {
  try {
    generalTrees[factionCode] ||= await api(`/api/general-tree?faction=${factionCode}`);
    normalizeGeneralTree(generalTrees[factionCode]);
    generalTreeData = generalTrees[factionCode];
  } catch (error) {
    console.error(`Failed to load general tree for ${factionCode}:`, error);
    generalTreeData = null;
  }
}

async function loadAllGeneralTrees() {
  await Promise.all(Object.keys(ARMY_POSITIONS).map(async (faction) => {
    generalTrees[faction] = await api(`/api/general-tree?faction=${faction}`);
    normalizeGeneralTree(generalTrees[faction]);
    initialGeneralTrees[faction] = JSON.parse(JSON.stringify(generalTrees[faction]));
  }));
}

function initializeGeneralRuntime() {
  for (const key of Object.keys(generalOwners)) delete generalOwners[key];
  for (const key of Object.keys(loyaltyOverrides)) delete loyaltyOverrides[key];
  for (const key of Object.keys(initialGeneralOwners)) delete initialGeneralOwners[key];
  for (const [faction, tree] of Object.entries(generalTrees)) {
    normalizeGeneralTree(tree);
    for (const generalId of Object.keys(tree.generals || {})) {
      generalOwners[generalId] = faction;
      initialGeneralOwners[generalId] = faction;
    }
  }
}

function generalAbsoluteLoyaltyActive(general) {
  if (!general?.absolute_loyalty) return false;
  if (Object.hasOwn(loyaltyOverrides, general.id) && Number(loyaltyOverrides[general.id]) <= 1) return false;
  const initialOwner = initialGeneralOwners[general.id];
  return !initialOwner || generalOwners[general.id] === initialOwner;
}

function normalizedSlotCount(general) {
  const role = general?.role || "major_general";
  if (role === "great_general") return GENERAL_SLOT_DEFAULTS.great_general;
  if (role === "major_general") return GENERAL_SLOT_DEFAULTS.major_general;
  const current = Number(general?.subordinate_slots ?? GENERAL_SLOT_DEFAULTS.lieutenant_general);
  return Math.max(GENERAL_SLOT_DEFAULTS.lieutenant_general, Math.min(LIEUTENANT_SLOT_CAP, current || 0));
}

function normalizeGeneralTree(tree) {
  for (const general of Object.values(tree?.generals || {})) {
    const slots = normalizedSlotCount(general);
    general.subordinate_slots = slots;
    if (general.role === "major_general") general.subordinates = [];
  }
  return tree;
}

function synchronizeFieldArmies() {
  for (const [faction, armies] of Object.entries(ARMY_POSITIONS)) {
    const tree = generalTrees[faction];
    for (const army of armies) {
      const general = tree?.generals?.[army.generalId];
      if (!general) throw new Error(`Field army ${army.id} has no matching general ${army.generalId}`);
      army.general = general.name;
      army.units = { ...general.units };
      army.status = "active";
      army.faction = faction;
      INITIAL_ARMY_UNITS[army.id] = { ...general.units };
      LOYALTY_BASELINE_ARMY_UNITS[army.id] = { ...general.units };
      INITIAL_ARMY_FACTIONS[army.id] = faction;
    }
  }
}

function refreshArmyLoyaltyBaselines(force = false) {
  const turn = Number(state?.turn || 0);
  if (!force && turn % 5 !== 0) return;
  for (const army of allArmies()) {
    LOYALTY_BASELINE_ARMY_UNITS[army.id] = wholeUnits(armyUnits(army));
  }
}

function generalById(generalId) {
  const owner = generalOwners[generalId];
  return generalTrees[owner]?.generals?.[generalId]
    || Object.values(generalTrees).map((tree) => tree.generals?.[generalId]).find(Boolean)
    || null;
}

function mutableGeneralIdsForOwner(owner) {
  return Object.entries(generalOwners)
    .filter(([, generalOwner]) => generalOwner === owner)
    .map(([generalId]) => generalId)
    .filter((generalId) => {
      const general = generalById(generalId);
      return general && general.loyalty !== null && !generalAbsoluteLoyaltyActive(general) && !general.loyalty_exempt;
    });
}

function adjustGeneralLoyalty(generalId, amount) {
  const general = generalById(generalId);
  if (!general || general.loyalty === null || generalAbsoluteLoyaltyActive(general) || general.loyalty_exempt) return;
  const fieldArmy = allArmies(true).find((army) => army.generalId === generalId);
  const current = calculateGeneralLoyalty(general, fieldArmy).value ?? 1;
  loyaltyOverrides[generalId] = Math.max(1, Math.min(10, current + Number(amount || 0)));
}

function applyFunctionSideEffects(result) {
  if (result.assassination) applyAssassination(result.assassination);
  if (result.exile_recruit) applyExileRecruit(result.exile_recruit);
  if (result.target_general_id && result.loyalty_delta) {
    adjustGeneralLoyalty(result.target_general_id, result.loyalty_delta);
  }
  if (result.affiliation_slot_delta) {
    const { general_id: generalId, amount } = result.affiliation_slot_delta;
    const general = generalById(generalId);
    if (general && general.role === "lieutenant_general") {
      general.subordinate_slots = Math.min(
        LIEUTENANT_SLOT_CAP,
        Math.max(GENERAL_SLOT_DEFAULTS.lieutenant_general, Number(general.subordinate_slots || GENERAL_SLOT_DEFAULTS.lieutenant_general) + Number(amount || 0)),
      );
    }
  }
  if (result.loyalty_delta_all) {
    mutableGeneralIdsForOwner(result.loyalty_delta_all.owner)
      .forEach((generalId) => adjustGeneralLoyalty(generalId, result.loyalty_delta_all.amount));
  }
  for (const swing of result.loyalty_swings || []) {
    mutableGeneralIdsForOwner(swing.owner).forEach((generalId) => adjustGeneralLoyalty(generalId, swing.amount));
  }
  if (result.army_unit_delta) {
    const { general_id: generalId, unit_reserves: units, requires_active: requiresActive } = result.army_unit_delta;
    const army = allArmies(true).find((item) => item.generalId === generalId);
    if (!army || (requiresActive && army.status === "jailed")) return;
    const nextUnits = { ...armyUnits(army) };
    for (const [unitType, amount] of Object.entries(units || {})) {
      nextUnits[unitType] = Math.max(0, Math.ceil(Number(nextUnits[unitType] || 0) + Number(amount || 0)));
    }
    setArmyTotalUnits(army, nextUnits);
  }
}

function descendantGeneralIds(tree, generalId) {
  const descendants = [];
  const visit = (id) => {
    for (const subordinateId of tree?.generals?.[id]?.subordinates || []) {
      if (descendants.includes(subordinateId)) continue;
      descendants.push(subordinateId);
      visit(subordinateId);
    }
  };
  visit(generalId);
  return descendants;
}

function commandDescendantIds(sourceTree, generalId, capturedGeneral = null) {
  const descendants = new Set(descendantGeneralIds(sourceTree, generalId));
  const visitCopy = (general) => {
    for (const subordinate of general?.subordinates || []) {
      const subordinateId = typeof subordinate === "string" ? subordinate : subordinate?.id;
      if (!subordinateId || descendants.has(subordinateId)) continue;
      descendants.add(subordinateId);
      descendantGeneralIds(sourceTree, subordinateId).forEach((id) => descendants.add(id));
      if (typeof subordinate === "object") visitCopy(subordinate);
    }
  };
  visitCopy(capturedGeneral);
  return [...descendants];
}

async function api(path, payload = null) {
  const options = payload
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function tacticalSnapshot() {
  return {
    armies: Object.fromEntries(allArmies(true).map((army) => [army.id, {
      cellKey: army.cellKey,
      lon: army.lon,
      lat: army.lat,
      units: { ...army.units },
      status: army.status,
      faction: army.faction,
      embarkedOn: army.embarkedOn || null,
      previousCellKey: army.previousCellKey || null,
      resolvedTurn: army.resolvedTurn ?? null,
      specialOperation: army.specialOperation ? { ...army.specialOperation } : null,
      showRecruitment: Boolean(army.showRecruitment),
      npcGrowthEnded: Boolean(army.npcGrowthEnded),
      fieldHospitalPending: army.fieldHospitalPending || null,
      forcedMarchUntilTurn: army.forcedMarchUntilTurn ?? null,
      forcedMarchReadyTurn: army.forcedMarchReadyTurn ?? null,
    }])),
    cellFactions: Object.fromEntries(Object.values(cells).map((cell) => [cell.key, cell.fac])),
    cityFactions: Object.fromEntries((bootstrap.strategic_map?.cities || []).map((city) => [city.id, city.faction])),
    cityEconomy: Object.fromEntries((bootstrap.strategic_map?.cities || []).map((city) => [city.id, {
      cash: city.cash,
      factory: city.factory,
      faction: city.faction,
    }])),
    activeBattles: JSON.parse(JSON.stringify(activeBattles)),
    battleReports: JSON.parse(JSON.stringify(battleReports)),
    navyDivisions: JSON.parse(JSON.stringify(navyDivisions)),
    navyBattleReports: JSON.parse(JSON.stringify(navyBattleReports)),
    generalTrees: JSON.parse(JSON.stringify(generalTrees)),
    generalOwners: { ...generalOwners },
    loyaltyOverrides: { ...loyaltyOverrides },
    loyaltyBaselineArmyUnits: JSON.parse(JSON.stringify(LOYALTY_BASELINE_ARMY_UNITS)),
    jailedGenerals: JSON.parse(JSON.stringify(jailedGenerals)),
    recruitedGenerals: JSON.parse(JSON.stringify(recruitedGenerals)),
    completedPontoons: [...completedPontoons],
    completedFortresses: [...completedFortresses],
    resolvedArmyIds: [...resolvedArmyIds],
    resolvedNavyIds: [...resolvedNavyIds],
    armyOrderHistory: JSON.parse(JSON.stringify(armyOrderHistory)),
    navyOrderHistory: JSON.parse(JSON.stringify(navyOrderHistory)),
    turnReady: { ...turnReady },
    pendingProvinceClaims: JSON.parse(JSON.stringify(pendingProvinceClaims)),
  };
}

function replaceObject(target, source) {
  for (const key of Object.keys(target)) delete target[key];
  Object.assign(target, source || {});
}

function replaceArray(target, source) {
  target.splice(0, target.length, ...(source || []));
}

function applyTacticalSnapshot(snapshot) {
  if (!snapshot) return;
  for (const [armyId, saved] of Object.entries(snapshot.armies || {})) {
    const army = armyById(armyId);
    if (!army) continue;
    Object.assign(army, saved);
    if (!saved.specialOperation) delete army.specialOperation;
  }
  for (const [cellKey, faction] of Object.entries(snapshot.cellFactions || {})) {
    if (cells[cellKey]) cells[cellKey].fac = faction;
  }
  for (const city of bootstrap.strategic_map?.cities || []) {
    if (snapshot.cityFactions?.[city.id]) city.faction = snapshot.cityFactions[city.id];
    if (snapshot.cityEconomy?.[city.id]) {
      city.cash = snapshot.cityEconomy[city.id].cash ?? city.cash;
      city.factory = snapshot.cityEconomy[city.id].factory ?? city.factory;
      city.faction = snapshot.cityEconomy[city.id].faction || city.faction;
    }
  }
  replaceArray(activeBattles, snapshot.activeBattles);
  replaceArray(battleReports, snapshot.battleReports);
  if (Array.isArray(snapshot.navyDivisions) && snapshot.navyDivisions.length) {
    replaceArray(navyDivisions, snapshot.navyDivisions);
  }
  for (const navy of navyDivisions) normalizeNavyDivision(navy, navyRules());
  replaceArray(navyBattleReports, snapshot.navyBattleReports);
  replaceObject(generalTrees, JSON.parse(JSON.stringify(snapshot.generalTrees || generalTrees)));
  for (const tree of Object.values(generalTrees)) normalizeGeneralTree(tree);
  replaceObject(generalOwners, snapshot.generalOwners);
  replaceObject(loyaltyOverrides, snapshot.loyaltyOverrides);
  if (snapshot.loyaltyBaselineArmyUnits) replaceObject(LOYALTY_BASELINE_ARMY_UNITS, snapshot.loyaltyBaselineArmyUnits);
  for (const faction of new Set([...Object.keys(jailedGenerals), ...Object.keys(snapshot.jailedGenerals || {})])) {
    jailedGenerals[faction] ||= [];
    recruitedGenerals[faction] ||= [];
    replaceArray(jailedGenerals[faction], snapshot.jailedGenerals?.[faction]);
    replaceArray(recruitedGenerals[faction], snapshot.recruitedGenerals?.[faction]);
  }
  completedPontoons.clear();
  for (const key of snapshot.completedPontoons || []) completedPontoons.add(key);
  completedFortresses.clear();
  for (const key of snapshot.completedFortresses || []) completedFortresses.add(key);
  resolvedArmyIds.clear();
  for (const armyId of snapshot.resolvedArmyIds || []) resolvedArmyIds.add(armyId);
  resolvedNavyIds.clear();
  for (const navyId of snapshot.resolvedNavyIds || []) resolvedNavyIds.add(navyId);
  for (const army of allArmies(true)) {
    if (army.resolvedTurn === state?.turn && !resolvedArmyIds.has(army.id)) resolvedArmyIds.add(army.id);
  }
  for (const navy of navyDivisions) {
    if (navy.resolvedTurn === state?.turn && !resolvedNavyIds.has(navy.id)) resolvedNavyIds.add(navy.id);
  }
  replaceArray(armyOrderHistory, snapshot.armyOrderHistory);
  replaceArray(navyOrderHistory, snapshot.navyOrderHistory);
  replaceObject(turnReady, snapshot.turnReady);
  replaceArray(pendingProvinceClaims, snapshot.pendingProvinceClaims);
  normalizeArmyForceCaps();
  refreshArmyLoyaltyBaselines(!Object.keys(LOYALTY_BASELINE_ARMY_UNITS).length);
  generalTreeData = generalTrees[currentPlayer];
}

function syncStrategicCitiesFromState() {
  if (!bootstrap?.strategic_map?.cities || !state) return;
  const economyByCity = new Map();
  for (const payload of Object.values(state.players || {})) {
    for (const city of payload.city_economy || []) economyByCity.set(city.id, city);
  }
  for (const city of bootstrap.strategic_map.cities) {
    const economy = economyByCity.get(city.id);
    if (economy) {
      city.cash = economy.cash;
      city.factory = economy.factory;
    }
    const cell = cells[city.cellKey];
    if (cell) cell.city = city;
  }
}

function renderSynchronizedState() {
  syncStrategicCitiesFromState();
  updateTopBar();
  updatePhaseBanner();
  updateFeatureVisibility();
  initMap();
  renderPendingActions();
  const openPanel = document.querySelector(".overlay-panel.active");
  if (openPanel) renderPanel(openPanel.id.replace("panel", "").toLowerCase());
}

async function pullSharedState() {
  const remote = await api("/api/shared-state");
  const engineHash = JSON.stringify(remote.engine_state);
  const engineChanged = engineHash !== sharedEngineHash;
  state = remote.engine_state;
  syncStrategicCitiesFromState();
  sharedEngineHash = engineHash;
  if (remote.tactical && remote.revision !== sharedRevision) {
    applyTacticalSnapshot(remote.tactical);
    sharedRevision = remote.revision;
    sharedSnapshotHash = JSON.stringify(remote.tactical);
    if (sharedReady) renderSynchronizedState();
  } else if (engineChanged && sharedReady) {
    initMap();
    updateTopBar();
    renderPendingActions();
  }
  return remote;
}

async function publishSharedState(force = false) {
  const tactical = tacticalSnapshot();
  const signature = JSON.stringify(tactical);
  if (!force && signature === sharedSnapshotHash) return;
  try {
    const result = await api("/api/shared-state", {
      expected_revision: sharedRevision,
      tactical,
    });
    sharedRevision = result.revision;
    sharedSnapshotHash = signature;
    state = result.engine_state;
    syncStrategicCitiesFromState();
    sharedEngineHash = JSON.stringify(state);
  } catch (error) {
    await pullSharedState();
    throw error;
  }
}

async function synchronizeSharedGame() {
  if (!sharedReady || sharedSyncInFlight) return;
  sharedSyncInFlight = true;
  try {
    const signature = JSON.stringify(tacticalSnapshot());
    if (signature !== sharedSnapshotHash) await publishSharedState();
    else await pullSharedState();
    // 別家回應完事件卡之後，這邊要立刻換頁或收報。
    renderNewspaper();
  } catch (error) {
    console.warn("Shared game synchronization delayed:", error.message);
  } finally {
    sharedSyncInFlight = false;
  }
}

function indexCards() {
  // 事件卡不進 cardIndex——它不是手牌，走的是《民國報》那條路。
  cardIndex = {};
  for (const [name, group] of Object.entries(bootstrap.cards)) {
    if (name === "event") continue;
    for (const card of group) cardIndex[card.id] = card;
  }
}

function initializeNavies() {
  const cityById = new Map((bootstrap.strategic_map?.cities || []).map((city) => [city.id, city]));
  navyDivisions = createInitialNavies(bootstrap.navy_system, cells, cityById);
  initialNavyDivisions = JSON.parse(JSON.stringify(navyDivisions));
}

function cellDistance(first, second) {
  return Math.hypot(hcx(first.c) - hcx(second.c), hcy(first.c, first.r) - hcy(second.c, second.r));
}

function hexPathBetween(start, goal) {
  if (!start || !goal) return [];
  if (start.key === goal.key) return [start];
  const frontier = [start];
  const cameFrom = new Map([[start.key, null]]);
  while (frontier.length) {
    frontier.sort((first, second) => cellDistance(first, goal) - cellDistance(second, goal));
    const current = frontier.shift();
    if (current.key === goal.key) break;
    const neighbors = cellNeighbors(current)
      .filter((cell) => cell.land && !cameFrom.has(cell.key))
      .sort((first, second) => cellDistance(first, goal) - cellDistance(second, goal));
    for (const neighbor of neighbors) {
      cameFrom.set(neighbor.key, current.key);
      frontier.push(neighbor);
    }
  }
  if (!cameFrom.has(goal.key)) return [start, goal];
  const path = [];
  for (let key = goal.key; key; key = cameFrom.get(key)) path.push(cells[key]);
  return path.reverse();
}

function railroadRouteCells(railroad) {
  const route = [];
  for (let index = 0; index < railroad.points.length - 1; index++) {
    const start = cellAt(...railroad.points[index]);
    const goal = cellAt(...railroad.points[index + 1]);
    for (const cell of hexPathBetween(start, goal)) {
      if (cell && route.at(-1)?.key !== cell.key) route.push(cell);
    }
  }
  return route;
}

function indexScenarioCells() {
  const scenario = bootstrap.strategic_map || {};
  for (const cell of Object.values(cells)) {
    delete cell.city;
    cell.railroads = new Set();
    cell.railNeighbors = new Set();
    cell.railBridge = false;
    // 河港會把地格改成水域。先記下天然河道，重建時還原，否則第二次開局
    // assignCityCells 會把這些格子當成無橋水域而排除，城市指派就會漂移。
    if (cell.naturalRiver === undefined) cell.naturalRiver = cell.river;
    cell.river = cell.naturalRiver;
    cell.portWater = false;
  }
  for (const railroad of scenario.railroads || []) {
    const route = railroadRouteCells(railroad);
    railroad.cellKeys = route.map((cell) => cell.key);
    for (const cell of route) {
      cell.railroads.add(railroad.name);
      if (cell.river) cell.railBridge = true;
    }
    for (let index = 1; index < route.length; index++) {
      const previous = route[index - 1];
      const current = route[index];
      if (!cellNeighbors(previous).some((neighbor) => neighbor.key === current.key)) continue;
      previous.railNeighbors.add(current.key);
      current.railNeighbors.add(previous.key);
    }
  }

  const occupiedCityCells = new Set();
  for (const city of scenario.cities || []) {
    if (LAND_ONLY_CITY_IDS.has(city.id)) delete city.port;
    const placementFaction = city.scenario_faction || city.faction;
    INITIAL_CITY_FACTIONS[city.id] ||= placementFaction;
    const candidates = Object.values(cells).filter((cell) =>
      cell.land !== false
      &&
      !occupiedCityCells.has(cell.key)
      && !cell.power                       // 列強租借地不能拿來擺中國城市
      && (!cell.river || cell.railBridge)
    );
    const sameFaction = candidates.filter((cell) => cell.fac === placementFaction);
    const pool = sameFaction.length ? sameFaction : candidates;
    const cell = pool.reduce((nearest, candidate) => {
      const distance = (candidate.lon - city.lon) ** 2 + (candidate.lat - city.lat) ** 2;
      return !nearest || distance < nearest.distance ? { cell: candidate, distance } : nearest;
    }, null)?.cell;
    city.cellKey = cell?.key || null;
    if (!cell) throw new Error(`No valid tile available for city ${city.name}`);
    if (cell.river && !cell.railBridge) throw new Error(`City ${city.name} requires a railway bridge`);
    cell.city = city;
    if (LAND_ONLY_CITY_IDS.has(city.id)) {
      cell.river = null;
      cell.portWater = false;
      cell.railBridge = false;
    }
    occupiedCityCells.add(cell.key);
  }

  markRiverPortWater();
  bridgeRailwaysOverWater();
}

// 河港城市的地格一律視為水域。天然河道保留原名，其餘標為內河。
function markRiverPortWater() {
  for (const cell of Object.values(cells)) {
    if (LAND_ONLY_CITY_IDS.has(cell.city?.id)) continue;
    if (cell.city?.port !== "river") continue;
    cell.portWater = true;
    if (!cell.river) cell.river = nearestRiverName(cell) || "內河";
  }
}

// 河港是在城市指派之後才把地格改成水域的，所以上面那輪標鐵路橋時它們
// 還算陸地，漏掉了橋。這裡補一次：地格是水域又有鐵路通過就一定有鐵路橋。
function bridgeRailwaysOverWater() {
  for (const cell of Object.values(cells)) {
    if (cell.river && cell.railroads?.size) cell.railBridge = true;
  }
}

function nearestRiverName(cell, maxDegrees = 1.6) {
  let best = null;
  let bestDistance = Infinity;
  for (const river of RIVERS) {
    for (let i = 0; i < river.pts.length - 1; i++) {
      const distance = pointSegmentDistance(cell.lon, cell.lat, river.pts[i], river.pts[i + 1]);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = river.name;
      }
    }
  }
  return bestDistance <= maxDegrees ? best : null;
}

function pointSegmentDistance(x, y, [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSquared = dx * dx + dy * dy;
  const t = lengthSquared ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / lengthSquared)) : 0;
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}

// 擠不進起點城市時的備位格。畫成水面的地格（河道、近海）一律先跳過，
// 陸軍不該一開局就站在水裡；真的找不到乾地才退而求其次。
function nearestFreeCell(origin, occupied) {
  const pick = (allowWater) => {
    let best = null;
    let bestDistance = Infinity;
    for (const cell of Object.values(cells)) {
      if (!cell.land || occupied.has(cell.key) || cell.city) continue;
      if (!allowWater && (cell.river || cell.coastalWater)) continue;
      const distance = (cell.lon - origin.lon) ** 2 + (cell.lat - origin.lat) ** 2;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = cell;
      }
    }
    return best;
  };
  return pick(false) || pick(true);
}

function snapArmiesToStartCities() {
  const occupied = new Set();
  const cityById = new Map((bootstrap.strategic_map?.cities || []).map((city) => [city.id, city]));
  for (const armies of Object.values(ARMY_POSITIONS)) {
    for (const army of armies) {
      const city = cityById.get(army.startCityId);
      const home = city?.cellKey ? cells[city.cellKey] : null;
      if (!home) continue;
      // 指定了起始地格的部隊直接放上去，不參與搶城市格。
      const assigned = army.startCellKey ? cells[army.startCellKey] : null;
      if (assigned && !occupied.has(assigned.key)) {
        army.cellKey = assigned.key;
        army.lon = assigned.lon;
        army.lat = assigned.lat;
        if (INITIAL_ARMY_CELLS[army.id]) {
          INITIAL_ARMY_CELLS[army.id] = { cellKey: assigned.key, lon: assigned.lon, lat: assigned.lat };
        }
        occupied.add(assigned.key);
        continue;
      }
      // Two armies can share a start city (e.g. 馬家軍 after 導河 left the map);
      // the second one falls back to the nearest free land cell rather than
      // being dropped without a position.
      const cell = occupied.has(home.key) ? nearestFreeCell(home, occupied) : home;
      if (!cell) continue;
      army.cellKey = cell.key;
      army.lon = cell.lon;
      army.lat = cell.lat;
      if (INITIAL_ARMY_CELLS[army.id]) {
        INITIAL_ARMY_CELLS[army.id] = { cellKey: cell.key, lon: cell.lon, lat: cell.lat };
      }
      occupied.add(cell.key);
    }
  }
}

function featurePolygons(feature) {
  const coordinates = feature?.geometry?.coordinates || [];
  return feature?.geometry?.type === "Polygon" ? [coordinates] : coordinates;
}

function provinceAt(lon, lat) {
  for (const feature of provinceGeoJson?.features || []) {
    for (const polygon of featurePolygons(feature)) {
      if (polygon[0] && pointInPolygon(lon, lat, polygon[0])) return feature.properties.name;
    }
  }
  return null;
}

function indexProvinceCells() {
  for (const cell of Object.values(cells)) cell.province = provinceAt(cell.lon, cell.lat);
}

function applyMapTransform() {
  $("mapStage").style.transform = `translate(${mapPanX}px, ${mapPanY}px) scale(${mapZoom})`;
  $("zoomRange").value = String(Math.round(mapZoom * 100));
}

function fitMap(resetPan = false) {
  const container = document.querySelector(".map-container");
  const stage = $("mapStage");
  const heightBasedWidth = container.clientHeight * (MAPW / MAPH);
  const baseWidth = window.matchMedia("(max-width: 760px)").matches
    ? heightBasedWidth
    : Math.min(container.clientWidth, heightBasedWidth);
  const baseHeight = baseWidth * (MAPH / MAPW);
  stage.style.width = `${baseWidth}px`;
  stage.style.height = `${baseHeight}px`;
  if (resetPan) {
    mapPanX = (container.clientWidth - baseWidth) / 2;
    mapPanY = (container.clientHeight - baseHeight) / 2;
  }
  applyMapTransform();
}

function applyMapZoom(nextZoom, clientX = null, clientY = null) {
  const container = document.querySelector(".map-container");
  const rect = container.getBoundingClientRect();
  const anchorX = (clientX ?? rect.left + rect.width / 2) - rect.left;
  const anchorY = (clientY ?? rect.top + rect.height / 2) - rect.top;
  const oldZoom = mapZoom;
  const stageX = (anchorX - mapPanX) / oldZoom;
  const stageY = (anchorY - mapPanY) / oldZoom;
  mapZoom = Math.min(2.5, Math.max(0.6, nextZoom));
  mapPanX = anchorX - stageX * mapZoom;
  mapPanY = anchorY - stageY * mapZoom;
  applyMapTransform();
}

function setupMapZoom() {
  const container = document.querySelector(".map-container");
  $("zoomOut").addEventListener("click", () => applyMapZoom(mapZoom - 0.2));
  $("zoomIn").addEventListener("click", () => applyMapZoom(mapZoom + 0.2));
  $("zoomReset").addEventListener("click", () => { mapZoom = 1; fitMap(true); });
  $("zoomRange").addEventListener("input", (event) => applyMapZoom(Number(event.target.value) / 100));
  container.addEventListener("wheel", (event) => {
    event.preventDefault();
    applyMapZoom(mapZoom * Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
  }, { passive: false });
  let drag = null;
  container.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest(".army-marker, .navy-marker, .battle-marker")) return;
    drag = { x: event.clientX, y: event.clientY, panX: mapPanX, panY: mapPanY, moved: false };
    container.classList.add("panning");
  });
  container.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    mapPanX = drag.panX + dx;
    mapPanY = drag.panY + dy;
    applyMapTransform();
  });
  const finishDrag = () => {
    if (!drag) return;
    suppressMapClick = drag.moved;
    drag = null;
    container.classList.remove("panning");
  };
  window.addEventListener("pointerup", finishDrag);
  window.addEventListener("pointercancel", finishDrag);
  window.addEventListener("resize", () => fitMap(false));
  fitMap(true);
}

function formatLoanRate(rate) {
  const percent = Number(rate || 0) * 100;
  return `${Number.isInteger(percent) ? percent : percent.toFixed(1)}%`;
}

// 利息不是固定百分比：每筆貸款各用自己的利率計息（普通借貸 8%、優惠借貸 5%、
// 孔祥熙從政之後的新借款 3%……），所以標題要照後端記下的明細寫出實際利率。
function interestRateLabel(service) {
  const breakdown = (service?.interest_breakdown || []).filter((entry) => entry.outstanding > 0);
  if (!breakdown.length) return "貸款利息";
  if (breakdown.length === 1) return `貸款利息（${formatLoanRate(breakdown[0].rate)}／回合）`;
  return `貸款利息（${breakdown.map((entry) => formatLoanRate(entry.rate)).join("、")}）`;
}

// 最上一排的 $ 與工廠：點一下展開逐城明細，再點一下（或點別處、按 Esc）收起。
// 浮層掛在 body 上而不是頂欄裡，因為頂欄是 overflow: hidden，放裡面會被裁掉。
function statBreakdownMarkup(kind, profile = state?.players?.[currentPlayer]) {
  if (!profile) return "";
  const cities = profile.city_economy || [];
  const field = kind === "cash" ? "cash" : "factory";
  const unit = kind === "cash" ? "$" : "";
  const suffix = kind === "cash" ? "" : " 點";
  const total = cities.reduce((sum, city) => sum + Number(city[field] || 0), 0);
  const rows = cities.length
    ? [...cities]
      .sort((first, second) => Number(second[field] || 0) - Number(first[field] || 0))
      .map((city) => `<span><i>${city.name} · ${city.province}</i><strong>${unit}${city[field] || 0}${suffix}</strong></span>`)
      .join("")
    : '<span><i>目前沒有控制任何城市</i><strong>—</strong></span>';

  const service = profile.last_debt_service;
  const breakdown = (service?.interest_breakdown || []).filter((entry) => entry.outstanding > 0);
  const interestRows = breakdown.length > 1
    // 手上同時有不同利率的貸款時，逐一列出，不要混成一個數字。
    ? breakdown.map((entry) => `
        <span><i>利息 ${formatLoanRate(entry.rate)}／回合（餘額 $${entry.outstanding}）</i><strong>+$${entry.interest} 債</strong></span>
      `).join("")
    : `<span><i>${interestRateLabel(service)}</i><strong>+$${service?.interest ?? 0} 債</strong></span>`;
  const debtRows = kind === "cash" && service ? `
    <b>上回合債務結算</b>
    <span><i>城市收入</i><strong>+$${service.gross_income ?? 0}</strong></span>
    ${interestRows}
    <span><i>逾期強制清償</i><strong>-$${service.forced_repayment ?? 0}</strong></span>
    <span><i>實收現金</i><strong>+$${service.net_income ?? 0}</strong></span>
    ${(service.cash_effects || []).map((effect) => `
      <span><i>${effect.name || effect.effect_id}</i><strong>${effect.amount >= 0 ? "+" : ""}$${effect.amount}</strong></span>
    `).join("")}
  ` : "";
  // 租界管制：明細裡要看得出哪幾座城被哪幾國掐著、扣了多少、加成是不是也停了。
  const controlled = cities.filter((city) => city.concession_control);
  const controlRows = controlled.length ? `
    <b>租界管制</b>
    ${controlled.map((city) => {
      const info = city.concession_control;
      const powers = (info.powers || []).map((key) => POWER_LABELS[key] || key).join("、");
      const suspended = info.bonus_suspended ? "，租界加成已停" : "";
      return `<span><i>${city.name}（${powers}管制${suspended}）</i>`
        + `<strong>${unit}-${info.penalty}${suffix}</strong></span>`;
    }).join("")}
    <span class="stat-popover-note"><i>管制持續至與該國關係改善至非敵對（&gt; −4）的下一回合；一城多國租界時，只有全部租界國都管制，租界加成才會消失。</i></span>
  ` : "";
  const footer = kind === "cash"
    ? `<span class="stat-popover-total"><i>每回合現金合計</i><strong>+$${total}</strong></span>`
    : `<span class="stat-popover-total"><i>每回合工廠合計</i><strong>+${total} 點</strong></span>
       <span class="stat-popover-total"><i>目前可用工廠點</i><strong>${profile.factory_points ?? 0} 點</strong></span>`;

  return `
    <b>${kind === "cash" ? "城市現金來源" : "城市工廠來源"}</b>
    ${rows}
    ${controlRows}
    ${footer}
    ${debtRows}
  `;
}

let openStatChip = null;

function setupStatPopover() {
  const popover = document.createElement("div");
  popover.className = "stat-popover";
  popover.hidden = true;
  document.body.appendChild(popover);

  const show = (chip) => {
    openStatChip = chip.dataset.stat;
    popover.innerHTML = statBreakdownMarkup(chip.dataset.stat);
    popover.hidden = false;
    const rect = chip.getBoundingClientRect();
    popover.style.top = `${rect.bottom + 6}px`;
    popover.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
    for (const other of $("factionStats").querySelectorAll("[data-stat]")) {
      other.classList.toggle("stat-chip-open", other.dataset.stat === chip.dataset.stat);
    }
  };
  const hide = () => {
    openStatChip = null;
    popover.hidden = true;
    for (const other of $("factionStats").querySelectorAll("[data-stat]")) {
      other.classList.remove("stat-chip-open");
    }
  };
  statPopoverRefresh = () => {
    if (!openStatChip) return;
    const chip = $("factionStats").querySelector(`[data-stat="${openStatChip}"]`);
    if (chip) show(chip);
    else hide();
  };

  const stats = $("factionStats");
  stats.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-stat]");
    if (!chip) return;
    event.stopPropagation();
    // 點同一個就收起，點另一個就換內容。
    if (!popover.hidden && openStatChip === chip.dataset.stat) hide();
    else show(chip);
  });
  stats.addEventListener("keydown", (event) => {
    const chip = event.target.closest("[data-stat]");
    if (!chip || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    if (!popover.hidden && openStatChip === chip.dataset.stat) hide();
    else show(chip);
  });
  document.addEventListener("click", (event) => {
    if (popover.hidden) return;
    if (event.target.closest(".stat-popover") || event.target.closest("[data-stat]")) return;
    hide();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
}

// 開著明細時數字有變動就重繪，不然玩家看到的是點開那一刻的舊資料。
let statPopoverRefresh = () => {};

function updateTopBar() {
  $("turnBadge").textContent = `回合 ${state.turn}`;
  const profile = state.players[currentPlayer];
  if (!profile) return;
  // 旗幟與陣營名移到右側部隊操作板頂端，最上一排只留數字。
  $("factionStats").innerHTML = `
    <span class="stat-chip" data-stat="cash" tabindex="0" role="button" title="點一下看明細">$${profile.treasury ?? 0} (+${profile.income ?? 0}/回合)</span>
    <span class="stat-chip" data-stat="factory" tabindex="0" role="button" title="點一下看明細">工廠 ${profile.factory_points ?? 0} (+${profile.factory_income ?? 0}/回合)</span>
    <span title="預備兵力">預備 ${profile.unit_reserve ?? 0}</span>
    <span title="債務">債 ${profile.debt ?? 0}</span>
  `;
  const dockFaction = $("dockFaction");
  if (dockFaction) {
    dockFaction.innerHTML = `
      ${factionFlagMarkup(currentPlayer, "flag-chip faction-flag")}
      <span class="faction-name">${FACTIONS[currentPlayer]?.name || currentPlayer}</span>
    `;
  }
  refreshLoansIfOpen();
  statPopoverRefresh();
}

function functionCardDrawCost() {
  return bootstrap?.features?.function_card_draw_cost || DEFAULT_FUNCTION_CARD_DRAW_COST;
}

function functionCardDrawFactoryCost() {
  return bootstrap?.features?.function_card_draw_factory_cost ?? DEFAULT_FUNCTION_CARD_DRAW_FACTORY_COST;
}

function functionPurchasePromptKey(player = currentPlayer) {
  return `${state?.turn || 0}:${player}`;
}

function canPurchaseFunctionCard(payload = state?.players?.[currentPlayer], player = currentPlayer) {
  if (!bootstrap?.features?.function_cards || !payload || payload.pending_draw) return false;
  if (Number(payload.function_purchase_count || 0) >= functionCardDrawLimit()) return false;
  if ((payload.treasury || 0) < functionCardDrawCost()) return false;
  if ((payload.factory_points || 0) < functionCardDrawFactoryCost()) return false;
  if (((payload.function_deck || []).length + (payload.discard || []).length) <= 0) return false;
  return !skippedFunctionPurchasePrompts.has(functionPurchasePromptKey(player));
}

function functionCardDrawLimit() {
  return bootstrap?.features?.function_card_purchase_limit || 2;
}

function functionPurchaseMarkup(payload = state?.players?.[currentPlayer], context = "panel") {
  const cost = functionCardDrawCost();
  const deckCount = (payload?.function_deck || []).length + (payload?.discard || []).length;
  const used = Number(payload?.function_purchase_count || 0);
  const limit = functionCardDrawLimit();
  let note = `可支付 $${cost}＋工業點 ${functionCardDrawFactoryCost()} 抽 1 張功能卡；每位玩家每回合最多 ${limit} 張（已抽 ${used}/${limit}）。`;
  if (payload?.pending_draw) note = "先棄置一張手牌，接收已購買的新功能卡。";
  else if (used >= limit) note = `本回合已抽滿 ${limit} 張功能卡。`;
  else if ((payload?.treasury || 0) < cost) note = `現金不足，購買功能卡需要 $${cost}。`;
  else if ((payload?.factory_points || 0) < functionCardDrawFactoryCost()) note = `工業點不足，購買功能卡需要 ${functionCardDrawFactoryCost()} 點。`;
  else if (deckCount <= 0) note = "功能卡牌庫已空。";
  return `
    <div class="function-purchase ${context}">
      <div>
        <b>功能卡購買</b>
        <span>${note}</span>
      </div>
      <button data-buy-function-card="${currentPlayer}" ${canPurchaseFunctionCard(payload) ? "" : "disabled"}>支付 $${cost}＋工${functionCardDrawFactoryCost()}</button>
    </div>
  `;
}

async function buyFunctionCard(button) {
  button.disabled = true;
  const player = button.dataset.buyFunctionCard || currentPlayer;
  try {
    const result = await api("/api/draw-function", { player });
    state = result.state;
    syncStrategicCitiesFromState();
    const drawCount = Number(state.players[player]?.function_purchase_count || 0);
    uiNotice = result.requires_discard
      ? `已支付 $${result.draw_cost} 購買「${result.card.name}」，請棄置一張手牌接收。`
      : drawCount >= functionCardDrawLimit()
        ? `已支付 $${result.draw_cost} 購買「${result.card.name}」；本回合抽牌已達上限。`
        : null;
    updateTopBar();
    renderPendingActions();
    if ($("panelCards")?.classList.contains("active")) renderPanel("cards");
  } catch (error) {
    button.disabled = false;
    showNotice(error.message);
  }
}

function factionLabel(code, possessive = false) {
  if (possessive && code === currentPlayer) return "你";
  return FACTIONS[code]?.shortName || code || "未知勢力";
}

function cityLabel(cityId) {
  return (bootstrap.strategic_map?.cities || []).find((city) => city.id === cityId)?.name || cityId || "未知城市";
}

function provinceOptions() {
  const provinces = new Set((bootstrap.strategic_map?.cities || [])
    .map((city) => city.province)
    .filter(Boolean));
  return [...provinces].sort((first, second) => first.localeCompare(second, "zh-Hant"));
}

function strategicProvinceForCell(cell) {
  if (!cell) return null;
  if (cell.city?.province) return cell.city.province;
  const playableProvinces = new Set(provinceOptions());
  if (playableProvinces.has(cell.province)) return cell.province;
  const nearestCity = (bootstrap.strategic_map?.cities || []).reduce((nearest, city) => {
    const cityCell = cells[city.cellKey];
    if (!cityCell) return nearest;
    const distance = (cityCell.lon - cell.lon) ** 2 + (cityCell.lat - cell.lat) ** 2;
    return !nearest || distance < nearest.distance ? { city, distance } : nearest;
  }, null)?.city;
  return nearestCity?.province || cell.province || null;
}

function activeTimedEffects(player, kind = null) {
  return (state.players[player]?.timed_effects || [])
    .filter((effect) => Number(effect.remaining_turns || 0) > 0 && (!kind || effect.kind === kind));
}

function factionHasPoliceProtection(player) {
  return activeTimedEffects(player, "police_system").length > 0;
}

function provinceForArmy(army) {
  return cityForArmy(army)?.province || strategicProvinceForCell(cells[army?.cellKey]) || null;
}

function armyRevealedByIntel(army, observer = currentPlayer) {
  const armyFaction = factionForArmy(army);
  if (!army || armyFaction === observer) return false;
  const province = provinceForArmy(army);
  // 飛艇在雲上照相，情報局的反情報擋不住；一般情報網照舊會被擋。
  const byAir = activeTimedEffects(observer, "aerial_recon")
    .some((effect) => (effect.target_provinces || []).includes(province));
  if (byAir) return true;
  if (factionHasPoliceProtection(armyFaction)) return false;
  return activeTimedEffects(observer, "intel_network")
    .some((effect) => effect.target_province === province);
}

function activeEffectsMarkup(payload = state.players[currentPlayer]) {
  const effects = (payload?.timed_effects || []).filter((effect) => Number(effect.remaining_turns || 0) > 0);
  const cityEffects = (state.city_output_effects || []).filter((effect) =>
    effect.kind === "qing_gang_riot"
    && (effect.initiator === currentPlayer || effect.target_owner === currentPlayer)
  );
  const uprisings = (state.city_output_effects || []).filter((effect) =>
    effect.kind === "red_army_uprising"
    && (effect.initiator === currentPlayer || effect.target_owner === currentPlayer)
  );
  const railways = (state.railway_effects || []).filter((effect) => Number(effect.remaining_turns || 0) > 0);
  const ports = (state.port_effects || []).filter((effect) =>
    Number(effect.remaining_turns || 0) > 0
    && (effect.initiator === currentPlayer || effect.owner === currentPlayer)
  );
  const economyFlags = Boolean(payload?.loan_penalties?.length || payload?.soong_patronage
    || Number(payload?.loan_ban_until_turn || 0) > Number(state?.turn || 0)
    || payload?.loan_interest_override);
  if (!effects.length && !cityEffects.length && !uprisings.length && !railways.length
    && !ports.length && !economyFlags) return "";
  return `<div class="active-effect-list">
    ${effects.map((effect) => {
      const label = effect.kind === "police_system"
        ? `警政保護剩餘 ${effect.remaining_turns} 回合`
        : effect.kind === "aerial_recon"
          ? `飛艇偵查：${(effect.target_provinces || []).join("、")}，剩餘 ${effect.remaining_turns} 回合`
          : effect.kind === "intel_network"
          ? `情報網：${effect.target_province}，剩餘 ${effect.remaining_turns} 回合`
          : `${effect.name || "持續效果"}剩餘 ${effect.remaining_turns} 回合`;
      return `<span>${label}</span>`;
    }).join("")}
    ${cityEffects.map((effect) => {
      const role = effect.initiator === currentPlayer ? "發動" : "受害";
      const progress = `${effect.garrison_progress || 0}/${effect.required_turns || 3}`;
      return `<span>${effect.label || "黑幫暴動"}(${role})：${effect.province}，鎮壓 ${progress}</span>`;
    }).join("")}
    ${uprisings.map((effect) => {
      const role = effect.initiator === currentPlayer ? "發動" : "受害";
      const names = (effect.cities || []).map((city) => city.name).join("、");
      return `<span>${effect.name || "紅軍起義"}(${role})：${names}，需駐 ${effect.required_battalions || 5} 營</span>`;
    }).join("")}
    ${railways.map((effect) => `<span>${effect.railway} 搶修中，剩餘 ${effect.remaining_turns} 回合</span>`).join("")}
    ${ports.map((effect) => {
      const role = effect.initiator === currentPlayer ? "發動" : "受害";
      return `<span>${effect.name || "大港開炸"}(${role})：${effect.city_name}港務癱瘓，剩餘 ${effect.remaining_turns} 回合</span>`;
    }).join("")}
    ${(payload?.loan_penalties || []).map((clause) => `<span>${clause.label || "貸款違約條款"}${
      clause.remaining_turns === null || clause.remaining_turns === undefined
        ? "（永久）" : `，剩餘 ${clause.remaining_turns} 回合`}</span>`).join("")}
    ${payload?.soong_patronage ? `<span>上海宋家支持：每三回合 +$${payload.soong_patronage.cash}、工廠 +${payload.soong_patronage.factory}</span>` : ""}
    ${payload?.loan_interest_override !== null && payload?.loan_interest_override !== undefined
      ? `<span>中央銀行：新借款利率 ${Math.round(payload.loan_interest_override * 100)}%、期限 +${payload.loan_term_bonus || 0}</span>` : ""}
    ${Number(payload?.loan_ban_until_turn || 0) > Number(state?.turn || 0)
      ? `<span>信用受損：列強銀行拒貸，至第 ${payload.loan_ban_until_turn} 回合</span>` : ""}
  </div>`;
}

// 11.1 江浙財團的墊款：回報「現在有部隊處於交戰中」的省份。
//
// 判定三步走，用的都是既有資料：
//   1. allArmies() 每支部隊的 cellKey 決定它在哪一省（provinceForArmy）
//   2. activeBattleForArmy() 查 activeBattles 裡 status 為 pending／ongoing 的場次
//   3. 有任一支部隊在該省且交戰中 → 該省列入清單，後端據此扣產出
//
// 後端沒有部隊資料，所以這份清單隨 next_turn 一起送過去
// （與 riot_garrisons、city_garrisons 同一條通道）。
function contestedProvinces() {
  const provinces = new Set();
  for (const army of allArmies()) {
    if (army?.status === "jailed") continue;
    if (!activeBattleForArmy(army)) continue;
    const province = provinceForArmy(army);
    if (province) provinces.add(province);
  }
  return [...provinces];
}

function qingGangRiotGarrisons() {
  const report = {};
  for (const effect of state?.city_output_effects || []) {
    if (effect.kind !== "qing_gang_riot") continue;
    report[effect.id] = allArmies().some((army) =>
      factionForArmy(army) === effect.target_owner
      && army.status !== "jailed"
      && provinceForArmy(army) === effect.province
      && forcePoints(armyUnits(army)) >= Number(effect.required_force || 15)
    );
  }
  return report;
}

// 紅軍起義：回報受影響城市裡「目標勢力自己的」駐軍營數，一個單位算一營。
function uprisingCityGarrisons() {
  const report = {};
  for (const effect of state?.city_output_effects || []) {
    if (effect.kind !== "red_army_uprising") continue;
    for (const cityId of effect.city_ids || []) {
      const city = (bootstrap.strategic_map?.cities || []).find((item) => item.id === cityId);
      if (!city) continue;
      const battalions = allArmies()
        .filter((army) => factionForArmy(army) === effect.target_owner
          && army.status !== "jailed"
          && army.cellKey === city.cellKey)
        .reduce((total, army) => total + Object.values(armyUnits(army)).reduce((sum, count) => sum + count, 0), 0);
      report[cityId] = Math.max(report[cityId] || 0, battalions);
    }
  }
  return report;
}

function generalLabel(generalId, owner = null) {
  const general = generalById(generalId);
  const prefix = owner ? `${factionLabel(owner)} · ` : "";
  return `${prefix}${general?.name || generalId || "未知將領"}`;
}

function functionActionMessage(action, viewer = currentPlayer) {
  if (!action || action.type !== "function_card") return "";
  const actor = factionLabel(action.player);
  const cardName = action.card?.name || "功能卡";
  const parts = [];
  const reserveDeltas = action.reserve_deltas?.length ? action.reserve_deltas : (action.reserve_delta ? [action.reserve_delta] : []);
  if (reserveDeltas.length) {
    const byOwner = new Map();
    reserveDeltas.forEach((reserve) => {
      const list = byOwner.get(reserve.owner) || [];
      const unit = UNIT_META[reserve.unit_type]?.name || reserve.unit_type;
      const sign = reserve.amount >= 0 ? "+" : "-";
      list.push(`${unit}${sign}${Math.abs(Number(reserve.amount || 0))}`);
      byOwner.set(reserve.owner, list);
    });
    parts.push([...byOwner.entries()]
      .map(([owner, list]) => `${factionLabel(owner, owner === viewer)}預備隊 ${list.join("、")}`)
      .join("；"));
  }
  if (action.artifact_sale) {
    const sale = action.artifact_sale;
    parts.push(`向${POWER_NAME[sale.power] || sale.power}盜賣文物，進帳 $${sale.payout}`
      + (sale.shame_cards_added ? `；牌庫多了 ${sale.shame_cards_added} 張〈中國人之恥〉（${sale.shame_cards_total}/${sale.shame_cap}）` : "；恥辱牌已達上限"));
  }
  if (action.piaohao_exchange) {
    const deal = action.piaohao_exchange;
    parts.push(deal.direction === "factory_to_cash"
      ? `票號兌出：工業點 ${deal.factory_spent} → $${deal.cash_gained}`
        + `（工業點 ${deal.factory_before} → ${deal.factory_after}，現金 $${deal.cash_before} → $${deal.cash_after}）`
      : `票號兌入：$${deal.cash_spent} → 工業點 ${deal.factory_gained}`
        + `（現金 $${deal.cash_before} → $${deal.cash_after}，工業點 ${deal.factory_before} → ${deal.factory_after}）`);
  }
  if (action.riot_shield) {
    const shield = action.riot_shield;
    parts.push(`${shield.province}設立警政單位，${shield.remaining_turns} 回合內免疫黑幫暴動`
      + (shield.quelled_count ? `，並立即平息現行暴動 ${shield.quelled_count} 起` : ""));
  }
  if (action.loyalty_delta && action.target_general_id) {
    const target = generalLabel(action.target_general_id, action.target_owner);
    const sign = action.loyalty_delta > 0 ? "+" : "";
    parts.push(`${target}忠誠 ${sign}${action.loyalty_delta}`);
  }
  if (action.assassination) {
    const hit = action.assassination;
    const target = generalLabel(hit.target_general_id, hit.target_owner);
    const rate = `成功率 ${Math.round(hit.chance * 100)}%`;
    const guard = hit.guard_reduction ? `（親衛隊 −${Math.round(hit.guard_reduction * 100)}%）` : "";
    parts.push(hit.success
      ? `暗殺${target}得手，該人物身亡，麾下少將忠誠歸零（${rate}${guard}）`
      : `暗殺${target}未得手（${rate}${guard}）`);
  }
  if (action.loan_effect) {
    const loan = action.loan_effect;
    const rate = loan.interest_per_turn !== null ? `利率 ${Math.round(loan.interest_per_turn * 100)}%` : "";
    parts.push(`現金 +$${loan.cash}、負債 +${loan.debt}（${rate}，第 ${loan.due_turn} 回合到期）`);
    if (loan.loan_ban_until_turn) {
      parts.push(`信用受損：列強銀行拒絕承作新貸款，至第 ${loan.loan_ban_until_turn} 回合`);
    }
  }
  if (action.unlock_effect?.kind === "central_bank") {
    const bank = action.unlock_effect;
    parts.push(`此後新借款利率一律 ${Math.round(bank.interest_per_turn * 100)}%、期限 +${bank.loan_term_bonus} 回合`);
  }
  if (action.body_guard) {
    const guard = action.body_guard;
    parts.push(`${generalLabel(guard.general_id, guard.owner)}編成親衛隊，第 ${guard.active_from_turn} 回合起生效`);
  }
  if (action.loyalty_delta_all) {
    const owner = factionLabel(action.loyalty_delta_all.owner, action.loyalty_delta_all.owner === viewer);
    const sign = action.loyalty_delta_all.amount > 0 ? "+" : "";
    parts.push(`${owner}全體可變忠誠將領忠誠 ${sign}${action.loyalty_delta_all.amount}`);
  }
  for (const swing of action.loyalty_swings || []) {
    const owner = factionLabel(swing.owner, swing.owner === viewer);
    const sign = swing.amount > 0 ? "+" : "";
    parts.push(`${owner}全體可變忠誠將領忠誠 ${sign}${swing.amount}`);
  }
  const developments = action.city_developments?.length ? action.city_developments : (action.city_development ? [action.city_development] : []);
  if (developments.length) {
    parts.push(developments.map((development) =>
      `${cityLabel(development.city_id)}產出 +$${development.cash}、工廠 +${development.factory}`
    ).join("；"));
  }
  if (action.cash_delta) {
    parts.push(`${factionLabel(action.player, action.player === viewer)}現金 ${action.cash_delta > 0 ? "+" : ""}${action.cash_delta}`);
  }
  if (action.permanent_output_delta) {
    const delta = action.permanent_output_delta;
    parts.push(`${factionLabel(delta.owner, delta.owner === viewer)}永久收入 +$${delta.cash}、工廠 +${delta.factory}/回合`);
  }
  if (action.debt_delta) {
    parts.push(`${factionLabel(action.player, action.player === viewer)}負債 ${action.debt_delta > 0 ? "+" : ""}${action.debt_delta}`);
  }
  if (action.army_unit_delta) {
    const delta = action.army_unit_delta;
    const army = allArmies(true).find((item) => item.generalId === delta.general_id);
    const units = Object.entries(delta.unit_reserves || {})
      .map(([unitType, amount]) => `${UNIT_META[unitType]?.name || unitType}+${amount}`)
      .join("、");
    parts.push(`${army?.general || generalLabel(delta.general_id, delta.owner)}所在軍隊 ${units}`);
  }
  if (action.affiliation_slot_delta) {
    const delta = action.affiliation_slot_delta;
    parts.push(`${generalLabel(delta.general_id, delta.owner)}直屬名額 +${delta.amount}`);
  }
  if (action.foreign_relation_delta) {
    const labels = { jp: "日本", su: "蘇聯", uk: "英國", fr: "法國", us: "美國" };
    const delta = action.foreign_relation_delta;
    parts.push(`${labels[delta.power] || delta.power}關係 ${delta.before} -> ${delta.after}`);
  }
  if (action.timed_effect) {
    const turns = action.timed_effect.remaining_turns || 0;
    const owners = (action.timed_effect.owners || [action.player])
      .map((owner) => factionLabel(owner, owner === viewer))
      .join("、");
    const effectDetail = action.timed_effect.kind === "intel_network"
      ? `揭露${action.timed_effect.target_province}`
      : action.timed_effect.kind === "police_system"
        ? "反情報保護"
        : action.timed_effect.name || "持續效果";
    parts.push(`${owners}${effectDetail}啟動 ${turns} 回合`);
  }
  if (action.recurring_effect) {
    parts.push(`${action.recurring_effect.name || "持續收支"}啟動 ${action.recurring_effect.remaining_turns || 0} 回合`);
  }
  if (action.city_disruption) {
    const target = factionLabel(action.city_disruption.target_owner, action.city_disruption.target_owner === viewer);
    const cities = (action.city_disruption.cities || []).map((city) => city.name).join("、");
    if (action.city_disruption.kind === "qing_gang_riot") {
      parts.push(`${target}${action.city_disruption.province}${action.city_disruption.label || "黑幫暴動"}，城市 ${cities} 產出停擺；需 ${action.city_disruption.required_force || 15} 戰力軍隊連續駐留 ${action.city_disruption.required_turns || 2} 回合鎮壓`);
    } else {
      parts.push(`${target}${cities}產出停擺 ${action.city_disruption.remaining_turns} 回合`);
    }
  }
  return `${actor}打出「${cardName}」${parts.length ? `：${parts.join("；")}。` : "：無效果，浪費一次出牌。"}`;
}

function functionActionVisibleTo(action, viewer = currentPlayer) {
  if (!action || action.type !== "function_card") return false;
  if (action.player === viewer) return true;
  if (action.card?.mechanic === "intel_network") return false;
  if (action.city_disruption?.target_owner === viewer) return true;
  if (action.city_disruption?.initiator === viewer) return true;
  if ((action.reserve_deltas || []).some((delta) => delta.owner === viewer)) return true;
  if (action.target_owner === viewer) return true;
  if (action.loyalty_delta_all?.owner === viewer) return true;
  if ((action.loyalty_swings || []).some((swing) => swing.owner === viewer)) return true;
  if (action.permanent_output_delta?.owner === viewer) return true;
  if (action.army_unit_delta?.owner === viewer) return true;
  if (action.affiliation_slot_delta?.owner === viewer) return true;
  if ((action.timed_effect?.owners || []).includes(viewer)) return true;
  return false;
}

function updateFeatureVisibility() {
  const cardsEnabled = Boolean(bootstrap?.features?.function_cards);
  document.body.classList.toggle("cards-enabled", cardsEnabled);
  document.querySelectorAll(".feature-cards").forEach((element) => { element.hidden = !cardsEnabled; });
}

function updatePhaseBanner() {
  const phaseLabels = {
    preparation: "準備階段",
    military: "軍事行動",
  };
  const phaseName = phaseLabels[currentPhase] || "軍事行動";
  $("phaseBanner").querySelector(".phase-label").textContent = phaseName;
  $("phaseBanner").title = phaseName;
}

function setupPanels() {
  // Open panels
  document.querySelectorAll("[data-panel]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panelName = btn.dataset.panel;
      closeAllPanels();
      const panel = document.getElementById(`panel${capitalize(panelName)}`);
      if (panel) {
        panel.classList.add("active");
        renderPanel(panelName);
      }
    });
  });

  // Close panels
  document.querySelectorAll("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panelName = btn.dataset.close;
      const panel = document.getElementById(`panel${capitalize(panelName)}`);
      if (panel) panel.classList.remove("active");
    });
  });

}

function closeAllPanels() {
  document.querySelectorAll(".overlay-panel").forEach((p) => p.classList.remove("active"));
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function renderPanel(panelName) {
  const contentId = `${panelName}Content`;
  const element = $(contentId);
  if (!element) return;

  switch (panelName) {
    case "generals":
      element.innerHTML = renderGeneralsPanel();
      attachGeneralHandlers(element);
      break;
    case "recruitment":
      element.innerHTML = renderRecruitmentPanel();
      attachRecruitmentHandlers();
      break;
    case "loans":
      renderLoansPanel(element);
      break;
    case "foreign":
      element.innerHTML = renderForeignPanel();
      attachForeignHandlers();
      break;
    case "cards":
      element.innerHTML = renderCardsPanel();
      attachCardHandlers(element);
      break;
  }
}

function renderGeneralsPanel() {
  if (!generalTreeData || !generalTreeData.generals) {
    return `<div class="empty-state">將領樹資料載入中...</div>`;
  }

  const generals = generalTreeData.generals;
  const greatGeneralId = generalTreeData.great_general_id;
  const greatGeneral = generals[greatGeneralId];

  if (!greatGeneral) {
    return `<div class="empty-state">無法載入大元帥資料</div>`;
  }

  let html = '<div class="family-tree-container">';

  // Level 0: Great General
  html += '<div class="tree-level level-0">';
  html += renderGeneralTreeCard(greatGeneral);
  html += '</div>';

  // Level 1: Lieutenant Generals
  if (greatGeneral.subordinates && greatGeneral.subordinates.length > 0) {
    html += '<div class="tree-connector-vertical"></div>';
    html += '<div class="tree-level level-1">';

    for (let i = 0; i < greatGeneral.subordinates.length; i++) {
      const ltId = greatGeneral.subordinates[i];
      const lt = generals[ltId];
      if (!lt) continue;

      html += '<div class="tree-branch">';
      html += '<div class="tree-connector-branch"></div>';
      html += renderGeneralTreeCard(lt);
      html += renderGeneralSubtree(lt, generals);

      html += '</div>';
    }

    html += '</div>';
  }

  html += '</div>';
  const prisoners = jailedGenerals[currentPlayer] || [];
  const lieutenants = availableLieutenantGenerals(currentPlayer);
  const freeMajorSlots = availableMajorGeneralSlots(currentPlayer);
  html += `
    <section class="jail-roster">
      <h3>被俘將領</h3>
      ${prisoners.length ? prisoners.map((record) => {
        const neededSlots = 1;
        const canRecruit = lieutenants.length && freeMajorSlots >= neededSlots && (state.players[currentPlayer]?.unit_reserves?.infantry || 0) >= 5;
        return `
        <div class="jail-general">
          ${renderGeneralTreeCard(record.general, { includeCaptured: true })}
          <div><small>原屬 ${FACTIONS[record.originFaction]?.name || record.originFaction}</small>
            <select data-recruit-superior="${record.armyId}" ${lieutenants.length ? "" : "disabled"}>${lieutenants.map((general) => `<option value="${general.id}">隸屬 ${general.name}</option>`).join("")}</select>
            <button data-recruit-prisoner="${record.armyId}" ${canRecruit ? "" : "disabled"}>招降 · 步兵5營${neededSlots > 1 ? ` · 空位${neededSlots}` : ""}</button>
          </div>
        </div>`;
      }).join("") : '<div class="empty-state compact">目前無俘虜</div>'}
    </section>`;
  const exiles = exilePoolEntries();
  html += `
    <section class="exile-roster">
      <h3>在野將領</h3>
      <p class="exile-note">下野賦閒、不屬於任何陣營，開局不在場上。打出〈在野名將投效〉並付其身價全額外加 $${EXILE_RECRUIT_SURCHARGE} 出山附加費，即可請人出山，帶著自帶部隊在大帥所在地現身。</p>
      ${exiles.length ? exiles.map(({ general, recruitedBy, forbidden, price }) => `
        <div class="exile-general${recruitedBy ? " recruited" : ""}${forbidden ? " forbidden" : ""}">
          ${renderGeneralTreeCard(general, { includeCaptured: true })}
          <div class="exile-meta">
            <small>${general.background || ""}</small>
            <small>${general.ability || ""}</small>
            <small>${recruitedBy
              ? `已由 ${FACTIONS[recruitedBy]?.name || recruitedBy} 延攬出山`
              : forbidden
                ? `身價 ${general.recruit_value} · 不願投靠${FACTIONS[currentPlayer]?.name || currentPlayer}`
                : `身價 ${general.recruit_value} · 延攬費 $${price}（全額 + 出山附加費 $${EXILE_RECRUIT_SURCHARGE}）`}</small>
          </div>
        </div>`).join("") : '<div class="empty-state compact">在野將領池已空</div>'}
    </section>`;
  return html;
}

function renderGeneralSubtree(general, generals) {
  const subordinates = (general.subordinates || [])
    .map((id) => generals[id])
    .filter((item) => item && generalOwners[item.id] === currentPlayer);
  if (!subordinates.length) return "";
  return `
    <div class="tree-connector-vertical-small"></div>
    <div class="tree-subbranch">
      ${subordinates.map((subordinate) => `
        <div class="tree-leaf">
          <div class="tree-connector-leaf"></div>
          ${renderGeneralTreeCard(subordinate)}
          ${renderGeneralSubtree(subordinate, generals)}
        </div>
      `).join("")}
    </div>
  `;
}

function attachGeneralHandlers(root) {
  root.querySelectorAll("[data-recruit-prisoner]").forEach((button) => {
    button.addEventListener("click", async () => {
      const prisoners = jailedGenerals[currentPlayer];
      const index = prisoners.findIndex((record) => record.armyId === button.dataset.recruitPrisoner);
      if (index < 0) return;
      const record = prisoners[index];
      const superiorId = root.querySelector(`[data-recruit-superior="${button.dataset.recruitPrisoner}"]`)?.value;
      const deploymentCell = recruitmentDeploymentCell(currentPlayer);
      if (!superiorId || !deploymentCell) {
        showNotice(!superiorId ? "沒有可隸屬的現役中將。" : "沒有可部署新編軍的己方主要城市。");
        return;
      }
      const branchSize = 1;
      if (availableMajorGeneralSlots(currentPlayer) < branchSize) {
        showNotice(`中將空位不足：此批將領需要 ${branchSize} 個少將空位。`);
        return;
      }
      button.disabled = true;
      try {
        const result = await api("/api/recruit-captive-general", {
          player: currentPlayer,
          traits: transferringTraits(generalTrees[record.originFaction], record.general),
          general_id: record.general?.id,
        });
        state = result.state;
        syncStrategicCitiesFromState();
        prisoners.splice(index, 1);
        recruitCapturedGeneral(record, currentPlayer, superiorId, deploymentCell);
        recruitedGenerals[currentPlayer].push(record);
        updateTopBar();
        renderArmyMarkers(currentPlayer);
        renderPanel("generals");
        renderPendingActions();
      } catch (error) {
        button.disabled = false;
        showNotice(error.message);
      }
    });
  });
}

function availableLieutenantGenerals(faction) {
  return Object.values(generalTrees[faction]?.generals || {}).filter((general) => {
    if (general.role !== "lieutenant_general" || generalOwners[general.id] !== faction) return false;
    const army = allArmies(true).find((item) => item.generalId === general.id);
    if (army?.status === "jailed") return false;
    return lieutenantGeneralOpenSlots(general) > 0;
  });
}

function lieutenantGeneralOpenSlots(general) {
  const capacity = normalizedSlotCount(general);
  const occupied = (general?.subordinates || []).filter((id) => {
    const subordinate = generalById(id);
    return subordinate && subordinate.role === "major_general" && subordinate.status !== "killed";
  }).length;
  return Math.max(0, capacity - occupied);
}

function availableMajorGeneralSlots(faction) {
  return Object.values(generalTrees[faction]?.generals || {})
    .filter((general) => general.role === "lieutenant_general" && generalOwners[general.id] === faction)
    .reduce((sum, general) => sum + lieutenantGeneralOpenSlots(general), 0);
}

function recruitmentDeploymentCell(faction) {
  const occupied = new Set(allArmies().map((army) => army.cellKey));
  const cities = (bootstrap.strategic_map?.cities || []).filter((city) =>
    city.faction === faction && city.level >= 3 && cells[city.cellKey]?.fac === faction && !occupied.has(city.cellKey)
  );
  return cells[cities[0]?.cellKey] || null;
}

function appendGeneralToTree(general, faction, superiorId, loyalty = 2, options = {}) {
  const tree = generalTrees[faction];
  const superior = tree?.generals?.[superiorId];
  if (!tree || !superior || superior.role !== "lieutenant_general") throw new Error("invalid lieutenant affiliation");
  const appended = {
    ...JSON.parse(JSON.stringify(general)),
    faction: FACTIONS[faction].name,
    role: options.role || "major_general",
    loyalty,
    loyalty_exempt: false,
    status: "active",
    subordinates: options.subordinates ? [...options.subordinates] : [],
  };
  tree.generals[appended.id] = appended;
  superior.subordinates ||= [];
  if (!superior.subordinates.includes(appended.id)) superior.subordinates.push(appended.id);
  generalOwners[appended.id] = faction;
  loyaltyOverrides[appended.id] = loyalty;
  return appended;
}

function transferBranchSize(sourceTree, generalId) {
  return generalId ? 1 : 0;
}

// 招降／策反只處理被點選的將領本人；原本麾下關係在轉入新陣營後失效。
// 後端只需要知道本人帶來的非戰鬥技能。
function transferringTraits(sourceTree, general) {
  const traits = new Set(general.traits || []);
  for (const trait of sourceTree?.generals?.[general.id]?.traits || []) traits.add(trait);
  return [...traits];
}

function installTransferredCommand(transferred, destinationFaction, preferredSuperiorId, rootLoyalty = 2) {
  const destinationTree = generalTrees[destinationFaction];
  if (!destinationTree) throw new Error("invalid destination faction");
  const allLieutenants = availableLieutenantGenerals(destinationFaction);
  const preferred = destinationTree.generals?.[preferredSuperiorId];
  const reorderedLieutenants = [
    ...(preferred && preferred.role === "lieutenant_general" && lieutenantGeneralOpenSlots(preferred) > 0 ? [preferred] : []),
    ...allLieutenants.filter((general) => general.id !== preferredSuperiorId),
  ];
  if (reorderedLieutenants.reduce((sum, general) => sum + lieutenantGeneralOpenSlots(general), 0) < transferred.length) {
    throw new Error("沒有足夠的中將空位接收這批將領");
  }
  const installed = [];
  for (const general of transferred) {
    const superior = reorderedLieutenants.find((item) => lieutenantGeneralOpenSlots(item) > 0);
    if (!superior) throw new Error("沒有足夠的中將空位接收這批將領");
    const copied = JSON.parse(JSON.stringify(general));
    copied.faction = general.faction || FACTIONS[destinationFaction].name;
    copied.status = "active";
    copied.loyalty_exempt = false;
    copied.loyalty = copied.id === transferred[0].id ? rootLoyalty : 1;
    copied.role = "major_general";
    copied.subordinate_slots = 0;
    copied.subordinates = [];
    copied.parent_id = superior.id;
    destinationTree.generals[copied.id] = copied;
    generalOwners[copied.id] = destinationFaction;
    loyaltyOverrides[copied.id] = copied.loyalty;
    superior.subordinates ||= [];
    superior.subordinates.push(copied.id);
    installed.push({ general: copied, superiorId: superior.id });
  }
  return installed;
}

function queueDescendantCaptivesForRecruitedLeader(record, captorFaction) {
  const sourceTree = generalTrees[record.originFaction];
  const descendants = commandDescendantIds(sourceTree, record.general.id, record.general);
  for (const generalId of descendants) {
    const descendant = sourceTree?.generals?.[generalId];
    const army = allArmies(true).find((item) => item.generalId === generalId);
    if (!descendant || !army || factionForArmy(army) !== record.originFaction
      || ["jailed", "killed", "destroyed"].includes(army.status)) continue;
    if ((jailedGenerals[captorFaction] || []).some((item) => item.general?.id === generalId)) continue;
    const preservedUnits = wholeUnits(armyUnits(army));
    jailedGenerals[captorFaction].push({
      armyId: army.id,
      originFaction: record.originFaction,
      capturedTurn: state.turn,
      cellKey: army.cellKey,
      lon: army.lon,
      lat: army.lat,
      general: {
        ...JSON.parse(JSON.stringify(descendant)),
        role: "major_general",
        subordinates: [],
        subordinate_slots: 0,
        parent_id: null,
        status: "jailed",
        loyalty: descendant.loyalty === null ? null : 1,
        units: preservedUnits,
      },
    });
    const ledger = state.players[record.originFaction]?.army_reinforcements;
    if (ledger) delete ledger[army.id];
    army.units = Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0]));
    army.status = "jailed";
    descendant.status = "jailed";
    descendant.loyalty_exempt = false;
    if (descendant.loyalty !== null && descendant.loyalty !== undefined) descendant.loyalty = 1;
    loyaltyOverrides[generalId] = 1;
    markArmyResolved(army);
  }
}

function transferFactionNavies(originFaction, destinationFaction) {
  let sequence = allNavies(true).filter((navy) => navyFaction(navy) === destinationFaction).length + 1;
  const transferred = [];
  for (const navy of allNavies(true)) {
    if (navyFaction(navy) !== originFaction) continue;
    normalizeNavyDivision(navy, navyRules());
    if (!(navy.gunBoats || []).length && !(navy.cargoBoatHp || []).length) continue;
    navy.faction = destinationFaction;
    navy.name = `${FACTIONS[destinationFaction]?.name || destinationFaction}第${chineseNumber(sequence)}江防艦隊`;
    delete navy.resolvedTurn;
    resolvedNavyIds.delete(navy.id);
    transferred.push(navy.name);
    sequence += 1;
  }
  return transferred;
}

function recruitCapturedGeneral(record, faction, superiorId, deploymentCell) {
  const army = armyById(record.armyId);
  const sourceTree = generalTrees[record.originFaction];
  if (!army) throw new Error("找不到俘虜原部隊，無法招降。");
  const general = JSON.parse(JSON.stringify(record.general || sourceTree?.generals?.[record.general.id]));
  queueDescendantCaptivesForRecruitedLeader(record, faction);
  const wasFactionLeader = sourceTree?.great_general_id === general.id || general.role === "great_general";
  detachGeneralFromTree(sourceTree, general.id);
  installTransferredCommand([general], faction, superiorId, 2);
  const nextNumber = nextAvailableArmyNumber(faction, army.id);
  const startingUnits = { infantry: 5, cavalry: 0, artillery: 0, machine_gun: 0 };
  Object.assign(army, {
    faction,
    general: general.name,
    designator: formatArmyDesignator(nextNumber),
    status: "active",
    units: startingUnits,
  });
  const installedGeneral = generalTrees[faction]?.generals?.[general.id];
  if (installedGeneral) installedGeneral.units = { ...startingUnits };
  LOYALTY_BASELINE_ARMY_UNITS[army.id] = { ...startingUnits };
  const targetCell = cells[record.cellKey] || deploymentCell;
  moveArmyToCell(army, targetCell);
  if (targetCell) occupyTile(targetCell, faction);
  state.players[faction].army_reinforcements[army.id] = {};
  if (wasFactionLeader) {
    const navies = transferFactionNavies(record.originFaction, faction);
    if (navies.length) uiNotice = `${general.name}歸降，${navies.join("、")}轉投我方。`;
  }
}

function detachGeneralFromTree(tree, generalId) {
  for (const general of Object.values(tree?.generals || {})) {
    if (general.subordinates?.includes(generalId)) {
      general.subordinates = general.subordinates.filter((id) => id !== generalId);
    }
  }
}

function transferDefectingCommand(army, destinationFaction, superiorId) {
  const sourceFaction = generalOwners[army.generalId] || factionForArmy(army);
  const sourceTree = generalTrees[sourceFaction];
  const general = sourceTree?.generals?.[army.generalId];
  if (!general) throw new Error("找不到可策反將領。");
  const transferred = [JSON.parse(JSON.stringify(general))];
  detachGeneralFromTree(sourceTree, army.generalId);
  installTransferredCommand(transferred, destinationFaction, superiorId, 2);
  army.designator = formatArmyDesignator(nextAvailableArmyNumber(destinationFaction, army.id));
  army.faction = destinationFaction;
  army.status = "active";
  army.general = transferred[0]?.name || army.general;
  markArmyResolved(army);
  if (army.cellKey && cells[army.cellKey]) occupyTile(cells[army.cellKey], destinationFaction);
  const oldLedger = state.players[sourceFaction]?.army_reinforcements?.[army.id];
  if (oldLedger) {
    state.players[destinationFaction].army_reinforcements[army.id] = { ...oldLedger };
    if (state.players[sourceFaction]) {
      delete state.players[sourceFaction].army_reinforcements[army.id];
    }
  }
  return transferred;
}

async function attemptArmyDefection(army, superiorId) {
  if (!army || factionForArmy(army) === currentPlayer || activeBattleForArmy(army)) {
    showNotice(activeBattleForArmy(army) ? "交戰中的將領無法被策反。" : "無法策反此軍。");
    return;
  }
  const general = generalById(army.generalId);
  const loyalty = calculateGeneralLoyalty(general, army).value;
  if (loyalty === null || general?.loyalty_exempt || generalAbsoluteLoyaltyActive(general)) {
    showNotice("此將領屬於派系核心，不能以金錢策反。");
    return;
  }
  const branchSize = transferBranchSize(generalTrees[factionForArmy(army)], army.generalId);
  if (availableMajorGeneralSlots(currentPlayer) < branchSize) {
    showNotice("我方中將空位不足，無法接收這名將領。");
    return;
  }
  const result = await api("/api/attempt-defection", {
    player: currentPlayer,
    loyalty,
    force: forcePoints(armyUnits(army)),
    traits: transferringTraits(generalTrees[factionForArmy(army)], general),
    general_id: general?.id,
    resistance: defectionResistance(general),
  });
  state = result.state;
  syncStrategicCitiesFromState();
  updateTopBar();
  if (!result.success) {
    showNotice(`策反失敗；已支付 $${result.cost}（成功率 ${Math.round(result.chance * 100)}%）。`);
    return;
  }
  const transferred = transferDefectingCommand(army, currentPlayer, superiorId);
  selectedArmyId = army.id;
  uiNotice = `策反成功：${army.general}轉投我方，原部隊完整保留。`;
  generalTreeData = generalTrees[currentPlayer];
  initMap();
  renderPendingActions();
  if ($("panelGenerals")?.classList.contains("active")) renderPanel("generals");
}

function renderGeneralTreeCard(general, { includeCaptured = false } = {}) {
  const portrait = getGeneralPortrait(general);
  const fieldArmy = allArmies(true).find((army) => army.generalId === general.id);
  if (!includeCaptured && generalOwners[general.id] !== currentPlayer) return "";
  if (!includeCaptured && fieldArmy?.status === "jailed") return "";
  const hasArmy = Boolean(fieldArmy) && fieldArmy.status !== "jailed" && general.status !== "recruited";
  const capturedUnits = includeCaptured ? wholeUnits(general.units || {}) : null;
  const hasCapturedUnits = capturedUnits && forcePoints(capturedUnits) > 0;
  const unitsText = general.status === "in_exile"
    ? `自帶 ${unitSummary(Object.fromEntries(Object.entries(general.units || {}).filter(([, count]) => Number(count) > 0)))}`
    : (hasArmy ? unitSummary(armyUnits(fieldArmy)) : hasCapturedUnits ? unitSummary(capturedUnits) : "無部隊");
  const loyalty = calculateGeneralLoyalty(general, fieldArmy);
  const lowLoyalty = loyalty.value !== null && loyalty.value < 6;
  const loyaltyText = loyalty.value !== null ? loyalty.value : '—';
  const guard = state?.body_guards?.[general.id];
  const guardTag = guard
    ? `<span class="tree-guard">親衛隊${Number(state.turn || 0) < Number(guard.active_from_turn || 0) ? "（下回合生效）" : ""}</span>`
    : "";
  const killedTag = general.status === "killed" ? `<span class="tree-killed">已身亡</span>` : "";

  return `
    <div class="tree-general-card ${lowLoyalty ? 'low-loyalty' : ''}" data-general="${general.id}">
      ${portrait
        ? `<img class="tree-portrait" src="${portrait}" alt="${general.name}">`
        : `<div class="tree-portrait portrait-placeholder">${general.name.charAt(0)}</div>`}
      <div class="tree-info">
        <div class="tree-name">${general.name}${killedTag}${guardTag}</div>
        <div class="tree-faction">${general.faction || "在野"}</div>
        <div class="tree-units">${unitsText}</div>
        ${hasArmy ? forceMeterMarkup(armyUnits(fieldArmy), { compact: true }) : hasCapturedUnits ? forceMeterMarkup(capturedUnits, { compact: true }) : ""}
        <div class="tree-traits">${(general.traits || []).map((trait) => traitChip(trait, general.id)).join("")}</div>
      </div>
      ${general.loyalty !== null ? `
          <div class="tree-loyalty" data-tooltip="${loyalty.tooltip}">
          <div class="loyalty-num">${loyaltyText}</div>
          <div class="loyalty-lbl">忠誠</div>
        </div>
      ` : ''}
    </div>
  `;
}

function calculateGeneralLoyalty(general, fieldArmy) {
  if (general.loyalty === null || general.loyalty === undefined) return { value: null, tooltip: "" };
  if (generalAbsoluteLoyaltyActive(general)) {
    return { value: 10, tooltip: "絕對忠誠: 固定 10\n不受功能卡、戰損或策反效果影響" };
  }
  const relationPenalty = traitLoyaltyAdjustment(general);
  const hasOverride = Object.hasOwn(loyaltyOverrides, general.id);
  const baseSource = hasOverride ? loyaltyOverrides[general.id] : Number(general.loyalty);
  const baseLoyalty = Math.max(0, Math.min(10, Number(baseSource) + relationPenalty.amount));
  const overrideNote = hasOverride ? "\n當前忠誠曾受俘虜、招降、策反或功能卡改變" : "";
  if (general.status === "in_exile") {
    return { value: baseLoyalty, tooltip: `出山時的基礎忠誠: ${baseLoyalty}${relationPenalty.note}\n在野期間不套用部隊相關的增減` };
  }
  if (!fieldArmy || fieldArmy.status === "jailed" || general.status === "recruited") {
    const value = Math.min(baseLoyalty, 2);
    return { value, tooltip: `基礎忠誠: ${baseLoyalty}${relationPenalty.note}${overrideNote}\n無直屬部隊: -${Math.max(0, baseLoyalty - value)}` };
  }
  const faction = factionForArmy(fieldArmy);
  const friendlyForces = allArmies()
    .filter((army) => factionForArmy(army) === faction)
    .filter((army) => army.status !== "jailed")
    .map((army) => forcePoints(armyUnits(army)));
  const currentForce = forcePoints(armyUnits(fieldArmy));
  const averageForce = friendlyForces.reduce((sum, value) => sum + value, 0) / Math.max(1, friendlyForces.length);
  const relativePower = Math.max(-2, Math.min(2, Math.round((currentForce / Math.max(1, averageForce) - 1) * 3)));
  const initialForce = forcePoints(LOYALTY_BASELINE_ARMY_UNITS[fieldArmy.id] || INITIAL_ARMY_UNITS[fieldArmy.id] || {});
  const lossRate = Math.max(0, (initialForce - currentForce) / Math.max(1, initialForce));
  const battleLoss = -Math.min(4, Math.floor(lossRate * 5));
  const value = Math.max(0, Math.min(10, baseLoyalty + relativePower + battleLoss));
  return {
    value,
    tooltip: `基礎忠誠: ${baseLoyalty}${relationPenalty.note}${overrideNote}\n相對實力影響: ${relativePower >= 0 ? '+' : ''}${relativePower}\n戰損影響: ${battleLoss}\n現有戰力: ${Math.round(currentForce)} / 基準 ${Math.round(initialForce)}`,
  };
}

// 被策反時對方成功率的額外扣減（唐生智的〈佛教將軍〉-5%）。
function defectionResistance(general) {
  return (general?.traits || []).reduce(
    (total, trait) => total + (DEFECTION_RESISTANCE_TRAITS[trait] || 0),
    0,
  );
}

function factionHoldingGeneral(generalId) {
  return generalOwners[generalId]
    || Object.keys(FACTIONS).find((key) => generalTrees[key]?.generals?.[generalId])
    || null;
}

// 技能帶來的忠誠增減（回傳的 amount 已經是帶正負號的總和）：
// 列強關係讓技能失效時的處罰（張宗昌、何鍵各 -5）。
function traitLoyaltyAdjustment(general) {
  const faction = factionHoldingGeneral(general.id);
  if (!faction) return { amount: 0, note: "" };
  let amount = 0;
  const reasons = [];
  for (const trait of general.traits || []) {
    const rule = RELATION_DISABLED_TRAITS[trait];
    if (rule?.loyalty_penalty && traitDisabledByRelations(trait, faction)) {
      amount -= rule.loyalty_penalty;
      reasons.push(`〈${traitLabel(trait, general.id)}〉失效: -${rule.loyalty_penalty}`);
    }
  }
  return { amount, note: reasons.length ? `\n${reasons.join("\n")}` : "" };
}

function getGeneralPortrait(general) {
  return PORTRAIT_BY_ID[general.id] || null;
}

function getRoleLabel(role) {
  const labels = {
    great_general: "大元帥",
    lieutenant_general: "上將",
    major_general: "中將"
  };
  return labels[role] || role;
}

function formatUnits(units) {
  return Object.entries(UNIT_META)
    .filter(([type]) => units?.[type])
    .map(([type, meta]) => `${meta.short}${units[type]}營 (${formatUnitQuantity(type, units[type])})`)
    .join(" · ") || "無部隊";
}

function armyTooltipText(army, observer = currentPlayer) {
  return [
    armyCombatLabel(army),
    army.general,
    armyCompositionVisible(army, observer) ? formatUnits(armyUnits(army)) : "兵力不明，需交戰或情報網揭露編制",
  ].join("\n");
}

function renderRecruitmentPanel() {
  const profile = state.players[currentPlayer] || {};
  const costModifier = profile.recruitment_cost_modifier ?? 1;
  const costs = bootstrap.recruit_costs || {};
  const navyCosts = bootstrap.navy_recruit_costs || {};

  return `
    <div class="recruitment-grid">
      ${Object.entries(UNIT_META).map(([type, unit]) => {
        // 卡片給的固定加減（汪精衛復出：步兵 -1）疊在陣營費率之後，下限 1。
        const adjustment = profile.recruit_cost_adjustment?.[type] || {};
        const cash = Math.max(1, Math.ceil((costs[type]?.cash ?? 0) * costModifier) + Number(adjustment.cash || 0));
        const factory = Math.max(0, (costs[type]?.factory ?? 0) + Number(adjustment.factory || 0));
        const reserve = profile.unit_reserves?.[type] ?? 0;
        return `
        <div class="unit-option" data-unit="${type}">
          <div class="unit-icon-hoi4">${unitSymbol(type)}</div>
          <div class="unit-details">
            <h3>${unit.name}</h3>
            <div class="unit-stats">預備 ${reserve} · 現金 $${cash} · 工廠 ${factory}</div>
          </div>
          <div class="unit-cost">
            <button class="train-unit-btn" data-train-unit="${type}">訓練 +1</button>
          </div>
        </div>
      `}).join('')}
    </div>
    <h3 class="panel-subtitle">海軍預備</h3>
    <div class="recruitment-grid navy-recruitment-grid">
      ${Object.entries(NAVY_UNIT_META).map(([type, unit]) => {
        const cost = navyCosts[type] || {};
        const reserve = profile.navy_reserves?.[type] ?? 0;
        return `
        <div class="unit-option" data-navy-unit="${type}">
          <div class="navy-profile-icon">${type === "gun_boat" ? "砲" : "運"}</div>
          <div class="unit-details">
            <h3>${unit.name}</h3>
            <div class="unit-stats">預備 ${reserve} · 現金 $${cost.cash ?? 0} · 工廠 ${cost.factory ?? 0}</div>
          </div>
          <div class="unit-cost">
            <button class="train-unit-btn" data-train-navy-unit="${type}">建造 +1</button>
          </div>
        </div>
      `}).join('')}
    </div>
    <div class="panel-note">
      可用現金 $${profile.treasury ?? 0} · 工廠點 ${profile.factory_points ?? 0} · 招募費率 ${Math.round(costModifier * 100)}%
    </div>
  `;
}

function unitSymbol(type, count = null) {
  const unit = UNIT_META[type];
  return `<span class="unit-symbol symbol-${unit.symbol}" aria-label="${unit.name}">
    <span class="unit-symbol-mark"></span>
    ${count === null ? "" : `<span class="unit-symbol-count">${count}</span>`}
  </span>`;
}

function attachRecruitmentHandlers() {
  $("recruitmentContent").querySelectorAll("[data-train-unit]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/train-unit", {
          player: currentPlayer,
          unit_type: button.dataset.trainUnit,
          count: 1,
        });
        state = result.state;
        syncStrategicCitiesFromState();
        updateTopBar();
        renderPanel("recruitment");
        renderPendingActions();
      } catch (error) {
        showNotice(error.message);
      }
    });
  });
  $("recruitmentContent").querySelectorAll("[data-train-navy-unit]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/train-navy-unit", {
          player: currentPlayer,
          unit_type: button.dataset.trainNavyUnit,
          count: 1,
        });
        state = result.state;
        syncStrategicCitiesFromState();
        updateTopBar();
        renderPanel("recruitment");
        renderPendingActions();
      } catch (error) {
        showNotice(error.message);
      }
    });
  });
}

// ---- 借款面板 ---------------------------------------------------------
// 上半部：各家銀行的可貸額度、利率、還款期限。下半部：尚未清償的貸款。
// 兩者都直接讀 /api/loan-offers，所以列強關係一變動，額度與等級即時反映。

let loanPanelCache = null;
let loanPanelRefreshing = false;

// 借款面板與列強關係即時連動：任何會改變狀態的動作最後都會呼叫 updateTopBar()，
// 我們在那裡順手把開著的借款面板重新拉一次，額度與等級就會跟著關係值變動。
function refreshLoansIfOpen() {
  const panel = document.getElementById("panelLoans");
  if (!panel || !panel.classList.contains("active") || loanPanelRefreshing) return;
  loanPanelRefreshing = true;
  loanPanelCache = null;
  renderLoansPanel().finally(() => { loanPanelRefreshing = false; });
}

const TIER_LABEL = { blocked: "不可借貸", standard: "普通借貸", preferred: "優惠借貸" };

function renderLoanOfferRow(row) {
  const blocked = !row.can_borrow;
  const rate = row.interest_per_turn == null ? "—" : `${Math.round(row.interest_per_turn * 100)}%／回合`;
  const term = row.term_turns == null ? "—" : `${row.term_turns} 回合`;
  const relation = row.relation == null
    ? '<small class="loan-neutral">中立商行</small>'
    : `<small>關係 ${row.relation > 0 ? "+" : ""}${row.relation}</small>`;
  return `
    <tr class="${blocked ? "loan-blocked" : ""}">
      <td class="loan-bank-cell">${powerFlagMarkup(row.power, "flag-chip bank-flag")}<span><b>${row.name}</b><br>${relation}</span></td>
      <td>${TIER_LABEL[row.tier] || row.tier_label || "—"}</td>
      <td class="num">${row.available} / ${row.limit}</td>
      <td class="num">${rate}</td>
      <td class="num">${term}</td>
      <td>${blocked
        ? `<span class="loan-blocked-note">${row.loan_ban_remaining_turns ? `公債封鎖 ${row.loan_ban_remaining_turns} 回合` : row.tier === "blocked" ? "關係交惡" : row.tier_label || "不承作"}</span>`
        : `<button class="loan-borrow-btn" data-borrow-bank="${row.bank}" data-max="${row.available}">借款</button>`}</td>
    </tr>
  `;
}

function renderLoanRow(loan, turn) {
  const overdue = loan.overdue;
  const remaining = loan.turns_remaining;
  const remainingText = overdue
    ? `<b class="loan-overdue">逾期 ${Math.abs(remaining)} 回合</b>`
    : `${remaining} 回合`;
  return `
    <tr class="${overdue ? "loan-overdue-row" : ""}">
      <td class="loan-bank-cell">${loan.domestic
        ? factionFlagMarkup(loan.issuer || currentPlayer, "flag-chip bank-flag")
        : powerFlagMarkup(loan.bank_power, "flag-chip bank-flag")}<span>${loan.bank_name}</span></td>
      <td class="num">$${loan.outstanding}</td>
      <td class="num">${Math.round(loan.interest_per_turn * 100)}%</td>
      <td class="num">${remainingText}</td>
      <td><small>${loan.domestic ? "公債" : loan.source && loan.source.startsWith("card:") ? "功能卡" : "銀行"}</small></td>
    </tr>
  `;
}

function renderLoansMarkup(data) {
  const offers = data.offers || [];
  const loans = data.loans || [];
  const total = loans.reduce((sum, loan) => sum + loan.outstanding, 0);
  const banTurns = Number(data.loan_ban_remaining_turns || 0);
  return `
    <div class="loan-summary">
      <span>金庫 <b>$${data.treasury ?? 0}</b></span>
      <span>負債總額 <b class="debt">$${total}</b></span>
      <span>回合 <b>${data.turn ?? 0}</b></span>
    </div>
    ${banTurns > 0 ? `<p class="loan-ban-note">
      <span class="loan-ban-title">信用受損：外國銀行全面拒貸</span>
      你發行過〈軍閥公債〉，下面五家銀行（橫濱正金、匯豐、東方匯理、花旗、德華）
      在解禁前<b>一律不受理新借款</b>，表格最右邊的「借款」鍵會是關閉的。
      還要 <b>${banTurns}</b> 回合（到第 ${data.loan_ban_until_turn} 回合）才恢復正常。
      不受影響的有兩種：<b>已經借出的舊債</b>照常計息、照常還款、逾期照樣被扣；
      <b>功能卡貸款</b>（〈軍閥公債〉本身、〈橫濱正金短貸〉〈匯豐周轉授信〉〈花旗工業貸款〉）
      也照樣打得出來，它們走的不是這張表格。
    </p>` : ""}

    <h3 class="loan-heading">可借額度</h3>
    <table class="loan-table">
      <thead><tr><th>銀行</th><th>等級</th><th>可借／額度</th><th>利率</th><th>期限</th><th></th></tr></thead>
      <tbody>${offers.map(renderLoanOfferRow).join("")}</tbody>
    </table>

    <h3 class="loan-heading">未清償貸款</h3>
    ${loans.length ? `
      <table class="loan-table">
        <thead><tr><th>銀行</th><th>餘額</th><th>利率</th><th>到期</th><th>來源</th></tr></thead>
        <tbody>${loans.map((loan) => renderLoanRow(loan, data.turn)).join("")}</tbody>
      </table>
    ` : '<p class="loan-empty">目前沒有未清償的貸款。</p>'}

    <h3 class="loan-heading">提前還款</h3>
    ${debtRepayMarkup()}
  `;
}

// 提前還款：原本擺在「經濟」面板，經濟面板取消後移到借款面板最下方。
function debtRepayMarkup() {
  const payload = state.players[currentPlayer] || {};
  const debt = Number(payload.debt || 0);
  const treasury = Number(payload.treasury || 0);
  const max = Math.min(debt, treasury);
  const canRepay = max > 0;
  return `
    <div class="debt-repay-panel">
      <label>償還負債<input id="debtRepayAmount" type="number" min="1" max="${max}" value="${max}" ${canRepay ? "" : "disabled"}></label>
      <button data-repay-debt ${canRepay ? "" : "disabled"}>還款</button>
    </div>
    ${canRepay ? "" : `<p class="loan-empty">${debt <= 0 ? "目前沒有負債。" : "金庫沒有現金可用來還款。"}</p>`}
  `;
}

async function renderLoansPanel(element) {
  const target = element || document.getElementById("loansContent");
  if (!target) return;
  target.innerHTML = loanPanelCache ? renderLoansMarkup(loanPanelCache) : '<p class="loan-empty">讀取中…</p>';
  try {
    loanPanelCache = await api("/api/loan-offers", { player: currentPlayer });
    target.innerHTML = renderLoansMarkup(loanPanelCache);
    attachLoanHandlers(target);
  } catch (error) {
    target.innerHTML = `<p class="loan-empty">無法取得借款資料：${error.message}</p>`;
  }
}

function attachLoanHandlers(root) {
  attachDebtRepayHandler(root);
  root.querySelectorAll("[data-borrow-bank]").forEach((button) => {
    button.addEventListener("click", async () => {
      const bank = button.dataset.borrowBank;
      const max = Number(button.dataset.max || 0);
      const raw = window.prompt(`借款金額（上限 $${max}）`, String(max));
      if (raw === null) return;
      const amount = Number(raw);
      if (!Number.isFinite(amount) || amount <= 0) {
        showNotice("借款金額必須是大於 0 的數字。");
        return;
      }
      try {
        const result = await api("/api/take-loan", { player: currentPlayer, bank, amount });
        state = result.state;
        syncStrategicCitiesFromState();
        updateTopBar();
        loanPanelCache = null;
        await renderLoansPanel(root);
        showNotice(`向${result.loan.bank_name}借款 $${result.loan.principal}，${result.loan.term_turns} 回合到期。`);
      } catch (error) {
        showNotice(error.message);
      }
    });
  });
}


function attachDebtRepayHandler(root = document) {
  root.querySelector("[data-repay-debt]")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/repay-debt", {
        player: currentPlayer,
        amount: Number(root.querySelector("#debtRepayAmount")?.value || 0),
      });
      state = result.state;
      syncStrategicCitiesFromState();
      updateTopBar();
      loanPanelCache = null;
      await renderLoansPanel(document.getElementById("loansContent"));
      renderPendingActions();
      showNotice(`${factionLabel(currentPlayer)}償還負債 $${result.amount}。`);
    } catch (error) {
      showNotice(error.message);
    }
  });
}

function renderForeignPanel() {
  if (!currentPlayer || !state.players[currentPlayer]) {
    return `<div class="empty-state">請選擇玩家</div>`;
  }

  const payload = state.players[currentPlayer];
  const tabs = `
    <div class="foreign-tabs" role="tablist">
      <button class="${foreignTab === "warlords" ? "active" : ""}" data-foreign-tab="warlords">軍閥</button>
      <button class="${foreignTab === "powers" ? "active" : ""}" data-foreign-tab="powers">列強</button>
    </div>
  `;

  if (foreignTab === "powers") {
    const relations = payload.foreign_relations || {};
    const powers = [
      { key: "jp", name: "日本", territories: "朝鮮、台灣、關東州" },
      { key: "su", name: "蘇聯", territories: "蘇聯遠東、外蒙古" },
      { key: "uk", name: "英國", territories: "華南沿海商路、香港、緬甸、印度" },
      { key: "fr", name: "法國", territories: "法屬印度支那" },
      { key: "us", name: "美國", territories: "太平洋外交與商業利益" },
    ];
    return tabs + `<div class="relations-list">${powers.map((power) => {
      const value = relations[power.key] ?? 0;
      const relationText = value >= 6 ? "友好" : value <= -4 ? "敵對" : "中立";
      return `
        <div class="relation-row">
          ${flagMarkup(power.key, "flag-chip relation-flag")}
          <div><b>${power.name}</b><small>${power.territories}</small></div>
          <span class="power-relation ${value >= 6 ? "good" : value <= -4 ? "poor" : ""}">
            ${relationText} ${value > 0 ? "+" : ""}${value}
          </span>
        </div>
      `;
    }).join("")}</div>`;
  }

  const warlords = Object.keys(state.players || {}).filter((code) => code !== currentPlayer);
  return tabs + `<div class="relations-list">${warlords.map((code) => {
    const relation = payload.warlord_relations?.[code] || { status: "peace" };
    const atWar = relation.status === "war";
    const warTurns = atWar ? Math.max(0, state.turn - (relation.war_started_turn ?? state.turn)) : 0;
    const isPlayable = Boolean(state.players[code]);
    const lockedWar = !isPlayable || relation.permanent_war;
    return `
      <div class="warlord-relation ${atWar ? "at-war" : ""}">
        <div class="warlord-row">
          ${factionFlagMarkup(code, "flag-chip warlord-flag")}
          <span class="faction-swatch" style="background:${FACTIONS[code].color}"></span>
          <div class="warlord-name"><b>${FACTIONS[code].name}</b><small>${lockedWar ? "NPC · 永久交戰" : atWar ? `交戰第 ${warTurns} / 10 回合` : "和平 · 不可越境"}</small></div>
          <button data-diplomacy-status="${atWar ? "peace" : "war"}" data-target="${code}" ${lockedWar || (atWar && warTurns < 10) ? `disabled title="${lockedWar ? "NPC 勢力不可外交" : "交戰滿十回合後方可議和"}"` : ""}>${lockedWar ? "永久戰爭" : atWar ? "議和" : "宣戰"}</button>
          ${isPlayable ? `<button data-open-deal="${code}">交易</button>` : ""}
        </div>
        ${dealTarget === code ? `
          <div class="deal-editor">
            <label>資金<input id="dealFunds" type="number" min="0" value="0"></label>
            <label>預備兵<select id="dealUnitType">${Object.entries(UNIT_META).map(([type, unit]) => `<option value="${type}">${unit.name}</option>`).join("")}</select></label>
            <label>數量<input id="dealReserve" type="number" min="0" value="0"></label>
            <button data-submit-deal="${code}">提出交易</button>
          </div>
        ` : ""}
      </div>
    `;
  }).join("")}</div>`;
}

function attachForeignHandlers() {
  const root = $("foreignContent");
  root.querySelectorAll("[data-foreign-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      foreignTab = button.dataset.foreignTab;
      dealTarget = null;
      renderPanel("foreign");
    });
  });
  root.querySelectorAll("[data-diplomacy-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/diplomacy", {
          player: currentPlayer,
          target: button.dataset.target,
          status: button.dataset.diplomacyStatus,
        });
        state = result.state;
        syncStrategicCitiesFromState();
        renderPanel("foreign");
        renderPendingActions();
      } catch (error) {
        showNotice(error.message);
      }
    });
  });
  root.querySelectorAll("[data-open-deal]").forEach((button) => {
    button.addEventListener("click", () => {
      dealTarget = dealTarget === button.dataset.openDeal ? null : button.dataset.openDeal;
      renderPanel("foreign");
    });
  });
  root.querySelector("[data-submit-deal]")?.addEventListener("click", async (event) => {
    try {
      const result = await api("/api/deal", {
        player: currentPlayer,
        target: event.currentTarget.dataset.submitDeal,
        funds: Number($("dealFunds").value || 0),
        unit_type: $("dealUnitType").value,
        reserve: Number($("dealReserve").value || 0),
      });
      state = result.state;
      syncStrategicCitiesFromState();
      dealTarget = null;
      updateTopBar();
      renderPanel("foreign");
      renderPendingActions();
      showNotice("交易提案已送出，待對方決定。切換至對方陣營可接受或拒絕。");
    } catch (error) {
      showNotice(error.message);
    }
  });
}

function renderCardsPanel() {
  if (!currentPlayer || !state.players[currentPlayer]) {
    return `<div class="empty-state">請選擇玩家</div>`;
  }

  const payload = state.players[currentPlayer];
  const cards = payload.hand.map((id) => cardIndex[id]).filter(Boolean);
  const pendingCard = payload.pending_draw ? cardIndex[payload.pending_draw] : null;
  const purchase = functionPurchaseMarkup(payload, "panel");

  if (!cards.length) {
    return `${purchase}${activeEffectsMarkup(payload)}<div class="empty-state">目前無手牌</div>`;
  }

  const cardsHtml = cards.map((card) => `
    <div class="card-item-full">
      <div class="card-header-row">
        <div class="card-name">${card.name}</div>
        ${pendingCard
          ? `<button class="card-use-btn discard" data-discard="${card.id}">棄置</button>`
          : `<button class="card-use-btn" data-use="${card.id}" data-player="${currentPlayer}">打出</button>`}
      </div>
      <div class="card-category">${card.category || "function"}</div>
      ${card.story ? `<div class="card-story">${card.story}</div>` : ''}
      ${card.effect ? `<div class="card-effect">${card.effect}</div>` : ''}
      ${functionCardTargetMarkup(card)}
    </div>
  `).join("");

  return `
    ${purchase}
    ${activeEffectsMarkup(payload)}
    ${pendingCard ? `<div class="discard-panel-notice">新牌「${pendingCard.name}」等待加入。請棄置一張現有手牌。</div>` : ""}
    <div style="margin-bottom: 16px; padding: 12px; background: var(--terracotta-tint); border-radius: 8px;">
      <div style="font-size: 13px; color: var(--muted);">
        牌庫 ${payload.function_deck.length} · 手牌 ${payload.hand.length}/${MAX_HAND_SIZE} · 棄牌 ${payload.discard.length} · 本回合抽牌 ${payload.function_purchase_count || 0}/${functionCardDrawLimit()}
      </div>
    </div>
    <div class="card-detail-list">${cardsHtml}</div>
  `;
}

function attachCardHandlers(root = document) {
  root.querySelectorAll("[data-buy-function-card]").forEach((button) => {
    button.addEventListener("click", () => buyFunctionCard(button));
  });

  // 黑幫暴動：換了目標勢力，可選省份也跟著換成該勢力當前控制的省份。
  root.querySelectorAll("[data-gang-riot]").forEach((select) => {
    select.addEventListener("change", () => {
      const card = cardIndex[select.dataset.gangRiot];
      const provinceSelect = root.querySelector(`[data-card-target-province="${select.dataset.gangRiot}"]`);
      if (!card || !provinceSelect) return;
      const entry = gangRiotTargets(card).find((item) => item.owner === select.value);
      provinceSelect.innerHTML = provinceOptionMarkup(entry?.provinces || []);
    });
  });

  root.querySelectorAll("[data-use]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const card = cardIndex[button.dataset.use];
        if (card?.mechanic === "army_unit_bundle") {
          const army = allArmies(true).find((item) => item.generalId === card.target_general_id);
          if (!army || (card.requires_active !== false && army.status === "jailed")) {
            throw new Error("指定將領已被俘或不在戰場，不能打出此牌。");
          }
        }
        const targetGeneralId = root.querySelector(`[data-card-target="${button.dataset.use}"]`)?.value;
        if (card?.mechanic === "affiliation_slot") {
          const general = generalById(targetGeneralId);
          if (!general || generalOwners[targetGeneralId] !== currentPlayer || general.role !== "lieutenant_general") {
            throw new Error("擴編直屬只能指定己方中將。");
          }
          if (normalizedSlotCount(general) >= LIEUTENANT_SLOT_CAP) {
            throw new Error("該中將直屬名額已達上限。");
          }
        }
        const result = await api("/api/use-function", {
          player: button.dataset.player,
          card_id: button.dataset.use,
          target_general_id: targetGeneralId,
          target_owner: root.querySelector(`[data-card-target-owner="${button.dataset.use}"]`)?.value
            || generalOwners[targetGeneralId],
          target_city_id: root.querySelector(`[data-card-target-city="${button.dataset.use}"]`)?.value,
          target_city_ids: [...root.querySelectorAll(`[data-card-target-cities="${button.dataset.use}"]`)]
            .map((select) => select.value).filter(Boolean),
          target_province: root.querySelector(`[data-card-target-province="${button.dataset.use}"]`)?.value,
          target_provinces: [...root.querySelectorAll(`[data-card-target-provinces="${button.dataset.use}"]`)]
            .map((select) => select.value).filter(Boolean),
          target_railway: root.querySelector(`[data-card-target-railway="${button.dataset.use}"]`)?.value,
          target_power: root.querySelector(`[data-card-target-power="${button.dataset.use}"]`)?.value,
          exchange_direction: root.querySelector(`[data-card-exchange-direction="${button.dataset.use}"]`)?.value,
          exchange_amount: (() => {
            const field = root.querySelector(`[data-card-exchange-amount="${button.dataset.use}"]`);
            return field ? Number(field.value) : undefined;
          })(),
        });
        state = result.state;
        applyFunctionSideEffects(result);
        syncStrategicCitiesFromState();
        uiNotice = functionActionMessage(state.last_action, currentPlayer);
        await publishSharedState(true);
        updateTopBar();
        initMap();
        renderPendingActions();
        if ($("panelGenerals")?.classList.contains("active")) renderPanel("generals");
        if ($("panelCards").classList.contains("active")) renderPanel("cards");
      } catch (error) {
        button.disabled = false;
        showNotice(error.message);
      }
    });
  });

  root.querySelectorAll("[data-discard]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/discard-for-draw", {
          player: currentPlayer,
          card_id: button.dataset.discard,
        });
        state = result.state;
        syncStrategicCitiesFromState();
        renderPendingActions();
        if ($("panelCards").classList.contains("active")) renderPanel("cards");
      } catch (error) {
        button.disabled = false;
        showNotice(error.message);
      }
    });
  });
}

function loyaltyCardTargets(card) {
  const ownCard = card.id === "unit_promotion";
  return Object.entries(generalOwners).flatMap(([generalId, owner]) => {
    if ((ownCard && owner !== currentPlayer) || (!ownCard && owner === currentPlayer)) return [];
    const general = generalById(generalId);
    if (!general || general.loyalty === null || generalAbsoluteLoyaltyActive(general) || (!ownCard && general.loyalty_exempt)) return [];
    const fieldArmy = allArmies(true).find((army) => army.generalId === generalId);
    if (fieldArmy?.status === "jailed") return [];
    const loyalty = calculateGeneralLoyalty(general, fieldArmy).value;
    return [{ general, owner, loyalty }];
  });
}

// ---- 暗殺與親衛隊 ---------------------------------------------------------

function generalIsAlive(general) {
  return Boolean(general) && general.status !== "killed";
}

// 「任意一位敵方人物」：所有非我方陣營的在世將領，含大帥與 NPC 陣營。
function assassinationTargets() {
  return Object.entries(generalOwners).flatMap(([generalId, owner]) => {
    if (owner === currentPlayer) return [];
    const general = generalById(generalId);
    if (!generalIsAlive(general)) return [];
    return [{ general, owner, guarded: Boolean(state?.body_guards?.[generalId]) }];
  });
}

// 親衛隊只給自己人，而且每人全場一支。
function bodyGuardTargets() {
  return Object.entries(generalOwners)
    .filter(([generalId, owner]) => owner === currentPlayer && !state?.body_guards?.[generalId])
    .map(([generalId]) => generalById(generalId))
    .filter(generalIsAlive);
}

// 後端只回報成敗，實際把人從將領樹上抹掉是前端的事，
// 規則沿用 general_tree.kill_general：本人陣亡，麾下少將忠誠歸零。
function applyAssassination(outcome) {
  if (!outcome?.success) return;
  applyGeneralDeath(outcome.target_general_id);
}

// ── 在野將領 ────────────────────────────────────────────────────────────
// 開局不在場上、不屬於任何陣營；只有〈在野名將投效〉能把人請出山。
function exilePool() {
  return bootstrap?.generals_in_exile?.generals || {};
}

// 延攬費 = 身價全額 + 出山附加費。附加費是請人重新拉隊伍的開辦成本。
const EXILE_RECRUIT_SURCHARGE = 15;

// 有些在野將領有舊怨，不肯投靠特定陣營（盧永祥不投五省聯軍、陳炯明不投國民革命軍）。
function exileForbiddenFor(general, faction = currentPlayer) {
  return (general?.forbidden_factions || []).includes(faction);
}

function exilePoolEntries() {
  const taken = state?.recruited_exiles || {};
  return Object.values(exilePool()).map((general) => ({
    general,
    recruitedBy: taken[general.id] || null,
    forbidden: exileForbiddenFor(general),
    price: Number(general.recruit_value || 0) + EXILE_RECRUIT_SURCHARGE,
  }));
}

function availableExiles() {
  return exilePoolEntries().filter((entry) => !entry.recruitedBy && !entry.forbidden);
}

const ARMY_ORDINALS = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];

// 後端只負責扣款與鎖定人選，把人放進將領樹與地圖是前端的事。
function applyExileRecruit(outcome) {
  if (!outcome?.general_id) return;
  const owner = outcome.owner;
  const source = exilePool()[outcome.general_id];
  const tree = generalTrees[owner];
  if (!source || !tree) return;
  if (tree.generals[outcome.general_id]) return;

  const greatId = tree.great_general_id;
  const great = tree.generals[greatId];
  if (!great) return;

  const general = JSON.parse(JSON.stringify(source));
  general.faction = FACTIONS[owner]?.shortName || owner;
  general.core_faction = false;
  general.status = "active";
  general.parent_id = greatId;
  general.came_from_exile = true;
  tree.generals[general.id] = general;
  great.subordinates = [...(great.subordinates || []), general.id];
  great.subordinate_slots = Math.max(Number(great.subordinate_slots || 0), great.subordinates.length);
  generalOwners[general.id] = owner;

  // 出山地點：該陣營大帥所在地，就近找一格自己控制的空格。
  const list = ARMY_POSITIONS[owner] || (ARMY_POSITIONS[owner] = []);
  const anchorArmy = list.find((army) => army.generalId === greatId) || list[0];
  const occupied = new Set(allArmies(true).map((army) => army.cellKey).filter(Boolean));
  const cell = anchorArmy ? cellAt(anchorArmy.lon, anchorArmy.lat, owner, occupied) : null;
  if (!cell) return;
  const index = list.length + 1;
  list.push({
    id: `${owner}-${index}`,
    generalId: general.id,
    general: general.name,
    designator: `第${ARMY_ORDINALS[index] || index}軍`,
    startCityId: anchorArmy?.startCityId || null,
    lon: cell.lon,
    lat: cell.lat,
    cellKey: cell.key,
    units: { infantry: 0, cavalry: 0, artillery: 0, machine_gun: 0, ...(outcome.units || {}) },
  });
}

function loyaltyCardTargetMarkup(card) {
  if (!["unit_promotion", "local_autonomy_agitation"].includes(card.id)) return "";
  const targets = loyaltyCardTargets(card);
  return `<label class="card-target">指定將領<select data-card-target="${card.id}" ${targets.length ? "" : "disabled"}>${targets.map(({ general, owner, loyalty }) => `<option value="${general.id}">${FACTIONS[owner]?.shortName || owner} · ${general.name}（忠誠 ${loyalty}）</option>`).join("")}</select></label>`;
}

// 警政單位只能佈在自己有城市的省份。
function ownedProvinceOptions() {
  const owned = new Set((state?.players?.[currentPlayer]?.city_economy || []).map((city) => city.province));
  return [...owned].filter(Boolean).sort();
}

// 己方所有還在場上的將領，供〈成立機械化步兵師〉這類指定卡使用。
function ownGeneralOptions() {
  return Object.entries(generalOwners)
    .filter(([, owner]) => owner === currentPlayer)
    .map(([generalId]) => generalById(generalId))
    .filter((general) => general && general.status !== "killed")
    .map((general) => ({ id: general.id, name: general.name }));
}

function subordinateSlotTargets() {
  return Object.entries(generalOwners)
    .filter(([, owner]) => owner === currentPlayer)
    .map(([generalId]) => generalById(generalId))
    .filter((general) => general?.role === "lieutenant_general" && normalizedSlotCount(general) < LIEUTENANT_SLOT_CAP)
    .map((general) => ({ general, slots: normalizedSlotCount(general) }));
}

// 黑幫暴動類卡片只列真的打得出去的目標：對方在該省要有城市、
// 該省沒有警政單位駐防、對方也沒有宋家撐腰。
function gangRiotShielded(owner, province, mechanic) {
  return (state?.players?.[owner]?.timed_effects || []).some((effect) =>
    effect.kind === "gang_riot_shield"
    && Number(effect.remaining_turns || 0) > 0
    && effect.province === province
    && (effect.blocked_mechanics || []).includes(mechanic));
}

function gangRiotTargets(card) {
  const allowed = card.provinces?.length ? new Set(card.provinces) : null;
  return TURN_PLAYERS
    .filter((player) => player !== currentPlayer)
    .map((owner) => {
      const payload = state?.players?.[owner] || {};
      if ((payload.soong_patronage?.immune_cards || []).includes(card.id)) return { owner, provinces: [] };
      const controlled = new Set((payload.city_economy || []).map((city) => city.province).filter(Boolean));
      const provinces = [...controlled]
        .filter((province) => !allowed || allowed.has(province))
        .filter((province) => !gangRiotShielded(owner, province, card.mechanic))
        .sort((first, second) => first.localeCompare(second, "zh-Hant"));
      return { owner, provinces };
    })
    .filter((entry) => entry.provinces.length);
}

// 共黨暴動與紅軍起義：對方要有城市可癱瘓就行。
// （〈自由中國教育家〉已改制成事件卡 10.6，改走事件卡池封鎖，不再是打牌時的護盾。）
function riotTargets(card) {
  return TURN_PLAYERS
    .filter((player) => player !== currentPlayer)
    .filter((owner) => (state?.players?.[owner]?.city_economy || []).length);
}

function provinceOptionMarkup(provinces) {
  return provinces.map((province) => `<option value="${province}">${province}</option>`).join("");
}

// 大港開炸可以炸的目標：他方勢力控制、且還沒在搶修中的港口城市。
function enemyPortCityOptions() {
  const downed = paralysedPorts();
  const options = [];
  for (const cell of Object.values(cells)) {
    const city = cell.city;
    if (!city?.port || downed.has(String(city.id))) continue;
    const owner = city.faction || cell.fac;
    if (!owner || owner === currentPlayer || !FACTIONS[owner] || FACTIONS[owner].type !== "player") continue;
    options.push({ id: city.id, name: city.name, owner, port: city.port });
  }
  return options.sort((a, b) => a.owner.localeCompare(b.owner) || a.name.localeCompare(b.name));
}

function functionCardTargetMarkup(card) {
  if (card.mechanic === "qing_gang_riot") {
    const entries = gangRiotTargets(card);
    if (!entries.length) {
      const scope = card.provinces?.length ? `本卡限 ${card.provinces.join("、")}；` : "";
      return `<div class="card-target-note">${scope}對手在這些省份都沒有城市，或已有警政單位駐防</div>`;
    }
    // 省份清單跟著上面選到的勢力走，切換勢力時由 attachCardHandlers 重填。
    return `
      <label class="card-target">指定勢力<select data-card-target-owner="${card.id}" data-gang-riot="${card.id}">${entries
        .map(({ owner }) => `<option value="${owner}">${FACTIONS[owner]?.name || owner}</option>`).join("")}</select></label>
      <label class="card-target">指定省份<select data-card-target-province="${card.id}">${provinceOptionMarkup(entries[0].provinces)}</select></label>`;
  }
  if (card.mechanic === "railway_sabotage") {
    const downed = disabledRailways();
    const lines = (card.railways || []).filter((name) => !downed.has(name));
    if (!lines.length) return `<div class="card-target-note">所有可指定的鐵路都已在搶修中</div>`;
    return `<label class="card-target">指定鐵路<select data-card-target-railway="${card.id}">${lines.map((name) => `<option value="${name}">${name}</option>`).join("")}</select></label>`;
  }
  if (["communist_riot", "red_army_uprising"].includes(card.mechanic)) {
    const targets = riotTargets(card);
    if (!targets.length) return `<div class="card-target-note">目前沒有可癱瘓的對手：對方沒有城市</div>`;
    return `<label class="card-target">指定勢力<select data-card-target-owner="${card.id}">${targets.map((player) => `<option value="${player}">${FACTIONS[player]?.name || player}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "reserve_loss") {
    const targets = TURN_PLAYERS.filter((player) => player !== currentPlayer);
    return `<label class="card-target">指定勢力<select data-card-target-owner="${card.id}">${targets.map((player) => `<option value="${player}">${FACTIONS[player]?.name || player}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "assassination") {
    const targets = assassinationTargets();
    if (!targets.length) return `<div class="card-target-note">目前沒有可指定的敵方人物</div>`;
    // target_owner 由 use-function 從 generalOwners[目標] 推導，不必另外附欄位。
    return `<label class="card-target">指定人物<select data-card-target="${card.id}">${targets
      .map(({ general, owner, guarded }) => `<option value="${general.id}" data-owner="${owner}">${FACTIONS[owner]?.shortName || owner} · ${general.name}${guarded ? "（有親衛隊）" : ""}</option>`)
      .join("")}</select></label>`;
  }
  if (card.mechanic === "body_guard") {
    const targets = bodyGuardTargets();
    if (!targets.length) return `<div class="card-target-note">己方人物都已編成親衛隊</div>`;
    return `<label class="card-target">指定人物<select data-card-target="${card.id}">${targets
      .map((general) => `<option value="${general.id}">${general.name}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "piaohao_exchange") {
    const rate = card.factory_per_cash || 2;
    const player = state?.players?.[currentPlayer] || {};
    const factory = Number(player.factory_points || 0);
    const cash = Number(player.treasury || 0);
    return `
      <label class="card-target">兌換方向<select data-card-exchange-direction="${card.id}">
        <option value="factory_to_cash">賣工廠換錢（${rate} 工廠 → $1）</option>
        <option value="cash_to_factory">用錢買工廠（$1 → ${rate} 工廠）</option>
      </select></label>
      <label class="card-target">數量<input type="number" min="1" step="1" value="${rate}"
        data-card-exchange-amount="${card.id}"></label>
      <div class="card-target-note" data-card-exchange-hint="${card.id}">
        目前工業點 ${factory}、現金 $${cash}。賣工廠時填工業點（須為 ${rate} 的倍數），買工廠時填要花的金錢。
      </div>`;
  }
  if (card.mechanic === "artifact_smuggling") {
    const powers = card.powers || Object.keys(POWER_NAME);
    return `<label class="card-target">指定列強<select data-card-target-power="${card.id}">${powers
      .map((key) => `<option value="${key}">${POWER_NAME[key] || key}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "gang_riot_shield") {
    const provinces = ownedProvinceOptions();
    if (!provinces.length) return `<div class="card-target-note">你目前沒有控制任何城市</div>`;
    return `<label class="card-target">指定省份<select data-card-target-province="${card.id}">${provinces
      .map((province) => `<option value="${province}">${province}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "exile_recruit") {
    const targets = availableExiles();
    if (!targets.length) return `<div class="card-target-note">在野將領池已空，本卡改為半價補充步兵 ×2、機槍 ×1（不收工業點）</div>`;
    return `<label class="card-target">延攬人物<select data-card-target="${card.id}">${targets
      .map(({ general, price }) => `<option value="${general.id}">${general.name}（$${price}）</option>`)
      .join("")}</select></label>`;
  }
  if (card.mechanic === "intel_network") {
    const provinces = provinceOptions();
    return `<label class="card-target">指定省份<select data-card-target-province="${card.id}">${provinces.map((province) => `<option value="${province}">${province}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "city_development") {
    const cities = state.players[currentPlayer]?.city_economy || [];
    return `<label class="card-target">指定城市<select data-card-target-city="${card.id}" ${cities.length ? "" : "disabled"}>${cities.map((city) => `<option value="${city.id}">${city.name} · $${city.cash} 工${city.factory}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "multi_city_development") {
    const cities = state.players[currentPlayer]?.city_economy || [];
    const wanted = Number(card.city_count || 2);
    if (cities.length < wanted) {
      return `<div class="card-target-note">需要至少 ${wanted} 座己方城市才打得出來（目前 ${cities.length} 座）</div>`;
    }
    const options = (selectedIndex) => cities
      .map((city, index) => `<option value="${city.id}"${index === selectedIndex ? " selected" : ""}>${city.name} · $${city.cash} 工${city.factory}</option>`)
      .join("");
    return Array.from({ length: wanted }, (unused, index) =>
      `<label class="card-target">第 ${index + 1} 座城市<select data-card-target-cities="${card.id}">${options(index)}</select></label>`
    ).join("");
  }
  if (card.mechanic === "port_demolition") {
    const cities = enemyPortCityOptions();
    const wanted = Number(card.target_city_count || 2);
    if (cities.length < wanted) {
      return `<div class="card-target-note">可炸的敵方港口不足 ${wanted} 座（目前 ${cities.length} 座）</div>`;
    }
    const options = (selectedIndex) => cities
      .map((city, index) => `<option value="${city.id}"${index === selectedIndex ? " selected" : ""}>${FACTIONS[city.owner]?.shortName || city.owner} · ${city.name}（${city.port === "sea" ? "海港" : "河港"}）</option>`)
      .join("");
    return Array.from({ length: wanted }, (unused, index) =>
      `<label class="card-target">第 ${index + 1} 座港口<select data-card-target-cities="${card.id}">${options(index)}</select></label>`
    ).join("");
  }
  if (card.mechanic === "aerial_recon") {
    const provinces = provinceOptions();
    const wanted = Number(card.province_count || 3);
    return Array.from({ length: wanted }, (unused, index) =>
      `<label class="card-target">第 ${index + 1} 省<select data-card-target-provinces="${card.id}">${provinces
        .map((province, order) => `<option value="${province}"${order === index ? " selected" : ""}>${province}</option>`)
        .join("")}</select></label>`
    ).join("");
  }
  if (["mechanized_division", "field_hospital"].includes(card.mechanic)) {
    const targets = ownGeneralOptions();
    if (!targets.length) return `<div class="card-target-note">目前沒有可指定的己方將領</div>`;
    return `<label class="card-target">指定將領<select data-card-target="${card.id}">${targets
      .map((general) => `<option value="${general.id}">${general.name}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "affiliation_slot") {
    const targets = subordinateSlotTargets();
    if (!targets.length) return `<div class="card-target-note">目前沒有可再擴編的中將</div>`;
    return `<label class="card-target">指定中將<select data-card-target="${card.id}">${targets
      .map(({ general, slots }) => `<option value="${general.id}">${general.name}（${slots}/${LIEUTENANT_SLOT_CAP}）</option>`)
      .join("")}</select></label>`;
  }
  return loyaltyCardTargetMarkup(card);
}

async function boot() {
  [bootstrap, provinceGeoJson] = await Promise.all([
    api("/api/bootstrap"),
    fetch("/data/provinces_1926.geojson").then((response) => response.json()),
  ]);
  indexCards();
  indexScenarioCells();
  snapArmiesToStartCities();
  initializeNavies();
  indexProvinceCells();
  await loadAllGeneralTrees();
  initializeGeneralRuntime();
  synchronizeFieldArmies();

  // 只列陣營名，不再附上領袖姓名。
  $("playerSelect").innerHTML = bootstrap.players.map((p) => `<option value="${p.code}">${p.name}</option>`).join("");
  $("debugForceTurnBtn").hidden = !DEBUG_MODE;

  // Set current player from select
  currentPlayer = $("playerSelect").value;
  currentPhase = "military";

  const shared = await api("/api/shared-state");
  state = shared.engine_state;
  syncStrategicCitiesFromState();
  sharedEngineHash = JSON.stringify(state);
  sharedRevision = shared.revision;
  if (shared.tactical) {
    applyTacticalSnapshot(shared.tactical);
    sharedSnapshotHash = JSON.stringify(shared.tactical);
  }
  updateFeatureVisibility();

  // Load general tree data for selected faction
  await loadGeneralTreeForFaction(currentPlayer);

  $("playerSelect").addEventListener("change", (event) => switchFaction(event.target.value));

  setupPanels();
  setupPendingActions();
  setupUiTooltip();
  setupStatPopover();
  setupNewspaper();
  loadEventCards();
  renderNewspaper();
  updateTopBar();
  updatePhaseBanner();

  // Initialize map rendering
  initMap();
  setupMapZoom();
  renderPendingActions();
  sharedReady = true;
  if (!shared.tactical) await publishSharedState(true);
  window.setInterval(synchronizeSharedGame, 1200);
}

// ===== Map Initialization =====
function addPolygonPath(ctx, polygon) {
  polygon.forEach((point, index) => {
    const [x, y] = px(point[0], point[1]);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
}

function tracePolygon(ctx, polygon) {
  ctx.beginPath();
  addPolygonPath(ctx, polygon);
}

function traceChinaPath(ctx) {
  tracePolygon(ctx, CHINA_PROPER);
}

function tracePlayableRegion(ctx) {
  ctx.beginPath();
  addPolygonPath(ctx, CHINA_PROPER);
  addPolygonPath(ctx, HAINAN);
}

function traceGeoLine(ctx, points) {
  ctx.beginPath();
  points.forEach((point, index) => {
    const [x, y] = px(point[0], point[1]);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
}

function drawInfrastructure(ctx) {
  ctx.save();
  tracePlayableRegion(ctx);
  ctx.clip();

  // Administrative outlines use authoritative province polygons. They are
  // deliberately thin and long-dashed so they cannot be mistaken for rail.
  ctx.strokeStyle = 'rgba(71, 62, 49, 0.48)';
  ctx.lineWidth = 1.15;
  ctx.setLineDash([8, 6]);
  for (const feature of provinceGeoJson?.features || []) {
    for (const polygon of featurePolygons(feature)) {
      if (!polygon[0]) continue;
      traceGeoLine(ctx, polygon[0]);
      ctx.closePath();
      ctx.stroke();
    }
  }

  ctx.setLineDash([]);
  ctx.lineCap = 'round';
  // 列強經營的鐵路（南滿、中東、滇越）畫成紅白相間，和國有各線區分開。
  const traceRail = (railroad) => {
    const route = (railroad.cellKeys || []).map((key) => cells[key]).filter(Boolean);
    if (!route.length) return false;
    ctx.beginPath();
    route.forEach((cell, index) => {
      const x = hcx(cell.c);
      const y = hcy(cell.c, cell.r);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    return true;
  };
  const rails = bootstrap.strategic_map?.railroads || [];
  const domestic = rails.filter((line) => !line.foreign);
  const foreign = rails.filter((line) => line.foreign);
  for (const [group, base, dash] of [
    [domestic, 'rgba(31, 28, 23, 0.94)', 'rgba(238, 224, 190, 0.95)'],
    [foreign, 'rgba(176, 34, 34, 0.96)', 'rgba(252, 249, 244, 0.98)'],
  ]) {
    ctx.setLineDash([]);
    ctx.strokeStyle = base;
    ctx.lineWidth = 4.2;
    for (const railroad of group) if (traceRail(railroad)) ctx.stroke();
    ctx.setLineDash([2, 4]);
    ctx.strokeStyle = dash;
    ctx.lineWidth = 1.8;
    for (const railroad of group) if (traceRail(railroad)) ctx.stroke();
  }

  ctx.setLineDash([]);
  for (const cell of Object.values(cells).filter((item) => item.railBridge)) {
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    ctx.fillStyle = '#f2cf73';
    ctx.strokeStyle = '#2c261e';
    ctx.lineWidth = 1.4;
    ctx.fillRect(x - 5, y - 5, 10, 10);
    ctx.strokeRect(x - 5, y - 5, 10, 10);
  }
  ctx.restore();
}

function drawCities(ctx) {
  const cities = bootstrap.strategic_map?.cities || [];
  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = '700 9px Inter';
  for (const city of cities) {
    const cell = cells[city.cellKey];
    if (!cell) continue;
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    const points = hexPts(x, y);
    ctx.beginPath();
    points.forEach(([hx, hy], index) => index ? ctx.lineTo(hx, hy) : ctx.moveTo(hx, hy));
    ctx.closePath();
    const level = Math.max(1, Math.min(5, city.level || 1));
    // 被列強佔領的城市換成列強紅（同香港、旅順、海參崴那種不屬於任何勢力的樣子）。
    const occupied = occupationForCell(cell);
    const occupiedCity = occupied && occupied.kind === 'ground_occupation';
    ctx.fillStyle = occupiedCity
      ? OCCUPIED_CITY_FILL
      : `rgba(${66 - level * 5}, ${60 - level * 4}, ${48 - level * 3}, 0.9)`;
    ctx.fill();
    ctx.strokeStyle = occupiedCity
      ? FOREIGN_CITY_OUTLINE
      : (level >= 4 ? '#f0c65a' : '#f7f1df');
    ctx.lineWidth = occupiedCity ? 2.2 : 1.1 + level * 0.28;
    ctx.stroke();

    // Each level adds one building around the same central tower, keeping the
    // visual language continuous while making strategic city value scannable.
    const buildings = [
      { offset: 0, width: 4, height: 11 },
      { offset: -5, width: 4, height: 8 },
      { offset: 5, width: 4, height: 8 },
      { offset: -9, width: 3, height: 6 },
      { offset: 9, width: 3, height: 6 },
    ];
    ctx.fillStyle = '#fff9e8';
    ctx.fillRect(x - 11, y + 2, 22, 1.5);
    buildings.slice(0, level).forEach((building) => {
      ctx.fillRect(x + building.offset - building.width / 2, y + 2 - building.height, building.width, building.height);
    });
    if (level >= 4) {
      ctx.fillStyle = '#f0c65a';
      ctx.beginPath();
      ctx.moveTo(x, y - 12);
      ctx.lineTo(x + 5, y - 9.5);
      ctx.lineTo(x, y - 7.5);
      ctx.closePath();
      ctx.fill();
    }
    // 水波紋：所有河港都畫，不再只畫有鐵路橋的那幾座。
    // 鐵路橋另有黃色方塊標記，兩者互不取代。
    if (city.port === 'river' || city.port === 'sea' || cell.railBridge) {
      ctx.strokeStyle = '#79b8d2';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - 9, y + 7);
      ctx.quadraticCurveTo(x - 4, y + 2, x, y + 7);
      ctx.quadraticCurveTo(x + 4, y + 12, x + 9, y + 7);
      ctx.stroke();
    }
    // 鐵路橋標記畫在城市六邊形之上。鐵路那一層也畫過同樣的方塊，但城市會蓋掉，
    // 所以有城市的地格要在這裡補畫一次，位置挪到左上角避開城樓與等級標記。
    if (cell.railBridge) {
      ctx.fillStyle = '#f2cf73';
      ctx.strokeStyle = '#2c261e';
      ctx.lineWidth = 1.2;
      ctx.fillRect(x - 10, y - 12, 6, 6);
      ctx.strokeRect(x - 10, y - 12, 6, 6);
    }
    for (let marker = 0; marker < level; marker++) {
      ctx.fillStyle = level >= 4 ? '#f0c65a' : '#dcd3bf';
      ctx.fillRect(x - ((level - 1) * 2) + marker * 4 - 1, y + 5, 2, 2);
    }
    // 產出那一行：正常時報 $ 與 工；停產時直接說明原因，不要騙玩家還有收入。
    const status = cityPunishmentStatus(city.id);
    ctx.font = '700 8px Inter';
    if (status) {
      const mark = status.status === 'bombing' ? BOMBING_MARK : REBUILD_MARK;
      const text = status.status === 'rebuilding' && status.remaining_turns
        ? `${status.label} ${status.remaining_turns}`
        : status.label;
      // 轟炸中的城市標上施暴國的國旗（旭日旗），一眼看得出是誰在炸。
      const flagPower = status.status === 'bombing' ? status.power : null;
      const hasFlag = Boolean(flagPower && FLAG[flagPower]);
      const flagW = 10;
      const width = 30 + (hasFlag ? flagW + 3 : 0);
      ctx.fillStyle = 'rgba(20, 16, 14, 0.88)';
      ctx.fillRect(x - width / 2, y + 6, width, 11);
      ctx.strokeStyle = mark;
      ctx.lineWidth = 1;
      ctx.strokeRect(x - width / 2, y + 6, width, 11);
      ctx.fillStyle = mark;
      if (hasFlag) {
        drawPowerFlag(ctx, flagPower, x - width / 2 + 2 + flagW / 2, y + 11.5, flagW);
        ctx.fillText(text, x + (flagW + 3) / 2, y + 11.5);
      } else {
        ctx.fillText(text, x, y + 11.5);
      }
    } else if (occupiedCity) {
      ctx.fillStyle = '#f4c9c4';
      ctx.fillText('收入歸零', x, y + 11);
    } else {
      ctx.fillStyle = '#fff9e8';
      ctx.fillText(`$${city.cash} 工${city.factory}`, x, y + 11);
    }
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#f1ead8';
    ctx.font = '700 10px Inter';
    ctx.strokeText(city.name, x, y - s - 7);
    ctx.fillStyle = '#28231c';
    ctx.fillText(city.name, x, y - s - 7);
  }
  ctx.restore();
}

// 列強租借地上的城市。畫法與中國城市相同，但用列強紅、不標產出，
// 因為它們不屬於任何勢力的經濟，只是地圖上不可進入的一塊。
function drawForeignCities(ctx) {
  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const city of FOREIGN_CITIES) {
    const cell = cells[city.cellKey];
    if (!cell) continue;
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    ctx.beginPath();
    hexPts(x, y).forEach(([hx, hy], index) => index ? ctx.lineTo(hx, hy) : ctx.moveTo(hx, hy));
    ctx.closePath();
    ctx.fillStyle = 'rgba(74, 26, 24, 0.92)';
    ctx.fill();
    ctx.strokeStyle = FOREIGN_CITY_OUTLINE;
    ctx.lineWidth = 2.2;
    ctx.stroke();

    ctx.fillStyle = '#fff3ec';
    ctx.fillRect(x - 11, y + 2, 22, 1.5);
    [
      { offset: 0, width: 4, height: 11 },
      { offset: -5, width: 4, height: 8 },
      { offset: 5, width: 4, height: 8 },
      { offset: -9, width: 3, height: 6 },
      { offset: 9, width: 3, height: 6 },
    ].forEach((building) => {
      ctx.fillRect(x + building.offset - building.width / 2, y + 2 - building.height, building.width, building.height);
    });
    ctx.fillStyle = FOREIGN_CITY_OUTLINE;
    ctx.beginPath();
    ctx.moveTo(x, y - 12);
    ctx.lineTo(x + 5, y - 9.5);
    ctx.lineTo(x, y - 7.5);
    ctx.closePath();
    ctx.fill();
    for (let marker = 0; marker < city.level; marker++) {
      ctx.fillRect(x - ((city.level - 1) * 2) + marker * 4 - 1, y + 5, 2, 2);
    }

    ctx.lineWidth = 3;
    ctx.strokeStyle = '#f1ead8';
    ctx.font = '700 10px Inter';
    ctx.strokeText(city.name, x, y - s - 7);
    ctx.fillStyle = '#8c1f1c';
    ctx.fillText(city.name, x, y - s - 7);
  }
  ctx.restore();
}

function drawCompletedEngineering(ctx) {
  ctx.save();
  for (const key of completedPontoons) {
    const cell = cells[key];
    if (!cell) continue;
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    ctx.strokeStyle = '#f2cf73';
    ctx.lineWidth = 3;
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    ctx.moveTo(x - 10, y - 6);
    ctx.lineTo(x + 10, y + 6);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  for (const key of completedFortresses) {
    const cell = cells[key];
    if (!cell) continue;
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    ctx.strokeStyle = '#332b20';
    ctx.fillStyle = '#eee2c5';
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 9, y - 9, 18, 18);
    ctx.fillRect(x - 5, y - 5, 10, 10);
  }
  ctx.restore();
}

function drawOutsideMapAtmosphere(ctx) {
  ctx.save();
  ctx.fillStyle = SCAN_MARGIN_COLOR;         // 地圖上緣那條窄帶就靠這層
  ctx.fillRect(0, 0, MAPW, MAPH);
  // 最底層：列強瓜分中國圖，負責填掃描件蓋不到的右下楔形；
  // 上緣以上不畫，免得從地圖頂端露出來。
  if (underlayMapArt.complete && underlayMapArt.naturalWidth) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, SCAN_TOP_Y, MAPW, MAPH - SCAN_TOP_Y);
    ctx.clip();
    ctx.drawImage(underlayMapArt, 0, 0, MAPW, MAPH);
    ctx.restore();
  }
  // 上層：對位過的《中華民國全圖》，裁切在掃描件實際涵蓋的範圍內，邊緣不羽化。
  if (outsideMapArt.complete && outsideMapArt.naturalWidth) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(-MAPW, SCAN_TOP_Y);
    for (const [x, y] of SCAN_RIGHT_EDGE) ctx.lineTo(x, y);
    ctx.lineTo(-MAPW, SCAN_BOTTOM_Y);
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(outsideMapArt, 0, 0, MAPW, MAPH);
    ctx.restore();
  }
  ctx.restore();
}

function initMap() {
  const canvas = $('mapCanvas');
  const svgOverlay = document.getElementById('armyOverlay');

  if (!canvas || !svgOverlay) {
    console.error('Map elements not found');
    return;
  }

  const ctx = canvas.getContext('2d');

  // Render above CSS resolution so the map remains crisp while zooming.
  const renderScale = Math.min(3, Math.max(2, window.devicePixelRatio || 1));
  canvas.width = Math.round(MAPW * renderScale);
  canvas.height = Math.round(MAPH * renderScale);
  ctx.setTransform(renderScale, 0, 0, renderScale, 0, 0);
  svgOverlay.setAttribute('viewBox', `0 0 ${MAPW} ${MAPH}`);
  $("mapStage").style.aspectRatio = `${MAPW} / ${MAPH}`;

  drawOutsideMapAtmosphere(ctx);

  // Draw China proper (mainland)
  ctx.save();
  ctx.globalAlpha = PLAYABLE_LAYER_ALPHA;
  ctx.fillStyle = '#e7dcbe'; // Land color
  ctx.strokeStyle = '#7c6a44';
  ctx.lineWidth = 1.4;
  traceChinaPath(ctx);
  ctx.fill();
  ctx.stroke();
  tracePolygon(ctx, HAINAN);
  ctx.fill();
  ctx.stroke();

  // Draw hexagonal grid with faction coloring
  ctx.lineWidth = 0.5;
  const factionCentroids = {}; // Track centroids for faction labels
  const occupationCentroids = {}; // 佔領區的中心，用來插旗

  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const cell = cells[`${c},${r}`];
      if (!cell || (!cell.land && !cell.coastalWater)) continue;

      const X = hcx(c), Y = hcy(c, r);

      // Draw faction-colored hex fill
      if (cell.coastalWater) {
        // 近海：藍調壓淡摻灰之外再加一點黃，貼近底圖泛黃的海面，
        // 但仍留得住藍，讓可遊玩的水域與背景分得開。
        ctx.fillStyle = "rgba(152, 172, 164, 0.44)";
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const hx = X + s * Math.cos(a);
          const hy = Y + s * Math.sin(a);
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fill();
      } else if (cell.fac && FACTIONS[cell.fac]) {
        const facColor = FACTIONS[cell.fac].color;
        ctx.fillStyle = mixColor(facColor);
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const hx = X + s * Math.cos(a);
          const hy = Y + s * Math.sin(a);
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fill();

        // Accumulate centroid for faction labels
        if (!factionCentroids[cell.fac]) {
          factionCentroids[cell.fac] = { sumX: 0, sumY: 0, count: 0 };
        }
        factionCentroids[cell.fac].sumX += X;
        factionCentroids[cell.fac].sumY += Y;
        factionCentroids[cell.fac].count++;
      }

      // 列強懲戒佔領／封鎖：整片換成該列強的領土色，水域另加斜紋。
      const occupation = occupationForCell(cell);
      if (occupation) {
        // save/restore 一定要包住：格線的 lineWidth 是迴圈外設好的 0.5，
        // 這裡若把它改掉又不還原，之後每一格的格線都會變粗變深。
        ctx.save();
        const color = POWER_TERRITORY_COLORS[occupation.power] || '#b02222';
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const hx = X + s * Math.cos(a);
          const hy = Y + s * Math.sin(a);
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fillStyle = occupation.kind === 'water_blockade'
          ? withAlpha(color, 0.72) : withAlpha(color, 0.88);
        ctx.fill();
        // 封鎖水域再壓一層斜紋，跟陸地佔領區分得開。
        if (occupation.kind === 'water_blockade') {
          ctx.save();
          ctx.clip();
          ctx.strokeStyle = 'rgba(38, 26, 20, 0.75)';
          ctx.lineWidth = 1.6;
          for (let d = -s * 2; d < s * 2; d += 4) {
            ctx.beginPath();
            ctx.moveTo(X + d, Y - s);
            ctx.lineTo(X + d + s * 2, Y + s);
            ctx.stroke();
          }
          ctx.restore();
        }
        // 演習有期限、懲戒沒有——邊框用虛線與實線分開。
        ctx.strokeStyle = withAlpha(color, 1);
        ctx.lineWidth = 1.2;
        ctx.setLineDash(occupation.drill ? [4, 3] : []);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
        const bucket = occupationCentroids[occupation.id]
          || (occupationCentroids[occupation.id] = { sumX: 0, sumY: 0, count: 0, entry: occupation });
        bucket.sumX += X; bucket.sumY += Y; bucket.count++;
      }

      // 列強租界地：用與列強鐵路相同的紅色標示。
      if (cell.power) {
        ctx.fillStyle = FOREIGN_TERRITORY_FILL;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const hx = X + s * Math.cos(a);
          const hy = Y + s * Math.sin(a);
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fill();
      }

      // Highlight river hexes
      if (cell.river) {
        // 河道同樣調淡加灰泛黃，與近海保持同一個色系。
        ctx.fillStyle = '#b4c6bd';
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const hx = X + s * Math.cos(a);
          const hy = Y + s * Math.sin(a);
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fill();
      }

      // Draw hex outline
      ctx.strokeStyle = '#6b5c3880';
      ctx.lineWidth = 0.5;   // 明講，不靠迴圈外殘留的狀態
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 180 * (60 * i);
        const hx = X + s * Math.cos(a);
        const hy = Y + s * Math.sin(a);
        if (i === 0) ctx.moveTo(hx, hy);
        else ctx.lineTo(hx, hy);
      }
      ctx.closePath();
      ctx.stroke();
    }
  }
  ctx.restore();

  drawInfrastructure(ctx);

  // Draw faction name labels (HOI4 style)
  ctx.font = 'bold 18px Inter';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  Object.keys(factionCentroids).forEach(fac => {
    const faction = FACTIONS[fac];
    if (!faction) return;

    const centroid = factionCentroids[fac];
    const cx = centroid.sumX / centroid.count;
    const cy = centroid.sumY / centroid.count;

    // Draw text with stroke for visibility
    ctx.strokeStyle = '#f3ecdb';
    ctx.lineWidth = 4;
    ctx.strokeText(faction.shortName, cx, cy);

    ctx.fillStyle = faction.color;
    ctx.fillText(faction.shortName, cx, cy);
  });

  drawCities(ctx);
  drawForeignCities(ctx);
  // 佔領旗要壓在城市之上：城市畫在後面，先前旗子會被城市六角形蓋掉。
  drawOccupationBanners(ctx, occupationCentroids);
  drawCompletedEngineering(ctx);

  ctx.strokeStyle = '#7c6a44';
  ctx.lineWidth = 1.4;
  traceChinaPath(ctx);
  ctx.stroke();
  tracePolygon(ctx, HAINAN);
  ctx.stroke();

  // Draw army markers on SVG overlay
  renderArmyMarkers(currentPlayer);
  setupMapMovement();
}

// 佔領區中央插上該列強的旗幟，底下標明是懲戒還是演習。畫在城市之後，
// 且文字底下墊一塊深色牌子，否則壓到城市六角形上就讀不出來了。
function drawOccupationBanners(ctx, occupationCentroids) {
  Object.values(occupationCentroids || {}).forEach((bucket) => {
    const entry = bucket.entry;
    const cx = bucket.sumX / bucket.count;
    const cy = bucket.sumY / bucket.count;
    const color = POWER_TERRITORY_COLORS[entry.power] || '#b02222';
    const power = POWER_LABELS[entry.power] || entry.power;
    // 三種說法要分得開：演習有期限、封鎖是水域、佔領是土地易主。
    const label = entry.drill ? `${power}演習`
      : entry.kind === 'water_blockade' ? `${power}封鎖` : `${power}佔領`;

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '700 11px Inter';
    const width = ctx.measureText(label).width + 14;
    ctx.fillStyle = 'rgba(24, 20, 16, 0.82)';
    ctx.beginPath();
    ctx.roundRect(cx - width / 2, cy - 22, width, 40, 5);
    ctx.fill();
    ctx.strokeStyle = withAlpha(color, 0.95);
    ctx.lineWidth = 1.4;
    ctx.stroke();

    if (!drawPowerFlag(ctx, entry.power, cx, cy - 6, 26)) {
      ctx.font = '700 20px Inter';
      ctx.fillStyle = '#fdf7e6';
      ctx.fillText('⚑', cx, cy - 6);
    }

    // 字一律用米白：領土色有深有淺（蘇聯是深紅），拿它當字色壓在深色牌子上會看不見。
    ctx.font = '700 11px Inter';
    ctx.fillStyle = '#fdf7e6';
    ctx.fillText(label, cx, cy + 11);
    ctx.restore();
  });
}

// 被列強懲戒鎖住的部隊／艦隊在地圖上的樣子：紅虛線圈 ＋ 下方紅底標記 ＋ 國旗。
function appendPunishedBadge(group, x, y, entry, label, above = false) {
  const ns = 'http://www.w3.org/2000/svg';
  const ring = document.createElementNS(ns, 'circle');
  ring.setAttribute('cx', x);
  ring.setAttribute('cy', y);
  ring.setAttribute('r', 15);
  ring.setAttribute('fill', 'none');
  ring.setAttribute('stroke', BOMBING_MARK);
  ring.setAttribute('stroke-width', '2');
  ring.setAttribute('stroke-dasharray', '4 3');
  group.appendChild(ring);

  const flagUrl = powerFlagDataUrl(entry.power);
  const flagW = 12;
  const width = flagUrl ? 30 + flagW + 3 : 30;
  // 城市地格底下已經有「轟炸中／重建中」與收入標記，標記改掛在上方免得疊在一起。
  const top = above ? y - 30 : y + 15;
  const plate = document.createElementNS(ns, 'rect');
  plate.setAttribute('x', x - width / 2);
  plate.setAttribute('y', top);
  plate.setAttribute('width', width);
  plate.setAttribute('height', 13);
  plate.setAttribute('rx', '3');
  plate.setAttribute('fill', BOMBING_MARK);
  plate.setAttribute('stroke', '#2a1410');
  plate.setAttribute('stroke-width', '0.8');
  group.appendChild(plate);

  if (flagUrl) {
    const flagImage = document.createElementNS(ns, 'image');
    flagImage.setAttributeNS('http://www.w3.org/1999/xlink', 'href', flagUrl);
    flagImage.setAttribute('href', flagUrl);
    flagImage.setAttribute('x', x - width / 2 + 2);
    flagImage.setAttribute('y', top + 2.5);
    flagImage.setAttribute('width', flagW);
    flagImage.setAttribute('height', flagW * 2 / 3);
    group.appendChild(flagImage);
  }

  const tag = document.createElementNS(ns, 'text');
  tag.setAttribute('x', flagUrl ? x + (flagW + 3) / 2 : x);
  tag.setAttribute('y', top + 10);
  tag.setAttribute('text-anchor', 'middle');
  tag.setAttribute('font-size', '9');
  tag.setAttribute('font-weight', '800');
  tag.setAttribute('fill', '#fff8e8');
  tag.textContent = label;
  group.appendChild(tag);
}

function renderArmyMarkers(faction) {
  const svgOverlay = document.getElementById('armyOverlay');
  svgOverlay.innerHTML = ''; // Clear existing markers
  ensureHostileEncounters();

  const armies = Object.values(ARMY_POSITIONS).flatMap((factionArmies) =>
    factionArmies.map((army) => ({ army, armyFaction: factionForArmy(army) }))
  ).filter(({ army, armyFaction }) => !["jailed", "killed", "destroyed"].includes(army.status)
    && armyIsVisible(army, armyFaction, faction));
  const occupancy = new Map();

  armies.forEach(({ army, armyFaction }, idx) => {
    const cell = cells[army.cellKey] || cellAt(army.lon, army.lat, armyFaction);
    if (!cell) return;

    const occupants = occupancy.get(cell.key) || 0;
    occupancy.set(cell.key, occupants + 1);
    const X = hcx(cell.c) + (occupants ? 7 : 0), Y = hcy(cell.c, cell.r) + (occupants ? 5 : 0);
    const color = FACTIONS[armyFaction]?.color || '#666';

    // Create army marker group
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const markerClasses = ['army-marker'];
    if (armyFaction !== faction) markerClasses.push('enemy');
    if (armyIsResolvedThisTurn(army)) markerClasses.push('resolved');
    if (selectedArmyId === army.id) markerClasses.push('selected');
    g.setAttribute('class', markerClasses.join(' '));
    g.setAttribute('data-army-id', army.id);
    g.setAttribute('data-general', army.general);
    g.setAttribute('data-designator', army.designator);
    g.setAttribute('role', 'button');
    g.setAttribute('tabindex', '0');

    // Halo (for unmoved units)
    const halo = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    halo.setAttribute('class', 'army-halo');
    halo.setAttribute('cx', X);
    halo.setAttribute('cy', Y);
    halo.setAttribute('r', 13);
    halo.setAttribute('fill', color);
    halo.setAttribute('opacity', '0.3');
    if (armyFaction === faction && !armyIsResolvedThisTurn(army) && !activeBattleForArmy(army)) g.appendChild(halo);

    // Army circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', X);
    circle.setAttribute('cy', Y);
    circle.setAttribute('r', 10);
    circle.setAttribute('fill', color);
    circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', '2');
    g.appendChild(circle);

    // 番號 text (designator number)
    const numberMatch = army.designator.match(/第(.+)軍/);
    const number = numberMatch ? numberMatch[1] : (idx + 1);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', X);
    text.setAttribute('y', Y + 3);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '10');
    text.setAttribute('font-weight', 'bold');
    text.setAttribute('fill', '#fff');
    text.textContent = number;
    g.appendChild(text);

    // 佔領區內的部隊：紅色虛線圈 ＋ 下方「受困」標記與施暴國國旗。
    const lock = punishmentLockForArmy(army);
    if (lock) appendPunishedBadge(g, X, Y, lock, '受困', Boolean(cell.city));

    // Tooltip on hover
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = armyTooltipText(army, faction)
      + (lock ? `\n${punishmentLockLabel(lock)}：被鎖在原地，無法移動` : '');
    g.appendChild(title);

    const focusArmy = () => {
      const battle = activeBattleForArmy(army);
      if (battle) selectBattle(battle.id);
      else selectArmy(army.id);
    };
    g.addEventListener('click', focusArmy);
    g.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        focusArmy();
      }
    });

    svgOverlay.appendChild(g);
  });

  renderNavyMarkers(svgOverlay, faction);
  renderBattleMarkers(svgOverlay);
}

function navyTooltipText(navy) {
  normalizeNavyDivision(navy, navyRules());
  const active = activeGunBoats(navy, navyRules()).length;
  return `${navy.name}\n砲艇 ${active}/${navy.gunBoats.length} 可戰 · 運輸船 ${navy.cargoBoats} · HP ${Math.round(totalGunBoatHp(navy))}/${maxGunBoatHp(navy)} · 運輸 ${Math.round(totalCargoBoatHp(navy, navyRules()))}/${maxCargoBoatHp(navy, navyRules())}`;
}

function navyCellLabel(cell) {
  return cell?.city?.name || cell?.river || cell?.navalRouteName || "水域";
}

function navyMoveFactoryCost(navy) {
  const perGunBoat = Number(navyRules().move?.factory_cost_per_gun_boat || 5);
  normalizeNavyDivision(navy, navyRules());
  return Math.max(0, (navy?.gunBoats || []).length * perGunBoat);
}

function navyMoveCostText(navy) {
  const perGunBoat = Number(navyRules().move?.factory_cost_per_gun_boat || 5);
  const gunBoats = (navy?.gunBoats || []).length;
  return `每艘砲艇工業點 ${perGunBoat}；本艦隊 ${gunBoats} 艘砲艇，共工業點 ${navyMoveFactoryCost(navy)}`;
}

function renderNavyMarkers(svgOverlay, observer) {
  const occupancy = new Map();
  for (const navy of allNavies()) {
    normalizeNavyDivision(navy, navyRules());
    const faction = navyFaction(navy);
    const cell = cells[navy.cellKey];
    if (!cell) continue;
    if (!navyIsVisible(navy, observer)) continue;
    const occupants = occupancy.get(cell.key) || 0;
    occupancy.set(cell.key, occupants + 1);
    const x = hcx(cell.c) + occupants * 8;
    const y = hcy(cell.c, cell.r) + occupants * 5;
    const color = FACTIONS[faction]?.color || "#315f73";
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const classes = ["navy-marker"];
    if (faction !== observer) classes.push("enemy");
    if (navyIsResolvedThisTurn(navy)) classes.push("resolved");
    if (selectedNavyId === navy.id) classes.push("selected");
    g.setAttribute("class", classes.join(" "));
    g.setAttribute("data-navy-id", navy.id);
    g.setAttribute("role", "button");
    g.setAttribute("tabindex", "0");
    g.setAttribute("transform", `translate(${x}, ${y})`);

    const hull = document.createElementNS("http://www.w3.org/2000/svg", "path");
    hull.setAttribute("d", "M-14 -3 L10 -3 L15 2 L8 9 L-8 9 L-15 2 Z");
    hull.setAttribute("fill", color);
    hull.setAttribute("stroke", "#fff8e8");
    hull.setAttribute("stroke-width", "2");
    g.appendChild(hull);

    const cabin = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    cabin.setAttribute("x", "-6");
    cabin.setAttribute("y", "-9");
    cabin.setAttribute("width", "11");
    cabin.setAttribute("height", "6");
    cabin.setAttribute("rx", "1");
    cabin.setAttribute("fill", "#fff8e8");
    g.appendChild(cabin);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "0");
    label.setAttribute("y", "6");
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("font-size", "10");
    label.setAttribute("font-weight", "800");
    label.setAttribute("fill", "#1f2421");
    label.textContent = "艦";
    g.appendChild(label);

    // 封鎖水域／佔領區內的艦隊：與陸軍同一套標記，寫「封鎖」。
    const navyLock = punishmentLockForNavy(navy);
    if (navyLock) appendPunishedBadge(g, 0, 0, navyLock, '封鎖', Boolean(cell.city));

    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = navyTooltipText(navy)
      + (navyLock ? `\n${punishmentLockLabel(navyLock)}：被鎖在原地，無法移動` : "");
    g.appendChild(title);

    const focus = () => {
      selectNavy(navy.id);
    };
    g.addEventListener("click", focus);
    g.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focus();
      }
    });
    svgOverlay.appendChild(g);
  }
}

function currentArmies() {
  return allArmies().filter((army) => factionForArmy(army) === currentPlayer);
}

function allArmies(includeInactive = false) {
  const armies = Object.values(ARMY_POSITIONS).flat();
  return includeInactive
    ? armies
    : armies.filter((army) => !["jailed", "killed", "destroyed"].includes(army.status) && !army.embarkedOn);
}

function armyById(armyId) {
  return allArmies(true).find((army) => army.id === armyId) || null;
}

function allNavies(includeInactive = false) {
  for (const navy of navyDivisions) normalizeNavyDivision(navy, navyRules());
  return includeInactive
    ? navyDivisions
    : navyDivisions.filter((navy) =>
      navy.status !== "retreated" && ((navy.gunBoats || []).length || (navy.cargoBoatHp || []).length)
    );
}

function currentNavies() {
  return allNavies().filter((navy) => navyFaction(navy) === currentPlayer);
}

function navyById(navyId) {
  return allNavies(true).find((navy) => navy.id === navyId) || null;
}

function selectedNavy() {
  return selectedNavyId ? navyById(selectedNavyId) : null;
}

function navyRules() {
  return bootstrap?.navy_system || {};
}

function navyIsResolvedThisTurn(navy) {
  return Boolean(navy && (navy.resolvedTurn === state?.turn || resolvedNavyIds.has(navy.id)));
}

function markNavyResolved(navyOrId) {
  const navy = typeof navyOrId === "string" ? navyById(navyOrId) : navyOrId;
  if (!navy) return;
  navy.resolvedTurn = state?.turn ?? 0;
  resolvedNavyIds.add(navy.id);
}

function clearNavyResolved(navy) {
  if (!navy) return;
  delete navy.resolvedTurn;
  resolvedNavyIds.delete(navy.id);
}

function navyCanReceiveOrder(navy) {
  return Boolean(navy) && !navyIsResolvedThisTurn(navy) && !navyLockedInPort(navy);
}

function navyAtCell(cellKey, owner = null) {
  return allNavies().find((navy) =>
    navy.cellKey === cellKey && (!owner || navyFaction(navy) === owner)
  ) || null;
}

function enemyNavyAtCell(cellKey, faction = currentPlayer) {
  return allNavies().find((navy) => navy.cellKey === cellKey && navyFaction(navy) !== faction) || null;
}

function navyInContact(navy) {
  const faction = navyFaction(navy);
  const enemyNavy = enemyNavyAtCell(navy.cellKey, faction);
  return Boolean((enemyNavy && factionsAtWar(faction, navyFaction(enemyNavy)))
    || allArmies().some((army) =>
      army.cellKey === navy.cellKey
      && factionForArmy(army) !== faction
      && factionsAtWar(faction, factionForArmy(army))
    ));
}

function cellVector(fromCell, toCell) {
  if (!fromCell || !toCell) return { x: 0, y: 0 };
  return { x: hcx(toCell.c) - hcx(fromCell.c), y: hcy(toCell.c, toCell.r) - hcy(fromCell.c, fromCell.r) };
}

function waterRetreatPriority(cell) {
  if (cell.coastalWater || (cell.river && !cell.city)) return 0;
  if (cell.river || cell.city?.port) return 1;
  if (cell.railBridge) return 2;
  return 3;
}

function navyRetreatCell(navy, threatCell = null) {
  const source = cells[navy.cellKey];
  const faction = navyFaction(navy);
  const away = threatCell ? cellVector(threatCell, source) : null;
  const options = cellNeighbors(source).filter((cell) =>
    navyCanEnterCell(cell)
    && !enemyNavyAtCell(cell.key, faction)
    && !allArmies().some((army) => army.cellKey === cell.key && factionForArmy(army) !== faction)
  );
  options.sort((a, b) => {
    const water = waterRetreatPriority(a) - waterRetreatPriority(b);
    if (water) return water;
    if (!away) return 0;
    const va = cellVector(source, a);
    const vb = cellVector(source, b);
    const dotA = va.x * away.x + va.y * away.y;
    const dotB = vb.x * away.x + vb.y * away.y;
    return dotB - dotA;
  });
  return options[0] || null;
}

function navyContactEstimate(navy) {
  const faction = navyFaction(navy);
  const rules = navyRules();
  const ownMax = retreatBaselineGunBoatHp(navy, rules);
  const ownHp = totalGunBoatHp(navy);
  const retreatHp = ownMax * (1 - Number(rules?.land_interaction?.navy_retreat_gun_boat_hp_loss_ratio || 0.5));
  const enemyNavy = enemyNavyAtCell(navy.cellKey, faction);
  const enemyArmy = allArmies().find((army) =>
    army.cellKey === navy.cellKey && factionForArmy(army) !== faction && factionsAtWar(faction, factionForArmy(army))
  );
  let incoming = 0;
  const notes = [];
  if (enemyNavy && factionsAtWar(faction, navyFaction(enemyNavy))) {
    const damage = activeGunBoats(enemyNavy, rules).length * Number(rules?.units?.gun_boat?.attack?.gun_boat || 5);
    incoming += damage;
    notes.push(`${enemyNavy.name}砲艇火力 ${damage}`);
  }
  if (enemyArmy) {
    const damage = Math.max(0, Math.round(Number(armyUnits(enemyArmy).artillery || 0)))
      * Number(rules?.land_interaction?.artillery_attack_to_gun_boat || 1);
    incoming += damage;
    notes.push(`${armyCombatLabel(enemyArmy)}砲兵火力 ${damage}`);
  }
  if (ownMax <= 0) return "已無砲艇可戰";
  if (ownHp <= retreatHp) return "已達退卻線，可撤退";
  if (incoming <= 0) return "敵方目前無有效反艦火力";
  const ownRounds = Math.max(1, Math.ceil((ownHp - retreatHp) / incoming));
  const enemyEstimate = enemyNavy && factionsAtWar(faction, navyFaction(enemyNavy))
    ? (() => {
      const enemyMax = retreatBaselineGunBoatHp(enemyNavy, rules);
      const enemyHp = totalGunBoatHp(enemyNavy);
      const enemyFloor = enemyMax * (1 - Number(rules?.land_interaction?.navy_retreat_gun_boat_hp_loss_ratio || 0.5));
      const enemyIncoming = activeGunBoats(navy, rules).length * Number(rules?.units?.gun_boat?.attack?.gun_boat || 5);
      if (enemyMax <= 0) return "；敵方已無砲艇可戰";
      if (enemyHp <= enemyFloor) return "；敵方已達退卻線";
      if (enemyIncoming <= 0) return "";
      return `；敵方約 ${Math.max(1, Math.ceil((enemyHp - enemyFloor) / enemyIncoming))} 輪達退卻線`;
    })()
    : "";
  return `我方約 ${ownRounds} 輪達退卻線${enemyEstimate}（${notes.join("；")}）`;
}

function factionForArmy(army) {
  return army?.faction || army?.id?.split("-")[0] || null;
}

function factionsAtWar(firstFaction, secondFaction) {
  if (!state || !firstFaction || !secondFaction || firstFaction === secondFaction) return false;
  return state.players[firstFaction]?.warlord_relations?.[secondFaction]?.status === "war"
    || state.players[secondFaction]?.warlord_relations?.[firstFaction]?.status === "war";
}

function armiesShareBattle(firstArmy, secondArmy) {
  return activeBattles.some((battle) =>
    battleParticipantIds(battle).includes(firstArmy.id)
    && battleParticipantIds(battle).includes(secondArmy.id)
  );
}

function battleArmyIds(battle, side) {
  const leadId = side === "A" ? battle.attackerId : battle.defenderId;
  return [leadId, ...(battle.reinforcementIds?.[side] || [])];
}

function battleParticipantIds(battle) {
  return [...battleArmyIds(battle, "A"), ...battleArmyIds(battle, "B")];
}

function battleArmies(battle, side) {
  return battleArmyIds(battle, side).map(armyById).filter(Boolean);
}

function battleSideForFaction(battle, faction) {
  if (battle.attackerFaction === faction) return "A";
  if (battle.defenderFaction === faction) return "B";
  return null;
}

function battleSideForArmy(battle, army) {
  if (battleArmyIds(battle, "A").includes(army?.id)) return "A";
  if (battleArmyIds(battle, "B").includes(army?.id)) return "B";
  return null;
}

function activeBattleForArmy(army) {
  return activeBattles.find((battle) =>
    battleIsActive(battle)
    && battleParticipantIds(battle).includes(army?.id)
  ) || null;
}

function battleIsActive(battle) {
  return ["pending", "ongoing"].includes(battle?.status);
}

function archiveTerminalBattles() {
  const terminalBattles = activeBattles.filter((battle) => !battleIsActive(battle));
  for (const battle of terminalBattles) {
    if (!battleReports.some((report) => report.id === battle.id)) {
      battleReports.push(battle);
    }
    const index = activeBattles.findIndex((item) => item.id === battle.id);
    if (index >= 0) activeBattles.splice(index, 1);
  }
  return terminalBattles;
}

function armyIsResolvedThisTurn(army) {
  return Boolean(army && (army.resolvedTurn === state?.turn || resolvedArmyIds.has(army.id)));
}

function markArmyResolved(armyOrId) {
  const army = typeof armyOrId === "string" ? armyById(armyOrId) : armyOrId;
  if (!army) return;
  army.resolvedTurn = state?.turn ?? 0;
  resolvedArmyIds.add(army.id);
}

function clearArmyResolved(army) {
  if (!army) return;
  delete army.resolvedTurn;
  resolvedArmyIds.delete(army.id);
}

function armyCanReceiveOrder(army) {
  if (!army || army.status === "jailed") return false;
  return !armyIsResolvedThisTurn(army) && !activeBattleForArmy(army) && !army.specialOperation;
}

function absoluteTransferPair(firstArmy, secondArmy) {
  if (!firstArmy || !secondArmy || firstArmy.id === secondArmy.id) return false;
  if (factionForArmy(firstArmy) !== factionForArmy(secondArmy)) return false;
  if (firstArmy.status === "jailed" || secondArmy.status === "jailed") return false;
  if (activeBattleForArmy(firstArmy) || activeBattleForArmy(secondArmy)) return false;
  if (!cellWithinRange(firstArmy.cellKey, secondArmy.cellKey, 1)) return false;
  const firstGeneral = generalById(firstArmy.generalId);
  const secondGeneral = generalById(secondArmy.generalId);
  const roles = new Set([firstGeneral?.role, secondGeneral?.role]);
  const hasAbsolute = Boolean(generalAbsoluteLoyaltyActive(firstGeneral) || generalAbsoluteLoyaltyActive(secondGeneral));
  return hasAbsolute && roles.has("great_general") && roles.has("lieutenant_general");
}

function absoluteTransferPartners(army) {
  if (factionForArmy(army) !== currentPlayer) return [];
  return currentArmies().filter((other) => absoluteTransferPair(army, other));
}

function joinableBattleForArmy(army) {
  if (!army || army.status === "jailed" || armyIsResolvedThisTurn(army) || activeBattleForArmy(army)) return null;
  const faction = factionForArmy(army);
  return activeBattles.find((battle) => {
    if (!["pending", "ongoing"].includes(battle.status) || !battleSideForFaction(battle, faction)) return false;
    return cellNeighbors(cells[army.cellKey]).some((cell) => cell.key === battle.cellKey);
  }) || null;
}

function addUnitTotals(first, second) {
  return Object.fromEntries(Object.keys(UNIT_META).map((type) => [
    type,
    (first?.[type] || 0) + (second?.[type] || 0),
  ]));
}

function battleSideUnits(battle, side) {
  return battleArmies(battle, side).reduce((totals, army) => addUnitTotals(totals, armyUnits(army)), {});
}

function fallbackBattleOrigin(army, collisionCell) {
  const occupied = new Set(allArmies().filter((other) => other.id !== army.id).map((other) => other.cellKey));
  return cellNeighbors(collisionCell).find((cell) => cell.fac === factionForArmy(army) && !occupied.has(cell.key))?.key
    || cellNeighbors(collisionCell).find((cell) => !occupied.has(cell.key))?.key
    || collisionCell.key;
}

function startBattle(attacker, defender, collisionCell, attackerOrigin, action = null) {
  if (!attacker || !defender || !collisionCell || activeBattleForArmy(attacker) || activeBattleForArmy(defender)) return null;
  const attackerFaction = factionForArmy(attacker);
  const defenderFaction = factionForArmy(defender);
  if (!factionsAtWar(attackerFaction, defenderFaction)) return null;
  const battle = {
    id: Date.now() * 100 + activeBattles.length,
    cellKey: collisionCell.key,
    attackerId: attacker.id,
    defenderId: defender.id,
    attackerFaction,
    defenderFaction,
    attackerOrigin: attackerOrigin || fallbackBattleOrigin(attacker, collisionCell),
    originalFaction: collisionCell.fac,
    initial: { A: armyUnits(attacker), B: armyUnits(defender) },
    initialByArmy: {
      [attacker.id]: { ...armyUnits(attacker) },
      [defender.id]: { ...armyUnits(defender) },
    },
    reinforcementIds: { A: [], B: [] },
    tactics: { A: "normal_advance", B: "normal_advance" },
    confirmed: { A: false, B: false },
    tacticRevision: { A: true, B: true },
    rounds: 0,
    roundResolvedTurn: null,
    status: "pending",
  };
  applyNpcBattleDefaults(battle);
  if (action) {
    action.battleId = battle.id;
    action.defenderWasResolved = armyIsResolvedThisTurn(defender);
    action.defenderBefore = {
      id: defender.id,
      cellKey: defender.cellKey,
      lon: defender.lon,
      lat: defender.lat,
      units: { ...defender.units },
      reinforcements: { ...(state.players[defenderFaction]?.army_reinforcements?.[defender.id] || {}) },
      status: defender.status,
    };
  }
  activeBattles.push(battle);
  markArmyResolved(attacker);
  markArmyResolved(defender);
  selectedBattleId = battle.id;
  if (forcePoints(armyUnits(defender)) <= 5) surrenderArmy(defender, attackerFaction, battle, action);
  else if (forcePoints(armyUnits(attacker)) <= 5) surrenderArmy(attacker, defenderFaction, battle, action);
  return battle;
}

function ensureHostileEncounters() {
  if (!state) return;
  const occupantsByCell = new Map();
  for (const army of allArmies()) {
    const occupants = occupantsByCell.get(army.cellKey) || [];
    occupants.push(army);
    occupantsByCell.set(army.cellKey, occupants);
  }
  for (const [cellKey, occupants] of occupantsByCell) {
    for (let first = 0; first < occupants.length; first++) {
      for (let second = first + 1; second < occupants.length; second++) {
        let attacker = occupants[first];
        let defender = occupants[second];
        if (!factionsAtWar(factionForArmy(attacker), factionForArmy(defender)) || armiesShareBattle(attacker, defender)) continue;
        if (forcePoints(armyUnits(attacker)) <= 5 && forcePoints(armyUnits(defender)) > 5) {
          [attacker, defender] = [defender, attacker];
        }
        startBattle(attacker, defender, cells[cellKey], attacker.previousCellKey);
      }
    }
  }
}

function cellWithinRange(fromKey, toKey, range = 2) {
  if (fromKey === toKey) return true;
  let frontier = [cells[fromKey]];
  const visited = new Set([fromKey]);
  for (let step = 0; step < range; step++) {
    const next = [];
    for (const cell of frontier.filter(Boolean)) {
      for (const neighbor of cellNeighbors(cell)) {
        if (neighbor.key === toKey) return true;
        if (!visited.has(neighbor.key)) {
          visited.add(neighbor.key);
          next.push(neighbor);
        }
      }
    }
    frontier = next;
  }
  return false;
}

function armyIsVisible(army, armyFaction, observer) {
  if (armyFaction === observer) return true;
  const nearbyArmy = allArmies().some((ownArmy) =>
    factionForArmy(ownArmy) === observer && cellWithinRange(ownArmy.cellKey, army.cellKey, 2)
  );
  const nearbyNavy = allNavies().some((navy) =>
    navyFaction(navy) === observer && cellWithinRange(navy.cellKey, army.cellKey, 2)
  );
  if (nearbyArmy || nearbyNavy) return true;
  return armyRevealedByIntel(army, observer);
}

function navyIsVisible(navy, observer = currentPlayer) {
  const faction = navyFaction(navy);
  if (faction === observer) return true;
  const cell = cells[navy?.cellKey];
  if (!cell) return false;
  const nearbyArmy = allArmies().some((army) =>
    factionForArmy(army) === observer && cellWithinRange(army.cellKey, navy.cellKey, 2)
  );
  const nearbyNavy = allNavies().some((ownNavy) =>
    navyFaction(ownNavy) === observer && cellWithinRange(ownNavy.cellKey, navy.cellKey, 2)
  );
  if (nearbyArmy || nearbyNavy) return true;
  const province = cell.city?.province || strategicProvinceForCell(cell);
  const byAir = activeTimedEffects(observer, "aerial_recon")
    .some((effect) => (effect.target_provinces || []).includes(province));
  if (byAir) return true;
  if (factionHasPoliceProtection(faction)) return false;
  return activeTimedEffects(observer, "intel_network")
    .some((effect) => effect.target_province === province);
}

function selectedArmy() {
  return allArmies().find((army) => army.id === selectedArmyId) || null;
}

function armyUnits(army) {
  return Object.fromEntries(
    Object.keys(UNIT_META).map((type) => [type, Math.max(0, Math.round(Number(army?.units?.[type] || 0)))])
  );
}

function wholeUnits(units) {
  return Object.fromEntries(Object.keys(UNIT_META).map((type) => [
    type,
    Math.max(0, Math.round(Number(units?.[type] || 0))),
  ]));
}

// 急行軍改成逐軍購買的軍令：付錢後該支部隊 3 回合內每回合可走 2 格，
// 效果結束再冷卻 3 回合才能為同一支部隊再買一次。
const FORCED_MARCH = {
  cash: 10,
  factory: 10,
  durationTurns: 3,
  cooldownTurns: 3,
  tiles: 2,
};

function forcedMarchRules() {
  const feature = bootstrap?.features?.forced_march;
  if (!feature) return FORCED_MARCH;
  return {
    cash: Number(feature.cash ?? FORCED_MARCH.cash),
    factory: Number(feature.factory ?? FORCED_MARCH.factory),
    durationTurns: Number(feature.duration_turns ?? FORCED_MARCH.durationTurns),
    cooldownTurns: Number(feature.cooldown_turns ?? FORCED_MARCH.cooldownTurns),
    tiles: Number(feature.tiles ?? FORCED_MARCH.tiles),
  };
}

// 〈成立機械化步兵師〉買下來的將領，部隊永久維持急行軍，不必再付費也沒有冷卻。
// ── 進口盤尼西林：野戰醫院 ────────────────────────────────────────────
// 有配野戰醫院的將領，其部隊在作戰中損兵之後，下一回合可免費歸隊一個營，
// 兵種從這一戰真的損失過的兵種裡隨機挑。效果跟著將領本人走。
function hasFieldHospital(army) {
  if (!army?.generalId) return false;
  const faction = factionForArmy(army);
  if (fieldHospitalWindowActive(faction)) return true;   // 泳渡海峽的女子：全軍適用
  return (state?.players?.[faction]?.field_hospital_generals || []).includes(army.generalId);
}

function recordCombatLosses(army, unitsBefore) {
  if (!hasFieldHospital(army)) return;
  const after = armyUnits(army);
  const lost = Object.keys(UNIT_META).filter((type) =>
    Number(unitsBefore[type] || 0) > Number(after[type] || 0));
  if (!lost.length) return;
  // 只留最近一戰的損失清單，下一回合結算時用掉就清掉。
  army.fieldHospitalPending = { turn: Number(state?.turn || 0), units: lost };
}

function applyFieldHospitalRecovery() {
  const healed = [];
  const turn = Number(state?.turn || 0);
  for (const army of allArmies()) {
    const pending = army.fieldHospitalPending;
    if (!pending || !pending.units?.length) continue;
    if (turn <= Number(pending.turn || 0)) continue;   // 要等到「下一回合」
    if (!hasFieldHospital(army)) { delete army.fieldHospitalPending; continue; }
    const pick = pending.units[Math.floor(Math.random() * pending.units.length)];
    army.units[pick] = Number(army.units[pick] || 0) + 1;
    army.units = clampUnitsToForceCap(army.units);
    delete army.fieldHospitalPending;
    healed.push(`${army.designator}：${UNIT_META[pick]?.name || pick} +1 營`);
  }
  return healed;
}

function hasPermanentForcedMarch(army) {
  if (!army?.generalId) return false;
  const faction = factionForArmy(army);
  return (state?.players?.[faction]?.permanent_forced_march_generals || []).includes(army.generalId);
}

// 本回合這支部隊是不是還在急行軍效果內。
function forcedMarchActive(army, turn = Number(state?.turn || 0)) {
  if (!army) return false;
  if (hasPermanentForcedMarch(army)) return true;
  if (army.forcedMarchUntilTurn == null) return false;
  return turn <= Number(army.forcedMarchUntilTurn);
}

function forcedMarchRemainingTurns(army, turn = Number(state?.turn || 0)) {
  return Math.max(0, Number(army?.forcedMarchUntilTurn || 0) - turn + 1);
}

// 回傳「還要幾回合才能再買」；0 代表現在就能買。
function forcedMarchCooldownTurns(army, turn = Number(state?.turn || 0)) {
  if (forcedMarchActive(army, turn)) return 0;
  return Math.max(0, Number(army?.forcedMarchReadyTurn || 0) - turn);
}

function forceMeterMarkup(units, { compact = false } = {}) {
  const cap = armyForceCap();
  const force = Math.round(forcePoints(units));
  const ratio = Math.max(0, Math.min(1, force / cap));
  const level = ratio >= 1 ? "full" : ratio >= 0.85 ? "high" : "";
  return `
    <div class="force-meter ${compact ? "compact" : ""} ${level}">
      <div class="force-meter-label"><span>戰力</span><b>${force} / ${cap}</b></div>
      <div class="force-meter-track"><i style="width:${(ratio * 100).toFixed(1)}%"></i></div>
    </div>
  `;
}

// 再補一營這個兵種會不會爆表。
function reinforcementWouldExceedCap(units, unitType, count = 1) {
  const cap = armyForceCap();
  const points = bootstrap?.features?.unit_force_points || {
    infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4,
  };
  return forcePoints(units) + Number(points[unitType] || 0) * count > cap;
}

function armyForceCap() {
  return Number(bootstrap?.features?.army_force_cap || 100);
}

function forcePoints(units) {
  const points = bootstrap?.features?.unit_force_points || {
    infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4,
  };
  return Object.keys(UNIT_META).reduce((sum, type) =>
    sum + Math.max(0, Number(units?.[type] || 0)) * Number(points[type] || 0), 0);
}

function clampUnitsToForceCap(units, cap = armyForceCap()) {
  const points = bootstrap?.features?.unit_force_points || {
    infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4,
  };
  const normalized = wholeUnits(units);
  const trimOrder = Object.keys(UNIT_META)
    .sort((a, b) => Number(points[b] || 0) - Number(points[a] || 0));
  while (forcePoints(normalized) > cap) {
    const unit = trimOrder.find((type) => Number(normalized[type] || 0) > 0);
    if (!unit) break;
    normalized[unit] = Math.max(0, Number(normalized[unit] || 0) - 1);
  }
  return normalized;
}

function normalizeArmyForceCaps() {
  for (const army of allArmies(true)) {
    if (!army?.units || ["jailed", "killed", "destroyed"].includes(army.status)) continue;
    const before = forcePoints(armyUnits(army));
    if (before <= armyForceCap()) continue;
    army.units = clampUnitsToForceCap(armyUnits(army));
    const general = generalById(army.generalId);
    if (general) general.units = { ...army.units };
    const ledger = state?.players?.[factionForArmy(army)]?.army_reinforcements;
    if (ledger) delete ledger[army.id];
  }
}

function citiesInProvince(province) {
  return (bootstrap.strategic_map?.cities || []).filter((city) => city.province === province);
}

function queueProvinceClaimIfReady(province, faction) {
  if (!province || !state?.players?.[faction]) return;
  const cities = citiesInProvince(province);
  if (!cities.length || !cities.every((city) => city.faction === faction)) return;
  if (pendingProvinceClaims.some((claim) => claim.province === province && claim.faction === faction)) return;
  const provinceCells = Object.values(cells).filter((cell) => strategicProvinceForCell(cell) === province);
  if (!provinceCells.some((cell) => cell.fac !== faction)) return;
  pendingProvinceClaims.push({ province, faction, turn: state.turn });
}

function claimProvince(province, faction) {
  const blockedByForeignArmy = new Set(
    allArmies(true)
      .filter((army) => army.status !== "jailed" && factionForArmy(army) !== faction)
      .map((army) => army.cellKey)
  );
  let painted = 0;
  for (const cell of Object.values(cells)) {
    if (strategicProvinceForCell(cell) !== province || blockedByForeignArmy.has(cell.key)) continue;
    if (cell.fac !== faction) {
      cell.fac = faction;
      painted += 1;
    }
  }
  const index = pendingProvinceClaims.findIndex((claim) => claim.province === province && claim.faction === faction);
  if (index >= 0) pendingProvinceClaims.splice(index, 1);
  uiNotice = `${FACTIONS[faction]?.shortName || faction}宣布接管${province}，已改色 ${painted} 格；他軍駐紮格暫不變更。`;
  initMap();
  renderPendingActions();
  publishSharedState(true).catch((error) => showNotice(`省份歸屬同步失敗：${error.message}`));
}

function skipProvinceClaim(province, faction) {
  const index = pendingProvinceClaims.findIndex((claim) => claim.province === province && claim.faction === faction);
  if (index >= 0) pendingProvinceClaims.splice(index, 1);
  uiNotice = `本次暫不宣告${province}歸屬。`;
  renderPendingActions();
  publishSharedState(true).catch((error) => showNotice(`省份歸屬同步失敗：${error.message}`));
}

function occupyTile(cell, faction, record = null) {
  if (!cell || cell.fac === faction) return;
  const previousFaction = cell.fac;
  const previousCityFaction = cell.city?.faction || null;
  if (record) record.territoryChange = { key: cell.key, previousFaction, previousCityFaction };
  cell.fac = faction;
  if (cell.city && previousCityFaction !== faction) {
    transferCityEconomy(cell.city, previousCityFaction, faction);
    queueCityOwnershipSync(cell.city.id, faction);
  }
}

function transferCityEconomy(city, previousFaction, nextFaction) {
  if (!city || previousFaction === nextFaction) return;
  for (const payload of Object.values(state.players)) {
    payload.city_economy = (payload.city_economy || []).filter((item) => item.id !== city.id);
  }
  const nextProfile = state.players[nextFaction];
  if (nextProfile) {
    nextProfile.city_economy.push({
      id: city.id,
      name: city.name,
      province: city.province,
      cash: city.cash || 0,
      factory: city.factory || 0,
    });
  }
  city.faction = nextFaction;
  queueProvinceClaimIfReady(city.province, nextFaction);
  for (const payload of Object.values(state.players)) {
    const bonus = payload.permanent_output_bonus || {};
    payload.income = (payload.city_economy || []).reduce((sum, item) => sum + (item.cash || 0), 0) + Number(bonus.cash || 0);
    payload.factory_income = (payload.city_economy || []).reduce((sum, item) => sum + (item.factory || 0), 0) + Number(bonus.factory || 0);
  }
  updateTopBar();
}

function queueCityOwnershipSync(cityId, faction) {
  cityEconomySync = cityEconomySync
    .then(() => api("/api/capture-city", { city_id: cityId, faction }))
    .catch((error) => {
      console.error("City economy sync failed:", error);
      uiNotice = `城市經濟同步失敗：${error.message}`;
      renderPendingActions();
    });
  return cityEconomySync;
}

function renderBattleMarkers(svgOverlay) {
  const markers = activeBattles
    .filter((battle) => reportVisibleToPlayer(battle))
    .map((battle) => ({
      id: battle.id,
      status: battle.status,
      cellKey: battle.cellKey,
      label: "戰",
      title: battle.status === 'pending' ? '戰鬥待決' : '查看戰果',
    }));
  for (const report of navyBattleReports) {
    if (hiddenNavyBattleReportIds.has(report.id) || !reportVisibleToPlayer(report)) continue;
    const navy = navyById(report.navyId);
    const army = armyById(report.armyId);
    const cellKey = report.cellKey || navy?.cellKey || army?.cellKey;
    if (!cellKey) continue;
    markers.push({
      id: report.id,
      status: "resolved",
      cellKey,
      label: "戰",
      title: report.message || "查看海戰情報",
    });
  }
  for (const battle of markers) {
    const cell = cells[battle.cellKey];
    if (!cell) continue;
    const x = hcx(cell.c), y = hcy(cell.c, cell.r);
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', `battle-marker ${battle.status}`);
    group.setAttribute('role', 'button');
    group.setAttribute('tabindex', '0');
    group.setAttribute('transform', `translate(${x}, ${y - 22})`);
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', '11');
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('y', '4');
    label.textContent = battle.label;
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = battle.title;
    group.append(circle, label, title);
    const open = () => selectBattle(battle.id);
    group.addEventListener('click', open);
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') open();
    });
    svgOverlay.appendChild(group);
  }
}

function selectBattle(battleId) {
  const battle = [...activeBattles, ...battleReports].find((item) =>
    item.id === battleId && reportVisibleToPlayer(item)
  );
  const navyBattle = navyBattleReports.find((item) =>
    item.id === battleId && reportVisibleToPlayer(item)
  );
  if (!battle && !navyBattle) {
    selectedBattleId = null;
    renderBattlePanel();
    renderMapUnits();
    return;
  }
  selectedBattleId = battleId;
  const participant = (battle ? battleParticipantIds(battle) : [])
    .map(armyById)
    .find((army) => factionForArmy(army) === currentPlayer);
  selectedArmyId = participant?.id || null;
  moveMode = false;
  engineeringMode = null;
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function unitSummary(units) {
  return `<div class="unit-summary">${Object.entries(UNIT_META)
    .map(([type, meta]) => {
      const battalions = Math.max(0, Math.round(Number(units?.[type] || 0)));
      return `<span><b>${meta.short}${battalions}營</b><small>${formatUnitQuantity(type, battalions)}</small></span>`;
    })
    .join("")}</div>`;
}

function casualties(initial, remaining) {
  return Object.fromEntries(Object.keys(UNIT_META).map((type) => [
    type,
    Math.max(0, Math.round((initial[type] || 0) - (remaining[type] || 0))),
  ]));
}

function battleSideLabel(battle, side) {
  return battleArmies(battle, side).map(armyCombatLabel).join("、");
}

function estimatedRoundsUntilBreak(battle, side) {
  const currentSections = battle.result?.remaining?.[side]?.sections || {};
  const sectionStatuses = Object.values(currentSections);
  if (sectionStatuses.length && sectionStatuses.every((status) => status === "fleeing")) return 0;
  const latestEstimate = [...(battle.result?.log || [])]
    .reverse()
    .find((entry) => entry.round && entry.time_to_breakdown?.[side]);
  const aggregate = latestEstimate?.time_to_breakdown?.[side]?.aggregate || {};
  const resolverTurns = Object.values(aggregate).filter((value) => Number.isFinite(value) && value > 0);
  if (resolverTurns.length) return Math.max(1, Math.ceil(Math.min(...resolverTurns)));
  const opponentSide = side === "A" ? "B" : "A";
  const currentForce = forcePoints(battleSideUnits(battle, side));
  const initialForce = Math.max(currentForce, forcePoints(battle.initial[side]));
  const opponentForce = forcePoints(battleSideUnits(battle, opponentSide));
  const ownTactic = tacticData(battle.tactics[side]);
  const opponentTactic = tacticData(battle.tactics[opponentSide]);
  const casualtiesSoFar = Math.max(0, initialForce - currentForce);
  const damageUntilBreak = Math.max(
    0.1,
    initialForce * Number(ownTactic.threshold) - casualtiesSoFar,
  );
  const incomingPerRound = opponentForce
    * Number(opponentTactic.attack_multiplier)
    * Number(ownTactic.harm_taken_multiplier)
    * COMBAT_ESTIMATE_CALIBRATION;
  if (incomingPerRound <= 0) return Infinity;
  return Math.max(1, Math.ceil(damageUntilBreak / incomingPerRound));
}

function retreatEstimate(battle, sideOrder = ["A", "B"]) {
  const turnsA = estimatedRoundsUntilBreak(battle, "A");
  const turnsB = estimatedRoundsUntilBreak(battle, "B");
  if (!Number.isFinite(turnsA) && !Number.isFinite(turnsB)) return "目前火力不足，無法估計退卻時間";
  const turns = { A: turnsA, B: turnsB };
  const estimate = (side, turns) => `${battleSideLabel(battle, side)} ${turns === 0 ? "已達退卻線" : Number.isFinite(turns) ? `約 ${turns} 輪` : "暫無退卻壓力"}`;
  return sideOrder.map((side) => estimate(side, turns[side])).join("；");
}

function battleFactionForSide(battle, side) {
  return side === "A" ? battle.attackerFaction : battle.defenderFaction;
}

function retreatConfirmationKey(battle, side) {
  return `${battle.id}:${side}`;
}

function retreatIsArmed(battle, side) {
  return (retreatConfirmations.get(retreatConfirmationKey(battle, side)) || 0) > Date.now();
}

function retreatButtonMarkup(battle, side) {
  const armed = retreatIsArmed(battle, side);
  return `<button class="${armed ? "retreat-confirm-armed" : ""}" data-retreat-battle="${battle.id}">${armed ? "再次確認撤退" : "撤退"}</button>`;
}

function pursuitReportMarkup(result) {
  const pursuit = result?.log?.find((entry) => entry.phase === "pursuit");
  if (!pursuit) return "";
  if (!pursuit.eligible) {
    return `<div class="battle-pursuit">追擊：${pursuit.reason || "未造成追擊傷害"}</div>`;
  }
  const damageByUnit = {};
  for (const target of pursuit.damage_by_target || []) {
    damageByUnit[target.unit] = (damageByUnit[target.unit] || 0) + Number(target.applied_damage || 0);
  }
  const damageText = Object.entries(damageByUnit)
    .filter(([, damage]) => damage > 0)
    .map(([unit, damage]) => `${UNIT_META[unit]?.name || unit} ${damage.toFixed(1)} HP`)
    .join("、") || "未造成傷害";
  return `<div class="battle-pursuit">追擊：勝方騎兵 ${pursuit.cavalry} 營，自由攻擊造成 ${damageText}；各兵種最多損失剩餘 HP 的 50%。</div>`;
}

function reportVisibleToPlayer(report, player = currentPlayer) {
  return report?.attackerFaction === player
    || report?.defenderFaction === player
    || report?.faction === player
    || report?.targetFaction === player;
}

function visibleCombatReports() {
  const landReports = [...activeBattles, ...battleReports]
    .filter((item) => !["pending", "ongoing"].includes(item.status))
    .filter((item) => !hiddenBattleReportIds.has(item.id) && reportVisibleToPlayer(item))
    .map((item) => ({ id: item.id, kind: "land", label: "戰", title: battleSideLabel(item, "A") + " vs " + battleSideLabel(item, "B") }));
  const seaReports = navyBattleReports
    .filter((item) => !hiddenNavyBattleReportIds.has(item.id) && reportVisibleToPlayer(item))
    .map((item) => ({ id: item.id, kind: "navy", label: "戰", title: item.message || "海戰情報" }));
  return [...landReports, ...seaReports].sort((a, b) => b.id - a.id).slice(0, 8);
}

function renderNavyBattlePanel(root, report) {
  const actor = report.kind === "army_navy" ? armyById(report.armyId) : navyById(report.navyId);
  const target = report.kind === "army_navy" ? navyById(report.navyId) : navyById(report.targetNavyId);
  root.hidden = false;
  $("battleReportDock").hidden = false;
  root.dataset.battleId = String(report.id);
  root.classList.remove("collapsed");
  const actorName = actor?.name || (actor ? armyCombatLabel(actor) : null) || FACTIONS[report.faction]?.name || "我方";
  const targetName = target?.name || (target ? armyCombatLabel(target) : null) || FACTIONS[report.targetFaction]?.name || "敵方";
  const details = report.kind === "navy_duel"
    ? `<span>${actorName} 對敵造成 ${Math.round(report.result?.attackerDamage || 0)} HP</span>
       <span>${targetName} 反擊造成 ${Math.round(report.result?.defenderDamage || 0)} HP</span>
       <span>${report.result?.attackerRetreat ? actorName + "撤離" : actorName + "留在戰區"}；${report.result?.defenderRetreat ? targetName + "撤離" : targetName + "留在戰區"}</span>`
    : `<span>陸軍砲兵：${report.result?.artilleryBefore || 0} → ${report.result?.artilleryAfter || 0} 營</span>
       <span>砲艇受損：${Math.round(report.result?.boatDamage || 0)} HP</span>
       <span>${report.result?.landRetreat ? "陸軍已無砲兵，退出接觸" : "陸軍仍有砲兵，留在戰區"}；${report.result?.navyRetreat ? "艦隊退卻" : "艦隊未退"}</span>`;
  const navy = navyById(report.navyId);
  const targetNavy = navyById(report.targetNavyId);
  const retreatNavy = [navy, targetNavy]
    .find((item) => item && navyFaction(item) === currentPlayer && navyInContact(item));
  root.innerHTML = `
    <div class="battle-heading"><b>海戰情報</b><span>${FACTIONS[report.faction]?.shortName || report.faction} vs ${FACTIONS[report.targetFaction]?.shortName || report.targetFaction}</span><button class="battle-collapse" data-dismiss-navy-report="${report.id}" title="移除此情報">×</button></div>
    <div class="battle-intelligence navy-battle-info">
      <span>${report.message || ""}</span>
      ${details}
    </div>
    ${navy ? `<div class="battle-sides"><div><b>${navy.name}</b>${navyHealthMarkup(navy)}</div>${targetNavy ? `<div><b>${targetNavy.name}</b>${navyHealthMarkup(targetNavy)}</div>` : ""}</div>` : ""}
    ${retreatNavy ? `<div class="battle-actions"><button data-navy-report-retreat="${retreatNavy.id}">撤退${retreatNavy.name}</button></div>` : ""}
    <div class="battle-result"><small>右鍵移除此情報</small></div>
  `;
}

function renderBattlePanel() {
  const root = $("battlePanel");
  const reports = [...activeBattles, ...battleReports]
    .filter((item) => !hiddenBattleReportIds.has(item.id))
    .filter((item) => reportVisibleToPlayer(item));
  const battle = reports.find((item) => item.id === selectedBattleId)
    || [...reports].reverse().find((item) =>
      item.attackerFaction === currentPlayer || item.defenderFaction === currentPlayer
    );
  const navyReport = navyBattleReports.find((item) =>
    item.id === selectedBattleId && !hiddenNavyBattleReportIds.has(item.id) && reportVisibleToPlayer(item)
  ) || (!battle ? [...navyBattleReports].reverse().find((item) =>
    !hiddenNavyBattleReportIds.has(item.id) && reportVisibleToPlayer(item)
  ) : null);
  if (navyReport && (!battle || selectedBattleId === navyReport.id)) {
    selectedBattleId = navyReport.id;
    renderNavyBattlePanel(root, navyReport);
    return;
  }
  if (!battle) {
    root.hidden = true;
    $("battleReportDock").hidden = true;
    root.innerHTML = "";
    delete root.dataset.battleId;
    return;
  }
  selectedBattleId = battle.id;
  $("battleReportDock").hidden = false;
  root.dataset.battleId = String(battle.id);
  const currentSide = battle.attackerFaction === currentPlayer ? "A"
    : battle.defenderFaction === currentPlayer ? "B" : null;
  const sideOrder = currentSide ? [currentSide, currentSide === "A" ? "B" : "A"] : ["A", "B"];
  const remaining = { A: battleSideUnits(battle, "A"), B: battleSideUnits(battle, "B") };
  const losses = {
    A: casualties(battle.initial.A, remaining.A),
    B: casualties(battle.initial.B, remaining.B),
  };
  root.hidden = false;
  root.classList.toggle("collapsed", collapsedBattleIds.has(battle.id));
  const active = battle.status === "pending" || battle.status === "ongoing";
  const openingRound = active && (battle.rounds || 0) === 0;
  const tacticLocked = !currentSide || !battle.tacticRevision?.[currentSide] || battle.confirmed?.[currentSide];
  root.innerHTML = `
    <div class="battle-heading"><b>${active ? `交戰中 · 第 ${(battle.rounds || 0) + 1} 輪` : "戰果"}</b><span>${sideOrder.map((side) => FACTIONS[battleFactionForSide(battle, side)].shortName).join(" vs ")}${completedFortresses.has(battle.cellKey) ? " · 要塞守備" : ""}</span><button class="battle-collapse" data-toggle-battle="${battle.id}" title="${collapsedBattleIds.has(battle.id) ? "展開戰鬥情報" : "收起戰鬥情報"}">${collapsedBattleIds.has(battle.id) ? "+" : "−"}</button></div>
    <div class="battle-sides">
      ${sideOrder.map((side) => `<div><b>${battleSideLabel(battle, side)}</b>${unitSummary(remaining[side])}<div class="battle-loss"><em>損失</em>${unitSummary(losses[side])}</div></div>`).join("")}
    </div>
    <div class="battle-intelligence">
      ${sideOrder.map((side) => `<span>${battleSideLabel(battle, side)}：${tacticOptionLabel(battle.tactics[side])}</span>`).join("")}
      ${active ? `<strong>預估：${retreatEstimate(battle, sideOrder)}</strong>` : ""}
    </div>
    ${pursuitReportMarkup(battle.result)}
    ${active && currentSide ? `
      <label class="battle-tactic">戰術
        <select data-battle-tactic="${currentSide}" ${tacticLocked ? "disabled" : ""}>${tacticOptionsMarkup(battle.tactics[currentSide], currentSide)}</select>
      </label>
      <div class="battle-actions">
        ${battle.tacticRevision?.[currentSide] ? `<button data-resolve-battle="${battle.id}" ${tacticLocked ? "disabled" : ""}>${battle.confirmed?.[currentSide] ? "戰術已確認" : "確認戰術"}</button>` : ""}
        ${retreatButtonMarkup(battle, currentSide)}
      </div>
      <small class="battle-confirmation">${openingRound ? `${battle.confirmed?.A ? "進攻方已定策" : "等待進攻方"} · ${battle.confirmed?.B ? "防守方已定策" : "等待防守方"}` : battle.tacticRevision?.[currentSide] ? "援軍抵達，可重新定策一次" : battle.roundResolvedTurn === state.turn ? "本回合戰鬥已結算" : "沿用既定戰術；回合結束時自動交戰"}</small>` : `<div class="battle-result">${battle.status === "surrendered" ? `${battleSideLabel(battle, battle.surrenderedSide)}${battle.annihilatedSide ? "遭殲滅" : "投降並被俘"}` : battle.result ? `勝方：${battle.result.winner === "A" ? battleSideLabel(battle, "A") : battle.result.winner === "B" ? battleSideLabel(battle, "B") : "雙方退卻"} · ${battle.result.rounds} 回合` : "部隊已撤出戰場"}<small>右鍵移除此情報</small></div>`}
  `;
}

function cityForArmy(army) {
  if (!army) return null;
  return (bootstrap.strategic_map?.cities || []).find((city) => city.cellKey === army.cellKey) || null;
}

function cityControlledBy(city, faction) {
  if (!city || !faction) return false;
  return (state?.city_owners?.[city.id] || city.faction) === faction;
}

function selectTile(cell) {
  selectedTileKey = cell?.key || null;
  renderTileInfo();
}

// 列強租借地：不屬於任何省分，只標等級；也沒有中國勢力的產出可言。
// 地格資訊上的鐵路狀態：搶修中、或列強線關係不到都要標出來，
// 否則玩家會以為點得動卻走不了三格。
function railwayStatusLabel(name) {
  if (disabledRailways().has(name)) return `${name}（搶修中）`;
  const power = FOREIGN_RAILWAY_POWERS[name];
  if (power && foreignRailwayRelation(name) < FOREIGN_RAILWAY_RELATION_MIN) {
    return `${name}（對${POWER_NAME[power] || power}關係未達 ${FOREIGN_RAILWAY_RELATION_MIN}，僅可通行）`;
  }
  return name;
}

function foreignTileInfoMarkup(cell) {
  const city = cell.foreignCity;
  const powerName = POWER_NAME[city.power] || city.power;
  const railroads = [...(cell.railroads || [])];
  const railText = railroads.length
    ? railroads.map(railwayStatusLabel).join("、")
    : "無";
  return `
    <div class="tile-info-heading">
      <b>${city.name}</b>
      <span class="tile-owner">${flagMarkup(city.power, "flag-chip tile-owner-flag")}${powerName}</span>
    </div>
    <div class="tile-info-grid">
      <span>地形<strong>陸地</strong></span>
      <span>聚落<strong>${city.level} 級城市</strong></span>
      <span>歸屬<strong>${powerName}</strong></span>
      <span>鐵路<strong>${railText}</strong></span>
    </div>
    <div class="tile-concession">
      <span class="tile-tag tile-tag-foreign">列強屬地</span>
      <span class="tile-foreign-note">中國各勢力不得進入或通過</span>
    </div>`;
}

function renderTileInfo() {
  const root = $("tileInfo");
  const cell = cells[selectedTileKey];
  if (!cell) {
    root.hidden = true;
    $("tileInfoDock").hidden = true;
    root.innerHTML = "";
    return;
  }
  $("tileInfoDock").hidden = false;
  if (cell.foreignCity) {
    root.hidden = false;
    root.innerHTML = foreignTileInfoMarkup(cell);
    return;
  }
  const city = cell.city;
  const fortifications = [];
  if (completedFortresses.has(cell.key)) fortifications.push("要塞");
  if (completedPontoons.has(cell.key)) fortifications.push("浮橋");
  if (cell.railBridge) fortifications.push("鐵路橋");
  const railroads = [...(cell.railroads || [])];
  // 租界僅標明身分與租界國，不寫加成數字。港口同樣只標身分。
  const concessionPowers = Array.isArray(city?.concession) ? city.concession : [];
  const tags = [];
  if (city?.port === "river") tags.push('<span class="tile-tag tile-tag-port">河港</span>');
  if (city?.port === "sea") tags.push('<span class="tile-tag tile-tag-port">海港</span>');
  if (portParalysed(city)) tags.push('<span class="tile-tag tile-tag-port">港務搶修中</span>');
  if (concessionPowers.length) {
    tags.push(`<span class="tile-tag tile-tag-concession">租界</span>` + concessionPowers.map((key) => `
      <span class="tile-concession-power">${flagMarkup(key, "flag-chip concession-flag")}${POWER_NAME[key] || key}</span>
    `).join(""));
  }
  const concessionRow = tags.length ? `<div class="tile-concession">${tags.join("")}</div>` : "";
  const naviesHere = allNavies().filter((navy) => navy.cellKey === cell.key);
  const navyRow = naviesHere.length
    ? `<div class="tile-concession">${naviesHere.map((navy) => `<span class="tile-tag tile-tag-port">${FACTIONS[navyFaction(navy)]?.shortName || navyFaction(navy)} · ${navy.name}</span>`).join("")}</div>`
    : "";
  const railText = railroads.length
    ? railroads.map(railwayStatusLabel).join("、")
    : "無";
  root.hidden = false;
  root.innerHTML = `
    <div class="tile-info-heading">
      <b>${city?.name || "鄉野地格"}</b>
      <span class="tile-owner">${factionFlagMarkup(cell.fac, "flag-chip tile-owner-flag")}${FACTIONS[cell.fac]?.shortName || "無控制"}</span>
    </div>
    <div class="tile-info-grid">
      <span>地形<strong>${cell.river ? `水域 · ${cell.river}` : "陸地"}</strong></span>
      <span>聚落<strong>${city ? `${city.province} · ${city.level} 級城市` : `${strategicProvinceForCell(cell) || "未知省份"} · 鄉村`}</strong></span>
      <span>歸屬<strong>${FACTIONS[cell.fac]?.name || "無控制"}</strong></span>
      <span>工事<strong>${fortifications.join("、") || "無"}</strong></span>
      <span>鐵路<strong>${railText}</strong></span>
      <span>產出<strong>$${city?.cash || 0} · 工廠 ${city?.factory || 0}</strong></span>
    </div>
    ${concessionRow}
    ${navyRow}`;
}

function engineeringOperationsFor(army) {
  const general = generalById(army.generalId);
  const skills = new Set(general?.skills || []);
  for (const [skill, traits] of Object.entries(ENGINEERING_TRAIT_SKILLS)) {
    if ((general?.traits || []).some((trait) => traits.has(trait))) skills.add(skill);
  }
  return [...skills].filter((skill) => ENGINEERING_OPERATIONS[skill]);
}

function payEngineeringCost(operation, action) {
  const cost = Number(operation?.factoryCost || 0);
  const payload = state.players[currentPlayer];
  if (!payload) throw new Error("找不到玩家工業點資料。");
  if (Number(payload.factory_points || 0) < cost) {
    throw new Error(`${operation.label}需要工業點 ${cost}（目前 ${Number(payload.factory_points || 0)}）。`);
  }
  payload.factory_points = Number(payload.factory_points || 0) - cost;
  if (action) action.factoryCost = cost;
  updateTopBar();
}

function startEngineeringOperation(army, engineering, targetCellKey) {
  const operation = ENGINEERING_OPERATIONS[engineering];
  const action = beginArmyOrder(army, "engineering");
  try {
    payEngineeringCost(operation, action);
  } catch (error) {
    const index = armyOrderHistory.indexOf(action);
    if (index >= 0) armyOrderHistory.splice(index, 1);
    throw error;
  }
  army.specialOperation = {
    id: engineering,
    label: operation.label,
    turnsRemaining: operation.turns,
    targetCellKey,
  };
  action.engineering = engineering;
  return action;
}

function renderArmyDetail() {
  const root = $("armyDetail");
  const navy = selectedNavy();
  if (navy) {
    renderNavyDetail(root, navy);
    return;
  }
  const army = selectedArmy();
  if (!army) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }

  const general = generalById(army.generalId);
  const armyFaction = factionForArmy(army);
  const isOwnArmy = armyFaction === currentPlayer;
  const traits = general?.traits || [];
  const portrait = PORTRAIT_BY_ID[army.generalId];
  const units = armyUnits(army);
  const showComposition = armyCompositionVisible(army);
  const city = cityForArmy(army);
  const fightingBattle = activeBattleForArmy(army);
  const resolvedThisTurn = armyIsResolvedThisTurn(army);
  const canOrder = isOwnArmy && armyCanReceiveOrder(army);
  const canReinforce = canOrder && cityControlledBy(city, currentPlayer) && city.level >= 3 && cells[army.cellKey]?.fac === currentPlayer;
  const profile = state.players[currentPlayer];
  const engineering = isOwnArmy ? engineeringOperationsFor(army) : [];
  const joinableBattle = isOwnArmy ? joinableBattleForArmy(army) : null;
  const loyalty = general ? calculateGeneralLoyalty(general, army).value : null;
  const defectionForce = forcePoints(units);
  const loyaltyForDefection = Math.max(1, loyalty || 1);
  const defectionCost = Math.ceil((10 + defectionForce * 3 + loyaltyForDefection * 2) * 0.5);
  const defectionBaseChance = 0.45 - loyaltyForDefection * 0.04 - defectionForce * 0.003;
  const defectionChance = Math.round(
    Math.max(0.03, Math.min(0.60, defectionBaseChance * 1.25) - defectionResistance(general)) * 100,
  );
  const lieutenants = availableLieutenantGenerals(currentPlayer);
  const branchSize = transferBranchSize(generalTrees[armyFaction], army.generalId);
  const canDefect = loyalty !== null && !general?.loyalty_exempt && !generalAbsoluteLoyaltyActive(general) && lieutenants.length
    && availableMajorGeneralSlots(currentPlayer) >= branchSize
    && (showComposition ? profile.treasury >= defectionCost : profile.treasury >= 10);

  root.hidden = false;
  root.innerHTML = `
    <div class="army-profile">
      ${portrait
        ? `<img src="${portrait}" alt="${army.general}">`
        : `<div class="army-profile-placeholder">${army.general.charAt(0)}</div>`}
      <div><b>${army.general}</b><span>${army.designator}</span></div>
      ${city ? `<small>${city.name} · ${city.province}</small>` : `<small>野外駐軍</small>`}
    </div>
    <div class="trait-list">${traits.length
      ? traits.map((trait) => traitChip(trait, army.generalId)).join("")
      : '<span>無已知特質</span>'}</div>
    ${showComposition ? `
      <div class="army-composition">
        ${Object.keys(UNIT_META).map((type) => `
          <div>${unitSymbol(type, units[type])}<span>${UNIT_META[type].name}<small>${formatUnitQuantity(type, units[type])}</small></span></div>
        `).join("")}
      </div>
      ${forceMeterMarkup(units)}
    ` : `<div class="enemy-hidden-composition"><b>兵力不明</b><span>敵軍編制需交戰或情報網揭露。</span></div>`}
    ${isOwnArmy ? absoluteTransferMarkup(army) : ""}
    ${!isOwnArmy ? `<div class="enemy-intelligence"><b>敵軍情報</b><span>忠誠 ${loyalty ?? "核心將領"}${loyalty === null ? "" : " / 10"}</span><small>${loyalty === null ? "派系核心不可策反" : showComposition ? `策反費用 $${defectionCost} · 成功率 ${defectionChance}%` : "兵力未明，策反費用與成功率不公開"}${availableMajorGeneralSlots(currentPlayer) < branchSize ? ` · 我方少將空位不足` : ""}</small><select data-defect-superior>${lieutenants.map((item) => `<option value="${item.id}">成功後隸屬 ${item.name}</option>`).join("")}</select><button data-defect-army="${army.id}" ${canDefect ? "" : "disabled"}>策反</button></div>` : ""}
    ${fightingBattle ? `<div class="active-operation">交戰中：不可移動、急行軍或補充。請在戰鬥情報中定策。</div>` : ""}
    ${!fightingBattle && resolvedThisTurn ? `<div class="active-operation">本回合軍令已執行。</div>` : ""}
    ${army.specialOperation ? `<div class="active-operation">進行中：${army.specialOperation.label} · 尚需 ${army.specialOperation.turnsRemaining} 回合</div>` : ""}
    ${isOwnArmy ? `
    <div class="army-operations">
      ${army.specialOperation || !canOrder ? `<button disabled>${army.specialOperation ? "工事進行中" : fightingBattle ? "交戰中" : "本回合已行動"}</button>` : `
      <button class="${moveMode ? "active" : ""}" data-army-operation="move">移動</button>
      ${joinableBattle ? `<button class="join-battle-command" data-join-battle="${joinableBattle.id}">加入戰鬥</button>` : ""}
      ${engineering.map((skill) => {
        const operation = ENGINEERING_OPERATIONS[skill];
        const affordable = Number(state.players[currentPlayer]?.factory_points || 0) >= operation.factoryCost;
        return `<button data-engineering-operation="${skill}" ${affordable ? "" : "disabled"} title="${operation.label}：需 ${operation.turns} 回合，消耗工業點/FP ${operation.factoryCost}">${operation.label} (${operation.turns} 回合 · 工${operation.factoryCost})</button>`;
      }).join("")}`}
      ${isOwnArmy && !fightingBattle && !army.specialOperation ? forcedMarchButtonMarkup(army) : ""}
      ${canReinforce ? `<button data-army-operation="recruit">補充兵力</button>` : ""}
    </div>
    ${canReinforce && army.showRecruitment ? `
      <div class="army-reinforcement">
        <b>${city.name}預備隊</b>
        ${Object.entries(UNIT_META).map(([type, unit]) => `
          <button data-reinforce-unit="${type}" title="${reinforcementWouldExceedCap(units, type) ? `再補一營會超過 ${armyForceCap()} 戰力上限` : ""}" ${profile.unit_reserves?.[type] && !reinforcementWouldExceedCap(units, type) ? "" : "disabled"}>
            ${unitSymbol(type)}<span>${unit.name}</span><strong>${profile.unit_reserves?.[type] ?? 0}</strong>
          </button>
        `).join("")}
      </div>
    ` : ""}` : ""}
  `;
}

function forcedMarchButtonMarkup(army) {
  const rules = forcedMarchRules();
  const turn = Number(state?.turn || 0);
  if (hasPermanentForcedMarch(army)) {
    return `<button class="forced-march-on" disabled>機械化步兵師 · 永久急行軍</button>`;
  }
  if (forcedMarchActive(army, turn)) {
    return `<button class="forced-march-on" disabled>急行軍中 · 剩 ${forcedMarchRemainingTurns(army, turn)} 回合</button>`;
  }
  const cooldown = forcedMarchCooldownTurns(army, turn);
  if (cooldown > 0) {
    return `<button class="forced-march-cooldown" disabled>急行軍冷卻 · 剩 ${cooldown} 回合</button>`;
  }
  const profile = state.players[currentPlayer];
  const affordable = Number(profile?.treasury || 0) >= rules.cash
    && Number(profile?.factory_points || 0) >= rules.factory;
  return `<button data-army-operation="forced_march" ${affordable ? "" : "disabled"}>急行軍 ($${rules.cash} + ${rules.factory} 工廠)</button>`;
}

async function buyForcedMarch(army, button) {
  const rules = forcedMarchRules();
  const turn = Number(state?.turn || 0);
  if (activeBattleForArmy(army)) {
    showNotice("交戰中的軍隊不能實施急行軍。");
    return;
  }
  if (hasPermanentForcedMarch(army)) {
    showNotice("此軍是機械化步兵師，本來就永久急行軍，不必再買。");
    return;
  }
  if (forcedMarchActive(army, turn)) {
    showNotice("此軍已在急行軍狀態。");
    return;
  }
  const cooldown = forcedMarchCooldownTurns(army, turn);
  if (cooldown > 0) {
    showNotice(`此軍急行軍冷卻中，還要 ${cooldown} 回合才能再次實施。`);
    return;
  }
  if (button) button.disabled = true;
  try {
    const result = await api("/api/pay-forced-march", {
      player: currentPlayer,
      army_id: army.id,
      cash: rules.cash,
      factory: rules.factory,
    });
    state = result.state;
    // 本回合起算 3 回合，效果結束再冷卻 3 回合才能為同一支部隊再買。
    army.forcedMarchUntilTurn = turn + rules.durationTurns - 1;
    army.forcedMarchReadyTurn = turn + rules.durationTurns + rules.cooldownTurns;
    updateTopBar();
    renderArmyDetail();
    renderPanel("generals");
    showNotice(`${army.designator} 開始急行軍：${rules.durationTurns} 回合內每回合可走 ${rules.tiles} 格陸地，結束後冷卻 ${rules.cooldownTurns} 回合。`);
    await publishSharedState(true);
  } catch (error) {
    if (button) button.disabled = false;
    showNotice(error.message);
  }
}

function navyHealthMarkup(navy) {
  normalizeNavyDivision(navy, navyRules());
  const floor = Number(navyRules()?.units?.gun_boat?.inactive_below_hp || 15);
  const gunMarkup = (navy.gunBoats || []).map((boat, index) => {
    const hp = Math.max(0, Number(boat.hp || 0));
    const maxHp = Math.max(1, Number(boat.maxHp || 30));
    const active = hp >= floor;
    return `
      <div class="navy-boat-health ${active ? "" : "inactive"}">
        <span>砲艇 ${index + 1}${active ? "" : " · 失能"}</span>
        <div class="boat-health-bar"><i style="width:${Math.max(0, Math.min(100, hp / maxHp * 100))}%"></i></div>
        <b>${Math.round(hp)}/${maxHp}</b>
      </div>`;
  }).join("");
  const cargoMarkup = (navy.cargoBoatHp || []).map((boat, index) => {
    const hp = Math.max(0, Number(boat.hp || 0));
    const maxHp = Math.max(1, Number(boat.maxHp || 10));
    return `
      <div class="navy-boat-health cargo">
        <span>運輸船 ${index + 1}</span>
        <div class="boat-health-bar"><i style="width:${Math.max(0, Math.min(100, hp / maxHp * 100))}%"></i></div>
        <b>${Math.round(hp)}/${maxHp}</b>
      </div>`;
  }).join("");
  return `<div class="navy-health-list">${gunMarkup}${cargoMarkup || '<small>無運輸船</small>'}</div>`;
}

// 大港開炸炸掉的港口：停靠、通行、修理、登陸、載運、編補全部停擺，直到搶修完成。
function paralysedPorts() {
  return new Set((state?.port_effects || [])
    .filter((effect) => Number(effect.remaining_turns || 0) > 0)
    .map((effect) => String(effect.city_id)));
}

function portParalysed(city) {
  return Boolean(city?.id) && paralysedPorts().has(String(city.id));
}

// 港務搶修期間，停在港內的艦隊不會受損也不會被趕走，但整支被鎖住，什麼都不能做。
function navyLockedInPort(navy) {
  const city = cells[navy?.cellKey]?.city;
  if (!portParalysed(city)) return null;
  return (state?.port_effects || []).find((effect) =>
    String(effect.city_id) === String(city.id) && Number(effect.remaining_turns || 0) > 0) || null;
}

function navyLockedNote(navy) {
  const effect = navyLockedInPort(navy);
  if (!effect) return "";
  return `${navy.name}被封在${effect.city_name}港內，搶修還有 ${effect.remaining_turns} 回合，期間不能有任何動作。`;
}

function portParalysedNote(city) {
  const effect = (state?.port_effects || [])
    .find((item) => String(item.city_id) === String(city?.id) && Number(item.remaining_turns || 0) > 0);
  if (!effect) return "";
  return `${city.name}港務遭破壞，搶修中，還有 ${effect.remaining_turns} 回合；期間不能停靠、通行、修理、登陸、載運與編補。`;
}

// 只有 3 級以上的港口（河港、海港皆同）才有船塢與軍需倉庫：修得了船、補得了艦。
// 2 級小港只能讓艦隊停靠與登陸卸兵。
const NAVY_SERVICE_PORT_LEVEL = 3;

function portServiceLevel(city) {
  return city?.port ? Number(city.level || 0) : 0;
}

function isServicePort(city) {
  return portServiceLevel(city) >= NAVY_SERVICE_PORT_LEVEL;
}

function portServiceNote(city) {
  if (!city?.port) return "此處不是港口。";
  return isServicePort(city)
    ? ""
    : `${city.name}是 ${city.level} 級小港，只能停靠與登陸；修理與編補艦隊要到 3 級以上的港口。`;
}

function carriedArmy(navy) {
  return navy?.carriedArmyId ? armyById(navy.carriedArmyId) : null;
}

function navyReserveButtonsMarkup(navy, city, faction) {
  if (!city?.port || !cityControlledBy(city, faction)) {
    return `<div class="active-operation">海軍預備隊只能在己方港口編入艦隊。</div>`;
  }
  if (portParalysed(city)) {
    return `<div class="active-operation">${portParalysedNote(city)}</div>`;
  }
  if (!isServicePort(city)) {
    return `<div class="active-operation">${portServiceNote(city)}</div>`;
  }
  const reserves = state.players[faction]?.navy_reserves || {};
  return `
    <div class="army-reinforcement navy-reinforcement">
      <b>${city.name}海軍預備隊</b>
      ${Object.entries(NAVY_UNIT_META).map(([type, unit]) => `
        <button data-reinforce-navy-unit="${type}" ${Number(reserves[type] || 0) > 0 ? "" : "disabled"}>
          <span>${unit.name}</span><strong>${reserves[type] ?? 0}</strong>
        </button>
      `).join("")}
    </div>
  `;
}

function embarkableArmies(navy) {
  const cell = cells[navy.cellKey];
  if (!cell?.city?.port) return [];
  const capacity = navyCapacity(navy, navyRules());
  return currentArmies().filter((army) =>
    army.cellKey === navy.cellKey
    && !army.embarkedOn
    && armyCanReceiveOrder(army)
    && !activeBattleForArmy(army)
    && forcePoints(armyUnits(army)) <= capacity
  );
}

function renderNavyDetail(root, navy) {
  const faction = navyFaction(navy);
  const isOwnNavy = faction === currentPlayer;
  const cell = cells[navy.cellKey];
  const city = cell?.city || null;
  const carried = carriedArmy(navy);
  const lockedInPort = navyLockedInPort(navy);
  const canOrder = isOwnNavy && navyCanReceiveOrder(navy);
  const moveCost = navyMoveFactoryCost(navy);
  const inContact = navyInContact(navy);
  const canRepair = isOwnNavy && isServicePort(city) && [...(navy.gunBoats || []), ...(navy.cargoBoatHp || [])]
    .some((boat) => Number(boat.hp || 0) < Number(boat.maxHp || 30));
  const embarkable = isOwnNavy && !carried ? embarkableArmies(navy) : [];
  root.hidden = false;
  root.innerHTML = `
    <div class="army-profile navy-profile">
      <div class="navy-profile-icon">艦</div>
      <div><b>${navy.name}</b><span>${FACTIONS[faction]?.shortName || faction} · 無將領</span></div>
      <small>${city ? `${city.name} · ${city.province}` : navyCellLabel(cell)}</small>
    </div>
    <div class="navy-composition">
      <span>砲艇 <b>${activeGunBoats(navy, navyRules()).length}/${navy.gunBoats.length}</b></span>
      <span>運輸船 <b>${navy.cargoBoats}</b></span>
      <span>運載 <b>${carried ? armyCombatLabel(carried) : `${navyCapacity(navy, navyRules())} 戰力容量`}</b></span>
    </div>
    ${navyHealthMarkup(navy)}
    ${lockedInPort ? `<div class="active-operation">${navyLockedNote(navy)}</div>` : ""}
    ${inContact ? `<div class="active-operation">交戰中：${navyContactEstimate(navy)}</div>` : ""}
    ${isOwnNavy ? `
      <div class="army-operations navy-operations">
        ${!canOrder ? `<button disabled>${lockedInPort ? "封港中" : navyIsResolvedThisTurn(navy) ? "本回合已行動" : "不可行動"}</button>${inContact && !lockedInPort ? `<button data-navy-operation="retreat">撤退</button>` : ""}` : `
          <button class="${navyMoveMode ? "active" : ""}" data-navy-operation="move" title="沿可航行水道最多 ${navyRules().move?.tiles_per_turn || 2} 格；${navyMoveCostText(navy)}">移動（${moveCost ? `工${moveCost}` : "工0"}）</button>
          <button data-navy-operation="hold">待命</button>
          ${canRepair ? `<button data-navy-operation="repair">修理</button>` : ""}
          ${inContact ? `<button data-navy-operation="retreat">撤退</button>` : ""}
          ${carried && city?.port ? `<button data-navy-operation="disembark">登陸</button>` : ""}
          ${embarkable.length ? `<button data-navy-operation="embark">搭載陸軍</button>` : ""}
        `}
      </div>
      ${embarkable.length ? `<div class="navy-embark-list">${embarkable.map((army) => `
        <button data-embark-army="${army.id}">${armyCombatLabel(army)} · 戰力 ${Math.round(forcePoints(armyUnits(army)))}</button>
      `).join("")}</div>` : ""}
      ${navyReserveButtonsMarkup(navy, city, faction)}
    ` : ""}
  `;
}

async function handleNavyOperation(navy, operation, embarkArmyId, target, reinforceUnitType = null) {
  if (navyLockedInPort(navy)) {
    showNotice(navyLockedNote(navy));
    return;
  }
  if (reinforceUnitType) {
    await reinforceNavyFromReserve(navy, reinforceUnitType, target);
    return;
  }
  if (operation === "retreat") {
    const destination = navyRetreatCell(navy);
    if (!destination) {
      showNotice("沒有可供艦隊撤退的相鄰水道。");
      return;
    }
    beginNavyOrder(navy, "retreat");
    moveNavyToCell(navy, destination);
    markNavyResolved(navy);
    uiNotice = `${navy.name}已撤退至${destination.city?.name || destination.river || "水域"}。`;
    initMap();
    renderPendingActions();
    await publishSharedState(true);
    return;
  }
  if (!navyCanReceiveOrder(navy)) {
    showNotice("此艦隊本回合已行動。");
    return;
  }
  if (operation === "embark" && !embarkArmyId) {
    const options = embarkableArmies(navy);
    if (options.length !== 1) {
      showNotice("請在下方選擇要搭載的陸軍。");
      return;
    }
    embarkArmyId = options[0].id;
  }
  if (embarkArmyId) {
    const army = armyById(embarkArmyId);
    if (!army || army.cellKey !== navy.cellKey) {
      showNotice("可搭載陸軍不在本艦隊所在港口。");
      return;
    }
    if (portParalysed(cells[navy.cellKey]?.city)) {
      showNotice(portParalysedNote(cells[navy.cellKey].city));
      return;
    }
    if (forcePoints(armyUnits(army)) > navyCapacity(navy, navyRules())) {
      showNotice(`運輸船容量不足：目前容量 ${navyCapacity(navy, navyRules())} 戰力點。`);
      return;
    }
    beginNavyOrder(navy, "embark");
    navy.carriedArmyId = army.id;
    army.embarkedOn = navy.id;
    moveNavyToCell(navy, cells[navy.cellKey]);
    markNavyResolved(navy);
    markArmyResolved(army);
    uiNotice = `${armyCombatLabel(army)}已登上${navy.name}。`;
    initMap();
    renderPendingActions();
    await publishSharedState(true);
    return;
  }
  if (operation === "move") {
    if (!navyCanReceiveOrder(navy)) {
      showNotice("此艦隊本回合已行動。");
      return;
    }
    navyMoveMode = !navyMoveMode;
    moveMode = false;
    engineeringMode = null;
    showNotice(navyMoveMode
      ? `選擇可航行地格；艦隊最多 ${navyRules().move?.tiles_per_turn || 2} 格，${navyMoveCostText(navy)}。`
      : "已取消艦隊移動。");
    $("mapStage").classList.toggle("move-mode", navyMoveMode);
    renderArmyDetail();
    return;
  }
  if (operation === "hold") {
    beginNavyOrder(navy, "hold");
    resolveNavyContacts(navy);
    resolveNavy(navy.id);
    await publishSharedState(true);
    return;
  }
  if (operation === "repair") {
    const cell = cells[navy.cellKey];
    if (!cell?.city?.port) {
      showNotice("艦艇只能在港口修理。");
      return;
    }
    if (portParalysed(cell.city)) {
      showNotice(portParalysedNote(cell.city));
      return;
    }
    if (!isServicePort(cell.city)) {
      showNotice(portServiceNote(cell.city));
      return;
    }
    const raw = window.prompt("將所有現存艦艇至少修到幾 HP？", String(navyRules().units?.gun_boat?.hp || 30));
    if (raw === null) return;
    const targetHp = Number(raw);
    if (!Number.isFinite(targetHp) || targetHp <= 0) {
      showNotice("修理目標 HP 必須是正數。");
      return;
    }
    const preview = JSON.parse(JSON.stringify(navy));
    const restored = restoreHpToFloor(preview, targetHp);
    if (restored <= 0) {
      showNotice("所有現存艦艇都已達到該 HP。");
      return;
    }
    target.disabled = true;
    try {
      const result = await api("/api/repair-navy", { player: currentPlayer, hp: restored });
      state = result.state;
      restoreHpToFloor(navy, targetHp);
      beginNavyOrder(navy, "repair");
      markNavyResolved(navy);
      syncStrategicCitiesFromState();
      updateTopBar();
      uiNotice = `${navy.name}修復 ${restored} HP，消耗工業點 ${result.factory}。`;
      initMap();
      renderPendingActions();
      await publishSharedState(true);
    } catch (error) {
      target.disabled = false;
      showNotice(error.message);
    }
    return;
  }
  if (operation === "disembark") {
    const cell = cells[navy.cellKey];
    const army = carriedArmy(navy);
    if (!cell?.city?.port || !army) {
      showNotice("登陸必須在港口，且艦隊需要載有陸軍。");
      return;
    }
    if (portParalysed(cell.city)) {
      showNotice(portParalysedNote(cell.city));
      return;
    }
    beginNavyOrder(navy, "disembark");
    delete army.embarkedOn;
    moveArmyToCell(army, cell);
    navy.carriedArmyId = null;
    markNavyResolved(navy);
    markArmyResolved(army);
    uiNotice = `${armyCombatLabel(army)}已自${navy.name}登陸${cell.city.name}。`;
    initMap();
    renderPendingActions();
    await publishSharedState(true);
  }
}

async function reinforceNavyFromReserve(navy, unitType, target) {
  const faction = navyFaction(navy);
  const cell = cells[navy.cellKey];
  const city = cell?.city || null;
  if (faction !== currentPlayer) {
    showNotice("只能編入自己的艦隊。");
    return;
  }
  if (!city?.port || !cityControlledBy(city, faction)) {
    showNotice("海軍預備隊只能在己方港口編入艦隊。");
    return;
  }
  if (portParalysed(city)) {
    showNotice(portParalysedNote(city));
    return;
  }
  if (!isServicePort(city)) {
    showNotice(portServiceNote(city));
    return;
  }
  if (!Number(state.players[faction]?.navy_reserves?.[unitType] || 0)) {
    showNotice("沒有可編入的海軍預備隊。");
    return;
  }
  if (target) target.disabled = true;
  try {
    const result = await api("/api/reinforce-navy", {
      player: faction,
      city_id: city.id,
      unit_type: unitType,
      count: 1,
    });
    state = result.state;
    if (unitType === "gun_boat") {
      const hp = Number(navyRules().units?.gun_boat?.hp || 30);
      navy.gunBoats ||= [];
      navy.gunBoats.push({ id: `${navy.id}-G${navy.gunBoats.length + 1}`, hp, maxHp: hp });
    } else if (unitType === "cargo_boat") {
      const hp = Number(navyRules().units?.cargo_boat?.hp || 10);
      navy.cargoBoatHp ||= [];
      navy.cargoBoatHp.push({ id: `${navy.id}-C${navy.cargoBoatHp.length + 1}`, hp, maxHp: hp });
      navy.cargoBoats = navy.cargoBoatHp.length;
    }
    syncStrategicCitiesFromState();
    updateTopBar();
    uiNotice = `${navy.name}編入${NAVY_UNIT_META[unitType]?.name || unitType} +1。`;
    renderArmyDetail();
    renderPendingActions();
    await publishSharedState(true);
  } catch (error) {
    if (target) target.disabled = false;
    showNotice(error.message);
  }
}

function pendingArmies() {
  const fightingIds = new Set(
    activeBattles.filter(battleIsActive).flatMap(battleParticipantIds),
  );
  return currentArmies().filter((army) => !armyIsResolvedThisTurn(army) && !fightingIds.has(army.id));
}

function pendingNavies() {
  // 鎖在港裡的艦隊不算待命：它本回合本來就動不了，不該卡住結束回合。
  return currentNavies().filter((navy) => !navyIsResolvedThisTurn(navy) && !navyLockedInPort(navy));
}

function joinBattle(army, battle) {
  const side = battle ? battleSideForFaction(battle, factionForArmy(army)) : null;
  if (!armyCanReceiveOrder(army)) {
    showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能再加入其他戰場。" : "此軍本回合已行動。");
    return;
  }
  if (!battle || !side || joinableBattleForArmy(army)?.id !== battle.id) {
    showNotice("此軍目前不在可支援戰場的相鄰地格。");
    return;
  }
  const action = beginArmyOrder(army, "join_battle");
  action.joinedBattle = { battleId: battle.id, side };
  battle.reinforcementIds ||= { A: [], B: [] };
  battle.reinforcementIds[side].push(army.id);
  battle.initial[side] = addUnitTotals(battle.initial[side], armyUnits(army));
  battle.initialByArmy ||= {};
  battle.initialByArmy[army.id] = { ...armyUnits(army) };
  battle.tacticRevision ||= { A: false, B: false };
  battle.tacticRevision[side] = true;
  battle.confirmed ||= { A: true, B: true };
  battle.confirmed[side] = false;
  markArmyResolved(army);
  selectedBattleId = battle.id;
  moveMode = false;
  uiNotice = `${armyCombatLabel(army)}已投入${battleSideLabel(battle, side)}的戰鬥，部隊仍顯示於支援地格。`;
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function selectNavy(navyId) {
  selectedNavyId = navyId;
  selectedArmyId = null;
  selectedBattleId = null;
  moveMode = false;
  navyMoveMode = false;
  engineeringMode = null;
  uiNotice = null;
  $("mapStage").classList.remove("move-mode");
  selectTile(cells[selectedNavy()?.cellKey]);
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
  document.querySelector(`[data-navy-id="${navyId}"]`)?.focus({ preventScroll: true });
}

function selectArmy(armyId) {
  selectedArmyId = armyId;
  selectedNavyId = null;
  navyMoveMode = false;
  moveMode = false;
  uiNotice = null;
  $("mapStage").classList.remove("move-mode");
  selectTile(cells[selectedArmy()?.cellKey]);
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
  document.querySelector(`[data-army-id="${armyId}"]`)?.focus({ preventScroll: true });
}

function resolveNavy(navyId) {
  markNavyResolved(navyId);
  navyMoveMode = false;
  uiNotice = null;
  const nextNavy = pendingNavies()[0];
  selectedNavyId = nextNavy?.id || null;
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function resolveArmy(armyId) {
  markArmyResolved(armyId);
  moveMode = false;
  uiNotice = null;
  const nextArmy = pendingArmies()[0];
  selectedArmyId = nextArmy?.id || null;
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function beginArmyOrder(army, type) {
  const action = {
    orderIndex: armyOrderHistory.length + navyOrderHistory.length,
    player: currentPlayer,
    type,
    armyId: army.id,
    wasResolved: armyIsResolvedThisTurn(army),
    before: {
      cellKey: army.cellKey,
      lon: army.lon,
      lat: army.lat,
      units: { ...army.units },
      reinforcements: { ...(state.players[currentPlayer]?.army_reinforcements?.[army.id] || {}) },
      specialOperation: army.specialOperation ? { ...army.specialOperation } : null,
      resolvedTurn: army.resolvedTurn ?? null,
      status: army.status,
    },
  };
  armyOrderHistory.push(action);
  return action;
}

function beginNavyOrder(navy, type) {
  const carried = carriedArmy(navy);
  const action = {
    orderIndex: armyOrderHistory.length + navyOrderHistory.length,
    player: currentPlayer,
    type,
    navyId: navy.id,
    wasResolved: navyIsResolvedThisTurn(navy),
    before: {
      cellKey: navy.cellKey,
      lon: navy.lon,
      lat: navy.lat,
      gunBoats: JSON.parse(JSON.stringify(navy.gunBoats || [])),
      cargoBoats: navy.cargoBoats,
      cargoBoatHp: JSON.parse(JSON.stringify(navy.cargoBoatHp || [])),
      carriedArmyId: navy.carriedArmyId || null,
      resolvedTurn: navy.resolvedTurn ?? null,
    },
    carriedArmyBefore: carried ? {
      id: carried.id,
      cellKey: carried.cellKey,
      lon: carried.lon,
      lat: carried.lat,
      embarkedOn: carried.embarkedOn || null,
      resolvedTurn: carried.resolvedTurn ?? null,
      // 海戰可能把船上的部隊打掉甚至連人帶船沉掉，撤銷時要一併還原。
      units: JSON.parse(JSON.stringify(armyUnits(carried))),
      status: carried.status || null,
      generalStatus: generalById(carried.generalId)?.status || null,
    } : null,
  };
  navyOrderHistory.push(action);
  return action;
}

function moveNavyToCell(navy, cell) {
  if (!navy || !cell) return;
  navy.cellKey = cell.key;
  navy.lon = cell.lon;
  navy.lat = cell.lat;
  const carried = carriedArmy(navy);
  if (carried) {
    carried.cellKey = cell.key;
    carried.lon = cell.lon;
    carried.lat = cell.lat;
  }
}

function recordNavyBattle(report) {
  const navy = navyById(report.navyId);
  const army = armyById(report.armyId);
  const stored = {
    id: Date.now() * 100 + navyBattleReports.length,
    turn: state?.turn || 0,
    cellKey: report.cellKey || navy?.cellKey || army?.cellKey || null,
    ...report,
  };
  navyBattleReports.push(stored);
  uiNotice = report.message;
  if (reportVisibleToPlayer(stored)) {
    selectedBattleId = stored.id;
    selectedNavyId = null;
    selectedArmyId = null;
  }
  return stored;
}

function navyDamageSummary(damage) {
  const sunk = (damage?.damaged || []).filter((item) => item.sunk);
  if (!sunk.length) return "";
  const labels = sunk.map((item) => item.type === "cargo_boat" ? "運輸船" : "砲艇");
  return `，擊沉${labels.join("、")}`;
}

// 將領陣亡的共同處理：本人與其直屬部隊標記陣亡，直屬中將忠誠歸零。
// 暗殺得手與運兵船連人帶船沉沒都走這條路。
function applyGeneralDeath(generalId, owner = null) {
  const faction = owner || generalOwners[generalId] || null;
  const tree = generalTrees[faction];
  const general = tree?.generals?.[generalId];
  if (!general) return false;
  general.status = "killed";
  for (const army of allArmies(true)) {
    if (army.generalId === generalId) army.status = "killed";
  }
  for (const childId of descendantGeneralIds(tree, generalId)) {
    const child = tree.generals?.[childId];
    if (!child || child.role !== "major_general") continue;
    if (generalAbsoluteLoyaltyActive(child) || child.loyalty_exempt || child.loyalty === null) continue;
    loyaltyOverrides[childId] = 0;
  }
  return true;
}

// 整支艦隊被打光時，運兵船上的陸軍隨船覆沒：部隊全滅，將領比照暗殺得手處理。
function sinkCarriedArmyWithNavy(navy) {
  const army = carriedArmy(navy);
  navy.carriedArmyId = null;
  if (!army) return null;
  const owner = generalOwners[army.generalId] || factionForArmy(army);
  const reinforcementLedger = state.players[owner]?.army_reinforcements;
  if (reinforcementLedger) delete reinforcementLedger[army.id];
  army.units = Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0]));
  const general = generalById(army.generalId);
  if (general) general.units = { ...army.units };
  delete army.embarkedOn;
  army.status = "killed";
  applyGeneralDeath(army.generalId, owner);
  markArmyResolved(army);
  return army;
}

// 運輸船被擊沉之後，可載運量可能已經低於船上陸軍的戰力。
// 超出的部分隨機挑兵種裁撤，直到剩下的戰力不超過現有容量。
function enforceNavyCargoCapacity(navy) {
  const army = carriedArmy(navy);
  if (!army) return null;
  const capacity = navyCapacity(navy, navyRules());
  const before = armyUnits(army);
  const units = { ...before };
  if (forcePoints(units) <= capacity) return null;
  const lost = {};
  while (forcePoints(units) > capacity) {
    const available = Object.keys(UNIT_META).filter((type) => Number(units[type] || 0) > 0);
    if (!available.length) break;
    const type = available[Math.floor(Math.random() * available.length)];
    units[type] -= 1;
    lost[type] = (lost[type] || 0) + 1;
  }
  setArmyTotalUnits(army, units, { capAtCurrent: true, currentUnits: before });
  return { army, capacity, lost };
}

// 每次海戰結束後結算船上的陸軍：艦隊全滅就連人帶船沉沒，
// 艦隊還在但運輸船有損失就把超出容量的部隊裁掉。
function settleNavyCarriedLosses(navy) {
  if (!navy) return;
  normalizeNavyDivision(navy, navyRules());
  const wipedOut = !(navy.gunBoats || []).length && !(navy.cargoBoatHp || []).length;
  if (wipedOut) {
    const army = sinkCarriedArmyWithNavy(navy);
    if (army) uiNotice = `${uiNotice || ""}${navy.name}遭全數擊沉，船上的${army.general}部隊隨船覆沒，${army.general}陣亡。`;
    return;
  }
  const trimmed = enforceNavyCargoCapacity(navy);
  if (!trimmed) return;
  const detail = Object.entries(trimmed.lost)
    .map(([type, count]) => `${UNIT_META[type]?.name || type} ${count}`)
    .join("、");
  uiNotice = `${uiNotice || ""}${navy.name}運輸船折損，可載運量降為 ${trimmed.capacity} 戰力點，${trimmed.army.general}部隊被迫減至容量以內${detail ? `（損失 ${detail}）` : ""}。`;
}

function applyArmyNavyContact(army, navy) {
  const before = armyUnits(army);
  const result = resolveArmyNavyContact(before, navy, navyRules());
  setArmyTotalUnits(army, { ...before, artillery: result.artilleryAfter }, { capAtCurrent: true, currentUnits: before });
  recordNavyBattle({
    kind: "army_navy",
    armyId: army.id,
    navyId: navy.id,
    faction: factionForArmy(army),
    targetFaction: navyFaction(navy),
    result,
    message: `${armyCombatLabel(army)}砲兵與${navy.name}交火：艦艇受損 ${Math.round(result.boatDamage)} HP${navyDamageSummary(result.boatDamageDetail)}，砲兵損失 ${result.artilleryLost} 營。${result.navyFired ? "砲艇完成還擊。" : "砲艇均已失能，未能還擊。"}${result.landRetreat ? "陸軍已無砲兵，被迫退出接觸。" : "陸軍仍有砲兵，繼續據守。"}${result.navyRetreat ? "艦隊達退卻條件。" : ""}`,
  });
  settleNavyCarriedLosses(navy);
  return result;
}

function applyNavyDuel(attacker, defender) {
  const result = resolveNavyDuel(attacker, defender, navyRules());
  recordNavyBattle({
    kind: "navy_duel",
    navyId: attacker.id,
    targetNavyId: defender.id,
    faction: navyFaction(attacker),
    targetFaction: navyFaction(defender),
    result,
    message: `${attacker.name}與${defender.name}交火：敵方受損 ${Math.round(result.attackerDamage)} HP${navyDamageSummary(result.attackerDamageDetail)}，我方受損 ${Math.round(result.defenderDamage)} HP${navyDamageSummary(result.defenderDamageDetail)}。${result.attackerActiveGunBoats ? "攻方完成射擊" : "攻方無可戰砲艇"}；${result.defenderActiveGunBoats ? "守方完成射擊" : "守方無可戰砲艇"}。`,
  });
  settleNavyCarriedLosses(attacker);
  settleNavyCarriedLosses(defender);
  return result;
}

function retreatNavyFromContact(navy, fallbackCell = null, threatCell = null) {
  const destination = navyRetreatCell(navy, threatCell);
  if (destination) moveNavyToCell(navy, destination);
  else if (fallbackCell) moveNavyToCell(navy, fallbackCell);
}

function retreatArmyFromNavyContact(army, navy, fallbackCell = null) {
  const destination = fallbackCell || retreatCellFor(army, null, navy?.cellKey);
  if (destination) moveArmyToCell(army, destination);
}

function resolveNavyContacts(navy, fallbackCell = null) {
  if (!navy) return false;
  const faction = navyFaction(navy);
  let fought = false;
  const enemyNavy = enemyNavyAtCell(navy.cellKey, faction);
  if (enemyNavy && factionsAtWar(faction, navyFaction(enemyNavy))) {
    fought = true;
    const result = applyNavyDuel(navy, enemyNavy);
    if (result.attackerRetreat) retreatNavyFromContact(navy, fallbackCell, cells[enemyNavy.previousCellKey] || cells[enemyNavy.cellKey]);
    if (result.defenderRetreat) retreatNavyFromContact(enemyNavy, null, cells[navy.previousCellKey] || cells[navy.cellKey]);
  }
  const hostileNavyStillScreening = allNavies().some((other) =>
    other.id !== navy.id
    && other.cellKey === navy.cellKey
    && factionsAtWar(faction, navyFaction(other))
  );
  if (hostileNavyStillScreening) return fought;
  const enemies = allArmies().filter((army) =>
    army.cellKey === navy.cellKey
    && factionForArmy(army) !== faction
    && factionsAtWar(faction, factionForArmy(army))
  );
  for (const army of enemies) {
    fought = true;
    const result = applyArmyNavyContact(army, navy);
    if (result.landRetreat) retreatArmyFromNavyContact(army, navy);
    if (result.navyRetreat) retreatNavyFromContact(navy, fallbackCell, cells[army.previousCellKey] || cells[army.cellKey]);
  }
  return fought;
}

function resolveAllNavyContacts() {
  const foughtPairs = new Set();
  let fought = false;
  for (const navy of allNavies()) {
    const faction = navyFaction(navy);
    const cellKey = navy.cellKey;
    for (const enemyNavy of allNavies()) {
      if (enemyNavy.id === navy.id || enemyNavy.cellKey !== cellKey) continue;
      const enemyFaction = navyFaction(enemyNavy);
      if (!factionsAtWar(faction, enemyFaction)) continue;
      const pairKey = [navy.id, enemyNavy.id].sort().join("|");
      if (foughtPairs.has(pairKey)) continue;
      foughtPairs.add(pairKey);
      fought = true;
      const result = applyNavyDuel(navy, enemyNavy);
      if (result.attackerRetreat) retreatNavyFromContact(navy, null, cells[enemyNavy.previousCellKey] || cells[enemyNavy.cellKey]);
      if (result.defenderRetreat) retreatNavyFromContact(enemyNavy, null, cells[navy.previousCellKey] || cells[navy.cellKey]);
    }
    const hostileNavyStillScreening = allNavies().some((other) =>
      other.id !== navy.id
      && other.cellKey === navy.cellKey
      && factionsAtWar(faction, navyFaction(other))
    );
    if (hostileNavyStillScreening) continue;
    for (const army of allArmies()) {
      if (army.cellKey !== cellKey || !factionsAtWar(faction, factionForArmy(army))) continue;
      const pairKey = [navy.id, army.id].sort().join("|");
      if (foughtPairs.has(pairKey)) continue;
      foughtPairs.add(pairKey);
      fought = true;
      const result = applyArmyNavyContact(army, navy);
      if (result.landRetreat) retreatArmyFromNavyContact(army, navy);
      if (result.navyRetreat) retreatNavyFromContact(navy, null, cells[army.previousCellKey] || cells[army.cellKey]);
    }
  }
  return fought;
}

function undoLastArmyOrder() {
  const latestArmy = armyOrderHistory
    .filter((action) => action.player === currentPlayer)
    .at(-1);
  const latestNavy = navyOrderHistory
    .filter((action) => action.player === currentPlayer)
    .at(-1);
  if (latestNavy && (!latestArmy || latestNavy.orderIndex > latestArmy.orderIndex)) {
    undoLastNavyOrder();
    return;
  }
  const actionIndex = armyOrderHistory.findLastIndex((action) => action.player === currentPlayer);
  if (actionIndex < 0) return;
  const [action] = armyOrderHistory.splice(actionIndex, 1);
  const army = currentArmies().find((item) => item.id === action.armyId);
  if (!army) return;
  Object.assign(army, {
    cellKey: action.before.cellKey,
    lon: action.before.lon,
    lat: action.before.lat,
    units: { ...action.before.units },
    status: action.before.status,
  });
  state.players[currentPlayer].army_reinforcements[army.id] = { ...action.before.reinforcements };
  if (action.before.specialOperation) army.specialOperation = { ...action.before.specialOperation };
  else delete army.specialOperation;
  if (action.before.resolvedTurn === null) delete army.resolvedTurn;
  else army.resolvedTurn = action.before.resolvedTurn;
  if (action.factoryCost && state.players[action.player]) {
    state.players[action.player].factory_points = Number(state.players[action.player].factory_points || 0) + Number(action.factoryCost);
  }
  if (action.battleId) {
    if (action.defenderBefore) {
      const defender = armyById(action.defenderBefore.id);
      if (defender) {
        Object.assign(defender, {
          cellKey: action.defenderBefore.cellKey,
          lon: action.defenderBefore.lon,
          lat: action.defenderBefore.lat,
          units: { ...action.defenderBefore.units },
          status: action.defenderBefore.status,
        });
        const defenderFaction = factionForArmy(defender);
        if (state.players[defenderFaction]) {
          state.players[defenderFaction].army_reinforcements[defender.id] = { ...action.defenderBefore.reinforcements };
        }
        if (action.defenderWasResolved) markArmyResolved(defender);
        else clearArmyResolved(defender);
      }
    }
    const battleIndex = activeBattles.findIndex((battle) => battle.id === action.battleId);
    if (battleIndex >= 0) activeBattles.splice(battleIndex, 1);
  }
  if (action.joinedBattle) {
    const battle = activeBattles.find((item) => item.id === action.joinedBattle.battleId);
    if (battle) {
      battle.reinforcementIds[action.joinedBattle.side] = battle.reinforcementIds[action.joinedBattle.side]
        .filter((armyId) => armyId !== army.id);
      const joinedUnits = addUnitTotals(action.before.units, action.before.reinforcements);
      battle.initial[action.joinedBattle.side] = Object.fromEntries(Object.keys(UNIT_META).map((type) => [
        type,
        Math.max(0, (battle.initial[action.joinedBattle.side][type] || 0) - (joinedUnits[type] || 0)),
      ]));
      delete battle.initialByArmy?.[army.id];
      battle.tacticRevision[action.joinedBattle.side] = false;
      battle.confirmed[action.joinedBattle.side] = true;
    }
  }
  if (action.territoryChange) {
    const changedCell = cells[action.territoryChange.key];
    changedCell.fac = action.territoryChange.previousFaction;
    if (changedCell.city && action.territoryChange.previousCityFaction
      && changedCell.city.faction !== action.territoryChange.previousCityFaction) {
      transferCityEconomy(changedCell.city, changedCell.city.faction, action.territoryChange.previousCityFaction);
      queueCityOwnershipSync(changedCell.city.id, action.territoryChange.previousCityFaction);
    }
  }
  const prisonersToUndo = action.prisoners || (action.prisoner ? [action.prisoner] : []);
  for (const prisoner of prisonersToUndo) {
    const jail = jailedGenerals[prisoner.captor] || [];
    const prisonerIndex = jail.findIndex((record) => record.armyId === prisoner.armyId);
    if (prisonerIndex >= 0) jail.splice(prisonerIndex, 1);
  }
  for (const before of Object.values(action.capturedBranchBefore || {})) {
    const restoredArmy = armyById(before.id);
    if (!restoredArmy) continue;
    Object.assign(restoredArmy, {
      faction: before.faction,
      cellKey: before.cellKey,
      lon: before.lon,
      lat: before.lat,
      units: { ...before.units },
      status: before.status,
    });
    if (state.players[before.faction]) {
      state.players[before.faction].army_reinforcements[before.id] = { ...before.reinforcements };
    }
    clearArmyResolved(restoredArmy);
  }
  if (action.loyaltyBefore) {
    for (const [generalId, previous] of Object.entries(action.loyaltyBefore)) {
      if (previous === null) delete loyaltyOverrides[generalId];
      else loyaltyOverrides[generalId] = previous;
    }
  }
  if (action.wasResolved) markArmyResolved(army);
  else clearArmyResolved(army);
  delete turnReady[currentPlayer];
  selectedArmyId = army.id;
  selectedBattleId = null;
  moveMode = false;
  engineeringMode = null;
  uiNotice = "已撤銷上一道軍令。";
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function canUndoArmyOrder() {
  return armyOrderHistory.some((action) => action.player === currentPlayer)
    || navyOrderHistory.some((action) => action.player === currentPlayer);
}

function undoLastNavyOrder() {
  const actionIndex = navyOrderHistory.findLastIndex((action) => action.player === currentPlayer);
  if (actionIndex < 0) return;
  const [action] = navyOrderHistory.splice(actionIndex, 1);
  const navy = navyById(action.navyId);
  if (!navy) return;
  Object.assign(navy, {
    cellKey: action.before.cellKey,
    lon: action.before.lon,
    lat: action.before.lat,
    gunBoats: JSON.parse(JSON.stringify(action.before.gunBoats || [])),
    cargoBoats: action.before.cargoBoats,
    cargoBoatHp: JSON.parse(JSON.stringify(action.before.cargoBoatHp || [])),
    carriedArmyId: action.before.carriedArmyId,
  });
  normalizeNavyDivision(navy, navyRules());
  if (action.before.resolvedTurn === null) delete navy.resolvedTurn;
  else navy.resolvedTurn = action.before.resolvedTurn;
  if (action.factoryCost && state.players[action.player]) {
    state.players[action.player].factory_points = Number(state.players[action.player].factory_points || 0) + Number(action.factoryCost);
  }
  if (action.territoryChange) {
    const changedCell = cells[action.territoryChange.key];
    if (changedCell) {
      changedCell.fac = action.territoryChange.previousFaction;
      if (changedCell.city && action.territoryChange.previousCityFaction
        && changedCell.city.faction !== action.territoryChange.previousCityFaction) {
        transferCityEconomy(changedCell.city, changedCell.city.faction, action.territoryChange.previousCityFaction);
        queueCityOwnershipSync(changedCell.city.id, action.territoryChange.previousCityFaction);
      }
    }
  }
  if (action.carriedArmyBefore) {
    const army = armyById(action.carriedArmyBefore.id);
    if (army) {
      Object.assign(army, {
        cellKey: action.carriedArmyBefore.cellKey,
        lon: action.carriedArmyBefore.lon,
        lat: action.carriedArmyBefore.lat,
      });
      if (action.carriedArmyBefore.units) {
        army.units = { ...action.carriedArmyBefore.units };
        const general = generalById(army.generalId);
        if (general) {
          general.units = { ...army.units };
          if (action.carriedArmyBefore.generalStatus) general.status = action.carriedArmyBefore.generalStatus;
        }
      }
      if (action.carriedArmyBefore.status) army.status = action.carriedArmyBefore.status;
      if (action.carriedArmyBefore.embarkedOn) army.embarkedOn = action.carriedArmyBefore.embarkedOn;
      else delete army.embarkedOn;
      if (action.carriedArmyBefore.resolvedTurn === null) clearArmyResolved(army);
      else {
        army.resolvedTurn = action.carriedArmyBefore.resolvedTurn;
        resolvedArmyIds.add(army.id);
      }
    }
  }
  if (action.wasResolved) markNavyResolved(navy);
  else clearNavyResolved(navy);
  delete turnReady[currentPlayer];
  selectedNavyId = navy.id;
  selectedArmyId = null;
  selectedBattleId = null;
  navyMoveMode = false;
  moveMode = false;
  uiNotice = "已撤銷上一道艦隊命令。";
  updateTopBar();
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
  publishSharedState(true).catch((error) => console.error("Undo navy publish failed:", error));
}

// ---- 崩鐵玩家：搶修中的鐵路 ----------------------------------------------

function disabledRailways() {
  return new Set((state?.railway_effects || [])
    .filter((effect) => Number(effect.remaining_turns || 0) > 0)
    .map((effect) => effect.railway));
}

// ---- 列強鐵路：關係不到就搭不上車 ---------------------------------------
// 南滿是日本的、中東是蘇聯的、滇越是法國的。關係要到友好門檻（6）人家才讓你
// 用它調兵；沒到門檻或線路正在搶修，沿線地格照樣走得過去，只是不能一次三格。
const FOREIGN_RAILWAY_POWERS = {
  南滿鐵路: "jp",
  中東鐵路: "su",
  滇越鐵路: "fr",
};
const FOREIGN_RAILWAY_RELATION_MIN = 6;

function foreignRailwayRelation(railway, faction = currentPlayer) {
  const power = FOREIGN_RAILWAY_POWERS[railway];
  if (!power) return null;
  return Number(state?.players?.[faction]?.foreign_relations?.[power] ?? 0);
}

function lockedForeignRailways(faction = currentPlayer) {
  return new Set(Object.keys(FOREIGN_RAILWAY_POWERS)
    .filter((railway) => foreignRailwayRelation(railway, faction) < FOREIGN_RAILWAY_RELATION_MIN));
}

// 交涉破裂的路權封鎖：只罰拒絕的那一家，別人照走（與全場停運的崩鐵不同）。
function bannedRailways(faction = currentPlayer) {
  const turn = Number(state?.turn || 0);
  return new Set((state?.railway_bans || [])
    .filter((entry) => entry.player === faction && turn < Number(entry.until_turn || 0))
    .map((entry) => entry.railway));
}

// 鐵路運輸走不了的線：搶修中的 ∪ 關係不到的列強線 ∪ 自己被封鎖路權的線。
function unusableRailways(faction = currentPlayer) {
  const blocked = disabledRailways();
  for (const railway of lockedForeignRailways(faction)) blocked.add(railway);
  for (const railway of bannedRailways(faction)) blocked.add(railway);
  return blocked;
}

// 一段鐵路連線只有在兩端共用一條「用得到」的鐵路時才算通。
function railLinkUsable(from, to, downed = unusableRailways()) {
  if (!downed.size) return true;
  for (const name of from.railroads || []) {
    if ((to.railroads || new Set()).has(name) && !downed.has(name)) return true;
  }
  return false;
}

// 鐵路癱瘓期間，該線沿線地格退化成普通地格：不能再做鐵路運輸，
// 但照常可以用一般移動（含急行軍）通行。
function cellIsPlainWhileDowned(cell, downed = unusableRailways()) {
  const lines = [...(cell?.railroads || [])];
  if (!lines.length) return false;
  return lines.every((name) => downed.has(name));
}

// 一格能不能當成鄉村地格走：本來就沒鐵路，或鐵路正在搶修中。
function cellUsableAsRural(cell, downed = unusableRailways()) {
  if (!cell || cell.city || cell.power) return false;
  if (!cell.railroads?.size) return true;
  return cellIsPlainWhileDowned(cell, downed);
}

function riverStepAllowed(from, to, railwayMovement = false) {
  const riverCells = [from, to].filter((cell) => cell.river);
  if (!riverCells.length) return true;
  // 河港開放陸軍自由通行，不需要浮橋。
  return riverCells.every((cell) => cell.city?.port === "river"
    || completedPontoons.has(cell.key)
    || (railwayMovement && cell.railBridge));
}

function hostileBlockingNavyAtCell(cell, movingFaction = currentPlayer) {
  if (!cell) return null;
  return allNavies().find((navy) =>
    navy.cellKey === cell.key
    && navyFaction(navy) !== movingFaction
    && factionsAtWar(movingFaction, navyFaction(navy))
  ) || null;
}

function railwayPath(source, destination) {
  if (!source.railNeighbors?.size || !destination.railroads?.size) return null;
  const downed = unusableRailways();
  const railLimit = railwayMoveLimit(currentPlayer);
  const queue = [{ cell: source, path: [source] }];
  const visited = new Set([source.key]);
  while (queue.length) {
    const { cell, path } = queue.shift();
    if (cell.key === destination.key) return path;
    if (path.length > railLimit) continue;
    for (const key of cell.railNeighbors || []) {
      if (visited.has(key)) continue;
      const next = cells[key];
      if (!next || next.power || !railLinkUsable(cell, next, downed)) continue;
      if (next.key !== destination.key && hostileBlockingNavyAtCell(next, currentPlayer)) continue;
      if (!riverStepAllowed(cell, next, true)) continue;
      visited.add(key);
      queue.push({ cell: next, path: [...path, next] });
    }
  }
  return null;
}

// 急行軍走的是「陸軍本來就走得到的地格」：城市、鐵路橋都算，只有列強租借地
// 進不去。過河一樣要浮橋（鐵路橋僅限沿鐵路移動時使用）。
function cellUsableForForcedMarch(cell) {
  return Boolean(cell) && !cell.power;
}

function forcedMarchPath(source, destination, army) {
  if (!forcedMarchActive(army)) return null;
  const limit = forcedMarchRules().tiles;
  if (limit <= 1) return null;
  if (!cellUsableForForcedMarch(destination)) return null;
  const queue = [{ cell: source, path: [source] }];
  const visited = new Set([source.key]);
  while (queue.length) {
    const { cell, path } = queue.shift();
    if (cell.key === destination.key) return path;
    if (path.length > limit) continue;
    for (const next of cellNeighbors(cell)) {
      if (visited.has(next.key)) continue;
      if (!cellUsableForForcedMarch(next)) continue;
      if (!riverStepAllowed(cell, next, false)) continue;
      visited.add(next.key);
      queue.push({ cell: next, path: [...path, next] });
    }
  }
  return null;
}

function railwayMoveLimit(player = currentPlayer) {
  const active = state.players[player]?.timed_effects || [];
  return active.reduce((limit, effect) => {
    if (effect.kind !== "rail_movement" || Number(effect.remaining_turns || 0) <= 0) return limit;
    return Math.max(limit, Number(effect.tiles || limit));
  }, 3);
}

// ── NPC 自動增兵 ────────────────────────────────────────────────
// 只有 NPC 勢力會自己長兵：每 3 回合每支部隊 +1 步兵，每 5 回合各家大帥
// +1 隨機重武器（機槍／騎兵／砲兵）。交戰中照樣成長；但一支部隊只要被玩家
// 策反或招降過，它的成長就永久停止，不因為之後怎麼易手而恢復。
const NPC_FACTIONS = ["Y", "G", "M", "H", "C", "D", "Q"];
const NPC_GROWTH = {
  infantryEveryTurns: 3,
  heavyEveryTurns: 5,
  heavyUnits: ["machine_gun", "cavalry", "artillery"],
};

// 大帥被俘或陣亡的陣營。後端沒有將領資料，內閣卡的失效條件要靠這份回報。
// 各陣營大帥的 general_id。引擎不持有將領資料，暗殺類事件要靠這份名單擲骰。
function factionMarshalIds() {
  const out = {};
  for (const faction of TURN_PLAYERS) {
    const marshalId = generalTrees[faction]?.great_general_id;
    if (marshalId) out[faction] = marshalId;
  }
  return out;
}

function fallenMarshals() {
  const fallen = [];
  for (const faction of TURN_PLAYERS) {
    const marshalId = generalTrees[faction]?.great_general_id;
    if (!marshalId) continue;
    const general = generalTrees[faction]?.generals?.[marshalId];
    const army = allArmies(true).find((item) => item.generalId === marshalId);
    const captured = army?.status === "jailed" || general?.status === "captured";
    const killed = general?.status === "killed" || army?.status === "killed";
    if (captured || killed) fallen.push(faction);
  }
  return fallen;
}

// 川軍與湘軍所有將領平行、沒有大帥，所以沒有五回合的重武器成長。
function npcMarshalArmyIds() {
  const ids = [];
  for (const faction of NPC_FACTIONS) {
    const marshalId = generalTrees[faction]?.great_general_id;
    if (!marshalId) continue;
    const army = (ARMY_POSITIONS[faction] || []).find((item) => item.generalId === marshalId);
    if (army) ids.push(army.id);
  }
  return ids;
}

// 跳槽過的部隊永久除名：發現原本的 NPC 將領現在屬於別家，就蓋上印記。
function markDefectedNpcArmies() {
  for (const faction of NPC_FACTIONS) {
    for (const army of ARMY_POSITIONS[faction] || []) {
      if (army.npcGrowthEnded) continue;
      const owner = generalOwners[army.generalId];
      // 兩個判準都看：將領歸屬換人（招降），或部隊本身改掛別家旗（策反）。
      if ((owner && owner !== faction) || (army.faction && army.faction !== faction)) {
        army.npcGrowthEnded = true;
      }
    }
  }
}

function npcArmyCanGrow(army) {
  if (!army || army.npcGrowthEnded) return false;
  if (["jailed", "killed", "destroyed", "surrendered"].includes(army.status)) return false;
  return forcePoints(armyUnits(army)) < armyForceCap();
}

function applyNpcReinforcements(turn = Number(state?.turn || 0)) {
  markDefectedNpcArmies();
  const grown = [];
  if (turn <= 0) return grown;
  const marshalIds = new Set(npcMarshalArmyIds());
  const infantryTurn = turn % NPC_GROWTH.infantryEveryTurns === 0;
  const heavyTurn = turn % NPC_GROWTH.heavyEveryTurns === 0;
  if (!infantryTurn && !heavyTurn) return grown;
  const capPoints = bootstrap?.features?.unit_force_points
    || { infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4 };
  for (const faction of NPC_FACTIONS) {
    for (const army of ARMY_POSITIONS[faction] || []) {
      if (!npcArmyCanGrow(army)) continue;
      const gains = [];
      if (infantryTurn && forcePoints(armyUnits(army)) + Number(capPoints.infantry || 1) <= armyForceCap()) {
        army.units.infantry = Number(army.units.infantry || 0) + 1;
        gains.push("步兵");
      }
      if (heavyTurn && marshalIds.has(army.id)) {
        // 上限放不下的兵種就從候選裡剔除，剩下的才抽。
        const room = armyForceCap() - forcePoints(armyUnits(army));
        const choices = NPC_GROWTH.heavyUnits.filter((unit) => Number(capPoints[unit] || 0) <= room);
        if (choices.length) {
          const pick = choices[Math.floor(Math.random() * choices.length)];
          army.units[pick] = Number(army.units[pick] || 0) + 1;
          gains.push(UNIT_META[pick]?.name || pick);
        }
      }
      army.units = clampUnitsToForceCap(army.units);
      if (gains.length) grown.push(`${FACTIONS[faction]?.shortName || faction} ${army.designator}：+${gains.join("、+")}`);
    }
  }
  return grown;
}


// ── 事件卡：《民國報》 ────────────────────────────────────────────────
// 每三回合後端會抽四張事件卡，抽到的順序是奉 → 直 → 五 → 國。畫面上不做「抽卡」
// 動作，而是直接跳出一張民國老報紙；玩家回應完四張，本回合的經濟才會結算。
let newspaperCardKey = null;
// 正在等第二層選擇的那個選項 id（例如售與洋商在等你挑買家）。
let newspaperFollowUp = null;

function pendingEventState() {
  const pending = state?.pending_events;
  if (!pending) return null;
  const index = Number(pending.index || 0);
  const entry = (pending.cards || [])[index];
  if (!entry) return null;
  const card = (bootstrap?.cards?.event || []).find((item) => item.id === entry.card_id)
    || eventCardIndex[entry.card_id];
  if (!card) return null;
  const answered = entry.responses || {};
  const strict = Boolean(bootstrap?.event_draw_rules?.strict_response_order);
  const factions = Object.keys(state?.players || {});
  let waiting;
  if (strict) {
    waiting = (entry.responders || []).filter((code) => !(code in answered));
  } else {
    waiting = Object.keys(answered).length ? [] : ((entry.responders || []).length ? entry.responders : factions);
  }
  return {
    turn: pending.turn,
    index,
    total: (pending.cards || []).length,
    card,
    drawer: entry.drawer,
    responders: entry.responders || [],
    responses: answered,
    // 暗殺類事件在抽出當下就擲好骰，結果掛在 pending 那一筆上；
    // 報紙的「本報附誌」要照它寫出成敗。
    assassination: entry.assassination || null,
    strict,
    needsEveryone: false,
    pendingResponders: waiting,
    // 寬鬆模式下這只用來顯示「還缺誰」，不再拿來鎖按鈕。
    waitingFor: waiting[0] || null,
  };
}

// 事件卡跟功能卡一樣由 bootstrap 帶下來，不另外抓檔案。
let eventCardIndex = {};

function loadEventCards() {
  eventCardIndex = Object.fromEntries((bootstrap?.cards?.event || []).map((card) => [card.id, card]));
}

// 設計稿沿用 Markdown 的 **粗體**，報紙上要轉成真的粗體而不是露出星號。
function newspaperInline(text) {
  return String(text || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`(.+?)`/g, "$1");
}

// 設計稿的效果欄有些是條列式，抽出來存進 JSON 時被併成一行（「⋯：<空格>-<空格>通電支持：⋯」），
// 這裡拆回條列。分隔符認的是半形連字號兩側帶空白；效果文字裡的負號一律用全形減號 U+2212，
// 所以不會誤切。第一段（冒號結尾的引言）不是條目，單獨當一段。
// 效果文字裡的換行是段落界線（11.5 的「報紙依判定結果擇一刊出」就是條列之後的收尾句），
// 條列與收尾句分屬不同段，所以先切段、再在段內切條目。
function newspaperEffectMarkup(effect) {
  const blocks = String(effect || "").split(/\n+/).map((block) => block.trim()).filter(Boolean);
  return blocks.map((block) => {
    const parts = block.split(/\s+-\s+/).map((part) => part.trim()).filter(Boolean);
    if (!parts.length) return "";
    const [lead, ...items] = parts;
    const leadHtml = `<p class="newspaper-effect-line">${newspaperInline(lead)}</p>`;
    if (!items.length) return leadHtml;
    return leadHtml + `<ul class="newspaper-effect-list">${
      items.map((item) => `<li>${newspaperInline(item)}</li>`).join("")}</ul>`;
  }).join("");
}

// 暗殺類事件：骰子在抽出當下就擲過了，報紙的「本報附誌」要照實寫出成敗，
// 不能只寫「將進行一次暗殺」讓玩家自己猜。
function assassinationVerdictMarkup(outcome) {
  if (!outcome) return "";
  const chance = Math.round(Number(outcome.chance || 0) * 100);
  const guard = Number(outcome.guard_reduction || 0)
    ? `（基礎 ${Math.round(Number(outcome.base_chance || 0) * 100)}%，親衛隊 −${
      Math.round(Number(outcome.guard_reduction) * 100)}%）` : "";
  const verdict = outcome.success
    ? `<b class="newspaper-effect-hit">行刺得手</b>：${
      factionLabel(outcome.target_owner, false)}大帥當場斃命。`
    : `<b>行刺未遂</b>：刺客當場被擒，${factionLabel(outcome.target_owner, false)}大帥無恙。`;
  return `<p class="newspaper-effect-line">${verdict}　成功率 ${chance}%${guard}</p>`;
}

// 有些卡的報紙不只一版（11.5 廢兩改元有「成」與「不成」兩則）。
// 後端在**抽出當下**就擲好骰並回傳 newspaper_index，報紙照結果刊——
// 先前這裡一律刊第 0 則，於是不管實際成不成，玩家看到的都是「今日實行」。
function newspaperForCard(card, index) {
  const variants = card.newspaper_variants;
  if (Array.isArray(variants) && Number.isInteger(index) && variants[index]) {
    return variants[index];
  }
  return card.newspaper || {};
}

function newspaperMarkup(view) {
  const card = view.card;
  const paper = newspaperForCard(card, view.newspaper_index);
  const paragraphs = (paper.paragraphs || [])
    .map((text) => `<p>${newspaperInline(text)}</p>`).join("");
  const notes = (card.apply?.notes || [])
    .map((note) => `<span class="newspaper-note">※ ${newspaperInline(note)}</span>`).join("");
  const resolution = card.resolution || {};
  // 測試版不鎖順序：誰在看誰就能點。唯一擋下的情況是「這一家已經表過態了」。
  const alreadyAnswered = currentPlayer in (view.responses || {});
  const mine = view.strict ? view.waitingFor === currentPlayer : !alreadyAnswered;
  // 有些選項還要再指定一個對象（〈殷墟第一鏟〉的售與洋商要選買家），
  // 點下去之後這一排按鈕會換成第二層。
  const pendingFollowUp = newspaperFollowUp
    && (resolution.options || []).find((option) => option.id === newspaperFollowUp);
  const buttons = pendingFollowUp
    ? `${(pendingFollowUp.follow_up.options || []).map((item) => `
        <button data-event-follow-up="${item.id}" ${mine ? "" : "disabled"}>${item.label}</button>`).join("")}
       <button data-event-follow-cancel>改選</button>`
    : resolution.type === "choice"
      ? (resolution.options || []).map((option) => `
          <button data-event-choice="${option.id}" ${mine ? "" : "disabled"}
            title="${option.effect_text || ""}">${option.label}</button>`).join("")
      : `<button data-event-choice="" ${mine ? "" : "disabled"}>我知道了</button>`;
  const choiceHints = resolution.type === "choice"
    ? `<div class="newspaper-effect"><div class="newspaper-effect-title">行 動 選 項</div>
        <ul class="newspaper-effect-list">${(resolution.options || [])
        .map((option) => `<li><b>${option.label}</b>：${newspaperInline(option.effect_text)}${
          option.follow_up ? `<i>（${newspaperInline(option.follow_up.prompt)}）</i>` : ""}</li>`).join("")}</ul>
        ${resolution.prompt ? `<span class="newspaper-note">${newspaperInline(resolution.prompt)}</span>` : ""}</div>`
    : "";
  const answered = Object.entries(view.responses || {})
    .map(([code, value]) => {
      const label = (resolution.options || []).find((option) => option.id === value)?.label;
      return `${FACTIONS[code]?.shortName || code}：${label || "已閱"}`;
    }).join("　");
  const effectLines = newspaperEffectMarkup(card.effect)
    + assassinationVerdictMarkup(view.assassination);
  const pendingNames = (view.pendingResponders || [])
    .map((code) => FACTIONS[code]?.shortName || code).join("、");
  let waitingText;
  if (pendingFollowUp) {
    waitingText = newspaperInline(pendingFollowUp.follow_up.prompt || "請再指定一個對象");
  } else if (view.strict) {
    waitingText = mine ? "請閣下裁示" : `等待 ${FACTIONS[view.waitingFor]?.name || view.waitingFor} 回應`;
  } else {
    waitingText = alreadyAnswered ? "已閱" : `等待 ${pendingNames || FACTIONS[view.drawer]?.name || view.drawer} 閱報`;
  }
  // 報紙自帶的陣營選擇欄：嚴格順序下玩家得先切到該回應的陣營才點得動按鈕，
  // 不必回主畫面找選單。四張結完報紙一收，這個選單也跟著消失。
  const factionPicker = `
    <label class="newspaper-faction">
      <span>閱報者</span>
      <select data-newspaper-faction>
        ${Object.keys(state?.players || {}).map((code) => `
          <option value="${code}" ${code === currentPlayer ? "selected" : ""}>
            ${FACTIONS[code]?.name || code}${code === view.waitingFor ? "　←應由此家回應" : ""}
          </option>`).join("")}
      </select>
    </label>`;
  return `
    <div class="newspaper-masthead">
      <h1 class="newspaper-title">民國報</h1>
      <div class="newspaper-masthead-right">
        ${factionPicker}
        <div class="newspaper-cardname">${card.name}</div>
      </div>
    </div>
    <div class="newspaper-dateline">
      <span>民國十五年　第 ${view.turn} 回合</span>
      <span class="newspaper-progress">本期第 ${view.index + 1} 則／共 ${view.total} 則</span>
    </div>
    <div class="newspaper-figure" data-event-figure="${card.id}"><span>［ 圖 片 待 補 ］${card.id}</span></div>
    <div class="newspaper-headline">${newspaperInline(paper.headline || card.name)}</div>
    <div class="newspaper-body">${paragraphs}</div>
    <div class="newspaper-effect"><div class="newspaper-effect-title">本 報 附 誌</div>${effectLines}${notes}</div>
    ${choiceHints}
    ${answered ? `<div class="newspaper-responses">已回應　${answered}</div>` : ""}
    <div class="newspaper-actions">
      <span class="newspaper-waiting">${waitingText}</span>
      ${buttons}
    </div>
  `;
}

function renderNewspaper() {
  const backdrop = $("newspaperBackdrop");
  const sheet = $("newspaper");
  if (!backdrop || !sheet) return;
  const view = pendingEventState();
  if (!view) {
    // 四張都結完就把報紙整份清掉，連帶那個陣營選擇欄一起消失，
    // 換陣營回歸主畫面上方的選單，直到下次發報。
    backdrop.hidden = true;
    sheet.innerHTML = "";
    newspaperCardKey = null;
    return;
  }
  const key = `${view.turn}:${view.index}:${currentPlayer}:${Object.keys(view.responses).length}:${newspaperFollowUp || ""}`;
  backdrop.hidden = false;
  if (key === newspaperCardKey) return;
  newspaperCardKey = key;
  sheet.innerHTML = newspaperMarkup(view);
  sheet.scrollTop = 0;
}

async function respondToEvent(choice, followUp = null) {
  const view = pendingEventState();
  if (!view) return;
  if (view.strict && view.waitingFor !== currentPlayer) return;
  if (!view.strict && currentPlayer in (view.responses || {})) return;
  if (view.strict && view.waitingFor && view.waitingFor !== currentPlayer) {
    showNotice(`現在輪到 ${FACTIONS[view.waitingFor]?.name || view.waitingFor} 回應這張事件卡。`);
    return;
  }
  const option = (view.card.resolution?.options || []).find((item) => item.id === choice);
  if (option?.follow_up && !followUp) {
    // 先把按鈕換成第二層，等玩家指定對象再送出。
    newspaperFollowUp = choice;
    newspaperCardKey = null;
    renderNewspaper();
    return;
  }
  for (const button of $("newspaper").querySelectorAll("[data-event-choice]")) button.disabled = true;
  try {
    const cardId = view.card?.id;
    const result = await api("/api/respond-event", {
      player: currentPlayer, choice: choice || null, follow_up: followUp || null,
    });
    state = result.state;
    newspaperFollowUp = null;
    newspaperCardKey = null;
    if (result.card_finished) {
      const notes = applyFrontendEventEffects(cardId);
      // 列強懲戒的部隊／艦隊傷害由後端排進待辦，這裡直接執行，不由玩家自行扣。
      notes.push(...await consumePendingFrontendEffects());
      if (notes.length) showNotice(`${view.card.name}：${notes.join("；")}`);
    }
    if (result.cycle_finished) {
      // 四張都結完了，後端才會把本回合的經濟結算跑完。
      syncStrategicCitiesFromState();
      advanceEngineering();
      const healed = applyFieldHospitalRecovery();
      if (healed.length) showNotice(`傷兵歸隊：${healed.join("；")}`);
      const npcGrowth = applyNpcReinforcements();
      if (npcGrowth.length) showNotice(`NPC 補充兵源：${npcGrowth.join("；")}`);
      normalizeArmyForceCaps();
      refreshArmyLoyaltyBaselines();
      resolvedArmyIds.clear();
      resolvedNavyIds.clear();
      replaceObject(turnReady, {});
      for (const army of allArmies()) {
        delete army.resolvedTurn;
        if (army.specialOperation) markArmyResolved(army);
      }
      for (const navy of allNavies(true)) delete navy.resolvedTurn;
      armyOrderHistory.length = 0;
      navyOrderHistory.length = 0;
      archiveTerminalBattles();
      currentPhase = "military";
      updatePhaseBanner();
      updateFeatureVisibility();
      initMap();
    }
    renderNewspaper();
    updateTopBar();
    renderPendingActions();
    await publishSharedState(true);
  } catch (error) {
    showNotice(error.message);
    newspaperFollowUp = null;
    newspaperCardKey = null;
    renderNewspaper();
  }
}

// 換陣營視角。主畫面上方的選單與報紙右上角的選單共用這一套。
async function switchFaction(code) {
  if (!code || code === currentPlayer) return;
  currentPlayer = code;
  if ($("playerSelect").value !== code) $("playerSelect").value = code;
  selectedArmyId = null;
  selectedNavyId = null;
  selectedBattleId = null;
  moveMode = false;
  navyMoveMode = false;
  uiNotice = null;

  await loadGeneralTreeForFaction(currentPlayer);
  renderArmyMarkers(currentPlayer);
  updateTopBar();
  renderPendingActions();
  newspaperCardKey = null;
  renderNewspaper();

  const openPanel = document.querySelector(".overlay-panel.active");
  if (openPanel) {
    const panelId = openPanel.id.replace("panel", "").toLowerCase();
    renderPanel(panelId.charAt(0).toLowerCase() + panelId.slice(1));
  }
}

// 少數事件卡的效果住在前端（部隊兵力、將領忠誠），後端結完之後由這裡補上。
function applyFrontendEventEffects(cardId) {
  const notes = [];
  if (cardId === "kellogg_briand_pact") {
    // 選了通電支持的那幾家，生效當下仍在打的仗一律強制撤退以結束戰鬥。
    for (const faction of TURN_PLAYERS) {
      const withdrawn = withdrawBattlesForForcedPeace(faction);
      if (withdrawn.length) {
        notes.push(`${factionLabel(faction, faction === currentPlayer)}因強制和平自 ${withdrawn.length} 場戰鬥撤退`);
      }
    }
  }
  if (cardId === "may_coup_wave") {
    // 大帥與嫡系（忠誠不變）將領旗下所有陸軍兵種各 +1 營，受 100 戰力上限限制。
    const points = bootstrap?.features?.unit_force_points
      || { infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4 };
    for (const army of allArmies()) {
      const faction = factionForArmy(army);
      if (!TURN_PLAYERS.includes(faction)) continue;
      const general = generalTrees[faction]?.generals?.[army.generalId];
      const core = general && (general.role === "great_general" || general.loyalty_exempt
        || general.loyalty === null || generalAbsoluteLoyaltyActive(general));
      if (!core) continue;
      const gained = [];
      for (const unit of Object.keys(UNIT_META)) {
        if (!Number(army.units[unit] || 0)) continue;
        if (forcePoints(armyUnits(army)) + Number(points[unit] || 1) > armyForceCap()) continue;
        army.units[unit] = Number(army.units[unit] || 0) + 1;
        gained.push(UNIT_META[unit]?.name || unit);
      }
      if (gained.length) notes.push(`${army.designator}：${gained.join("、")}各 +1 營`);
    }
  }
  if (cardId === "balfour_declaration") {
    // 每位玩家隨機一位可變忠誠將領 +1。
    for (const faction of TURN_PLAYERS) {
      const pool = Object.values(generalTrees[faction]?.generals || {}).filter((general) =>
        general.loyalty !== null && general.loyalty !== undefined
        && !generalAbsoluteLoyaltyActive(general) && !general.loyalty_exempt
        && generalOwners[general.id] === faction);
      if (!pool.length) continue;
      const pick = pool[Math.floor(Math.random() * pool.length)];
      adjustGeneralLoyalty(pick.id, 1);
      notes.push(`${FACTIONS[faction]?.shortName || faction} ${pick.name} 忠誠 +1`);
    }
  }
  return notes;
}

// 非戰公約的強制和平：簽了的人三回合內不得進入他方地格、不得宣戰，
// 因而無從主動開戰（主動開戰必須點敵方地格）。防禦戰照打，且承傷額外 −8%。
// 舊的 kind 是 "ceasefire"，改制後是 "forced_peace"；兩個都認，免得舊存檔讀不到。
function forcedPeaceEffect(faction = currentPlayer) {
  return activeTimedEffects(faction, "forced_peace")[0]
    || activeTimedEffects(faction, "ceasefire")[0]
    || null;
}

// 舊名保留，站台上還有幾處在呼叫。
function ceasefireEffect(faction = currentPlayer) {
  return forcedPeaceEffect(faction);
}

// 和平方在防禦戰裡的額外減傷（承傷 ×0.92），不分戰術一律適用。
function forcedPeaceDefenceModifiers(faction) {
  const peace = forcedPeaceEffect(faction);
  if (!peace) return [];
  const multiplier = Number(peace.defensive_harm_taken_multiplier || 0.92);
  return [{ stat: "harm_taken", multiplier, source_effect: peace.name || "強制和平" }];
}

// 事件生效當下仍在進行中的戰鬥：和平方一律強制撤退以結束戰鬥。
function withdrawBattlesForForcedPeace(faction) {
  const peace = forcedPeaceEffect(faction);
  if (!peace || !peace.withdraw_active_battles) return [];
  const withdrawn = [];
  for (const battle of [...activeBattles]) {
    if (!["pending", "ongoing"].includes(battle.status)) continue;
    const side = battle.attackerFaction === faction ? "A"
      : battle.defenderFaction === faction ? "B" : null;
    if (!side) continue;
    retreatFromBattle(battle, side);
    withdrawn.push(battle.id);
  }
  return withdrawn;
}

// 女子救護隊：三回合內所有部隊都吃戰後傷兵歸隊，不必買盤尼西林。
function fieldHospitalWindowActive(faction) {
  return activeTimedEffects(faction, "field_hospital_window").length > 0;
}

function setupNewspaper() {
  const sheet = $("newspaper");
  if (!sheet) return;
  sheet.addEventListener("click", (event) => {
    const cancel = event.target.closest("[data-event-follow-cancel]");
    if (cancel) {
      newspaperFollowUp = null;
      newspaperCardKey = null;
      renderNewspaper();
      return;
    }
    const followUp = event.target.closest("[data-event-follow-up]");
    if (followUp && !followUp.disabled) {
      respondToEvent(newspaperFollowUp, followUp.dataset.eventFollowUp);
      return;
    }
    const button = event.target.closest("[data-event-choice]");
    if (!button || button.disabled) return;
    respondToEvent(button.dataset.eventChoice || null);
  });
  sheet.addEventListener("change", (event) => {
    const picker = event.target.closest("[data-newspaper-faction]");
    if (picker) switchFaction(picker.value);
  });
}

function advanceEngineering() {
  for (const army of Object.values(ARMY_POSITIONS).flat()) {
    if (!army.specialOperation) continue;
    army.specialOperation.turnsRemaining -= 1;
    if (army.specialOperation.turnsRemaining > 0) continue;
    if (army.specialOperation.id === "pontoon_bridge") completedPontoons.add(army.specialOperation.targetCellKey);
    if (army.specialOperation.id === "fortress_builder") completedFortresses.add(army.specialOperation.targetCellKey);
    delete army.specialOperation;
  }
}

function setArmyTotalUnits(army, totals, options = {}) {
  const currentUnits = options.currentUnits || armyUnits(army);
  const normalized = wholeUnits(totals);
  const cappedTotals = options.capAtCurrent
    ? Object.fromEntries(Object.keys(UNIT_META).map((type) => [
      type,
      Math.min(Number(normalized[type] || 0), Number(currentUnits[type] || 0)),
    ]))
    : normalized;
  army.units = clampUnitsToForceCap(cappedTotals);
  const general = generalById(army.generalId);
  if (general) general.units = { ...army.units };
}

function transferArmyUnit(fromArmy, toArmy, unitType, count = 1) {
  if (!absoluteTransferPair(fromArmy, toArmy)) {
    showNotice("只有相鄰的大元帥與絕對忠誠將領可以自由調兵。");
    return;
  }
  const sourceUnits = armyUnits(fromArmy);
  if ((sourceUnits[unitType] || 0) < count) {
    showNotice(`${fromArmy.general}沒有可調出的${UNIT_META[unitType]?.name || unitType}。`);
    return;
  }
  const targetUnits = armyUnits(toArmy);
  sourceUnits[unitType] -= count;
  targetUnits[unitType] = (targetUnits[unitType] || 0) + count;
  setArmyTotalUnits(fromArmy, sourceUnits);
  setArmyTotalUnits(toArmy, targetUnits);
  uiNotice = `絕對忠誠調兵：${fromArmy.general}撥給${toArmy.general}${UNIT_META[unitType]?.name || unitType} ${count} 營。`;
  renderArmyDetail();
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
}

function absoluteTransferMarkup(army) {
  const partners = absoluteTransferPartners(army);
  if (!partners.length) return "";
  const ownUnits = armyUnits(army);
  return `
    <div class="army-free-transfer">
      <b>絕對忠誠調兵</b>
      <small>相鄰的大元帥與固定忠誠將領可互相調動部隊。</small>
      ${partners.map((partner) => {
        const partnerUnits = armyUnits(partner);
        return `
          <div class="transfer-row">
            <span>${partner.general}</span>
            <div class="transfer-buttons">
              ${Object.entries(UNIT_META).map(([type, unit]) => `
                <button data-transfer-unit="${type}" data-transfer-from="${army.id}" data-transfer-to="${partner.id}" ${ownUnits[type] ? "" : "disabled"}>給${unit.short}</button>
                <button data-transfer-unit="${type}" data-transfer-from="${partner.id}" data-transfer-to="${army.id}" ${partnerUnits[type] ? "" : "disabled"}>收${unit.short}</button>
              `).join("")}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

// 技能是否因為所屬陣營的列強關係而失效（張宗昌的〈白俄傭兵〉）。
function traitDisabledByRelations(trait, faction) {
  const rule = RELATION_DISABLED_TRAITS[trait];
  if (!rule) return false;
  const value = Number(state?.players?.[faction]?.foreign_relations?.[rule.power] ?? 0);
  if (rule.min !== undefined && value >= rule.min) return true;
  if (rule.max !== undefined && value <= rule.max) return true;
  return false;
}

// 這場戰鬥打在哪個省。攻方部隊還站在出發格，所以優先看戰場那一格。
function battleProvince(army, battle) {
  const battleCell = battle?.cellKey ? cells[battle.cellKey] : null;
  return (battleCell ? strategicProvinceForCell(battleCell) : null) || provinceForArmy(army);
}

function generalIdsOnSide(battle, side) {
  return battleArmies(battle, side).map((army) => army.generalId);
}

function combatTraitModifiers(army, battle = null, opponentFaction = null) {
  const faction = factionForArmy(army);
  const traits = generalTrees[faction]?.generals?.[army.generalId]?.traits || [];
  const side = battle ? battleSideForArmy(battle, army) : null;
  const enemySide = side === "A" ? "B" : side === "B" ? "A" : null;
  const allyIds = side ? generalIdsOnSide(battle, side) : [];
  const enemyIds = enemySide ? generalIdsOnSide(battle, enemySide) : [];
  return traits.flatMap((trait) => {
    if (traitDisabledByRelations(trait, faction)) return [];
    const extra = [];

    // 只在特定省份生效（水域作戰、山地師、精銳山地師）。
    const province = PROVINCE_CONDITIONAL_TRAITS[trait];
    if (province && province.provinces.has(battleProvince(army, battle))) extra.push(...province.modifiers);

    // 指定友軍同戰場才生效（盧永祥要段祺瑞在場）。
    const ally = ALLY_PRESENCE_TRAITS[trait];
    if (ally && ally.allies.some((id) => id !== army.generalId && allyIds.includes(id))) extra.push(...ally.modifiers);

    // 對面出現指定將領才生效（趙恒惕碰上唐生智）。
    const enemy = ENEMY_PRESENCE_TRAITS[trait];
    if (enemy && enemy.enemies.some((id) => enemyIds.includes(id))) extra.push(...enemy.modifiers);

    // 敵方陣營對某列強夠友好才生效（何鍵打親蘇勢力）。
    const enemyRelation = ENEMY_RELATION_TRAITS[trait];
    if (enemyRelation && opponentFaction) {
      const value = Number(state?.players?.[opponentFaction]?.foreign_relations?.[enemyRelation.power] ?? 0);
      if (value >= enemyRelation.min) extra.push(...enemyRelation.modifiers);
    }

    return [...traitModifiers(trait), ...extra].map((modifier) => ({ ...modifier }));
  });
}

// 光環：同一場戰鬥、同一邊的友軍將領帶來的加成（規則 42、43）。
function combatAuraModifiers(army, battle) {
  if (!battle) return [];
  const side = battleSideForArmy(battle, army);
  if (!side) return [];
  return battleArmies(battle, side).flatMap((ally) => {
    if (ally.id === army.id) return [];
    const allyFaction = factionForArmy(ally);
    const allyTraits = generalTrees[allyFaction]?.generals?.[ally.generalId]?.traits || [];
    return allyTraits.flatMap((trait) => {
      const aura = AURA_TRAITS[trait];
      if (!aura || !aura.partners.includes(army.generalId)) return [];
      return aura.modifiers.map((modifier) => ({ ...modifier, source_aura: trait }));
    });
  });
}

function timedCombatModifiers(faction, opponentFaction = null) {
  return (state.players[faction]?.timed_effects || []).flatMap((effect) => {
    if (effect.kind !== "combat_modifier" || Number(effect.remaining_turns || 0) <= 0) return [];
    if (effect.target_faction && opponentFaction && effect.target_faction !== opponentFaction) return [];
    // 列強戰鬥 perk 只在關係還撐得住時生效；後端也會清，這裡再擋一次避免打到一半的殘留。
    if (effect.expires_below_relation != null && effect.foreign_power_key) {
      const relation = Number(state.players[faction]?.foreign_relations?.[effect.foreign_power_key] ?? 0);
      if (relation < Number(effect.expires_below_relation)) return [];
    }
    return (effect.modifiers || []).map((modifier) => ({ ...modifier, source_effect: effect.name }));
  });
}

// 8.2 戈達德的火箭：找到發生戰鬥的部隊 → 判斷戰鬥地格內有沒有「要塞」這道工事
// → 有的話**雙方**砲兵攻擊 +5%（攻方打的是要塞駐軍，守方是作為要塞守軍），沒有就不調整。
// 卡片抽出後會替所有玩家寫入 event_goddard_rocket 解鎖旗標，這條規則才啟用。
function fortressArtilleryModifiers(faction, battle, army) {
  if (!(state?.players?.[faction]?.unlocks || []).includes("event_goddard_rocket")) return [];
  const cellKey = battle?.cellKey
    || activeBattles.find((item) => battleSideForArmy(item, army))?.cellKey;
  if (!cellKey || !completedFortresses.has(cellKey)) return [];
  return [{ stat: "attack", unit: "artillery", multiplier: 1.05, source_effect: "戈達德的火箭" }];
}

function combatArmyPayload(army, tactic, defending = false, battle = null, opponentFaction = null) {
  const faction = factionForArmy(army);
  return {
    name: army.id,
    units: armyUnits(army),
    initial_units: battle?.initialByArmy?.[army.id] || armyUnits(army),
    tactic,
    modifiers: [
      ...combatTraitModifiers(army, battle, opponentFaction),
      ...combatAuraModifiers(army, battle),
      ...timedCombatModifiers(faction, opponentFaction),
      ...fortressArtilleryModifiers(faction, battle, army),
      ...(defending ? forcedPeaceDefenceModifiers(faction) : []),
      ...(defending && completedFortresses.has(activeBattles.find((battle) => battleSideForArmy(battle, army))?.cellKey)
        ? [{ stat: "harm_taken", multiplier: 0.65 }]
        : []),
    ],
  };
}

const NO_CAPTURE_FACTIONS = [];

function armyCanBeCaptured(army) {
  const originFaction = generalOwners[army?.generalId] || factionForArmy(army);
  return !NO_CAPTURE_FACTIONS.includes(originFaction);
}

function annihilateArmy(army, battle, action = null) {
  const originFaction = generalOwners[army.generalId] || factionForArmy(army);
  const reinforcementLedger = state.players[originFaction]?.army_reinforcements;
  if (reinforcementLedger) delete reinforcementLedger[army.id];
  army.units = Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0]));
  army.status = "destroyed";
  const general = generalTrees[originFaction]?.generals?.[army.generalId];
  if (general) general.status = "killed";
  if (action) action.annihilated = { armyId: army.id, faction: originFaction };
  const destroyedSide = battleSideForArmy(battle, army) || (army.id === battle.attackerId ? "A" : "B");
  battle.status = "surrendered";
  battle.surrenderedSide = destroyedSide;
  battle.annihilatedSide = destroyedSide;
  battle.result = {
    winner: destroyedSide === "A" ? "B" : "A",
    rounds: battle.rounds || 0,
    remaining: {
      A: { units: destroyedSide === "A" ? Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0])) : battleSideUnits(battle, "A") },
      B: { units: destroyedSide === "B" ? Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0])) : battleSideUnits(battle, "B") },
    },
  };
  if (destroyedSide === "B") occupyTile(cells[battle.cellKey], battle.attackerFaction, action);
  markArmyResolved(army);
  uiNotice = `${army.general}兵力潰散，就地消滅。黔軍沒有可俘虜的將領。`;
}

function surrenderArmy(army, captorFaction, battle, action = null) {
  if (!armyCanBeCaptured(army)) {
    annihilateArmy(army, battle, action);
    return;
  }
  const originFaction = generalOwners[army.generalId] || factionForArmy(army);
  const general = generalTrees[originFaction]?.generals?.[army.generalId] || {
    id: army.generalId,
    name: army.general,
    traits: [],
    skills: [],
    units: { ...army.units },
  };
  jailedGenerals[captorFaction] ||= [];
  const capturedRecords = [];
  const jailFieldArmy = (fieldArmy) => {
    if (action) {
      action.capturedBranchBefore ||= {};
      action.capturedBranchBefore[fieldArmy.id] ||= {
        id: fieldArmy.id,
        faction: factionForArmy(fieldArmy),
        cellKey: fieldArmy.cellKey,
        lon: fieldArmy.lon,
        lat: fieldArmy.lat,
        units: { ...fieldArmy.units },
        reinforcements: { ...(state.players[factionForArmy(fieldArmy)]?.army_reinforcements?.[fieldArmy.id] || {}) },
        status: fieldArmy.status,
      };
    }
    const reinforcementLedger = state.players[originFaction]?.army_reinforcements;
    if (reinforcementLedger) delete reinforcementLedger[fieldArmy.id];
    fieldArmy.units = Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0]));
    fieldArmy.status = "jailed";
    markArmyResolved(fieldArmy);
  };
  const captureGeneral = (capturedGeneral, fieldArmy, options = {}) => {
    if (!capturedGeneral || !fieldArmy) return;
    if (jailedGenerals[captorFaction].some((record) => record.general?.id === capturedGeneral.id)) return;
    const preservedUnits = wholeUnits(armyUnits(fieldArmy));
    const capturedCopy = {
      ...JSON.parse(JSON.stringify(capturedGeneral)),
      status: "jailed",
      units: preservedUnits,
    };
    if (options.loyalty !== undefined && capturedCopy.loyalty !== null) {
      capturedCopy.loyalty = options.loyalty;
    }
    const record = {
      armyId: fieldArmy.id,
      originFaction,
      capturedTurn: state.turn,
      cellKey: fieldArmy.cellKey,
      lon: fieldArmy.lon,
      lat: fieldArmy.lat,
      general: capturedCopy,
    };
    jailFieldArmy(fieldArmy);
    jailedGenerals[captorFaction].push(record);
    capturedRecords.push(record);
  };
  captureGeneral(general, army);
  const affectedDescendants = commandDescendantIds(generalTrees[originFaction], army.generalId, general)
    .filter((id) => generalTrees[originFaction]?.generals?.[id]);
  if (action) {
    action.loyaltyBefore ||= {};
    for (const id of affectedDescendants) {
      action.loyaltyBefore[id] = Object.hasOwn(loyaltyOverrides, id) ? loyaltyOverrides[id] : null;
    }
  }
  for (const generalId of affectedDescendants) {
    const subordinate = generalTrees[originFaction]?.generals?.[generalId];
    if (!subordinate) continue;
    subordinate.loyalty_exempt = false;
    if (subordinate.loyalty !== null && subordinate.loyalty !== undefined) subordinate.loyalty = 1;
    loyaltyOverrides[generalId] = 1;
  }
  if (action) {
    action.prisoner = { captor: captorFaction, armyId: army.id };
    action.prisoners = capturedRecords.map((record) => ({ captor: captorFaction, armyId: record.armyId }));
  }
  const attacker = armyById(battle.attackerId);
  const defender = armyById(battle.defenderId);
  const surrenderedSide = battleSideForArmy(battle, army) || (army.id === battle.attackerId ? "A" : "B");
  battle.status = "surrendered";
  battle.surrenderedSide = surrenderedSide;
  battle.result = {
    winner: surrenderedSide === "A" ? "B" : "A",
    rounds: battle.rounds || 0,
    remaining: {
      A: { units: surrenderedSide === "A" ? Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0])) : battleSideUnits(battle, "A") },
      B: { units: surrenderedSide === "B" ? Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0])) : battleSideUnits(battle, "B") },
    },
  };
  if (surrenderedSide === "B") occupyTile(cells[battle.cellKey], battle.attackerFaction, action);
  uiNotice = `${army.general}兵力不足，遭攻擊後投降並被收押。可在將領樹的被俘將領區招降。`;
}

function retreatCellFor(army, preferredKey = null, awayFromKey = null) {
  if (preferredKey && cells[preferredKey]
    && !allArmies().some((other) => other.id !== army.id && other.cellKey === preferredKey)) {
    return cells[preferredKey];
  }
  const source = cells[army.cellKey];
  const faction = factionForArmy(army);
  const awayFrom = cells[awayFromKey];
  const direction = awayFrom
    ? [hcx(source.c) - hcx(awayFrom.c), hcy(source.c, source.r) - hcy(awayFrom.c, awayFrom.r)]
    : [0, 0];
  const candidates = cellNeighbors(source).filter((cell) =>
    !allArmies().some((other) => other.id !== army.id && other.cellKey === cell.key)
    && riverStepAllowed(source, cell, Boolean(source.railNeighbors?.has(cell.key)))
  ).sort((a, b) => {
    const score = (cell) => (cell.fac === faction ? 10000 : 0)
      + (hcx(cell.c) - hcx(source.c)) * direction[0]
      + (hcy(cell.c, cell.r) - hcy(source.c, source.r)) * direction[1];
    return score(b) - score(a);
  });
  return candidates.find((cell) => cell.fac === faction)
    || candidates.find((cell) =>
      state.players[faction]?.warlord_relations?.[cell.fac]?.status === "war"
      && !allArmies().some((other) => other.id !== army.id && other.cellKey === cell.key)
    ) || null;
}

function moveArmyToCell(army, cell) {
  if (!cell) return;
  army.cellKey = cell.key;
  army.lon = cell.lon;
  army.lat = cell.lat;
}

function battleWinnerSide(result, strengthA, strengthB) {
  if (result?.winner === "A" || result?.winner === "B") return result.winner;
  if (result?.winner === "draw" || result?.winner === "undecided") return null;
  return strengthA === strengthB ? null : (strengthA > strengthB ? "A" : "B");
}

function overrunSurrenderSide(result, strengthA, strengthB) {
  const winner = battleWinnerSide(result, strengthA, strengthB);
  if (!winner) return null;
  const loser = winner === "A" ? "B" : "A";
  const winnerStrength = winner === "A" ? strengthA : strengthB;
  const loserStrength = loser === "A" ? strengthA : strengthB;
  if (loserStrength <= 0) return loser;
  if (loserStrength <= OVERRUN_SURRENDER_FORCE && winnerStrength >= loserStrength * OVERRUN_FORCE_RATIO) return loser;
  return null;
}

function sideHasRetreatCell(battle, side) {
  const army = armyById(side === "A" ? battle.attackerId : battle.defenderId);
  if (!army) return false;
  if (side === "A") {
    const origin = cells[battle.attackerOrigin];
    return Boolean(origin && !allArmies().some((other) => other.id !== army.id && other.cellKey === origin.key));
  }
  return Boolean(retreatCellFor(army, null, battle.attackerOrigin));
}

async function resolveBattleRound(battle) {
  const attacker = armyById(battle.attackerId);
  const defender = armyById(battle.defenderId);
  const combatArmies = {
    A: [...battleArmies(battle, "A")].sort((first, second) => forcePoints(armyUnits(second)) - forcePoints(armyUnits(first))),
    B: [...battleArmies(battle, "B")].sort((first, second) => forcePoints(armyUnits(second)) - forcePoints(armyUnits(first))),
  };
  const reinforcements = ["A", "B"].flatMap((side) =>
    combatArmies[side].slice(1).map((army) => {
      const opponentFaction = side === "A" ? battle.defenderFaction : battle.attackerFaction;
      return {
        round: 1,
        side,
        army: combatArmyPayload(army, battle.tactics[side], side === "B", battle, opponentFaction),
      };
    })
  );
  const result = await api("/api/combat", {
    army_a: combatArmyPayload(combatArmies.A[0], battle.tactics.A, false, battle, battle.defenderFaction),
    army_b: combatArmyPayload(combatArmies.B[0], battle.tactics.B, true, battle, battle.attackerFaction),
    reinforcements,
    max_rounds: 1,
  });
  battle.rounds = (battle.rounds || 0) + result.rounds;
  result.rounds = battle.rounds;
  battle.result = result;
  battle.roundResolvedTurn = state.turn;
  for (const side of ["A", "B"]) {
    const remainingById = new Map((result.remaining[side].armies || []).map((army) => [army.name, army.units]));
    for (const army of battleArmies(battle, side)) {
      const before = { ...armyUnits(army) };
      setArmyTotalUnits(army, remainingById.get(army.id) || armyUnits(army), {
        capAtCurrent: true,
        currentUnits: before,
      });
      recordCombatLosses(army, before);
    }
  }
  const action = armyOrderHistory.find((item) => item.battleId === battle.id) || null;
  const strengthA = forcePoints(result.remaining.A.units);
  const strengthB = forcePoints(result.remaining.B.units);
  const overrunSide = overrunSurrenderSide(result, strengthA, strengthB);
  const winnerSide = battleWinnerSide(result, strengthA, strengthB);
  if (strengthA <= 5 && strengthB > 5) {
    for (const army of battleArmies(battle, "A")) surrenderArmy(army, battle.defenderFaction, battle, action);
    battle.surrenderedSide = "A";
  } else if (strengthB <= 5 && strengthA > 5) {
    for (const army of battleArmies(battle, "B")) surrenderArmy(army, battle.attackerFaction, battle, action);
    battle.surrenderedSide = "B";
  } else if (overrunSide === "A") {
    for (const army of battleArmies(battle, "A")) surrenderArmy(army, battle.defenderFaction, battle, action);
    battle.surrenderedSide = "A";
    uiNotice = "敗軍兵力過小且遭優勢兵力追擊，無法重新整隊，已被迫投降。";
  } else if (overrunSide === "B") {
    for (const army of battleArmies(battle, "B")) surrenderArmy(army, battle.attackerFaction, battle, action);
    battle.surrenderedSide = "B";
    uiNotice = "敗軍兵力過小且遭優勢兵力追擊，無法重新整隊，已被迫投降。";
  } else if (winnerSide === "A" && !sideHasRetreatCell(battle, "B")) {
    for (const army of battleArmies(battle, "B")) surrenderArmy(army, battle.attackerFaction, battle, action);
    battle.surrenderedSide = "B";
    uiNotice = "敗軍無可用退路，已被迫投降。";
  } else if (winnerSide === "B" && !sideHasRetreatCell(battle, "A")) {
    for (const army of battleArmies(battle, "A")) surrenderArmy(army, battle.defenderFaction, battle, action);
    battle.surrenderedSide = "A";
    uiNotice = "敗軍無可用退路，已被迫投降。";
  } else if (result.winner === "undecided") {
    battle.status = "ongoing";
    battle.confirmed = { A: true, B: true };
    markArmyResolved(attacker);
    markArmyResolved(defender);
    uiNotice = `第 ${battle.rounds} 輪戰鬥結束；交戰將延續至下一回合。`;
    initMap();
    renderPendingActions();
    return;
  } else if (result.winner === "B") {
    battle.status = "resolved";
    moveArmyToCell(attacker, cells[battle.attackerOrigin]);
  } else if (result.winner === "A") {
    battle.status = "resolved";
    moveArmyToCell(defender, retreatCellFor(defender, null, battle.attackerOrigin));
    occupyTile(cells[battle.cellKey], battle.attackerFaction, action);
  } else if (result.winner === "draw") {
    battle.status = "resolved";
    moveArmyToCell(attacker, cells[battle.attackerOrigin]);
    moveArmyToCell(defender, retreatCellFor(defender, null, battle.attackerOrigin));
  } else if (strengthA >= strengthB) {
    battle.status = "resolved";
    battle.result.winner = "A";
    moveArmyToCell(defender, retreatCellFor(defender, null, battle.attackerOrigin));
    occupyTile(cells[battle.cellKey], battle.attackerFaction, action);
  } else {
    battle.status = "resolved";
    battle.result.winner = "B";
    moveArmyToCell(attacker, cells[battle.attackerOrigin]);
  }
  markArmyResolved(attacker);
  markArmyResolved(defender);
  if (battle.status !== "surrendered" || !uiNotice) {
    uiNotice = "戰鬥結束。點擊地圖上的戰鬥圖示可再次查看兵力與分類傷亡。";
  }
  initMap();
  renderPendingActions();
}

async function confirmBattleTactic(battle, side) {
  if (!battle || !battle.tacticRevision?.[side]) return;
  battle.confirmed ||= { A: false, B: false };
  battle.confirmed[side] = true;
  battle.tacticRevision[side] = false;
  applyNpcBattleDefaults(battle);
  renderPendingActions();
  if (!battle.confirmed.A || !battle.confirmed.B) {
    const waitingFaction = side === "A" ? battle.defenderFaction : battle.attackerFaction;
    showNotice(`戰術已確認；請切換至${FACTIONS[waitingFaction].shortName}決定另一方戰術。`);
    return;
  }
  if ((battle.rounds || 0) === 0 && battle.roundResolvedTurn !== state.turn) await resolveBattleRound(battle);
}

function retreatFromBattle(battle, side) {
  retreatConfirmations.delete(retreatConfirmationKey(battle, side));
  const army = armyById(side === "A" ? battle.attackerId : battle.defenderId);
  const destination = side === "A"
    ? cells[battle.attackerOrigin]
    : retreatCellFor(army, null, battle.attackerOrigin);
  if (!destination) {
    showNotice("沒有可供撤退的己方相鄰地格。");
    return;
  }
  moveArmyToCell(army, destination);
  battle.status = "retreated";
  battle.retreatingSide = side;
  if (side === "B") {
    const action = armyOrderHistory.find((item) => item.battleId === battle.id) || null;
    occupyTile(cells[battle.cellKey], battle.attackerFaction, action);
  }
  markArmyResolved(army);
  uiNotice = `${army.designator}已撤出戰鬥。`;
  initMap();
  renderPendingActions();
}

function requestBattleRetreat(battle, side) {
  if (!battle || !side) return;
  const key = retreatConfirmationKey(battle, side);
  if (retreatIsArmed(battle, side)) {
    retreatConfirmations.delete(key);
    retreatFromBattle(battle, side);
    return;
  }
  const expiresAt = Date.now() + RETREAT_CONFIRMATION_MS;
  retreatConfirmations.set(key, expiresAt);
  uiNotice = "撤退尚未執行；請在三秒內再次點擊「確認撤退」。";
  renderPendingActions();
  setTimeout(() => {
    if (retreatConfirmations.get(key) !== expiresAt) return;
    retreatConfirmations.delete(key);
    if (activeBattles.some((item) => item.id === battle.id)) renderPendingActions();
  }, RETREAT_CONFIRMATION_MS);
}

function setupPendingActions() {
  $("dealInboxBadge").addEventListener("click", () => {
    closeAllPanels();
    uiNotice = null;
    renderPendingActions();
  });
  $("pendingList").addEventListener("click", (event) => {
    const battleAction = event.target.closest("[data-resolve-battle], [data-retreat-battle]");
    if (battleAction) {
      const battleId = Number(battleAction.dataset.resolveBattle || battleAction.dataset.retreatBattle);
      const battle = activeBattles.find((item) => item.id === battleId);
      const side = battle?.attackerFaction === currentPlayer ? "A" : "B";
      if (battleAction.dataset.retreatBattle) requestBattleRetreat(battle, side);
      else confirmBattleTactic(battle, side).catch((error) => showNotice(error.message));
      return;
    }
    const battleFocus = event.target.closest("[data-focus-battle]");
    if (battleFocus) {
      selectBattle(Number(battleFocus.dataset.focusBattle));
      return;
    }
    const reportFocus = event.target.closest("[data-focus-report]");
    if (reportFocus) {
      selectedBattleId = Number(reportFocus.dataset.focusReport);
      selectedArmyId = null;
      selectedNavyId = null;
      renderPendingActions();
      return;
    }
    const focusButton = event.target.closest("[data-focus-army]");
    const resolveButton = event.target.closest("[data-resolve-army]");
    const focusNavyButton = event.target.closest("[data-focus-navy]");
    const resolveNavyButton = event.target.closest("[data-resolve-navy]");
    if (resolveNavyButton) resolveNavy(resolveNavyButton.dataset.resolveNavy);
    else if (focusNavyButton) selectNavy(focusNavyButton.dataset.focusNavy);
    else if (resolveButton) resolveArmy(resolveButton.dataset.resolveArmy);
    else if (focusButton) selectArmy(focusButton.dataset.focusArmy);
  });
  $("cabinetList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-focus-cabinet]");
    if (!button) return;
    const cardId = button.dataset.focusCabinet;
    selectedCabinetCardId = selectedCabinetCardId === cardId ? null : cardId;
    renderCabinet();
  });
  $("pendingList").addEventListener("contextmenu", (event) => {
    const report = event.target.closest("[data-focus-report]");
    if (!report) return;
    event.preventDefault();
    const id = Number(report.dataset.focusReport);
    if (report.dataset.reportKind === "navy") hiddenNavyBattleReportIds.add(id);
    else hiddenBattleReportIds.add(id);
    if (selectedBattleId === id) selectedBattleId = null;
    renderPendingActions();
  });
  $("pendingList").addEventListener("change", (event) => {
    const side = event.target.dataset.battleTactic;
    const battle = activeBattles.find((item) => item.id === Number(event.target.dataset.battleId));
    if (battle && side && battle.tacticRevision?.[side] && !battle.confirmed?.[side]) {
      battle.tactics[side] = event.target.value;
      renderPendingActions();
    }
  });
  $("turnNotification").addEventListener("click", async (event) => {
    const claimButton = event.target.closest("[data-claim-province]");
    if (claimButton) {
      claimProvince(claimButton.dataset.claimProvince, claimButton.dataset.claimFaction || currentPlayer);
      return;
    }
    const skipClaimButton = event.target.closest("[data-skip-province-claim]");
    if (skipClaimButton) {
      skipProvinceClaim(skipClaimButton.dataset.skipProvinceClaim, skipClaimButton.dataset.claimFaction || currentPlayer);
      return;
    }
    const readButton = event.target.closest("[data-read-notifications]");
    if (readButton) {
      unreadNotifications().forEach((item) => readNotifications.add(item.key));
      renderPendingActions();
      return;
    }
    const buyButton = event.target.closest("[data-buy-function-card]");
    if (buyButton) {
      await buyFunctionCard(buyButton);
      return;
    }
    const skipButton = event.target.closest("[data-skip-function-purchase]");
    if (skipButton) {
      skippedFunctionPurchasePrompts.add(functionPurchasePromptKey(skipButton.dataset.skipFunctionPurchase));
      uiNotice = "本回合略過購買功能卡。";
      renderPendingActions();
      return;
    }
    const responseButton = event.target.closest("[data-deal-response]");
    if (!responseButton) return;
    responseButton.disabled = true;
    try {
      const result = await api("/api/respond-deal", {
        player: currentPlayer,
        deal_id: Number(responseButton.dataset.dealId),
        accept: responseButton.dataset.dealResponse === "accept",
      });
      state = result.state;
      syncStrategicCitiesFromState();
      uiNotice = result.deal.status === "accepted" ? "交易已接受，資源已轉移。" : "交易已拒絕。";
      updateTopBar();
      renderPendingActions();
    } catch (error) {
      responseButton.disabled = false;
      showNotice(error.message);
    }
  });
  $("battlePanel").addEventListener("change", (event) => {
    const side = event.target.dataset.battleTactic;
    const battle = activeBattles.find((item) => item.id === Number(event.currentTarget.dataset.battleId));
    if (battle && side && battle.tacticRevision?.[side] && !battle.confirmed?.[side]) {
      battle.tactics[side] = event.target.value;
      renderPendingActions();
    }
  });
  $("battlePanel").addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-toggle-battle]");
    if (toggle) {
      const battleId = Number(toggle.dataset.toggleBattle);
      if (collapsedBattleIds.has(battleId)) collapsedBattleIds.delete(battleId);
      else collapsedBattleIds.add(battleId);
      renderBattlePanel();
      return;
    }
    const dismissNavy = event.target.closest("[data-dismiss-navy-report]");
    if (dismissNavy) {
      hiddenNavyBattleReportIds.add(Number(dismissNavy.dataset.dismissNavyReport));
      selectedBattleId = null;
      renderBattlePanel();
      renderPendingActions();
      return;
    }
    const reportRetreat = event.target.closest("[data-navy-report-retreat]");
    if (reportRetreat) {
      const navy = navyById(reportRetreat.dataset.navyReportRetreat);
      if (!navy || navyFaction(navy) !== currentPlayer) return;
      await handleNavyOperation(navy, "retreat", null, reportRetreat);
      return;
    }
    const resolveButton = event.target.closest("[data-resolve-battle]");
    const retreatButton = event.target.closest("[data-retreat-battle]");
    const battle = activeBattles.find((item) => item.id === Number(
      resolveButton?.dataset.resolveBattle || retreatButton?.dataset.retreatBattle
    ));
    if (!battle) return;
    const side = battle.attackerFaction === currentPlayer ? "A" : "B";
    if (retreatButton) {
      requestBattleRetreat(battle, side);
      return;
    }
    resolveButton.disabled = true;
    try {
      await confirmBattleTactic(battle, side);
    } catch (error) {
      resolveButton.disabled = false;
      showNotice(error.message);
    }
  });
  $("battlePanel").addEventListener("contextmenu", (event) => {
    const battleId = Number(event.currentTarget.dataset.battleId);
    if (!battleId) return;
    const navyReport = navyBattleReports.find((item) => item.id === battleId);
    if (navyReport) {
      event.preventDefault();
      hiddenNavyBattleReportIds.add(battleId);
      selectedBattleId = null;
      renderBattlePanel();
      renderPendingActions();
      return;
    }
    const battle = [...activeBattles, ...battleReports].find((item) => item.id === battleId);
    if (!battle || ["pending", "ongoing"].includes(battle.status)) return;
    event.preventDefault();
    hiddenBattleReportIds.add(battleId);
    selectedBattleId = null;
    renderBattlePanel();
  });
  $("armyDetail").addEventListener("click", async (event) => {
    const navyOperation = event.target.closest("[data-navy-operation]")?.dataset.navyOperation;
    const embarkArmyId = event.target.closest("[data-embark-army]")?.dataset.embarkArmy;
    const reinforceNavyUnit = event.target.closest("[data-reinforce-navy-unit]")?.dataset.reinforceNavyUnit;
    const navy = selectedNavy();
    if (navy && (navyOperation || embarkArmyId || reinforceNavyUnit)) {
      await handleNavyOperation(navy, navyOperation, embarkArmyId, event.target, reinforceNavyUnit);
      return;
    }
    const operation = event.target.closest("[data-army-operation]")?.dataset.armyOperation;
    const engineering = event.target.closest("[data-engineering-operation]")?.dataset.engineeringOperation;
    const reinforcement = event.target.closest("[data-reinforce-unit]")?.dataset.reinforceUnit;
    const transferButton = event.target.closest("[data-transfer-unit]");
    const battleToJoin = event.target.closest("[data-join-battle]")?.dataset.joinBattle;
    const defectionTarget = event.target.closest("[data-defect-army]")?.dataset.defectArmy;
    const army = selectedArmy();
    if (!army) return;
    if (transferButton) {
      const fromArmy = armyById(transferButton.dataset.transferFrom);
      const toArmy = armyById(transferButton.dataset.transferTo);
      transferArmyUnit(fromArmy, toArmy, transferButton.dataset.transferUnit, 1);
      await publishSharedState(true);
    } else if (defectionTarget) {
      const superiorId = $("armyDetail").querySelector("[data-defect-superior]")?.value;
      if (!superiorId) {
        showNotice("我方沒有可接收此將領的現役中將。");
        return;
      }
      event.target.disabled = true;
      try {
        await attemptArmyDefection(army, superiorId);
      } catch (error) {
        event.target.disabled = false;
        showNotice(error.message);
      }
    } else if (battleToJoin) {
      joinBattle(army, activeBattles.find((battle) => battle.id === Number(battleToJoin)));
    } else if (operation === "move") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能脫離戰場移動。" : "此軍本回合已行動，不能再次移動。");
        return;
      }
      moveMode = !moveMode;
      engineeringMode = null;
      showNotice(moveMode
        ? `選擇地格；${forcedMarchActive(army) ? `急行軍中可走 ${forcedMarchRules().tiles} 格陸地` : "一般移動限相鄰地格"}；鐵路最多 ${railwayMoveLimit(currentPlayer)} 格；跨河需要浮橋或鐵路橋。`
        : "已取消移動。");
      $("mapStage").classList.toggle("move-mode", moveMode);
      renderArmyDetail();
    } else if (operation === "forced_march") {
      await buyForcedMarch(army, event.target);
    } else if (engineering === "pontoon_bridge") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能施工。" : "此軍本回合已行動。");
        return;
      }
      engineeringMode = engineering;
      moveMode = false;
      showNotice("選擇與軍隊相鄰的河流地格架設浮橋。工程需 2 回合，工業點/FP 10。");
      $("mapStage").classList.add("move-mode");
    } else if (engineering === "fortress_builder") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能施工。" : "此軍本回合已行動。");
        return;
      }
      try {
        startEngineeringOperation(army, engineering, army.cellKey);
      } catch (error) {
        showNotice(error.message);
        return;
      }
      moveMode = false;
      resolveArmy(army.id);
      showNotice("構築要塞開始：工程需 3 回合，已支付工業點/FP 10。");
      publishSharedState(true).catch((error) => console.error("Engineering publish failed:", error));
    } else if (operation === "recruit") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能補充兵力。" : "此軍本回合已行動。");
        return;
      }
      army.showRecruitment = !army.showRecruitment;
      renderArmyDetail();
    } else if (reinforcement) {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能補充兵力。" : "此軍本回合已行動。");
        return;
      }
      const city = cityForArmy(army);
      try {
        const result = await api("/api/reinforce-army", {
          player: currentPlayer,
          army_id: army.id,
          city_id: city.id,
          unit_type: reinforcement,
          count: 1,
          current_force: forcePoints(armyUnits(army)),
        });
        state = result.state;
        const acceptedType = result.unit_type || reinforcement;
        const acceptedCount = Math.max(1, Number(result.count || 1));
        const nextUnits = armyUnits(army);
        nextUnits[acceptedType] = Number(nextUnits[acceptedType] || 0) + acceptedCount;
        setArmyTotalUnits(army, nextUnits);
        syncStrategicCitiesFromState();
        updateTopBar();
        renderArmyDetail();
        renderArmyMarkers(currentPlayer);
        renderPendingActions();
        await publishSharedState(true);
      } catch (error) {
        showNotice(error.message);
      }
    }
  });
}

function showNotice(message) {
  uiNotice = message;
  renderPendingActions();
}

function setupMapMovement() {
  const canvas = $("mapCanvas");
  if (canvas.dataset.movementReady) return;
  canvas.dataset.movementReady = "true";
  canvas.addEventListener("click", async (event) => {
    if (suppressMapClick) {
      suppressMapClick = false;
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const mapX = ((event.clientX - rect.left) / rect.width) * MAPW;
    const mapY = ((event.clientY - rect.top) / rect.height) * MAPH;
    const [lon, lat] = unpx(mapX, mapY);
    const destination = cellAt(lon, lat);
    if (!moveMode && !engineeringMode && !navyMoveMode) {
      selectTile(destination);
      return;
    }
    if (navyMoveMode) {
      await handleNavyDestination(destination);
      return;
    }
    handleMapDestination(destination);
  });
}

async function handleNavyDestination(destination) {
  const navy = selectedNavy();
  const source = cells[navy?.cellKey];
  if (!navy || !destination || !source || destination.key === source.key) return;
  const navyLock = punishmentLockForNavy(navy);
  if (navyLock) {
    showNotice(`${navy.name}位於${punishmentLockLabel(navyLock)}內，被鎖在原地，無法移動。`);
    navyMoveMode = false;
    $("mapStage").classList.remove("move-mode");
    renderArmyDetail();
    return;
  }
  if (!navyCanReceiveOrder(navy)) {
    showNotice("此艦隊本回合已行動。");
    navyMoveMode = false;
    $("mapStage").classList.remove("move-mode");
    renderArmyDetail();
    return;
  }
  if (!navyCanEnterCell(destination)) {
    showNotice("艦隊只能進入河港、水域、鐵路橋或海港地格。");
    return;
  }
  const destinationOwner = destination.city?.faction || destination.fac;
  if (destination.city && destinationOwner && destinationOwner !== currentPlayer
    && !factionsAtWar(currentPlayer, destinationOwner)) {
    showNotice(`目前與${FACTIONS[destinationOwner]?.shortName || destinationOwner}和平，艦隊不能駛入其港口。`);
    return;
  }
  if (portParalysed(destination.city)) {
    showNotice(portParalysedNote(destination.city));
    return;
  }
  const path = navyPath(source, destination, cellNeighbors, navyRules());
  if (!path) {
    showNotice(`艦隊一回合最多沿可航行水道移動 ${navyRules().move?.tiles_per_turn || 2} 格。`);
    return;
  }
  // 炸壞的港口連通行都不行，航線經過也算，得繞開。
  const blockedPort = path.find((cell) => cell.key !== source.key && portParalysed(cell.city));
  if (blockedPort) {
    showNotice(portParalysedNote(blockedPort.city));
    return;
  }
  const ownNavy = navyAtCell(destination.key, currentPlayer);
  if (ownNavy && ownNavy.id !== navy.id) {
    showNotice("該地格已有己方艦隊。");
    return;
  }
  const enemyNavy = enemyNavyAtCell(destination.key, currentPlayer);
  const enemyArmy = allArmies().find((army) =>
    army.cellKey === destination.key
    && factionForArmy(army) !== currentPlayer
    && factionsAtWar(currentPlayer, factionForArmy(army))
  );
  if (enemyNavy && !factionsAtWar(currentPlayer, navyFaction(enemyNavy))) {
    showNotice(`目前與${FACTIONS[navyFaction(enemyNavy)]?.shortName || navyFaction(enemyNavy)}和平，不能攻擊其艦隊。`);
    return;
  }
  const peacefulArmy = allArmies().find((army) =>
    army.cellKey === destination.key
    && factionForArmy(army) !== currentPlayer
    && !factionsAtWar(currentPlayer, factionForArmy(army))
  );
  if (peacefulArmy) {
    const peacefulFaction = factionForArmy(peacefulArmy);
    showNotice(`目前與${FACTIONS[peacefulFaction]?.shortName || peacefulFaction}和平，艦隊不能駛入其部隊所在港區。`);
    return;
  }
  const action = beginNavyOrder(navy, "move");
  const moveCost = navyMoveFactoryCost(navy);
  try {
    const paid = await api("/api/pay-navy-move", { player: currentPlayer, factory: moveCost });
    state = paid.state;
    action.factoryCost = Number(paid.factory || moveCost);
    syncStrategicCitiesFromState();
  } catch (error) {
    navyOrderHistory.splice(navyOrderHistory.indexOf(action), 1);
    showNotice(error.message);
    return;
  }
  navy.previousCellKey = source.key;
  moveNavyToCell(navy, destination);
  let navalScreenCleared = !enemyNavy;
  if (enemyNavy) {
    const result = applyNavyDuel(navy, enemyNavy);
    navalScreenCleared = Boolean(result.defenderRetreat && !result.attackerRetreat);
    if (result.attackerRetreat) moveNavyToCell(navy, source);
    if (result.defenderRetreat) retreatNavyFromContact(enemyNavy, null, source);
  }
  if (enemyArmy && navalScreenCleared && navy.cellKey === destination.key) {
    const result = applyArmyNavyContact(enemyArmy, navy);
    if (result.landRetreat) retreatArmyFromNavyContact(enemyArmy, navy);
    if (result.navyRetreat) retreatNavyFromContact(navy, source, cells[enemyArmy.previousCellKey] || cells[enemyArmy.cellKey]);
  }
  if (destination.city && destinationOwner && destinationOwner !== currentPlayer
    && factionsAtWar(currentPlayer, destinationOwner)
    && navy.cellKey === destination.key) {
    occupyTile(destination, currentPlayer, action);
  }
  markNavyResolved(navy);
  navyMoveMode = false;
  $("mapStage").classList.remove("move-mode");
  updateTopBar();
  initMap();
  renderPendingActions();
  await publishSharedState(true);
}

function handleMapDestination(destination) {
    const army = selectedArmy();
    const source = cells[army?.cellKey];
    if (!army || !destination || !source || destination.key === source.key) return;
    if (!armyCanReceiveOrder(army)) {
      showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能脫離戰場移動。" : "此軍本回合已行動，不能再次移動。");
      moveMode = false;
      engineeringMode = null;
      $("mapStage").classList.remove("move-mode");
      renderArmyDetail();
      return;
    }

    if (engineeringMode === "pontoon_bridge") {
      const adjacent = cellNeighbors(source).some((cell) => cell.key === destination.key);
      if (!adjacent || !destination.river) {
        showNotice("浮橋只能架設在相鄰的河流地格。");
        return;
      }
      try {
        startEngineeringOperation(army, engineeringMode, destination.key);
      } catch (error) {
        showNotice(error.message);
        return;
      }
      engineeringMode = null;
      $("mapStage").classList.remove("move-mode");
      resolveArmy(army.id);
      showNotice("浮橋工程開始：工程需 2 回合，已支付工業點/FP 10。");
      publishSharedState(true).catch((error) => console.error("Engineering publish failed:", error));
      return;
    }

    if (destination.power) {
      showNotice(`${POWER_NAME[destination.power] || destination.power}的租借地，中國各勢力不得進入或通過。`);
      return;
    }
    // 事件卡下的原地戰備令：規則，不是提示。
    const freeze = movementFreezeForArmy(army);
    if (freeze) {
      const left = freeze.remaining_turns;
      showNotice(`${army.designator} 奉命原地戰備（${freeze.name || "事件"}）`
        + `${left ? `，剩餘 ${left} 回合` : "，本回合"}不可移動。`);
      return;
    }
    // 被列強佔領區鎖住的部隊不能動——這是規則，不是提示。
    const armyLock = punishmentLockForArmy(army);
    if (armyLock) {
      showNotice(`${army.designator}位於${punishmentLockLabel(armyLock)}內，被鎖在原地，無法移動。`);
      return;
    }
    const ceasefire = forcedPeaceEffect(currentPlayer);
    if (ceasefire && ceasefire.blocks_enemy_entry !== false) {
      const occupant = allArmies().find((other) => other.cellKey === destination.key
        && factionForArmy(other) !== currentPlayer);
      const foreignGround = destination.fac && destination.fac !== currentPlayer;
      if (occupant || foreignGround) {
        showNotice(`${ceasefire.name || "強制和平"}期間（剩餘 ${ceasefire.remaining_turns} 回合）`
          + "不得進入他方地格、不得宣戰。防禦戰仍可進行。");
        return;
      }
    }
    const adjacent = cellNeighbors(source).some((cell) => cell.key === destination.key);
    const blockingNavy = enemyNavyAtCell(destination.key, currentPlayer);
    const railPath = railwayPath(source, destination);
    const marchPath = railPath ? null : forcedMarchPath(source, destination, army);
    if (!adjacent && !railPath && !marchPath) {
      showNotice(forcedMarchActive(army)
        ? `急行軍中可走 ${forcedMarchRules().tiles} 格陸地；位於鐵路時可沿相連鐵路移動最多 ${railwayMoveLimit(currentPlayer)} 格。`
        : `一般移動限相鄰地格；購買急行軍後可走 ${forcedMarchRules().tiles} 格；位於鐵路時可沿相連鐵路移動最多 ${railwayMoveLimit(currentPlayer)} 格。`);
      return;
    }
    if (adjacent && !railPath && !marchPath && !blockingNavy && !riverStepAllowed(source, destination, false)) {
      showNotice("河流阻擋行軍：需先架設浮橋，或沿設有鐵路橋的鐵路通過。");
      return;
    }
    if (currentArmies().some((other) => other.id !== army.id && other.cellKey === destination.key)) {
      showNotice("該地格已有另一支軍隊。");
      return;
    }
    const enemy = allArmies().find((other) =>
      factionForArmy(other) !== currentPlayer && other.cellKey === destination.key
    );
    if (destination.fac !== currentPlayer) {
      if (!factionsAtWar(currentPlayer, destination.fac)) {
        showNotice(`目前與${FACTIONS[destination.fac]?.shortName || destination.fac}和平，不能進入其領土。`);
        return;
      }
    }
    if (blockingNavy && !factionsAtWar(currentPlayer, navyFaction(blockingNavy))) {
      showNotice(`目前與${FACTIONS[navyFaction(blockingNavy)]?.shortName || navyFaction(blockingNavy)}和平，不能攻擊其艦隊。`);
      return;
    }
    if (enemy) {
      const enemyFaction = factionForArmy(enemy);
      if (!factionsAtWar(currentPlayer, enemyFaction)) {
        showNotice(`目前與${FACTIONS[enemyFaction]?.shortName || enemyFaction}和平，不能攻擊其軍隊。`);
        return;
      }
      if (forcePoints(armyUnits(army)) <= 5) {
        showNotice("兵力需高於 5 戰力點才能主動攻擊。請先撤回或補充兵力。");
        return;
      }
    }
    const action = beginArmyOrder(army, railPath ? "rail_move" : marchPath ? "forced_march" : "move");
    army.previousCellKey = source.key;
    army.cellKey = destination.key;
    army.lon = destination.lon;
    army.lat = destination.lat;
    let navyContacted = false;
    let navyContactResult = null;
    if (blockingNavy) {
      navyContacted = true;
      navyContactResult = applyArmyNavyContact(army, blockingNavy);
      if (navyContactResult.landRetreat) {
        moveArmyToCell(army, source);
      }
      if (navyContactResult.navyRetreat) {
        retreatNavyFromContact(blockingNavy, null, source);
      }
    }
    if (!navyContacted && army.cellKey === destination.key && enemy) {
      startBattle(army, enemy, destination, source.key, action);
    } else if (!navyContacted && army.cellKey === destination.key && destination.fac !== currentPlayer) {
      occupyTile(destination, currentPlayer, action);
    } else if (navyContacted && navyContactResult?.navyRetreat && !enemy && army.cellKey === destination.key && destination.fac !== currentPlayer) {
      occupyTile(destination, currentPlayer, action);
    }
    moveMode = false;
    $("mapStage").classList.remove("move-mode");
    resolveArmy(army.id);
    if (!navyContacted && enemy && selectedBattleId) selectBattle(selectedBattleId);
    if (navyContacted || !enemy || activeBattles.at(-1)?.status === "surrendered") initMap();
}

function notificationKey(player, index, item) {
  return `${player}:${index}:${item.turn}`;
}

function unreadNotifications(payload = state.players[currentPlayer]) {
  return (payload?.notifications || [])
    .map((item, index) => ({ ...item, key: notificationKey(currentPlayer, index, item) }))
    .filter((item) => !readNotifications.has(item.key));
}

// ── 政府內閣 ──────────────────────────────────────────────────────────
// 五張單一玩家卡打出後，對應的人物就掛在陣營操作版最下方，與部隊分開。
// 卡片失效時人物離開，這一區也跟著消失。
let selectedCabinetCardId = null;

function cabinetEntries(faction = currentPlayer) {
  return Object.values(state?.cabinet || {}).filter((entry) => entry.owner === faction);
}

function cabinetPortraitMarkup(entry, className = "cabinet-portrait") {
  const name = entry.portrait || entry.person || "";
  return `<img class="${className}" src="/assets/portraits/${encodeURIComponent(name)}.jpg" alt="${entry.person}"
    onerror="this.replaceWith(Object.assign(document.createElement('div'), { className: '${className} portrait-placeholder', textContent: '${(entry.person || "?").charAt(0)}' }))">`;
}

function renderCabinetDetail() {
  const root = $("cabinetDetail");
  if (!root) return;
  const entry = cabinetEntries().find((item) => item.card_id === selectedCabinetCardId);
  if (!entry) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  root.hidden = false;
  root.innerHTML = `
    <div class="army-profile cabinet-profile">
      ${cabinetPortraitMarkup(entry)}
      <div class="cabinet-identity">
        <div class="cabinet-name-row">
          <b>${entry.person}</b>
          <span class="cabinet-card-name">${entry.card_name}</span>
        </div>
        <span>${entry.skill || ""}</span>
      </div>
    </div>
    <div class="cabinet-text">
      <b>效果說明</b>
      <p>${entry.effect || "（無）"}</p>
      <b>失效條件</b>
      <p>${entry.lapse_text || "（無）"}</p>
    </div>`;
}

function renderCabinet() {
  const section = $("cabinetSection");
  if (!section) return;
  const entries = cabinetEntries();
  if (selectedCabinetCardId && !entries.some((entry) => entry.card_id === selectedCabinetCardId)) {
    selectedCabinetCardId = null;
  }
  section.hidden = entries.length === 0;
  $("cabinetCount").textContent = String(entries.length);
  $("cabinetList").innerHTML = entries.map((entry) => `
    <div class="pending-unit cabinet-unit ${selectedCabinetCardId === entry.card_id ? "active" : ""}">
      <button class="pending-unit-main" data-focus-cabinet="${entry.card_id}">
        <span class="pending-unit-number">閣</span>
        <span><b>${entry.person}</b><small>${entry.card_name}</small></span>
      </button>
    </div>
  `).join("");
  renderCabinetDetail();
}


// ── 最後通牒的狀態說明 ──────────────────────────────────────────────
// 被下通牒的玩家必須知道三件事：還剩幾回合、該去哪幾座城、逾期會怎樣。
// 這塊常駐在側欄最上方，通牒結案（達成或逾期）之後還會再顯示一回合的結果。
function ultimatumCityName(cityId) {
  for (const cell of Object.values(cells)) {
    const city = cell.city || cell.foreignCity;
    if (city && city.id === cityId) return city.name;
  }
  return cityId;
}

function ultimatumsForPlayer(faction) {
  return (state?.ultimatums || []).filter((entry) => entry.owner === faction);
}

function ultimatumNoticeMarkup(faction = currentPlayer) {
  const turn = Number(state?.turn || 0);
  return ultimatumsForPlayer(faction).map((entry) => {
    const power = POWER_LABELS[entry.power] || entry.power;
    const cities = (entry.cities || []).map(ultimatumCityName).join("、");
    if (entry.status === "met") {
      return `<div class="ultimatum-notice met"><b class="ultimatum-title">${power}的最後通牒　已達成</b>
        <span>部隊已在指定城市周邊駐紮滿 1 回合，對${power}關係 +1；`
        + `${power}的地面部隊懲戒維持封鎖。</span></div>`;
    }
    if (entry.status === "failed") {
      return `<div class="ultimatum-notice failed"><b class="ultimatum-title">${power}的最後通牒　已逾期</b>
        <span>視為無視通牒：<b>${power}的地面部隊懲戒已對你解封</b>，隨時可能降臨。</span>
        <small>把對${power}關係修回非敵對（&gt; −4），下一回合起會重新上鎖。</small></div>`;
    }
    if (entry.status !== "open") return "";
    const left = Math.max(0, Number(entry.deadline_turn || 0) - turn);
    const posted = entry.seen_turn !== undefined && entry.seen_turn !== null;
    const progress = posted
      ? `<small>已有部隊就位（第 ${entry.seen_turn} 回合起）——再撐一個回合就算駐紮滿 1 回合。</small>`
      : `<small>目前無部隊在指定城市周邊；部隊必須<b>連續兩次回合推進</b>都在原地才算駐紮滿 1 回合。</small>`;
    return `<div class="ultimatum-notice"><b class="ultimatum-title">${power}的最後通牒　剩 ${left} 回合</b>
      <span>派部隊進駐 <span class="ultimatum-cities">${cities}</span> 其中一座城市的<b>周邊一格</b>，並駐紮至少 1 回合。</span>
      ${progress}
      <small>逾期未辦 → ${power}的地面部隊懲戒（佔領你的省份）全部對你解封。達成 → 對${power}關係 +1。</small></div>`;
  }).join("");
}

function renderPendingActions() {
  const pending = pendingArmies();
  const navyPending = pendingNavies();
  const fighting = activeBattles.filter((battle) =>
    (battle.status === "pending" || battle.status === "ongoing")
    && (battle.attackerFaction === currentPlayer || battle.defenderFaction === currentPlayer)
  );
  $("pendingCount").textContent = String(pending.length + navyPending.length);
  $("pendingTitle").textContent = fighting.length ? "交戰軍令" : (pending.length || navyPending.length) ? "待命軍隊" : "軍令完成";
  const fightingMarkup = fighting.map((battle) => {
    const side = battle.attackerFaction === currentPlayer ? "A" : "B";
    const army = armyById(side === "A" ? battle.attackerId : battle.defenderId);
    const openingRound = (battle.rounds || 0) === 0;
    const canRevise = battle.tacticRevision?.[side] && !battle.confirmed?.[side];
    const locked = !canRevise;
    return `<div class="pending-battle">
      <button class="pending-unit-main" data-focus-battle="${battle.id}"><span class="pending-unit-number">戰</span><span><b>${battleSideLabel(battle, side)}</b><small>${army.general} · 第 ${(battle.rounds || 0) + 1} 輪</small></span></button>
      <select data-battle-tactic="${side}" data-battle-id="${battle.id}" ${locked ? "disabled" : ""}>${tacticOptionsMarkup(battle.tactics[side], side)}</select>
      <div class="pending-battle-actions ${openingRound ? "" : "continuing"}">${canRevise ? `<button data-resolve-battle="${battle.id}">定策</button>` : ""}${retreatButtonMarkup(battle, side)}</div>
      ${openingRound ? "" : `<small class="pending-battle-note">${canRevise ? "援軍抵達，可重新定策一次" : battle.roundResolvedTurn === state.turn ? "本回合已交戰" : "沿用戰術；回合結束時自動交戰"}</small>`}
    </div>`;
  }).join("");
  const armyMarkup = pending.length
    ? pending.map((army) => `
      <div class="pending-unit ${selectedArmyId === army.id ? "active" : ""}">
        <button class="pending-unit-main" data-focus-army="${army.id}">
          <span class="pending-unit-number">${army.designator.replace("第", "").replace("軍", "")}</span>
          <span><b>${army.designator} · ${army.general}</b><small>${cityForArmy(army)?.name || cells[army.cellKey]?.province || "野外"} · 戰力 ${Math.round(forcePoints(armyUnits(army)))}</small></span>
        </button>
        <button class="hold-command" data-resolve-army="${army.id}" title="原地待命">待命</button>
      </div>
    `).join("")
    : "";
  const navyMarkup = navyPending.length
    ? navyPending.map((navy) => `
      <div class="pending-unit navy-pending ${selectedNavyId === navy.id ? "active" : ""}">
        <button class="pending-unit-main" data-focus-navy="${navy.id}">
          <span class="pending-unit-number">艦</span>
          <span><b>${navy.name}</b><small>${navyCellLabel(cells[navy.cellKey])} · HP ${Math.round(totalGunBoatHp(navy))}/${maxGunBoatHp(navy)}${navyInContact(navy) ? ` · 交戰中，${navyContactEstimate(navy)}` : ""}</small></span>
        </button>
        <button class="hold-command" data-resolve-navy="${navy.id}" title="原地待命">待命</button>
      </div>
    `).join("")
    : "";
  const completeMarkup = !fighting.length && !pending.length && !navyPending.length
    ? '<div class="pending-complete">所有軍隊均已收到命令</div>'
    : "";
  $("pendingList").innerHTML = ultimatumNoticeMarkup()
    + fightingMarkup + armyMarkup + navyMarkup + completeMarkup;

  renderArmyDetail();
  renderCabinet();
  renderBattlePanel();
  renderTileInfo();

  const payload = state.players[currentPlayer];
  const deals = payload?.pending_deals || [];
  const inboxBadge = $("dealInboxBadge");
  inboxBadge.hidden = deals.length === 0;
  inboxBadge.textContent = String(deals.length);
  const notification = $("turnNotification");
  const provinceClaim = pendingProvinceClaims.find((claim) => claim.faction === currentPlayer);
  if (provinceClaim) {
    notification.hidden = false;
    notification.innerHTML = `
      <b>省份歸屬</b>
      <span>${provinceClaim.province}所有城市已由${FACTIONS[currentPlayer]?.shortName || currentPlayer}控制。是否宣告接管全省？</span>
      <div class="notification-actions">
        <button data-claim-province="${provinceClaim.province}" data-claim-faction="${currentPlayer}">宣告接管</button>
        <button data-skip-province-claim="${provinceClaim.province}" data-claim-faction="${currentPlayer}">稍後再說</button>
      </div>`;
  } else if (unreadNotifications(payload).length) {
    const unread = unreadNotifications(payload);
    notification.hidden = false;
    notification.innerHTML = `
      <b>戰報</b>
      <span>${unread.map((item) => item.text).join("<br>")}</span>
      <div class="notification-actions">
        <button data-read-notifications="${currentPlayer}">知道了</button>
      </div>`;
  } else if (uiNotice) {
    notification.hidden = false;
    notification.innerHTML = `<b>軍令提示</b><span>${uiNotice}</span>`;
  } else if (deals.length) {
    const deal = deals[0];
    const sender = FACTIONS[deal.from]?.shortName || deal.from;
    const reserveText = deal.reserve ? `、${UNIT_META[deal.unit_type]?.name || deal.unit_type}預備隊 ${deal.reserve}` : "";
    notification.hidden = false;
    notification.innerHTML = `
      <b>${sender}提出交易</b>
      <span>資金 $${deal.funds}${reserveText}</span>
      <div class="notification-actions">
        <button data-deal-response="accept" data-deal-id="${deal.id}">接受</button>
        <button data-deal-response="decline" data-deal-id="${deal.id}">拒絕</button>
      </div>`;
  } else if (bootstrap.features?.function_cards && payload?.pending_draw) {
    const card = cardIndex[payload.pending_draw];
    notification.hidden = false;
    notification.innerHTML = `<b>手牌已滿</b><span>棄置一張牌以接收「${card?.name || "新功能卡"}」</span>`;
  } else if (canPurchaseFunctionCard(payload)) {
    const cost = functionCardDrawCost();
    const used = Number(payload.function_purchase_count || 0);
    const limit = functionCardDrawLimit();
    notification.hidden = false;
    notification.innerHTML = `
      <b>回合開始：購買功能卡？</b>
      <span>可支付 $${cost}＋工業點 ${functionCardDrawFactoryCost()} 抽 1 張功能卡；本回合最多 ${limit} 張，目前 ${used}/${limit}，也可以略過。</span>
      <div class="notification-actions">
        <button data-buy-function-card="${currentPlayer}">支付 $${cost}＋工${functionCardDrawFactoryCost()}</button>
        <button data-skip-function-purchase="${currentPlayer}">略過</button>
      </div>`;
  } else if (bootstrap.features?.function_cards && state.last_action?.type === "function_card" && functionActionVisibleTo(state.last_action, currentPlayer)) {
    const message = functionActionMessage(state.last_action, currentPlayer);
    notification.hidden = false;
    notification.innerHTML = `<b>功能卡效果</b><span>${message}</span>`;
    } else {
    notification.hidden = true;
    notification.innerHTML = "";
  }

  updateEndTurnButton();
}

function updateEndTurnButton() {
  const pending = pendingArmies();
  const navyPending = pendingNavies();
  const pendingBattles = activeBattles.filter((battle) =>
    ["pending", "ongoing"].includes(battle.status)
    && (!battle.confirmed?.A || !battle.confirmed?.B)
  );
  const btn = $("endTurnBtn");
  const readyPlayers = TURN_PLAYERS.filter((player) => turnReady[player] === state.turn);
  const waitingForAll = turnReady[currentPlayer] === state.turn && readyPlayers.length < TURN_PLAYERS.length;
  btn.classList.toggle("ready", pending.length === 0 && navyPending.length === 0 && pendingBattles.length === 0);
  btn.classList.toggle("waiting", waitingForAll);
  $("endTurnLabel").textContent = pending.length || navyPending.length
    ? `下一支軍隊 (${pending.length + navyPending.length})`
    : pendingBattles.length ? `處理戰鬥 (${pendingBattles.length})`
      : waitingForAll ? `等待玩家 (${readyPlayers.length}/${TURN_PLAYERS.length})`
        : `結束回合 (${readyPlayers.length}/${TURN_PLAYERS.length})`;
  $("undoOrderBtn").disabled = !canUndoArmyOrder();
}

function allPlayersReadyForTurn() {
  return TURN_PLAYERS.every((player) => turnReady[player] === state.turn);
}

async function resetGame() {
  await cityEconomySync;
  state = await api("/api/new-game", { players: bootstrap.players.map((p) => p.code) });
  syncStrategicCitiesFromState();
  const shared = await api("/api/shared-state");
  sharedRevision = shared.revision;
  sharedEngineHash = JSON.stringify(state);
  currentPlayer = $("playerSelect").value;
  currentPhase = "military";
  selectedArmyId = null;
  selectedBattleId = null;
  uiNotice = null;
  skippedFunctionPurchasePrompts.clear();
  resolvedArmyIds.clear();
  resolvedNavyIds.clear();
  replaceObject(turnReady, {});
  armyOrderHistory.length = 0;
  navyOrderHistory.length = 0;
  activeBattles.length = 0;
  battleReports.length = 0;
  navyBattleReports.length = 0;
  pendingProvinceClaims.length = 0;
  collapsedBattleIds.clear();
  hiddenBattleReportIds.clear();
  hiddenNavyBattleReportIds.clear();
  retreatConfirmations.clear();
  completedPontoons.clear();
  for (const key of PREBUILT_PONTOONS) completedPontoons.add(key);
  completedFortresses.clear();
  selectedTileKey = null;
  for (const cell of Object.values(cells)) cell.fac = INITIAL_CELL_FACTIONS[cell.key];
  for (const city of bootstrap.strategic_map?.cities || []) city.faction = INITIAL_CITY_FACTIONS[city.id];
  for (const faction of Object.keys(jailedGenerals)) {
    jailedGenerals[faction].length = 0;
    recruitedGenerals[faction].length = 0;
  }
  replaceObject(generalTrees, JSON.parse(JSON.stringify(initialGeneralTrees)));
  initializeGeneralRuntime();
  generalTreeData = generalTrees[currentPlayer];
  for (const army of Object.values(ARMY_POSITIONS).flat()) {
    Object.assign(army, INITIAL_ARMY_CELLS[army.id]);
    army.units = { ...INITIAL_ARMY_UNITS[army.id] };
    LOYALTY_BASELINE_ARMY_UNITS[army.id] = { ...army.units };
    army.status = "active";
    army.faction = INITIAL_ARMY_FACTIONS[army.id];
    delete army.specialOperation;
    delete army.showRecruitment;
    delete army.embarkedOn;
    delete army.previousCellKey;
    delete army.resolvedTurn;
  }
  replaceArray(navyDivisions, JSON.parse(JSON.stringify(initialNavyDivisions)));
  updateTopBar();
  updatePhaseBanner();
  updateFeatureVisibility();
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
  closeAllPanels();
  await publishSharedState(true);
}

$("newGame").addEventListener("click", () => {
  resetGame().catch((error) => alert("重新開始失敗：" + error.message));
});

$("undoOrderBtn").addEventListener("click", undoLastArmyOrder);

async function advanceToNextTurn(force = false) {
  const pending = pendingArmies();
  const navyPending = pendingNavies();
  if (!force && pending.length) {
    selectArmy(pending[0].id);
    return;
  }
  if (!force && navyPending.length) {
    selectNavy(navyPending[0].id);
    return;
  }
  for (const battle of activeBattles) applyNpcBattleDefaults(battle);
  const pendingBattle = activeBattles.find((battle) =>
    ["pending", "ongoing"].includes(battle.status)
    && (!battle.confirmed?.A || !battle.confirmed?.B)
  );
  if (!force && pendingBattle) {
    selectBattle(pendingBattle.id);
    return;
  }
  if (!force && turnReady[currentPlayer] === state.turn && !allPlayersReadyForTurn()) {
    showNotice("你已結束本回合；等待其他三方完成軍令。");
    await publishSharedState(true);
    return;
  }
  if (force) {
    for (const player of TURN_PLAYERS) turnReady[player] = state.turn;
  } else {
    turnReady[currentPlayer] = state.turn;
  }
  renderPendingActions();
  try {
    await publishSharedState(true);
  } catch (error) {
    showNotice(`同步結束回合狀態失敗：${error.message}`);
    return;
  }
  if (!force && !allPlayersReadyForTurn()) {
    const readyPlayers = TURN_PLAYERS.filter((player) => turnReady[player] === state.turn).length;
    showNotice(`已送出結束回合確認，等待其他玩家（${readyPlayers}/${TURN_PLAYERS.length}）。`);
    return;
  }

  try {
    const continuingBattles = activeBattles.filter((battle) =>
      ["pending", "ongoing"].includes(battle.status) && battle.roundResolvedTurn !== state.turn
    );
    for (const battle of continuingBattles) await resolveBattleRound(battle);
    resolveAllNavyContacts();
    await cityEconomySync;
    const result = await api("/api/next-turn", {
      active_player: currentPlayer,
      force,
      riot_garrisons: qingGangRiotGarrisons(),
      city_garrisons: uprisingCityGarrisons(),
      contested_provinces: contestedProvinces(),
      fallen_marshals: fallenMarshals(),
      ultimatum_garrisons: ultimatumGarrisons(),
      marshal_ids: factionMarshalIds(),
    });
    state = result.state;
    syncStrategicCitiesFromState();
    uiNotice = null;
    // 空襲每回合都炸一次，後端在 tick 時把傷害排進待辦，這裡立刻執行掉。
    const raidNotes = await consumePendingFrontendEffects();
    if (raidNotes.length) showNotice(raidNotes.join("；"));
    if (result.turn?.awaiting_events) {
      // 事件卡週期：先讀報，四張回應完後端才會結算本回合經濟。
      newspaperCardKey = null;
      renderNewspaper();
      updateTopBar();
      await publishSharedState(true);
      return;
    }
    advanceEngineering();
    const healed = applyFieldHospitalRecovery();
    if (healed.length) showNotice(`傷兵歸隊：${healed.join("；")}`);
    const npcGrowth = applyNpcReinforcements();
    resolvedArmyIds.clear();
    resolvedNavyIds.clear();
    replaceObject(turnReady, {});
    for (const army of allArmies()) {
      delete army.resolvedTurn;
      if (army.specialOperation) markArmyResolved(army);
    }
    for (const navy of allNavies(true)) delete navy.resolvedTurn;
    armyOrderHistory.length = 0;
    navyOrderHistory.length = 0;
    archiveTerminalBattles();
    const visibleActiveBattles = activeBattles.filter((battle) => reportVisibleToPlayer(battle));
    const visibleBattleReports = battleReports.filter((battle) => reportVisibleToPlayer(battle));
    selectedBattleId = visibleActiveBattles.at(-1)?.id || visibleBattleReports.at(-1)?.id || null;
    selectedArmyId = currentArmies()[0]?.id || null;
    selectedNavyId = selectedArmyId ? null : currentNavies()[0]?.id || null;
    currentPhase = "military";
    updateTopBar();
    updatePhaseBanner();
    updateFeatureVisibility();
    initMap();
    renderPendingActions();
    if (npcGrowth.length) showNotice(`NPC 補充兵源：${npcGrowth.join("；")}`);
    await publishSharedState(true);
  } catch (error) {
    console.error("Next turn error:", error);
    alert("下一回合失敗：" + error.message);
  }
}

$("endTurnBtn").addEventListener("click", () => {
  advanceToNextTurn(false);
});

$("debugForceTurnBtn").addEventListener("click", () => {
  advanceToNextTurn(true);
});

// 除錯掛勾：把戰鬥加成的組裝過程開放給自動化檢查用（和「強制下一回合」按鈕同性質）。
window.__neDebug = {
  combatArmyPayload,
  combatTraitModifiers,
  combatAuraModifiers,
  calculateGeneralLoyalty,
  generalTrees,
  activeBattles,
  allArmies,
  armyById,
  generalById,
  generalOwners,
  getState: () => state,
  getBootstrap: () => bootstrap,
  functionCardTargetMarkup,
  gangRiotTargets,
  riotTargets,
  getCardIndex: () => cardIndex,
  cells,
  selectTile,
  selectArmy,
  riverStepAllowed,
  cellUsableAsRural,
  cellUsableForForcedMarch,
  renderLoansMarkup,
  applyFrontendEventEffects,
  ceasefireEffect,
  forcedPeaceEffect,
  forcedPeaceDefenceModifiers,
  withdrawBattlesForForcedPeace,
  fortressArtilleryModifiers,
  fieldHospitalWindowActive,
  armyRevealedByIntel,
  provinceForArmy,
  hasFieldHospital,
  applyFieldHospitalRecovery,
  switchFaction,
  pendingEventState,
  renderNewspaper,
  respondToEvent,
  hasPermanentForcedMarch,
  unusableRailways,
  lockedForeignRailways,
  FOREIGN_RAILWAY_POWERS,
  FOREIGN_RAILWAY_RELATION_MIN,
  armyCanBeCaptured,
  annihilateArmy,
  applyGeneralDeath,
  settleNavyCarriedLosses,
  sinkCarriedArmyWithNavy,
  enforceNavyCargoCapacity,
  carriedArmy,
  paralysedPorts,
  portParalysed,
  navyLockedInPort,
  navyLockedNote,
  navyCanReceiveOrder,
  pendingNavies,
  traitLabel,
  traitDescription,
  enemyPortCityOptions,
  navyById,
  allNavies,
  navyRules,
  navyCapacity,
  NO_CAPTURE_FACTIONS,
  applyNpcReinforcements,
  npcMarshalArmyIds,
  markDefectedNpcArmies,
  npcArmyCanGrow,
  NPC_FACTIONS,
  forcedMarchPath,
  forcedMarchActive,
  forcedMarchRemainingTurns,
  forcedMarchCooldownTurns,
  forcePoints,
  armyUnits,
  armyForceCap,
  reinforcementWouldExceedCap,
  cellNeighbors,
  railwayPath,
  railwayMoveLimit,
};

boot().catch((error) => {
  console.error("Boot error:", error);
});
