// Simplified China provinces with key strategic locations
const provinces = [
  // South
  { id: "guangdong", name: "廣東", x: 650, y: 750, controlled_by: "N", adjacent: ["guangxi", "hunan", "jiangxi", "fujian"] },
  { id: "guangxi", name: "廣西", x: 520, y: 720, controlled_by: "N", adjacent: ["guangdong", "hunan", "guizhou", "yunnan"] },
  { id: "fujian", name: "福建", x: 750, y: 680, controlled_by: "N", adjacent: ["guangdong", "jiangxi", "zhejiang"] },

  // Central
  { id: "hunan", name: "湖南", x: 580, y: 620, controlled_by: "W", adjacent: ["guangdong", "guangxi", "guizhou", "hubei", "jiangxi"] },
  { id: "hubei", name: "湖北", x: 620, y: 540, controlled_by: "W", adjacent: ["hunan", "henan", "anhui", "jiangxi", "shaanxi"] },
  { id: "jiangxi", name: "江西", x: 680, y: 620, controlled_by: "S", adjacent: ["guangdong", "fujian", "zhejiang", "anhui", "hubei", "hunan"] },
  { id: "anhui", name: "安徽", x: 720, y: 540, controlled_by: "S", adjacent: ["jiangxi", "zhejiang", "jiangsu", "henan", "hubei"] },
  { id: "zhejiang", name: "浙江", x: 780, y: 600, controlled_by: "S", adjacent: ["fujian", "jiangxi", "anhui", "jiangsu"] },
  { id: "jiangsu", name: "江蘇", x: 760, y: 480, controlled_by: "S", adjacent: ["zhejiang", "anhui", "shandong"] },

  // East Coast
  { id: "shanghai", name: "上海", x: 800, y: 520, controlled_by: "S", adjacent: ["jiangsu", "zhejiang"], city: true },
  { id: "shandong", name: "山東", x: 740, y: 420, controlled_by: "F", adjacent: ["jiangsu", "anhui", "henan", "hebei"] },

  // North
  { id: "hebei", name: "河北", x: 680, y: 360, controlled_by: "F", adjacent: ["shandong", "henan", "shanxi", "beijing"] },
  { id: "beijing", name: "北京", x: 700, y: 300, controlled_by: "F", adjacent: ["hebei"], city: true },
  { id: "shanxi", name: "山西", x: 600, y: 380, controlled_by: "Y", adjacent: ["hebei", "henan", "shaanxi"] },

  // Central-West
  { id: "henan", name: "河南", x: 660, y: 460, controlled_by: "W", adjacent: ["shandong", "anhui", "hubei", "shaanxi", "shanxi", "hebei"] },
  { id: "shaanxi", name: "陝西", x: 540, y: 460, controlled_by: "G", adjacent: ["shanxi", "henan", "hubei", "sichuan", "gansu"] },

  // Southwest
  { id: "sichuan", name: "四川", x: 450, y: 560, controlled_by: "C", adjacent: ["shaanxi", "hubei", "guizhou", "yunnan", "gansu"] },
  { id: "guizhou", name: "貴州", x: 480, y: 650, controlled_by: "Q", adjacent: ["sichuan", "yunnan", "guangxi", "hunan"] },
  { id: "yunnan", name: "雲南", x: 380, y: 700, controlled_by: "D", adjacent: ["guizhou", "guangxi", "sichuan"] },

  // Northwest
  { id: "gansu", name: "甘肅", x: 440, y: 380, controlled_by: "M", adjacent: ["shaanxi", "sichuan"] },
];

// Army positions (番號 system)
const armies = [
  { id: "army_1", designation: "第一軍", general: "chiang_kai_shek", faction: "N", location: "guangdong",
    units: {infantry: 18, cavalry: 2, artillery: 3, machine_gun: 4}, has_moved: false },
  { id: "army_2", designation: "第二軍", general: "he_yingqin", faction: "N", location: "fujian",
    units: {infantry: 14, cavalry: 2, artillery: 2, machine_gun: 4}, has_moved: false },
  { id: "army_3", designation: "第三軍", general: "bai_chongxi", faction: "N", location: "guangxi",
    units: {infantry: 12, cavalry: 2, artillery: 2, machine_gun: 3}, has_moved: false },
  { id: "army_4", designation: "第四軍", general: "tang_shengzhi", faction: "N", location: "guangdong",
    units: {infantry: 10, cavalry: 3, artillery: 1, machine_gun: 2}, has_moved: false },
];

// Faction colors for army markers
const factionColors = {
  N: "#f9a825",
  F: "#546e7a",
  W: "#6a1b9a",
  S: "#2e7d32",
  Y: "#6d4c41",
  G: "#ad1457",
  C: "#ef6c00",
  D: "#5e35b1",
  Q: "#9e9d24",
  M: "#00897b",
};
