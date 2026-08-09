import { factionFlagMarkup, flagMarkup, powerFlagMarkup, POWER_NAME } from './flags.js';
import { RIVERS } from './map.js';
import { px, unpx, MAPW, MAPH, FACTIONS, CHINA_PROPER, HAINAN, pointInPolygon, hexPts, cells, cellAt, cellNeighbors, ARMY_POSITIONS, COLS, ROWS, hcx, hcy, s } from './map.js';

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
  wang_chengbin: "/assets/portraits/王承斌.jpg",
  han_fuqu: "/assets/portraits/韓復榘.jpg",
  sun_chuanfang: "/assets/portraits/孫傳芳.jpg",
  zhou_yinren: "/assets/portraits/周蔭人.jpg",
  li_houji: "/assets/portraits/李厚基.jpg",
  lu_yongxiang: "/assets/portraits/盧永祥.jpg",
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
};

let bootstrap = null;
let state = null;
let provinceGeoJson = null;
let cardIndex = {};
let generalTreeData = null;
const generalTrees = {};
const initialGeneralTrees = {};
const generalOwners = {};
const loyaltyOverrides = {};
let currentPhase = "event"; // event, preparation, military
let currentPlayer = null;
let eventHistory = []; // Store all events that have occurred
let selectedArmyId = null;
const resolvedArmyIds = new Set();
const MAX_HAND_SIZE = 6;
const DEFAULT_FUNCTION_CARD_DRAW_COST = 5;
let foreignTab = "warlords";
let dealTarget = null;
let moveMode = false;
let engineeringMode = null;
let uiNotice = null;
const armyOrderHistory = [];
const completedPontoons = new Set();
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
const outsideMapArt = new Image();
outsideMapArt.src = "/assets/shiju-border.png";
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


const TRAIT_LABELS = {
  warlord_supremacy: "軍閥統御",
  young_marshal: "少帥",
  industrial_organizer: "工業組織者",
  white_russian_mercenaries: "白俄傭兵",
  confucian_general: "儒將",
  defensive_specialist: "防禦專家",
  central_plains_veteran: "中原宿將",
  christian_general: "基督將軍",
  soviet_trained: "蘇式訓練",
  five_provinces_alliance: "五省聯軍",
  yangzi_defender: "長江守備",
  fujian_garrison: "福建守備",
  jiangxi_commander: "江西統帥",
  shock_column_leader: "突擊縱隊",
  steady_drillmaster: "練兵能手",
  fire_support_savant: "火力協同",
  local_supply_boss: "地方補給",
};

const TRAIT_DESCRIPTIONS = {
  warlord_supremacy: "以個人威望維繫全軍，適合統率大型軍團與地方派系。",
  young_marshal: "善於快速調動與接受新式軍事觀念，但政治根基仍在建立。",
  industrial_organizer: "擅長兵工、補給與軍需組織，提高重裝部隊的持續作戰能力。",
  white_russian_mercenaries: "能運用白俄軍官與雇傭兵，強化騎兵及專業火力。",
  confucian_general: "重視軍紀與傳統威望，有利於穩定部隊忠誠。",
  defensive_specialist: "擅長利用地形和縱深防禦，適合固守重要城市與交通線。",
  central_plains_veteran: "熟悉中原地形、補給路線與軍閥作戰方式。",
  christian_general: "依靠教會與地方人脈組織軍隊和補給。",
  soviet_trained: "接受蘇式參謀與協同作戰訓練。",
  five_provinces_alliance: "善於協調五省部隊，但必須兼顧各地派系利益。",
  yangzi_defender: "熟悉長江沿線防禦、渡口與水陸交通。",
  fujian_garrison: "熟悉福建山地、港口與地方守備體系。",
  jiangxi_commander: "熟悉江西交通、補給與地方部隊動員。",
  shock_column_leader: "步兵與騎兵攻擊 +15%，但所受傷害 +10%。",
  steady_drillmaster: "步兵攻擊 +10%。",
  fire_support_savant: "砲兵攻擊機槍 +25%，攻擊步兵 +15%。",
  local_supply_boss: "步兵與機槍的崩潰門檻提高 5%。",
};

function traitDescription(trait) {
  const base = TRAIT_DESCRIPTIONS[trait]
    || bootstrap?.general_traits?.traits?.[trait]?.background
    || "此特質目前沒有補充說明。";
  const modifiers = TRAIT_GAME_MODIFIERS?.[trait] || [];
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

function traitChip(trait) {
  const description = traitDescription(trait);
  return `<span class="trait-chip" tabindex="0" data-tooltip="${description}">${TRAIT_LABELS[trait] || trait}</span>`;
}

const ENGINEERING_OPERATIONS = {
  pontoon_bridge: { label: "架設浮橋", turns: 2 },
  fortress_builder: { label: "構築要塞", turns: 3 },
};
const ENGINEERING_TRAIT_SKILLS = {
  pontoon_bridge: new Set(["young_marshal", "christian_general", "yangzi_defender", "local_supply_boss"]),
  fortress_builder: new Set(["industrial_organizer", "defensive_specialist", "fujian_garrison", "warlord_supremacy", "shock_column_leader"]),
};
const TRAIT_GAME_MODIFIERS = {
  warlord_supremacy: [{ stat: "threshold", add: 0.03 }],
  young_marshal: [{ stat: "attack", unit: "cavalry", multiplier: 1.08 }],
  industrial_organizer: [{ stat: "attack", unit: "artillery", multiplier: 1.10 }],
  white_russian_mercenaries: [{ stat: "attack", unit: "cavalry", multiplier: 1.12 }, { stat: "hp", unit: "cavalry", multiplier: 1.08 }],
  confucian_general: [{ stat: "harm_taken", multiplier: 0.96 }],
  defensive_specialist: [{ stat: "harm_taken", multiplier: 0.88 }],
  central_plains_veteran: [{ stat: "attack", unit: "infantry", multiplier: 1.08 }],
  christian_general: [{ stat: "threshold", add: 0.03 }],
  soviet_trained: [{ stat: "attack", unit: "machine_gun", multiplier: 1.10 }],
  five_provinces_alliance: [{ stat: "harm_taken", unit: "infantry", multiplier: 0.94 }],
  yangzi_defender: [{ stat: "harm_taken", multiplier: 0.90 }],
  fujian_garrison: [{ stat: "harm_taken", unit: "infantry", multiplier: 0.90 }],
  jiangxi_commander: [{ stat: "attack", unit: "infantry", multiplier: 1.06 }],
  shock_column_leader: [{ stat: "attack", unit: "infantry", multiplier: 1.15 }, { stat: "attack", unit: "cavalry", multiplier: 1.15 }, { stat: "harm_taken", multiplier: 1.10 }],
  steady_drillmaster: [{ stat: "attack", unit: "infantry", multiplier: 1.10 }],
  fire_support_savant: [{ stat: "attack", unit: "artillery", target: "machine_gun", multiplier: 1.25 }, { stat: "attack", unit: "artillery", target: "infantry", multiplier: 1.15 }],
  local_supply_boss: [{ stat: "threshold", unit: "infantry", add: 0.05 }, { stat: "threshold", unit: "machine_gun", add: 0.05 }],
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
    generalTreeData = generalTrees[factionCode];
  } catch (error) {
    console.error(`Failed to load general tree for ${factionCode}:`, error);
    generalTreeData = null;
  }
}

async function loadAllGeneralTrees() {
  await Promise.all(Object.keys(ARMY_POSITIONS).map(async (faction) => {
    generalTrees[faction] = await api(`/api/general-tree?faction=${faction}`);
    initialGeneralTrees[faction] = JSON.parse(JSON.stringify(generalTrees[faction]));
  }));
}

function initializeGeneralRuntime() {
  for (const key of Object.keys(generalOwners)) delete generalOwners[key];
  for (const key of Object.keys(loyaltyOverrides)) delete loyaltyOverrides[key];
  for (const [faction, tree] of Object.entries(generalTrees)) {
    for (const generalId of Object.keys(tree.generals || {})) generalOwners[generalId] = faction;
  }
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
      INITIAL_ARMY_FACTIONS[army.id] = faction;
    }
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
      return general && general.loyalty !== null && !general.absolute_loyalty && !general.loyalty_exempt;
    });
}

function adjustGeneralLoyalty(generalId, amount) {
  const general = generalById(generalId);
  if (!general || general.loyalty === null || general.absolute_loyalty || general.loyalty_exempt) return;
  const fieldArmy = allArmies(true).find((army) => army.generalId === generalId);
  const current = calculateGeneralLoyalty(general, fieldArmy).value ?? 1;
  loyaltyOverrides[generalId] = Math.max(1, Math.min(10, current + Number(amount || 0)));
}

function applyFunctionSideEffects(result) {
  if (result.assassination) applyAssassination(result.assassination);
  if (result.target_general_id && result.loyalty_delta) {
    adjustGeneralLoyalty(result.target_general_id, result.loyalty_delta);
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
      previousCellKey: army.previousCellKey || null,
      resolvedTurn: army.resolvedTurn ?? null,
      specialOperation: army.specialOperation ? { ...army.specialOperation } : null,
      showRecruitment: Boolean(army.showRecruitment),
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
    generalTrees: JSON.parse(JSON.stringify(generalTrees)),
    generalOwners: { ...generalOwners },
    loyaltyOverrides: { ...loyaltyOverrides },
    jailedGenerals: JSON.parse(JSON.stringify(jailedGenerals)),
    recruitedGenerals: JSON.parse(JSON.stringify(recruitedGenerals)),
    completedPontoons: [...completedPontoons],
    completedFortresses: [...completedFortresses],
    resolvedArmyIds: [...resolvedArmyIds],
    armyOrderHistory: JSON.parse(JSON.stringify(armyOrderHistory)),
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
  replaceObject(generalTrees, JSON.parse(JSON.stringify(snapshot.generalTrees || generalTrees)));
  replaceObject(generalOwners, snapshot.generalOwners);
  replaceObject(loyaltyOverrides, snapshot.loyaltyOverrides);
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
  for (const army of allArmies(true)) {
    if (army.resolvedTurn === state?.turn && !resolvedArmyIds.has(army.id)) resolvedArmyIds.add(army.id);
  }
  replaceArray(armyOrderHistory, snapshot.armyOrderHistory);
  replaceObject(turnReady, snapshot.turnReady);
  replaceArray(pendingProvinceClaims, snapshot.pendingProvinceClaims);
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
  renderHandDock();
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
    renderHandDock();
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
  } catch (error) {
    console.warn("Shared game synchronization delayed:", error.message);
  } finally {
    sharedSyncInFlight = false;
  }
}

function indexCards() {
  cardIndex = {};
  for (const group of Object.values(bootstrap.cards)) {
    for (const card of group) cardIndex[card.id] = card;
  }
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
    INITIAL_CITY_FACTIONS[city.id] ||= city.faction;
    const candidates = Object.values(cells).filter((cell) =>
      !occupiedCityCells.has(cell.key)
      && (!cell.river || cell.railBridge)
    );
    const sameFaction = candidates.filter((cell) => cell.fac === city.faction);
    const pool = sameFaction.length ? sameFaction : candidates;
    const cell = pool.reduce((nearest, candidate) => {
      const distance = (candidate.lon - city.lon) ** 2 + (candidate.lat - city.lat) ** 2;
      return !nearest || distance < nearest.distance ? { cell: candidate, distance } : nearest;
    }, null)?.cell;
    city.cellKey = cell?.key || null;
    if (!cell) throw new Error(`No valid tile available for city ${city.name}`);
    if (cell.river && !cell.railBridge) throw new Error(`City ${city.name} requires a railway bridge`);
    cell.city = city;
    occupiedCityCells.add(cell.key);
  }

  markRiverPortWater();
}

// 河港城市的地格一律視為水域。天然河道保留原名，其餘標為內河。
function markRiverPortWater() {
  for (const cell of Object.values(cells)) {
    if (cell.city?.port !== "river") continue;
    cell.portWater = true;
    if (!cell.river) cell.river = nearestRiverName(cell) || "內河";
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

function nearestFreeCell(origin, occupied) {
  let best = null;
  let bestDistance = Infinity;
  for (const cell of Object.values(cells)) {
    if (!cell.land || occupied.has(cell.key) || cell.city) continue;
    const distance = (cell.lon - origin.lon) ** 2 + (cell.lat - origin.lat) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = cell;
    }
  }
  return best;
}

function snapArmiesToStartCities() {
  const occupied = new Set();
  const cityById = new Map((bootstrap.strategic_map?.cities || []).map((city) => [city.id, city]));
  for (const armies of Object.values(ARMY_POSITIONS)) {
    for (const army of armies) {
      const city = cityById.get(army.startCityId);
      const home = city?.cellKey ? cells[city.cellKey] : null;
      if (!home) continue;
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
    if (event.button !== 0 || event.target.closest(".army-marker, .battle-marker")) return;
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

function cardTitle(card) {
  if (!card) return "無事件";
  const bits = [card.name || card.id];
  if (card.category) bits.push(card.category);
  if (card.foreign_power) bits.push(card.foreign_power);
  if (card.npc_faction) bits.push(card.npc_faction);
  return bits.join(" · ");
}

function shortEffect(card) {
  if (!card) return "尚未抽事件。按「下一回合」開始新回合。";
  const injected = card.generated_event_cards?.length
    ? `\n\n注入事件：${card.generated_event_cards.map((c) => c.name || c.id).join("、")}`
    : "";
  return `${cardTitle(card)}\n\n${card.effect || "無效果文字"}${injected}`;
}

function debtServiceTitle(profile = state?.players?.[currentPlayer]) {
  const service = profile?.last_debt_service;
  if (!service) return "現金收入；若有負債，每回合先加 2% 利息，再用一半現金收入還債。";
  const effects = (service.cash_effects || [])
    .map((effect) => `${effect.name || effect.effect_id}: ${effect.amount >= 0 ? "+" : ""}${effect.amount}`)
    .join("；");
  return [
    `城市收入 ${service.gross_income ?? 0}`,
    `債務利息 +${service.interest ?? 0}`,
    `強制還債 -${service.forced_repayment ?? 0}`,
    `實收 ${service.net_income ?? 0}`,
    `負債 ${service.debt_before ?? 0} -> ${service.debt_after ?? 0}`,
    effects ? `持續效果：${effects}` : "",
  ].filter(Boolean).join("；");
}

function updateTopBar() {
  $("turnBadge").textContent = `回合 ${state.turn}`;
  const profile = state.players[currentPlayer];
  if (!profile) return;
  // 旗幟與陣營名移到右側部隊操作板頂端，最上一排只留數字。
  $("factionStats").innerHTML = `
    <span title="${debtServiceTitle(profile)}">$${profile.treasury ?? 0} (+${profile.income ?? 0}/回合)</span>
    <span title="可用工廠點與每回合城市產出">工廠 ${profile.factory_points ?? 0} (+${profile.factory_income ?? 0}/回合)</span>
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
}

function functionCardDrawCost() {
  return bootstrap?.features?.function_card_draw_cost || DEFAULT_FUNCTION_CARD_DRAW_COST;
}

function functionPurchasePromptKey(player = currentPlayer) {
  return `${state?.turn || 0}:${player}`;
}

function canPurchaseFunctionCard(payload = state?.players?.[currentPlayer], player = currentPlayer) {
  if (!bootstrap?.features?.function_cards || !payload || payload.pending_draw) return false;
  if (Number(payload.function_purchase_count || 0) >= functionCardDrawLimit()) return false;
  if ((payload.treasury || 0) < functionCardDrawCost()) return false;
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
  let note = `可支付 $${cost} 抽 1 張功能卡；每位玩家每回合最多 ${limit} 張（已抽 ${used}/${limit}）。`;
  if (payload?.pending_draw) note = "先棄置一張手牌，接收已購買的新功能卡。";
  else if (used >= limit) note = `本回合已抽滿 ${limit} 張功能卡。`;
  else if ((payload?.treasury || 0) < cost) note = `現金不足，購買功能卡需要 $${cost}。`;
  else if (deckCount <= 0) note = "功能卡牌庫已空。";
  return `
    <div class="function-purchase ${context}">
      <div>
        <b>功能卡購買</b>
        <span>${note}</span>
      </div>
      <button data-buy-function-card="${currentPlayer}" ${canPurchaseFunctionCard(payload) ? "" : "disabled"}>支付 $${cost}</button>
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
    renderHandDock();
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
  if (!army || armyFaction === observer || factionHasPoliceProtection(armyFaction)) return false;
  const province = provinceForArmy(army);
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
  const economyFlags = Boolean(payload?.loan_penalties?.length || payload?.soong_patronage
    || payload?.bank_success_rate || payload?.loan_interest_override);
  if (!effects.length && !cityEffects.length && !uprisings.length && !railways.length && !economyFlags) return "";
  return `<div class="active-effect-list">
    ${effects.map((effect) => {
      const label = effect.kind === "police_system"
        ? `警政保護剩餘 ${effect.remaining_turns} 回合`
        : effect.kind === "intel_network"
          ? `情報網：${effect.target_province}，剩餘 ${effect.remaining_turns} 回合`
          : effect.kind === "ideology_shield"
            ? `${effect.name || "自由中國教育家"}：免疫共黨暴動與紅軍起義，剩餘 ${effect.remaining_turns} 回合`
            : `${effect.name || "持續效果"}剩餘 ${effect.remaining_turns} 回合`;
      return `<span>${label}</span>`;
    }).join("")}
    ${cityEffects.map((effect) => {
      const role = effect.initiator === currentPlayer ? "發動" : "受害";
      const progress = `${effect.garrison_progress || 0}/${effect.required_turns || 3}`;
      return `<span>青幫暴動(${role})：${effect.province}，鎮壓 ${progress}</span>`;
    }).join("")}
    ${uprisings.map((effect) => {
      const role = effect.initiator === currentPlayer ? "發動" : "受害";
      const names = (effect.cities || []).map((city) => city.name).join("、");
      return `<span>${effect.name || "紅軍起義"}(${role})：${names}，需駐 ${effect.required_battalions || 5} 營</span>`;
    }).join("")}
    ${railways.map((effect) => `<span>${effect.railway} 搶修中，剩餘 ${effect.remaining_turns} 回合</span>`).join("")}
    ${(payload?.loan_penalties || []).map((clause) => `<span>${clause.label || "貸款違約條款"}${
      clause.remaining_turns === null || clause.remaining_turns === undefined
        ? "（永久）" : `，剩餘 ${clause.remaining_turns} 回合`}</span>`).join("")}
    ${payload?.soong_patronage ? `<span>上海宋家支持：每三回合 +$${payload.soong_patronage.cash}、工廠 +${payload.soong_patronage.factory}</span>` : ""}
    ${payload?.loan_interest_override !== null && payload?.loan_interest_override !== undefined
      ? `<span>中央銀行：新借款利率 ${Math.round(payload.loan_interest_override * 100)}%、期限 +${payload.loan_term_bonus || 0}</span>` : ""}
    ${payload?.bank_success_rate ? `<span>信用受損：列強銀行申貸成功率 ${Math.round(payload.bank_success_rate * 100)}%</span>` : ""}
  </div>`;
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
    if (loan.bank_success_rate) parts.push(`此後列強銀行申貸成功率 ${Math.round(loan.bank_success_rate * 100)}%`);
  }
  if (action.unlock_effect?.kind === "central_bank") {
    const bank = action.unlock_effect;
    parts.push(`此後新借款利率一律 ${Math.round(bank.interest_per_turn * 100)}%、期限 +${bank.loan_term_bonus} 回合`);
  }
  if (action.unlock_effect?.kind === "ideology_counter") {
    const cleared = [...new Set(action.unlock_effect.cleared || [])].map((code) => factionLabel(code, code === viewer));
    parts.push(`壓制了 ${cleared.join("、")} 的自由中國教育家`);
  }
  if (action.timed_effect?.kind === "ideology_shield") {
    const cancelled = action.timed_effect.cancelled_effects || [];
    parts.push(`免疫紅軍起義與共黨暴動 ${action.timed_effect.remaining_turns} 回合`
      + (cancelled.length ? `，並使本回合的${cancelled.join("、")}失效` : ""));
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
        : action.timed_effect.kind === "rural_movement"
          ? `鄉村急行 ${action.timed_effect.tiles || 2} 格`
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
      parts.push(`${target}${action.city_disruption.province}青幫暴動，城市 ${cities} 產出停擺；需 15 戰力軍隊連續駐留 3 回合鎮壓`);
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
  if ((action.timed_effect?.owners || []).includes(viewer)) return true;
  return false;
}

function updateFeatureVisibility() {
  const cardsEnabled = Boolean(bootstrap?.features?.function_cards);
  const eventsEnabled = Boolean(bootstrap?.features?.events);
  document.body.classList.toggle("cards-enabled", cardsEnabled);
  document.querySelectorAll(".feature-cards").forEach((element) => { element.hidden = !cardsEnabled; });
  document.querySelectorAll(".feature-events").forEach((element) => { element.hidden = !eventsEnabled || !state?.last_event; });
  $("handDock").hidden = !cardsEnabled;
}

function updatePhaseBanner() {
  const phaseLabels = {
    event: "事件階段",
    preparation: "準備階段",
    military: "軍事行動"
  };
  const eventName = state?.last_event?.name;
  const phaseName = phaseLabels[currentPhase] || "事件階段";
  $("phaseBanner").querySelector(".phase-label").textContent = eventName
    ? `${phaseName} · ${eventName}`
    : phaseName;
  $("phaseBanner").title = state?.last_event?.effect || phaseName;
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

  // Event history button
  $("eventHistoryBtn").addEventListener("click", () => {
    if (!state.last_event) return;
    $("eventModal").classList.add("active");
    $("eventCardDisplay").textContent = shortEffect(state.last_event);
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
    case "economy":
      element.innerHTML = renderEconomyPanel();
      attachEconomyHandlers(element);
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
    case "eventHistory":
      renderEventHistory();
      break;
  }
}

function renderEventHistory() {
  const element = $("eventHistoryContent");
  if (!element) return;

  if (eventHistory.length === 0) {
    element.innerHTML = '<div class="empty-state">尚無事件記錄</div>';
    return;
  }

  element.innerHTML = eventHistory.map((evt, idx) => `
    <div class="event-history-item">
      <div class="event-turn-badge">第 ${evt.turn} 回合</div>
      <div class="event-history-card">
        <h3>${evt.card ? evt.card.name : '無事件'}</h3>
        ${evt.card ? `<p>${evt.card.effect || '無效果'}</p>` : ''}
      </div>
    </div>
  `).reverse().join('');
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
  html += `
    <section class="jail-roster">
      <h3>被俘將領</h3>
      ${prisoners.length ? prisoners.map((record) => `
        <div class="jail-general">
          ${renderGeneralTreeCard(record.general, { includeCaptured: true })}
          <div><small>原屬 ${FACTIONS[record.originFaction]?.name || record.originFaction}</small>
            <select data-recruit-superior="${record.armyId}" ${lieutenants.length ? "" : "disabled"}>${lieutenants.map((general) => `<option value="${general.id}">隸屬 ${general.name}</option>`).join("")}</select>
            <button data-recruit-prisoner="${record.armyId}" ${lieutenants.length && (state.players[currentPlayer]?.unit_reserves?.infantry || 0) >= 5 ? "" : "disabled"}>招降 · 步兵5營</button>
          </div>
        </div>`).join("") : '<div class="empty-state compact">目前無俘虜</div>'}
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
      const superiorId = root.querySelector(`[data-recruit-superior="${button.dataset.recruitPrisoner}"]`)?.value;
      const deploymentCell = recruitmentDeploymentCell(currentPlayer);
      if (!superiorId || !deploymentCell) {
        showNotice(!superiorId ? "沒有可隸屬的現役中將。" : "沒有可部署新編軍的己方主要城市。");
        return;
      }
      button.disabled = true;
      try {
        const result = await api("/api/recruit-captive-general", { player: currentPlayer });
        state = result.state;
        syncStrategicCitiesFromState();
        const [record] = prisoners.splice(index, 1);
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
    return army?.status !== "jailed";
  });
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

function installTransferredCommand(transferred, destinationFaction, superiorId, rootLoyalty = 2) {
  const destinationTree = generalTrees[destinationFaction];
  const superior = destinationTree?.generals?.[superiorId];
  if (!destinationTree || !superior || superior.role !== "lieutenant_general") throw new Error("invalid lieutenant affiliation");
  const transferredIds = new Set(transferred.map((general) => general.id));
  const root = transferred[0];
  for (const general of transferred) {
    const copied = JSON.parse(JSON.stringify(general));
    copied.faction = FACTIONS[destinationFaction].name;
    copied.status = "active";
    copied.loyalty_exempt = false;
    copied.loyalty = copied.id === root.id ? rootLoyalty : 1;
    copied.role = copied.id === root.id ? "major_general" : (copied.role === "great_general" ? "major_general" : copied.role);
    copied.subordinates = (copied.subordinates || []).filter((id) => transferredIds.has(id));
    destinationTree.generals[copied.id] = copied;
    generalOwners[copied.id] = destinationFaction;
    loyaltyOverrides[copied.id] = copied.loyalty;
  }
  superior.subordinates ||= [];
  if (!superior.subordinates.includes(root.id)) superior.subordinates.push(root.id);
}

function recruitCapturedGeneral(record, faction, superiorId, deploymentCell) {
  const army = armyById(record.armyId);
  const sourceTree = generalTrees[record.originFaction];
  const transferredIds = [record.general.id, ...descendantGeneralIds(sourceTree, record.general.id)];
  const transferred = transferredIds
    .map((id) => sourceTree?.generals?.[id] || (id === record.general.id ? record.general : null))
    .filter(Boolean)
    .map((general) => JSON.parse(JSON.stringify(general)));
  for (const general of transferred) detachGeneralFromTree(sourceTree, general.id);
  installTransferredCommand(transferred, faction, superiorId, 2);
  const general = transferred[0] || record.general;
  const nextNumber = nextAvailableArmyNumber(faction, army.id);
  Object.assign(army, {
    faction,
    general: general.name,
    designator: formatArmyDesignator(nextNumber),
    status: "active",
    units: { infantry: 5, cavalry: 0, artillery: 0, machine_gun: 0 },
  });
  moveArmyToCell(army, deploymentCell);
  state.players[faction].army_reinforcements[army.id] = {};
  for (const fieldArmy of allArmies(true).filter((item) => transferredIds.includes(item.generalId))) {
    fieldArmy.faction = faction;
    fieldArmy.status = "active";
    markArmyResolved(fieldArmy);
    const oldLedger = state.players[record.originFaction]?.army_reinforcements?.[fieldArmy.id];
    if (oldLedger) {
      state.players[faction].army_reinforcements[fieldArmy.id] = { ...oldLedger };
      if (state.players[record.originFaction]) {
        delete state.players[record.originFaction].army_reinforcements[fieldArmy.id];
      }
    }
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
  const transferredIds = [army.generalId, ...descendantGeneralIds(sourceTree, army.generalId)];
  const transferred = transferredIds
    .map((id) => sourceTree?.generals?.[id])
    .filter(Boolean)
    .map((general) => JSON.parse(JSON.stringify(general)));
  for (const general of transferred) detachGeneralFromTree(sourceTree, general.id);
  installTransferredCommand(transferred, destinationFaction, superiorId, 2);
  for (const fieldArmy of allArmies(true).filter((item) => transferredIds.includes(item.generalId))) {
    fieldArmy.designator = formatArmyDesignator(nextAvailableArmyNumber(destinationFaction, fieldArmy.id));
    fieldArmy.faction = destinationFaction;
    fieldArmy.status = "active";
    markArmyResolved(fieldArmy);
    const oldLedger = state.players[sourceFaction]?.army_reinforcements?.[fieldArmy.id];
    if (oldLedger) {
      state.players[destinationFaction].army_reinforcements[fieldArmy.id] = { ...oldLedger };
      if (state.players[sourceFaction]) {
        delete state.players[sourceFaction].army_reinforcements[fieldArmy.id];
      }
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
  if (loyalty === null || general?.loyalty_exempt || general?.absolute_loyalty) {
    showNotice("此將領屬於派系核心，不能以金錢策反。");
    return;
  }
  const result = await api("/api/attempt-defection", {
    player: currentPlayer,
    loyalty,
    force: forcePoints(armyUnits(army)),
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
  uiNotice = `策反成功：${army.general}及其麾下 ${Math.max(0, transferred.length - 1)} 名將領轉投我方，原部隊完整保留。`;
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
  const unitsText = hasArmy ? unitSummary(armyUnits(fieldArmy)) : "無部隊";
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
        <div class="tree-faction">${general.faction}</div>
        <div class="tree-units">${unitsText}</div>
        <div class="tree-traits">${(general.traits || []).map(traitChip).join("")}</div>
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
  if (general.absolute_loyalty) {
    return { value: 10, tooltip: "絕對忠誠: 固定 10\n不受功能卡、戰損或策反效果影響" };
  }
  if (Object.hasOwn(loyaltyOverrides, general.id)) {
    return { value: loyaltyOverrides[general.id], tooltip: `當前忠誠: ${loyaltyOverrides[general.id]}\n受俘虜、招降、策反或功能卡影響` };
  }
  const baseLoyalty = Number(general.loyalty);
  if (!fieldArmy || fieldArmy.status === "jailed" || general.status === "recruited") {
    const value = Math.min(baseLoyalty, 2);
    return { value, tooltip: `基礎忠誠: ${baseLoyalty}\n無直屬部隊: -${Math.max(0, baseLoyalty - value)}` };
  }
  const faction = factionForArmy(fieldArmy);
  const friendlyForces = allArmies()
    .filter((army) => factionForArmy(army) === faction)
    .filter((army) => army.status !== "jailed")
    .map((army) => forcePoints(armyUnits(army)));
  const currentForce = forcePoints(armyUnits(fieldArmy));
  const averageForce = friendlyForces.reduce((sum, value) => sum + value, 0) / Math.max(1, friendlyForces.length);
  const relativePower = Math.max(-2, Math.min(2, Math.round((currentForce / Math.max(1, averageForce) - 1) * 3)));
  const initialForce = forcePoints(INITIAL_ARMY_UNITS[fieldArmy.id] || {});
  const lossRate = Math.max(0, (initialForce - currentForce) / Math.max(1, initialForce));
  const battleLoss = -Math.min(4, Math.floor(lossRate * 5));
  const value = Math.max(0, Math.min(10, baseLoyalty + relativePower + battleLoss));
  return {
    value,
    tooltip: `基礎忠誠: ${baseLoyalty}\n相對實力影響: ${relativePower >= 0 ? '+' : ''}${relativePower}\n戰損影響: ${battleLoss}\n現有戰力: ${Math.round(currentForce)} / 初始 ${Math.round(initialForce)}`,
  };
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
}

function renderEconomyPanel() {
  if (!currentPlayer || !state.players[currentPlayer]) {
    return `<div class="empty-state">請選擇玩家</div>`;
  }

  const payload = state.players[currentPlayer];
  const cityEconomy = payload.city_economy || [];
  const breakdown = (field, suffix) => `
    <div class="value-breakdown">
      <b>城市來源</b>
      ${cityEconomy.map((city) => `
        <span><i>${city.name} · ${city.province}</i><strong>${city[field]} ${suffix}</strong></span>
      `).join("")}
    </div>
  `;
  const debtService = payload.last_debt_service;
  const debtBreakdown = debtService ? `
    <div class="value-breakdown">
      <b>上回合債務結算</b>
      <span><i>城市收入</i><strong>+$${debtService.gross_income ?? 0}</strong></span>
      <span><i>2% 利息</i><strong>+$${debtService.interest ?? 0} 債</strong></span>
      <span><i>逾期強制清償</i><strong>-$${debtService.forced_repayment ?? 0}</strong></span>
      <span><i>實收現金</i><strong>+$${debtService.net_income ?? 0}</strong></span>
      ${(debtService.cash_effects || []).map((effect) => `
        <span><i>${effect.name || effect.effect_id}</i><strong>${effect.amount >= 0 ? "+" : ""}$${effect.amount}</strong></span>
      `).join("")}
    </div>
  ` : "";
  const canRepay = (payload.debt || 0) > 0 && (payload.treasury || 0) > 0;

  return `
    <div class="economy-grid">
      <div class="economy-stat" tabindex="0" title="${debtServiceTitle(payload)}">
        <div class="economy-label">每回合現金</div>
        <div class="economy-value cash">+$${payload.income ?? 0}</div>
        <div class="economy-hint">${(payload.debt || 0) > 0 ? "逾期貸款才會強制扣收入" : "城市稅收"}</div>
        ${breakdown("cash", "現金")}
      </div>
      <div class="economy-stat" tabindex="0">
        <div class="economy-label">可用工廠點</div>
        <div class="economy-value factory">${payload.factory_points ?? 0}</div>
        <div class="economy-hint">每回合 +${payload.factory_income ?? 0}</div>
        ${breakdown("factory", "工廠")}
      </div>
      <div class="economy-stat compact">
        <div class="economy-label">金庫</div>
        <div class="economy-value">$${payload.treasury ?? 0}</div>
      </div>
      <div class="economy-stat compact">
        <div class="economy-label">負債</div>
        <div class="economy-value debt">$${payload.debt ?? 0}</div>
        ${debtBreakdown}
      </div>
    </div>
    <div class="debt-repay-panel">
      <label>償還負債<input id="debtRepayAmount" type="number" min="1" max="${Math.min(payload.debt || 0, payload.treasury || 0)}" value="${Math.min(payload.debt || 0, payload.treasury || 0)}" ${canRepay ? "" : "disabled"}></label>
      <button data-repay-debt ${canRepay ? "" : "disabled"}>還款</button>
    </div>
  `;
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
        ? `<span class="loan-blocked-note">${row.tier === "blocked" ? "關係交惡" : row.tier_label || "不承作"}</span>`
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
  return `
    <div class="loan-summary">
      <span>金庫 <b>$${data.treasury ?? 0}</b></span>
      <span>負債總額 <b class="debt">$${total}</b></span>
      <span>回合 <b>${data.turn ?? 0}</b></span>
    </div>

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
        renderPanel("economy");
        showNotice(`向${result.loan.bank_name}借款 $${result.loan.principal}，${result.loan.term_turns} 回合到期。`);
      } catch (error) {
        showNotice(error.message);
      }
    });
  });
}


function attachEconomyHandlers(root = document) {
  root.querySelector("[data-repay-debt]")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/repay-debt", {
        player: currentPlayer,
        amount: Number(root.querySelector("#debtRepayAmount")?.value || 0),
      });
      state = result.state;
      syncStrategicCitiesFromState();
      updateTopBar();
      renderPanel("economy");
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
      { key: "su", name: "蘇聯", territories: "蘇聯遠東、海參崴" },
      { key: "uk", name: "英國", territories: "華南沿海商路、印緬、印度" },
      { key: "fr", name: "法國", territories: "法屬印度支那、河內" },
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
        牌庫 ${payload.function_deck.length} · 手牌 ${payload.hand.length} · 棄牌 ${payload.discard.length} · 本回合抽牌 ${payload.function_purchase_count || 0}/${functionCardDrawLimit()}
      </div>
    </div>
    <div class="card-detail-list">${cardsHtml}</div>
  `;
}

function attachCardHandlers(root = document) {
  root.querySelectorAll("[data-buy-function-card]").forEach((button) => {
    button.addEventListener("click", () => buyFunctionCard(button));
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
        const result = await api("/api/use-function", {
          player: button.dataset.player,
          card_id: button.dataset.use,
          target_general_id: targetGeneralId,
          target_owner: root.querySelector(`[data-card-target-owner="${button.dataset.use}"]`)?.value
            || generalOwners[targetGeneralId],
          target_city_id: root.querySelector(`[data-card-target-city="${button.dataset.use}"]`)?.value,
          target_province: root.querySelector(`[data-card-target-province="${button.dataset.use}"]`)?.value,
          target_railway: root.querySelector(`[data-card-target-railway="${button.dataset.use}"]`)?.value,
        });
        state = result.state;
        applyFunctionSideEffects(result);
        syncStrategicCitiesFromState();
        uiNotice = functionActionMessage(state.last_action, currentPlayer);
        await publishSharedState(true);
        updateTopBar();
        initMap();
        renderHandDock();
        renderPendingActions();
        if ($("panelGenerals")?.classList.contains("active")) renderPanel("generals");
        if ($("panelEconomy")?.classList.contains("active")) renderPanel("economy");
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
        renderHandDock();
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
    if (!general || general.loyalty === null || general.absolute_loyalty || (!ownCard && general.loyalty_exempt)) return [];
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
  const generalId = outcome.target_general_id;
  const owner = generalOwners[generalId];
  const tree = generalTrees[owner];
  const general = tree?.generals?.[generalId];
  if (!general) return;
  general.status = "killed";
  for (const army of allArmies(true)) {
    if (army.generalId === generalId) army.status = "killed";
  }
  for (const childId of descendantGeneralIds(tree, generalId)) {
    const child = tree.generals?.[childId];
    if (!child || child.role !== "major_general") continue;
    if (child.absolute_loyalty || child.loyalty_exempt || child.loyalty === null) continue;
    loyaltyOverrides[childId] = 0;
  }
}

function loyaltyCardTargetMarkup(card) {
  if (!["unit_promotion", "local_autonomy_agitation"].includes(card.id)) return "";
  const targets = loyaltyCardTargets(card);
  return `<label class="card-target">指定將領<select data-card-target="${card.id}" ${targets.length ? "" : "disabled"}>${targets.map(({ general, owner, loyalty }) => `<option value="${general.id}">${FACTIONS[owner]?.shortName || owner} · ${general.name}（忠誠 ${loyalty}）</option>`).join("")}</select></label>`;
}

function functionCardTargetMarkup(card) {
  if (card.mechanic === "qing_gang_riot") {
    const targets = TURN_PLAYERS.filter((player) => player !== currentPlayer);
    const provinces = provinceOptions();
    return `
      <label class="card-target">指定勢力<select data-card-target-owner="${card.id}">${targets.map((player) => `<option value="${player}">${FACTIONS[player]?.name || player}</option>`).join("")}</select></label>
      <label class="card-target">指定省份<select data-card-target-province="${card.id}">${provinces.map((province) => `<option value="${province}">${province}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "railway_sabotage") {
    const downed = disabledRailways();
    const lines = (card.railways || []).filter((name) => !downed.has(name));
    if (!lines.length) return `<div class="card-target-note">所有可指定的鐵路都已在搶修中</div>`;
    return `<label class="card-target">指定鐵路<select data-card-target-railway="${card.id}">${lines.map((name) => `<option value="${name}">${name}</option>`).join("")}</select></label>`;
  }
  if (["reserve_loss", "communist_riot", "red_army_uprising"].includes(card.mechanic)) {
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
  if (card.mechanic === "intel_network") {
    const provinces = provinceOptions();
    return `<label class="card-target">指定省份<select data-card-target-province="${card.id}">${provinces.map((province) => `<option value="${province}">${province}</option>`).join("")}</select></label>`;
  }
  if (card.mechanic === "city_development") {
    const cities = state.players[currentPlayer]?.city_economy || [];
    return `<label class="card-target">指定城市<select data-card-target-city="${card.id}" ${cities.length ? "" : "disabled"}>${cities.map((city) => `<option value="${city.id}">${city.name} · $${city.cash} 工${city.factory}</option>`).join("")}</select></label>`;
  }
  return loyaltyCardTargetMarkup(card);
}

function renderHandDock() {
  if (!bootstrap.features?.function_cards) return;
  const payload = state.players[currentPlayer];
  if (!payload) return;
  const cards = payload.hand.map((id) => cardIndex[id]).filter(Boolean);
  const pendingCard = payload.pending_draw ? cardIndex[payload.pending_draw] : null;
  $("handCount").textContent = `${cards.length} / ${MAX_HAND_SIZE}`;
  $("handDock").classList.toggle("discard-required", Boolean(pendingCard));

  const prompt = pendingCard
    ? `<div class="discard-banner">新牌「${pendingCard.name}」等待加入：選一張棄置</div>`
    : functionPurchaseMarkup(payload, "dock") + activeEffectsMarkup(payload);
  const cardMarkup = cards.length
    ? cards.map((card, index) => `
      <article class="hand-card-mini" style="--card-index:${index}" tabindex="0">
        <div class="hand-card-category">${card.category || "功能"}</div>
        <h3>${card.name}</h3>
        ${card.story ? `<p class="hand-card-story">${card.story}</p>` : ""}
        <p>${card.effect || "無效果文字"}</p>
        ${functionCardTargetMarkup(card)}
        ${pendingCard
          ? `<button class="hand-card-action discard" data-discard="${card.id}">棄置此牌</button>`
          : `<button class="hand-card-action" data-use="${card.id}" data-player="${currentPlayer}">打出</button>`}
      </article>
    `).join("")
    : '<div class="hand-empty">目前無手牌</div>';

  $("handCards").innerHTML = prompt + cardMarkup;
  attachCardHandlers($("handCards"));
}

function setupEventModal() {
  $("eventModalClose").addEventListener("click", () => {
    $("eventModal").classList.remove("active");
    // After viewing event, stay in same phase (Civ6 style)
  });
}

function showEventIfNeeded(turn) {
  if (!bootstrap.features?.events) return;
  if (!state.last_event) return;
  if (!eventHistory.some((entry) => entry.turn === turn)) {
    eventHistory.push({ turn, card: state.last_event });
  }
  updateEventBadge();

  // Keep routine events in the turn dock; interrupt only at major intervals.
  if (turn % 3 === 0) {
    $("eventModal").classList.add("active");
    $("eventCardDisplay").textContent = shortEffect(state.last_event);
    $("eventCardDisplay").classList.remove("empty");
  }
}

function updateEventBadge() {
  const badge = $("eventBadge");
  if (state?.last_event) {
    badge.textContent = "!";
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

async function boot() {
  [bootstrap, provinceGeoJson] = await Promise.all([
    api("/api/bootstrap"),
    fetch("/data/provinces_1926.geojson").then((response) => response.json()),
  ]);
  indexCards();
  indexScenarioCells();
  snapArmiesToStartCities();
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

  $("playerSelect").addEventListener("change", async (e) => {
    currentPlayer = e.target.value;
    selectedArmyId = null;
    selectedBattleId = null;
    moveMode = false;
    uiNotice = null;

    // Reload general tree for new faction
    await loadGeneralTreeForFaction(currentPlayer);

    // Re-render army markers for new faction
    renderArmyMarkers(currentPlayer);
    updateTopBar();
    renderHandDock();
    renderPendingActions();

    // Refresh all open panels when faction changes
    const openPanel = document.querySelector('.overlay-panel.active');
    if (openPanel) {
      const panelId = openPanel.id.replace('panel', '').toLowerCase();
      const firstChar = panelId.charAt(0).toLowerCase();
      const rest = panelId.slice(1);
      const panelName = firstChar + rest;
      renderPanel(panelName);
    }
  });

  setupPanels();
  setupEventModal();
  setupPendingActions();
  setupUiTooltip();
  updateTopBar();
  updatePhaseBanner();

  // Initialize map rendering
  initMap();
  setupMapZoom();
  renderHandDock();
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
  ctx.strokeStyle = 'rgba(31, 28, 23, 0.94)';
  ctx.lineWidth = 4.2;
  for (const railroad of bootstrap.strategic_map?.railroads || []) {
    const route = (railroad.cellKeys || []).map((key) => cells[key]).filter(Boolean);
    if (!route.length) continue;
    ctx.beginPath();
    route.forEach((cell, index) => {
      const x = hcx(cell.c);
      const y = hcy(cell.c, cell.r);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(238, 224, 190, 0.95)';
  ctx.lineWidth = 1.8;
  ctx.setLineDash([2, 4]);
  for (const railroad of bootstrap.strategic_map?.railroads || []) {
    const route = (railroad.cellKeys || []).map((key) => cells[key]).filter(Boolean);
    if (!route.length) continue;
    ctx.beginPath();
    route.forEach((cell, index) => {
      const x = hcx(cell.c);
      const y = hcy(cell.c, cell.r);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
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
    ctx.fillStyle = `rgba(${66 - level * 5}, ${60 - level * 4}, ${48 - level * 3}, 0.9)`;
    ctx.fill();
    ctx.strokeStyle = level >= 4 ? '#f0c65a' : '#f7f1df';
    ctx.lineWidth = 1.1 + level * 0.28;
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
    if (cell.railBridge) {
      ctx.strokeStyle = '#79b8d2';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - 9, y + 7);
      ctx.quadraticCurveTo(x - 4, y + 2, x, y + 7);
      ctx.quadraticCurveTo(x + 4, y + 12, x + 9, y + 7);
      ctx.stroke();
    }
    for (let marker = 0; marker < level; marker++) {
      ctx.fillStyle = level >= 4 ? '#f0c65a' : '#dcd3bf';
      ctx.fillRect(x - ((level - 1) * 2) + marker * 4 - 1, y + 5, 2, 2);
    }
    ctx.font = '700 8px Inter';
    ctx.fillStyle = '#fff9e8';
    ctx.fillText(`$${city.cash} 工${city.factory}`, x, y + 11);
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#f1ead8';
    ctx.font = '700 10px Inter';
    ctx.strokeText(city.name, x, y - s - 7);
    ctx.fillStyle = '#28231c';
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
  ctx.fillStyle = '#c8b894';
  ctx.fillRect(0, 0, MAPW, MAPH);
  if (outsideMapArt.complete && outsideMapArt.naturalWidth) {
    ctx.globalAlpha = 0.72;
    ctx.drawImage(outsideMapArt, 0, 0, MAPW, MAPH);
    ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = 'rgba(64, 55, 42, 0.24)';
  ctx.lineWidth = 1;
  for (let x = -MAPH; x < MAPW + MAPH; x += 42) {
    ctx.beginPath();
    ctx.moveTo(x, MAPH);
    ctx.lineTo(x + MAPH, 0);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(52, 48, 41, 0.42)';
  ctx.font = '700 16px Fraunces, Georgia, serif';
  ctx.textAlign = 'center';
  ctx.fillText('外蒙 / 西域方向', 250, 120);
  ctx.fillText('日本海方向', MAPW - 190, 470);
  ctx.fillText('南洋航路', MAPW - 190, MAPH - 110);
  ctx.fillText('印緬邊境', 170, MAPH - 160);
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

  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const cell = cells[`${c},${r}`];
      if (!cell || !cell.land) continue;

      const X = hcx(c), Y = hcy(c, r);

      // Draw faction-colored hex fill
      if (cell.fac && FACTIONS[cell.fac]) {
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

      // Highlight river hexes
      if (cell.river) {
        ctx.fillStyle = '#92b6c1';
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

function renderArmyMarkers(faction) {
  const svgOverlay = document.getElementById('armyOverlay');
  svgOverlay.innerHTML = ''; // Clear existing markers
  ensureHostileEncounters();

  const armies = Object.values(ARMY_POSITIONS).flatMap((factionArmies) =>
    factionArmies.map((army) => ({ army, armyFaction: factionForArmy(army) }))
  ).filter(({ army, armyFaction }) => army.status !== "jailed" && army.status !== "killed"
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
    halo.setAttribute('r', 16);
    halo.setAttribute('fill', color);
    halo.setAttribute('opacity', '0.3');
    if (armyFaction === faction && !armyIsResolvedThisTurn(army) && !activeBattleForArmy(army)) g.appendChild(halo);

    // Army circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', X);
    circle.setAttribute('cy', Y);
    circle.setAttribute('r', 12.5);
    circle.setAttribute('fill', color);
    circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', '2');
    g.appendChild(circle);

    // 番號 text (designator number)
    const numberMatch = army.designator.match(/第(.+)軍/);
    const number = numberMatch ? numberMatch[1] : (idx + 1);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', X);
    text.setAttribute('y', Y + 4);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-weight', 'bold');
    text.setAttribute('fill', '#fff');
    text.textContent = number;
    g.appendChild(text);

    // Tooltip on hover
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = armyTooltipText(army, faction);
    g.appendChild(title);

    const focusArmy = () => {
      const battle = activeBattleForArmy(army);
      if (battle) selectBattle(battle.id);
      else if (armyFaction !== currentPlayer && moveMode) handleMapDestination(cell);
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

  renderBattleMarkers(svgOverlay);
}

function currentArmies() {
  return allArmies().filter((army) => factionForArmy(army) === currentPlayer);
}

function allArmies(includeInactive = false) {
  const armies = Object.values(ARMY_POSITIONS).flat();
  return includeInactive ? armies : armies.filter((army) => army.status !== "jailed" && army.status !== "killed");
}

function armyById(armyId) {
  return allArmies(true).find((army) => army.id === armyId) || null;
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
    ["pending", "ongoing"].includes(battle.status)
    && battleParticipantIds(battle).includes(army?.id)
  ) || null;
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
  const hasAbsolute = Boolean(firstGeneral?.absolute_loyalty || secondGeneral?.absolute_loyalty);
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
  if (activeBattles.some((battle) => battleParticipantIds(battle).includes(army.id))) return true;
  const nearbyArmy = allArmies().some((ownArmy) =>
    factionForArmy(ownArmy) === observer && cellWithinRange(ownArmy.cellKey, army.cellKey, 2)
  );
  if (nearbyArmy) return true;
  return armyRevealedByIntel(army, observer);
}

function selectedArmy() {
  return allArmies().find((army) => army.id === selectedArmyId) || null;
}

function armyUnits(army) {
  const faction = factionForArmy(army);
  const additions = state.players[faction]?.army_reinforcements?.[army.id] || {};
  return Object.fromEntries(
    Object.keys(UNIT_META).map((type) => [type, Math.max(0, Math.round((army.units[type] || 0) + (additions[type] || 0)))])
  );
}

function wholeUnits(units) {
  return Object.fromEntries(Object.keys(UNIT_META).map((type) => [
    type,
    Math.max(0, Math.round(Number(units?.[type] || 0))),
  ]));
}

function forcePoints(units) {
  return (units.infantry || 0)
    + (units.cavalry || 0)
    + (units.machine_gun || 0) * 2
    + (units.artillery || 0) * 4;
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
  if ($("panelEconomy")?.classList.contains("active")) renderPanel("economy");
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
  for (const battle of activeBattles) {
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
    label.textContent = '戰';
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = battle.status === 'pending' ? '戰鬥待決' : '查看戰果';
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
  selectedBattleId = battleId;
  const battle = activeBattles.find((item) => item.id === battleId);
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
  if (Object.values(currentSections).some((status) => status === "fleeing")) return 0;
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

function renderBattlePanel() {
  const root = $("battlePanel");
  const reports = [...activeBattles, ...battleReports].filter((item) => !hiddenBattleReportIds.has(item.id));
  const battle = reports.find((item) => item.id === selectedBattleId)
    || [...reports].reverse().find((item) =>
      item.attackerFaction === currentPlayer || item.defenderFaction === currentPlayer
    );
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
      <small class="battle-confirmation">${openingRound ? `${battle.confirmed?.A ? "進攻方已定策" : "等待進攻方"} · ${battle.confirmed?.B ? "防守方已定策" : "等待防守方"}` : battle.tacticRevision?.[currentSide] ? "援軍抵達，可重新定策一次" : battle.roundResolvedTurn === state.turn ? "本回合戰鬥已結算" : "沿用既定戰術；回合結束時自動交戰"}</small>` : `<div class="battle-result">${battle.status === "surrendered" ? `${battleSideLabel(battle, battle.surrenderedSide)}投降並被俘` : battle.result ? `勝方：${battle.result.winner === "A" ? battleSideLabel(battle, "A") : battle.result.winner === "B" ? battleSideLabel(battle, "B") : "雙方退卻"} · ${battle.result.rounds} 回合` : "部隊已撤出戰場"}<small>右鍵移除此情報</small></div>`}
  `;
}

function cityForArmy(army) {
  if (!army) return null;
  return (bootstrap.strategic_map?.cities || []).find((city) => city.cellKey === army.cellKey) || null;
}

function selectTile(cell) {
  selectedTileKey = cell?.key || null;
  renderTileInfo();
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
  if (concessionPowers.length) {
    tags.push(`<span class="tile-tag tile-tag-concession">租界城市</span>` + concessionPowers.map((key) => `
      <span class="tile-concession-power">${flagMarkup(key, "flag-chip concession-flag")}${POWER_NAME[key] || key}</span>
    `).join(""));
  }
  const concessionRow = tags.length ? `<div class="tile-concession">${tags.join("")}</div>` : "";
  root.hidden = false;
  root.innerHTML = `
    <div class="tile-info-heading"><b>${city?.name || "鄉野地格"}</b><span>${FACTIONS[cell.fac]?.shortName || "無控制"}</span></div>
    <div class="tile-info-grid">
      <span>地形<strong>${cell.river ? `水域 · ${cell.river}` : "陸地"}</strong></span>
      <span>聚落<strong>${city ? `${city.province} · ${city.level} 級城市` : `${strategicProvinceForCell(cell) || "未知省份"} · 鄉村`}</strong></span>
      <span>歸屬<strong>${FACTIONS[cell.fac]?.name || "無控制"}</strong></span>
      <span>工事<strong>${fortifications.join("、") || "無"}</strong></span>
      <span>產出<strong>$${city?.cash || 0} · 工廠 ${city?.factory || 0}</strong></span>
    </div>
    ${concessionRow}
    ${railroads.length ? `<small>鐵路：${railroads.map((name) => (disabledRailways().has(name) ? `${name}（搶修中）` : name)).join("、")}</small>` : ""}`;
}

function engineeringOperationsFor(army) {
  const general = generalById(army.generalId);
  const skills = new Set(general?.skills || []);
  for (const [skill, traits] of Object.entries(ENGINEERING_TRAIT_SKILLS)) {
    if ((general?.traits || []).some((trait) => traits.has(trait))) skills.add(skill);
  }
  return [...skills].filter((skill) => ENGINEERING_OPERATIONS[skill]);
}

function renderArmyDetail() {
  const root = $("armyDetail");
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
  const canReinforce = canOrder && city?.faction === currentPlayer && city.level >= 3 && cells[army.cellKey]?.fac === currentPlayer;
  const profile = state.players[currentPlayer];
  const engineering = isOwnArmy ? engineeringOperationsFor(army) : [];
  const joinableBattle = isOwnArmy ? joinableBattleForArmy(army) : null;
  const loyalty = general ? calculateGeneralLoyalty(general, army).value : null;
  const defectionForce = forcePoints(units);
  const loyaltyForDefection = Math.max(1, loyalty || 1);
  const defectionCost = Math.ceil((10 + defectionForce * 3 + loyaltyForDefection * 2) * 0.5);
  const defectionBaseChance = 0.45 - loyaltyForDefection * 0.04 - defectionForce * 0.003;
  const defectionChance = Math.round(Math.max(0.03, Math.min(0.60, defectionBaseChance * 1.25)) * 100);
  const lieutenants = availableLieutenantGenerals(currentPlayer);
  const canDefect = loyalty !== null && !general?.loyalty_exempt && !general?.absolute_loyalty && lieutenants.length
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
      ? traits.map(traitChip).join("")
      : '<span>無已知特質</span>'}</div>
    ${showComposition ? `
      <div class="army-composition">
        ${Object.keys(UNIT_META).map((type) => `
          <div>${unitSymbol(type, units[type])}<span>${UNIT_META[type].name}<small>${formatUnitQuantity(type, units[type])}</small></span></div>
        `).join("")}
      </div>
    ` : `<div class="enemy-hidden-composition"><b>兵力不明</b><span>敵軍編制需交戰或情報網揭露。</span></div>`}
    ${isOwnArmy ? absoluteTransferMarkup(army) : ""}
    ${!isOwnArmy ? `<div class="enemy-intelligence"><b>敵軍情報</b><span>忠誠 ${loyalty ?? "核心將領"}${loyalty === null ? "" : " / 10"}</span><small>${loyalty === null ? "派系核心不可策反" : showComposition ? `策反費用 $${defectionCost} · 成功率 ${defectionChance}%` : "兵力未明，策反費用與成功率不公開"}</small><select data-defect-superior>${lieutenants.map((item) => `<option value="${item.id}">成功後隸屬 ${item.name}</option>`).join("")}</select><button data-defect-army="${army.id}" ${canDefect ? "" : "disabled"}>策反</button></div>` : ""}
    ${fightingBattle ? `<div class="active-operation">交戰中：不可移動、休整或補充。請在戰鬥情報中定策。</div>` : ""}
    ${!fightingBattle && resolvedThisTurn ? `<div class="active-operation">本回合軍令已執行。</div>` : ""}
    ${army.specialOperation ? `<div class="active-operation">進行中：${army.specialOperation.label} · 尚需 ${army.specialOperation.turnsRemaining} 回合</div>` : ""}
    ${isOwnArmy ? `
    <div class="army-operations">
      ${army.specialOperation || !canOrder ? `<button disabled>${army.specialOperation ? "工事進行中" : fightingBattle ? "交戰中" : "本回合已行動"}</button>` : `
      <button class="${moveMode ? "active" : ""}" data-army-operation="move">移動</button>
      <button data-army-operation="rest">休整</button>
      ${joinableBattle ? `<button class="join-battle-command" data-join-battle="${joinableBattle.id}">加入戰鬥</button>` : ""}
      ${engineering.map((skill) => {
        const operation = ENGINEERING_OPERATIONS[skill];
        return `<button data-engineering-operation="${skill}">${operation.label} (${operation.turns} 回合)</button>`;
      }).join("")}`}
      ${canReinforce ? `<button data-army-operation="recruit">補充兵力</button>` : ""}
    </div>
    ${canReinforce && army.showRecruitment ? `
      <div class="army-reinforcement">
        <b>${city.name}預備隊</b>
        ${Object.entries(UNIT_META).map(([type, unit]) => `
          <button data-reinforce-unit="${type}" ${profile.unit_reserves?.[type] ? "" : "disabled"}>
            ${unitSymbol(type)}<span>${unit.name}</span><strong>${profile.unit_reserves?.[type] ?? 0}</strong>
          </button>
        `).join("")}
      </div>
    ` : ""}` : ""}
  `;
}

function pendingArmies() {
  const fightingIds = new Set(activeBattles.flatMap(battleParticipantIds));
  return currentArmies().filter((army) => !armyIsResolvedThisTurn(army) && !fightingIds.has(army.id));
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

function selectArmy(armyId) {
  selectedArmyId = armyId;
  moveMode = false;
  uiNotice = null;
  $("mapStage").classList.remove("move-mode");
  selectTile(cells[selectedArmy()?.cellKey]);
  renderArmyMarkers(currentPlayer);
  renderPendingActions();
  document.querySelector(`[data-army-id="${armyId}"]`)?.focus({ preventScroll: true });
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

function undoLastArmyOrder() {
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
  if (action.prisoner) {
    const jail = jailedGenerals[action.prisoner.captor] || [];
    const prisonerIndex = jail.findIndex((record) => record.armyId === action.prisoner.armyId);
    if (prisonerIndex >= 0) jail.splice(prisonerIndex, 1);
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
  return armyOrderHistory.some((action) => action.player === currentPlayer);
}

// ---- 崩鐵玩家：搶修中的鐵路 ----------------------------------------------

function disabledRailways() {
  return new Set((state?.railway_effects || [])
    .filter((effect) => Number(effect.remaining_turns || 0) > 0)
    .map((effect) => effect.railway));
}

// 一段鐵路連線只有在兩端共用一條「還在運轉」的鐵路時才算通。
function railLinkUsable(from, to, downed = disabledRailways()) {
  if (!downed.size) return true;
  for (const name of from.railroads || []) {
    if ((to.railroads || new Set()).has(name) && !downed.has(name)) return true;
  }
  return false;
}

// 位於搶修中鐵路沿線的部隊每回合只能走 1 格，連急行軍都不行。
function cellUnderRailwaySabotage(cell, downed = disabledRailways()) {
  if (!cell || !downed.size) return false;
  return [...(cell.railroads || [])].some((name) => downed.has(name));
}

function riverStepAllowed(from, to, railwayMovement = false) {
  const riverCells = [from, to].filter((cell) => cell.river);
  if (!riverCells.length) return true;
  // 河港開放陸軍自由通行，不需要浮橋。
  return riverCells.every((cell) => cell.city?.port === "river"
    || completedPontoons.has(cell.key)
    || (railwayMovement && cell.railBridge));
}

function railwayPath(source, destination) {
  if (!source.railNeighbors?.size || !destination.railroads?.size) return null;
  const downed = disabledRailways();
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
      if (!next || !railLinkUsable(cell, next, downed)) continue;
      if (!riverStepAllowed(cell, next, true)) continue;
      visited.add(key);
      queue.push({ cell: next, path: [...path, next] });
    }
  }
  return null;
}

function ruralMoveLimit(player = currentPlayer) {
  const active = state.players[player]?.timed_effects || [];
  return active.reduce((limit, effect) => {
    if (effect.kind !== "rural_movement" || Number(effect.remaining_turns || 0) <= 0) return limit;
    return Math.max(limit, Number(effect.tiles || limit));
  }, 1);
}

function ruralMovementPath(source, destination, player = currentPlayer) {
  const limit = ruralMoveLimit(player);
  if (limit <= 1) return null;
  // 崩鐵玩家：沿線地格出發的部隊本回合只剩 1 格，急行軍失效。
  if (cellUnderRailwaySabotage(source)) return null;
  if (destination.city || destination.railroads?.size) return null;
  const queue = [{ cell: source, path: [source] }];
  const visited = new Set([source.key]);
  while (queue.length) {
    const { cell, path } = queue.shift();
    if (cell.key === destination.key) return path;
    if (path.length > limit) continue;
    for (const next of cellNeighbors(cell)) {
      if (visited.has(next.key)) continue;
      if (next.city || next.railroads?.size) continue;
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

function setArmyTotalUnits(army, totals) {
  const faction = factionForArmy(army);
  army.units = wholeUnits(totals);
  const general = generalById(army.generalId);
  if (general) general.units = { ...army.units };
  const reinforcementLedger = state.players[faction]?.army_reinforcements;
  if (reinforcementLedger) delete reinforcementLedger[army.id];
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

function combatTraitModifiers(army) {
  const faction = factionForArmy(army);
  const traits = generalTrees[faction]?.generals?.[army.generalId]?.traits || [];
  return traits.flatMap((trait) => [
    ...(bootstrap.general_traits?.traits?.[trait]?.modifiers || []),
    ...(TRAIT_GAME_MODIFIERS[trait] || []),
  ].map((modifier) => ({ ...modifier })));
}

function timedCombatModifiers(faction, opponentFaction = null) {
  return (state.players[faction]?.timed_effects || []).flatMap((effect) => {
    if (effect.kind !== "combat_modifier" || Number(effect.remaining_turns || 0) <= 0) return [];
    if (effect.target_faction && opponentFaction && effect.target_faction !== opponentFaction) return [];
    return (effect.modifiers || []).map((modifier) => ({ ...modifier, source_effect: effect.name }));
  });
}

function combatArmyPayload(army, tactic, defending = false, battle = null, opponentFaction = null) {
  const faction = factionForArmy(army);
  return {
    name: army.id,
    units: armyUnits(army),
    initial_units: battle?.initialByArmy?.[army.id] || armyUnits(army),
    tactic,
    modifiers: [
      ...combatTraitModifiers(army),
      ...timedCombatModifiers(faction, opponentFaction),
      ...(defending && completedFortresses.has(activeBattles.find((battle) => battleSideForArmy(battle, army))?.cellKey)
        ? [{ stat: "harm_taken", multiplier: 0.65 }]
        : []),
    ],
  };
}

function surrenderArmy(army, captorFaction, battle, action = null) {
  const originFaction = generalOwners[army.generalId] || factionForArmy(army);
  const general = generalTrees[originFaction]?.generals?.[army.generalId] || {
    id: army.generalId,
    name: army.general,
    traits: [],
    skills: [],
    units: { ...army.units },
  };
  const record = {
    armyId: army.id,
    originFaction,
    capturedTurn: state.turn,
    general: {
      ...JSON.parse(JSON.stringify(general)),
      status: "jailed",
      units: Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0])),
    },
  };
  const reinforcementLedger = state.players[originFaction]?.army_reinforcements;
  if (reinforcementLedger) delete reinforcementLedger[army.id];
  army.units = Object.fromEntries(Object.keys(UNIT_META).map((type) => [type, 0]));
  army.status = "jailed";
  jailedGenerals[captorFaction] ||= [];
  jailedGenerals[captorFaction].push(record);
  const affectedDescendants = descendantGeneralIds(generalTrees[originFaction], army.generalId)
    .filter((id) => generalOwners[id] === originFaction);
  if (action) action.loyaltyBefore = Object.fromEntries(affectedDescendants.map((id) => [
    id,
    Object.hasOwn(loyaltyOverrides, id) ? loyaltyOverrides[id] : null,
  ]));
  for (const generalId of affectedDescendants) loyaltyOverrides[generalId] = 1;
  if (action) action.prisoner = { captor: captorFaction, armyId: army.id };
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
  markArmyResolved(army);
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
      setArmyTotalUnits(army, remainingById.get(army.id) || armyUnits(army));
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
    const focusButton = event.target.closest("[data-focus-army]");
    const resolveButton = event.target.closest("[data-resolve-army]");
    if (resolveButton) resolveArmy(resolveButton.dataset.resolveArmy);
    else if (focusButton) selectArmy(focusButton.dataset.focusArmy);
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
    const battle = [...activeBattles, ...battleReports].find((item) => item.id === battleId);
    if (!battle || ["pending", "ongoing"].includes(battle.status)) return;
    event.preventDefault();
    hiddenBattleReportIds.add(battleId);
    selectedBattleId = null;
    renderBattlePanel();
  });
  $("armyDetail").addEventListener("click", async (event) => {
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
      showNotice(moveMode ? `選擇相鄰地格；急行軍可走鄉村 ${ruralMoveLimit(currentPlayer)} 格；鐵路最多 ${railwayMoveLimit(currentPlayer)} 格；跨河需要浮橋或鐵路橋。` : "已取消移動。");
      $("mapStage").classList.toggle("move-mode", moveMode);
      renderArmyDetail();
    } else if (operation === "rest") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能休整。" : "此軍本回合已行動。");
        return;
      }
      moveMode = false;
      beginArmyOrder(army, "rest");
      resolveArmy(army.id);
    } else if (engineering === "pontoon_bridge") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能施工。" : "此軍本回合已行動。");
        return;
      }
      engineeringMode = engineering;
      moveMode = false;
      showNotice("選擇與軍隊相鄰的河流地格架設浮橋。工程需 2 回合。");
      $("mapStage").classList.add("move-mode");
    } else if (engineering === "fortress_builder") {
      if (!armyCanReceiveOrder(army)) {
        showNotice(activeBattleForArmy(army) ? "交戰中的軍隊不能施工。" : "此軍本回合已行動。");
        return;
      }
      const action = beginArmyOrder(army, "engineering");
      army.specialOperation = {
        id: engineering,
        label: ENGINEERING_OPERATIONS[engineering].label,
        turnsRemaining: ENGINEERING_OPERATIONS[engineering].turns,
        targetCellKey: army.cellKey,
      };
      action.engineering = engineering;
      moveMode = false;
      resolveArmy(army.id);
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
        });
        state = result.state;
        syncStrategicCitiesFromState();
        updateTopBar();
        renderArmyDetail();
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
  canvas.addEventListener("click", (event) => {
    if (suppressMapClick) {
      suppressMapClick = false;
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const mapX = ((event.clientX - rect.left) / rect.width) * MAPW;
    const mapY = ((event.clientY - rect.top) / rect.height) * MAPH;
    const [lon, lat] = unpx(mapX, mapY);
    const destination = cellAt(lon, lat);
    if (!moveMode && !engineeringMode) {
      selectTile(destination);
      return;
    }
    handleMapDestination(destination);
  });
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
      const action = beginArmyOrder(army, "engineering");
      army.specialOperation = {
        id: engineeringMode,
        label: ENGINEERING_OPERATIONS[engineeringMode].label,
        turnsRemaining: ENGINEERING_OPERATIONS[engineeringMode].turns,
        targetCellKey: destination.key,
      };
      action.engineering = engineeringMode;
      engineeringMode = null;
      $("mapStage").classList.remove("move-mode");
      resolveArmy(army.id);
      return;
    }

    const adjacent = cellNeighbors(source).some((cell) => cell.key === destination.key);
    const railPath = railwayPath(source, destination);
    const ruralPath = railPath ? null : ruralMovementPath(source, destination, currentPlayer);
    if (!adjacent && !railPath && !ruralPath) {
      showNotice(`一般移動限相鄰地格；急行軍可走鄉村 ${ruralMoveLimit(currentPlayer)} 格；位於鐵路時可沿相連鐵路移動最多 ${railwayMoveLimit(currentPlayer)} 格。`);
      return;
    }
    if (adjacent && !railPath && !ruralPath && !riverStepAllowed(source, destination, false)) {
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
    const action = beginArmyOrder(army, railPath ? "rail_move" : ruralPath ? "forced_march" : "move");
    army.previousCellKey = source.key;
    army.cellKey = destination.key;
    army.lon = destination.lon;
    army.lat = destination.lat;
    if (enemy) {
      startBattle(army, enemy, destination, source.key, action);
    } else if (destination.fac !== currentPlayer) {
      occupyTile(destination, currentPlayer, action);
    }
    moveMode = false;
    $("mapStage").classList.remove("move-mode");
    resolveArmy(army.id);
    if (enemy && selectedBattleId) selectBattle(selectedBattleId);
    if (!enemy || activeBattles.at(-1)?.status === "surrendered") initMap();
}

function notificationKey(player, index, item) {
  return `${player}:${index}:${item.turn}`;
}

function unreadNotifications(payload = state.players[currentPlayer]) {
  return (payload?.notifications || [])
    .map((item, index) => ({ ...item, key: notificationKey(currentPlayer, index, item) }))
    .filter((item) => !readNotifications.has(item.key));
}

function renderPendingActions() {
  const pending = pendingArmies();
  const fighting = activeBattles.filter((battle) =>
    (battle.status === "pending" || battle.status === "ongoing")
    && (battle.attackerFaction === currentPlayer || battle.defenderFaction === currentPlayer)
  );
  $("pendingCount").textContent = String(pending.length);
  $("pendingTitle").textContent = fighting.length ? "交戰軍令" : pending.length ? "待命軍隊" : "軍令完成";
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
    : fighting.length ? "" : '<div class="pending-complete">所有軍隊均已收到命令</div>';
  $("pendingList").innerHTML = fightingMarkup + armyMarkup;

  renderArmyDetail();
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
      <span>可支付 $${cost} 抽 1 張功能卡；本回合最多 ${limit} 張，目前 ${used}/${limit}，也可以略過。</span>
      <div class="notification-actions">
        <button data-buy-function-card="${currentPlayer}">支付 $${cost}</button>
        <button data-skip-function-purchase="${currentPlayer}">略過</button>
      </div>`;
  } else if (bootstrap.features?.function_cards && state.last_action?.type === "function_card" && functionActionVisibleTo(state.last_action, currentPlayer)) {
    const message = functionActionMessage(state.last_action, currentPlayer);
    notification.hidden = false;
    notification.innerHTML = `<b>功能卡效果</b><span>${message}</span>`;
  } else if (bootstrap.features?.events && state.last_event) {
    notification.hidden = false;
    notification.innerHTML = `<b>${state.last_event.name}</b><span>${state.last_event.effect || "本回合事件已生效"}</span>`;
  } else {
    notification.hidden = true;
    notification.innerHTML = "";
  }

  updateEndTurnButton();
}

function updateEndTurnButton() {
  const pending = pendingArmies();
  const pendingBattles = activeBattles.filter((battle) =>
    ["pending", "ongoing"].includes(battle.status)
    && (!battle.confirmed?.A || !battle.confirmed?.B)
  );
  const btn = $("endTurnBtn");
  const readyPlayers = TURN_PLAYERS.filter((player) => turnReady[player] === state.turn);
  const waitingForAll = turnReady[currentPlayer] === state.turn && readyPlayers.length < TURN_PLAYERS.length;
  btn.classList.toggle("ready", pending.length === 0 && pendingBattles.length === 0);
  btn.classList.toggle("waiting", waitingForAll);
  $("endTurnLabel").textContent = pending.length
    ? `下一支軍隊 (${pending.length})`
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
  eventHistory = [];
  selectedArmyId = null;
  selectedBattleId = null;
  uiNotice = null;
  skippedFunctionPurchasePrompts.clear();
  resolvedArmyIds.clear();
  replaceObject(turnReady, {});
  armyOrderHistory.length = 0;
  activeBattles.length = 0;
  battleReports.length = 0;
  pendingProvinceClaims.length = 0;
  collapsedBattleIds.clear();
  hiddenBattleReportIds.clear();
  retreatConfirmations.clear();
  completedPontoons.clear();
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
    army.status = "active";
    army.faction = INITIAL_ARMY_FACTIONS[army.id];
    delete army.specialOperation;
    delete army.showRecruitment;
    delete army.previousCellKey;
    delete army.resolvedTurn;
  }
  updateTopBar();
  updatePhaseBanner();
  updateEventBadge();
  updateFeatureVisibility();
  renderArmyMarkers(currentPlayer);
  renderHandDock();
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
  if (!force && pending.length) {
    selectArmy(pending[0].id);
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
    await cityEconomySync;
    const result = await api("/api/next-turn", {
      active_player: currentPlayer,
      force,
      riot_garrisons: qingGangRiotGarrisons(),
      city_garrisons: uprisingCityGarrisons(),
    });
    state = result.state;
    syncStrategicCitiesFromState();
    uiNotice = null;
    advanceEngineering();
    resolvedArmyIds.clear();
    replaceObject(turnReady, {});
    for (const army of allArmies()) {
      delete army.resolvedTurn;
      if (army.specialOperation) markArmyResolved(army);
    }
    armyOrderHistory.length = 0;
    const terminalBattles = activeBattles.filter((battle) => !["pending", "ongoing"].includes(battle.status));
    battleReports.push(...terminalBattles);
    for (const battle of terminalBattles) activeBattles.splice(activeBattles.indexOf(battle), 1);
    selectedBattleId = activeBattles.at(-1)?.id || battleReports.at(-1)?.id || null;
    selectedArmyId = currentArmies()[0]?.id || null;
    currentPhase = "military";
    updateTopBar();
    updatePhaseBanner();
    showEventIfNeeded(state.turn);
    updateFeatureVisibility();
    initMap();
    renderHandDock();
    renderPendingActions();
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

boot().catch((error) => {
  console.error("Boot error:", error);
});
