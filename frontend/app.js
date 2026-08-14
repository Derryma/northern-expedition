import { factionFlagMarkup, flagMarkup, powerFlagMarkup, POWER_NAME } from './flags.js';
import { RIVERS } from './map.js';
import { px, unpx, MAPW, MAPH, FACTIONS, CHINA_PROPER, HAINAN, pointInPolygon, hexPts, cells, cellAt, cellNeighbors, ARMY_POSITIONS, COLS, ROWS, hcx, hcy, s, FOREIGN_CITIES } from './map.js';

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
const loyaltyOverrides = {};
let currentPhase = "event"; // event, preparation, military
let currentPlayer = null;
let selectedArmyId = null;
const resolvedArmyIds = new Set();
const MAX_HAND_SIZE = 6;
const DEFAULT_FUNCTION_CARD_DRAW_COST = 5;
const DEFAULT_FUNCTION_CARD_DRAW_FACTORY_COST = 5;
let foreignTab = "warlords";
let dealTarget = null;
let moveMode = false;
let engineeringMode = null;
let uiNotice = null;
const armyOrderHistory = [];
// 瓊州海峽開局就架著浮橋，海南島才連得上大陸。
const PREBUILT_PONTOONS = ['20,38'];
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

const TRAIT_DESCRIPTIONS = {
  advantage_is_ours: "蔣介石的總司令威望。所部全體生命 +10%；何應欽在同一場戰鬥中作為友軍出現時，他的部隊生命也 +10%（戰鬥結束即恢復）。",
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
  zhili_veteran: "王承斌的直系班底。騎兵與砲兵攻擊 +7%；同陣營若有吳佩孚則忠誠 +1。",
  old_cantonese_army: "陳炯明的粵軍元老。砲兵攻擊 +12%，鎮壓紅軍起義只需一回合。國民革命軍不可延攬。",
  qilu_veteran: "田中玉的山東舊部。騎兵承傷 -7%、砲兵攻擊 +7%；同陣營若有張宗昌則忠誠 +1。",
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
const ALLY_LOYALTY_TRAITS = {
  zhili_veteran: { ally: "wu_peifu", delta: 1 },
  qilu_veteran: { ally: "zhang_zongchang", delta: 1 },
};

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

function traitDescription(trait) {
  const base = TRAIT_DESCRIPTIONS[trait]
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

function traitChip(trait) {
  const description = traitDescription(trait);
  return `<span class="trait-chip" tabindex="0" data-tooltip="${description}">${TRAIT_LABELS[trait] || trait}</span>`;
}

const ENGINEERING_OPERATIONS = {
  pontoon_bridge: { label: "架設浮橋", turns: 2 },
  fortress_builder: { label: "構築要塞", turns: 3 },
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
  for (const [faction, tree] of Object.entries(generalTrees)) {
    normalizeGeneralTree(tree);
    for (const generalId of Object.keys(tree.generals || {})) generalOwners[generalId] = faction;
  }
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
  for (const tree of Object.values(generalTrees)) normalizeGeneralTree(tree);
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
      && !cell.power                       // 列強租借地不能拿來擺中國城市
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
  bridgeRailwaysOverWater();
}

// 河港城市的地格一律視為水域。天然河道保留原名，其餘標為內河。
function markRiverPortWater() {
  for (const cell of Object.values(cells)) {
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
  const footer = kind === "cash"
    ? `<span class="stat-popover-total"><i>每回合現金合計</i><strong>+$${total}</strong></span>`
    : `<span class="stat-popover-total"><i>每回合工廠合計</i><strong>+${total} 點</strong></span>
       <span class="stat-popover-total"><i>目前可用工廠點</i><strong>${profile.factory_points ?? 0} 點</strong></span>`;

  return `
    <b>${kind === "cash" ? "城市現金來源" : "城市工廠來源"}</b>
    ${rows}
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
  const economyFlags = Boolean(payload?.loan_penalties?.length || payload?.soong_patronage
    || payload?.bank_success_rate || payload?.loan_interest_override);
  if (!effects.length && !cityEffects.length && !uprisings.length && !railways.length && !economyFlags) return "";
  return `<div class="active-effect-list">
    ${effects.map((effect) => {
      const label = effect.kind === "police_system"
        ? `警政保護剩餘 ${effect.remaining_turns} 回合`
        : effect.kind === "aerial_recon"
          ? `飛艇偵查：${(effect.target_provinces || []).join("、")}，剩餘 ${effect.remaining_turns} 回合`
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
      return `<span>${effect.label || "黑幫暴動"}(${role})：${effect.province}，鎮壓 ${progress}</span>`;
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
  if (action.artifact_sale) {
    const sale = action.artifact_sale;
    parts.push(`向${POWER_NAME[sale.power] || sale.power}盜賣文物，進帳 $${sale.payout}`
      + (sale.shame_cards_added ? `；牌庫多了 ${sale.shame_cards_added} 張〈中國人之恥〉（${sale.shame_cards_total}/${sale.shame_cap}）` : "；恥辱牌已達上限"));
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
        const neededSlots = transferBranchSize(generalTrees[record.originFaction], record.general.id);
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
      const branchSize = transferBranchSize(generalTrees[record.originFaction], record.general.id);
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
  return 1 + descendantGeneralIds(sourceTree, generalId).length;
}

// 招降／策反時整條支系都會跟著轉投，後端要知道這批人帶著哪些技能
// （目前只有〈日本買辦〉會在轉投時產生非戰鬥效果）。
function transferringTraits(sourceTree, general) {
  const ids = [general.id, ...descendantGeneralIds(sourceTree, general.id)];
  const traits = new Set(general.traits || []);
  for (const id of ids) {
    for (const trait of sourceTree?.generals?.[id]?.traits || []) traits.add(trait);
  }
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
    copied.faction = FACTIONS[destinationFaction].name;
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
    const transferredGeneral = transferred.find((item) => item.id === fieldArmy.generalId);
    const assignedNumber = nextAvailableArmyNumber(faction, fieldArmy.id);
    fieldArmy.faction = faction;
    fieldArmy.status = "active";
    fieldArmy.general = transferredGeneral?.name || fieldArmy.general;
    fieldArmy.designator = formatArmyDesignator(assignedNumber);
    markArmyResolved(fieldArmy);
    if (fieldArmy.cellKey && cells[fieldArmy.cellKey]) occupyTile(cells[fieldArmy.cellKey], faction);
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
    const transferredGeneral = transferred.find((item) => item.id === fieldArmy.generalId);
    fieldArmy.designator = formatArmyDesignator(nextAvailableArmyNumber(destinationFaction, fieldArmy.id));
    fieldArmy.faction = destinationFaction;
    fieldArmy.status = "active";
    fieldArmy.general = transferredGeneral?.name || fieldArmy.general;
    markArmyResolved(fieldArmy);
    if (fieldArmy.cellKey && cells[fieldArmy.cellKey]) occupyTile(cells[fieldArmy.cellKey], destinationFaction);
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
  const branchSize = transferBranchSize(generalTrees[factionForArmy(army)], army.generalId);
  if (availableMajorGeneralSlots(currentPlayer) < branchSize) {
    showNotice(`我方中將空位不足，這支部隊連同麾下 ${Math.max(0, branchSize - 1)} 名附屬將領無法一併接收。`);
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
  const unitsText = general.status === "in_exile"
    ? `自帶 ${unitSummary(Object.fromEntries(Object.entries(general.units || {}).filter(([, count]) => Number(count) > 0)))}`
    : (hasArmy ? unitSummary(armyUnits(fieldArmy)) : "無部隊");
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
        ${hasArmy ? forceMeterMarkup(armyUnits(fieldArmy), { compact: true }) : ""}
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
    const adjustment = traitLoyaltyAdjustment(general);
    const current = Math.max(0, Math.min(10, loyaltyOverrides[general.id] + adjustment.amount));
    return { value: current, tooltip: `當前忠誠: ${current}${adjustment.note}\n受俘虜、招降、策反或功能卡影響` };
  }
  const relationPenalty = traitLoyaltyAdjustment(general);
  const baseLoyalty = Math.max(0, Math.min(10, Number(general.loyalty) + relationPenalty.amount));
  if (general.status === "in_exile") {
    return { value: baseLoyalty, tooltip: `出山時的基礎忠誠: ${baseLoyalty}${relationPenalty.note}\n在野期間不套用部隊相關的增減` };
  }
  if (!fieldArmy || fieldArmy.status === "jailed" || general.status === "recruited") {
    const value = Math.min(baseLoyalty, 2);
    return { value, tooltip: `基礎忠誠: ${baseLoyalty}${relationPenalty.note}\n無直屬部隊: -${Math.max(0, baseLoyalty - value)}` };
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
    tooltip: `基礎忠誠: ${baseLoyalty}${relationPenalty.note}\n相對實力影響: ${relativePower >= 0 ? '+' : ''}${relativePower}\n戰損影響: ${battleLoss}\n現有戰力: ${Math.round(currentForce)} / 初始 ${Math.round(initialForce)}`,
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
// 列強關係讓技能失效時的處罰（張宗昌、何鍵各 -5），
// 以及同陣營有指定將領時的加成（王承斌配吳佩孚、田中玉配張宗昌各 +1）。
function traitLoyaltyAdjustment(general) {
  const faction = factionHoldingGeneral(general.id);
  if (!faction) return { amount: 0, note: "" };
  let amount = 0;
  const reasons = [];
  for (const trait of general.traits || []) {
    const rule = RELATION_DISABLED_TRAITS[trait];
    if (rule?.loyalty_penalty && traitDisabledByRelations(trait, faction)) {
      amount -= rule.loyalty_penalty;
      reasons.push(`〈${TRAIT_LABELS[trait] || trait}〉失效: -${rule.loyalty_penalty}`);
    }
    const ally = ALLY_LOYALTY_TRAITS[trait];
    if (ally && generalTrees[faction]?.generals?.[ally.ally]) {
      const allyName = generalTrees[faction].generals[ally.ally].name;
      amount += ally.delta;
      reasons.push(`同陣營有${allyName}: +${ally.delta}`);
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
    ${banTurns > 0 ? `<p class="loan-ban-note">軍閥公債發行後信用受損：列強銀行拒絕承作新貸款，還要 <b>${banTurns}</b> 回合（至第 ${data.loan_ban_until_turn} 回合）才會恢復。本國公債與功能卡貸款不受影響。</p>` : ""}

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

function ideologyShielded(owner, cardId) {
  return (state?.players?.[owner]?.timed_effects || []).some((effect) =>
    effect.kind === "ideology_shield"
    && Number(effect.remaining_turns || 0) > 0
    && (effect.shields_cards || []).includes(cardId));
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

// 共黨暴動與紅軍起義：對方要有城市可癱瘓，而且沒有「自由中國教育家」護持。
function riotTargets(card) {
  return TURN_PLAYERS
    .filter((player) => player !== currentPlayer)
    .filter((owner) => (state?.players?.[owner]?.city_economy || []).length)
    .filter((owner) => !ideologyShielded(owner, card.id));
}

function provinceOptionMarkup(provinces) {
  return provinces.map((province) => `<option value="${province}">${province}</option>`).join("");
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
    if (!targets.length) return `<div class="card-target-note">目前沒有可癱瘓的對手：對方沒有城市，或已有「自由中國教育家」護持</div>`;
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
    // 水波紋：所有河港都畫，不再只畫有鐵路橋的那幾座。
    // 鐵路橋另有黃色方塊標記，兩者互不取代。
    if (city.port === 'river' || cell.railBridge) {
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

      // 列強租借地：用與列強鐵路相同的紅色標示。
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
  return includeInactive
    ? armies
    : armies.filter((army) => !["jailed", "killed", "destroyed"].includes(army.status));
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
  if (concessionPowers.length) {
    tags.push(`<span class="tile-tag tile-tag-concession">租界</span>` + concessionPowers.map((key) => `
      <span class="tile-concession-power">${flagMarkup(key, "flag-chip concession-flag")}${POWER_NAME[key] || key}</span>
    `).join(""));
  }
  const concessionRow = tags.length ? `<div class="tile-concession">${tags.join("")}</div>` : "";
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
    ${concessionRow}`;
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
  const canDefect = loyalty !== null && !general?.loyalty_exempt && !general?.absolute_loyalty && lieutenants.length
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
      ? traits.map(traitChip).join("")
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
        return `<button data-engineering-operation="${skill}">${operation.label} (${operation.turns} 回合)</button>`;
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

// 鐵路運輸走不了的線：搶修中的 ∪ 關係不到的列強線。
function unusableRailways(faction = currentPlayer) {
  const blocked = disabledRailways();
  for (const railway of lockedForeignRailways(faction)) blocked.add(railway);
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
  // scope 是 drawer 的卡（有進入條件的那幾張）只有抽到的那一家要回應。
  const resolutionMeta = card.resolution || {};
  const needsEveryone = resolutionMeta.type === "choice" && resolutionMeta.scope !== "drawer";
  const factions = Object.keys(state?.players || {});
  let waiting;
  if (needsEveryone) waiting = factions.filter((code) => !(code in answered));
  else if (strict) waiting = (entry.responders || []).filter((code) => !(code in answered));
  else waiting = Object.keys(answered).length ? [] : factions;
  return {
    turn: pending.turn,
    index,
    total: (pending.cards || []).length,
    card,
    drawer: entry.drawer,
    responders: entry.responders || [],
    responses: answered,
    strict,
    needsEveryone,
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

function newspaperMarkup(view) {
  const card = view.card;
  const paragraphs = (card.newspaper?.paragraphs || [])
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
    ? `<div class="newspaper-effect"><b>行 動 選 項</b>${(resolution.options || [])
        .map((option) => `<div>${option.label}：${newspaperInline(option.effect_text)}${
          option.follow_up ? `<i>（${newspaperInline(option.follow_up.prompt)}）</i>` : ""}</div>`).join("")}
        ${resolution.prompt ? `<span class="newspaper-note">${newspaperInline(resolution.prompt)}</span>` : ""}</div>`
    : "";
  const answered = Object.entries(view.responses || {})
    .map(([code, value]) => {
      const label = (resolution.options || []).find((option) => option.id === value)?.label;
      return `${FACTIONS[code]?.shortName || code}：${label || "已閱"}`;
    }).join("　");
  // 設計稿的效果欄有些是條列式（「- 通電支持：⋯」），抽出來時被併成一行，這裡拆回去。
  const effectLines = String(card.effect || "")
    .split(/\s+-\s+(?=\*\*)/)
    .map((line, index) => `<div>${index ? "・" : ""}${newspaperInline(line)}</div>`)
    .join("");
  const pendingNames = (view.pendingResponders || [])
    .map((code) => FACTIONS[code]?.shortName || code).join("、");
  let waitingText;
  if (pendingFollowUp) {
    waitingText = newspaperInline(pendingFollowUp.follow_up.prompt || "請再指定一個對象");
  } else if (view.strict) {
    waitingText = mine ? "請閣下裁示" : `等待 ${FACTIONS[view.waitingFor]?.name || view.waitingFor} 回應`;
  } else if (view.needsEveryone) {
    waitingText = alreadyAnswered
      ? `貴方已表態，尚待 ${pendingNames} 表態`
      : `各勢力分別表態，尚待 ${pendingNames}`;
  } else {
    waitingText = "任一勢力點閱即可";
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
    <div class="newspaper-headline">${newspaperInline(card.newspaper?.headline || card.name)}</div>
    <div class="newspaper-body">${paragraphs}</div>
    <div class="newspaper-effect"><b>本 報 附 誌</b>${effectLines}${notes}</div>
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
      resolvedArmyIds.clear();
      replaceObject(turnReady, {});
      for (const army of allArmies()) {
        delete army.resolvedTurn;
        if (army.specialOperation) markArmyResolved(army);
      }
      armyOrderHistory.length = 0;
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
  selectedBattleId = null;
  moveMode = false;
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
  if (cardId === "may_coup_wave") {
    // 大帥與嫡系（忠誠不變）將領旗下所有陸軍兵種各 +1 營，受 100 戰力上限限制。
    const points = bootstrap?.features?.unit_force_points
      || { infantry: 1, cavalry: 1, machine_gun: 2, artillery: 4 };
    for (const army of allArmies()) {
      const faction = factionForArmy(army);
      if (!TURN_PLAYERS.includes(faction)) continue;
      const general = generalTrees[faction]?.generals?.[army.generalId];
      const core = general && (general.role === "great_general" || general.loyalty_exempt
        || general.loyalty === null || general.absolute_loyalty);
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
        && !general.absolute_loyalty && !general.loyalty_exempt
        && generalOwners[general.id] === faction);
      if (!pool.length) continue;
      const pick = pool[Math.floor(Math.random() * pool.length)];
      adjustGeneralLoyalty(pick.id, 1);
      notes.push(`${FACTIONS[faction]?.shortName || faction} ${pick.name} 忠誠 +1`);
    }
  }
  return notes;
}

// 非戰公約的停戰：簽了的人三回合內不得主動攻擊、也不得移入他方領地。
function ceasefireEffect(faction = currentPlayer) {
  return activeTimedEffects(faction, "ceasefire")[0] || null;
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
      ...(defending && completedFortresses.has(activeBattles.find((battle) => battleSideForArmy(battle, army))?.cellKey)
        ? [{ stat: "harm_taken", multiplier: 0.65 }]
        : []),
    ],
  };
}

// 黔軍是地方民團而不是某位督軍的班底，沒有可俘可招的人；它的部隊被打垮就是
// 就地潰散，不進俘虜區、不留將領、也不會拖累別人的忠誠。
const NO_CAPTURE_FACTIONS = ["Q"];

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
      const before = { ...armyUnits(army) };
      setArmyTotalUnits(army, remainingById.get(army.id) || armyUnits(army));
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
          current_force: forcePoints(armyUnits(army)),
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

    if (destination.power) {
      showNotice(`${POWER_NAME[destination.power] || destination.power}的租借地，中國各勢力不得進入或通過。`);
      return;
    }
    const ceasefire = ceasefireEffect(currentPlayer);
    if (ceasefire) {
      const occupant = allArmies().find((other) => other.cellKey === destination.key
        && factionForArmy(other) !== currentPlayer);
      const foreignGround = destination.fac && destination.fac !== currentPlayer;
      if (occupant || foreignGround) {
        showNotice(`${ceasefire.name || "停戰"}期間（剩餘 ${ceasefire.remaining_turns} 回合）不得主動攻擊、也不得移入他方領地。`);
        return;
      }
    }
    const adjacent = cellNeighbors(source).some((cell) => cell.key === destination.key);
    const railPath = railwayPath(source, destination);
    const marchPath = railPath ? null : forcedMarchPath(source, destination, army);
    if (!adjacent && !railPath && !marchPath) {
      showNotice(forcedMarchActive(army)
        ? `急行軍中可走 ${forcedMarchRules().tiles} 格陸地；位於鐵路時可沿相連鐵路移動最多 ${railwayMoveLimit(currentPlayer)} 格。`
        : `一般移動限相鄰地格；購買急行軍後可走 ${forcedMarchRules().tiles} 格；位於鐵路時可沿相連鐵路移動最多 ${railwayMoveLimit(currentPlayer)} 格。`);
      return;
    }
    if (adjacent && !railPath && !marchPath && !riverStepAllowed(source, destination, false)) {
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
    const action = beginArmyOrder(army, railPath ? "rail_move" : marchPath ? "forced_march" : "move");
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
    army.status = "active";
    army.faction = INITIAL_ARMY_FACTIONS[army.id];
    delete army.specialOperation;
    delete army.showRecruitment;
    delete army.previousCellKey;
    delete army.resolvedTurn;
  }
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
  applyFrontendEventEffects,
  ceasefireEffect,
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
