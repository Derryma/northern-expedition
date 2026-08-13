// Inline flag artwork, ported from the faction operation board so the playtest UI
// uses the same drawings. Everything is plain SVG, no assets to load.

const sunRays = (cx, cy, rOut, rIn, n, fill) => Array.from({ length: n }, (_, i) => {
  const a = i * (360 / n) * Math.PI / 180;
  const w = Math.PI / n * 0.75;
  const p = (angle, r) => `${(cx + Math.cos(angle) * r).toFixed(2)},${(cy + Math.sin(angle) * r).toFixed(2)}`;
  return `<polygon points="${p(a, rOut)} ${p(a - w, rIn)} ${p(a + w, rIn)}" fill="${fill}"/>`;
}).join("");

export const FLAG = {
  // 五色旗（北洋）— 奉系、直系、五省聯軍共用
  wuse: `<svg viewBox="0 0 60 40">${["#d8322f", "#f2c200", "#1f4e9c", "#ffffff", "#1a1a1a"]
    .map((c, i) => `<rect y="${i * 8}" width="60" height="8" fill="${c}"/>`).join("")}</svg>`,

  // 青天白日滿地紅 — 國民革命軍
  roc: `<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#e60012"/><rect x="15" y="9" width="30" height="22" fill="#12279e"/>
    ${sunRays(30, 20, 9.2, 4.6, 12, "#fff")}<circle cx="30" cy="20" r="4.4" fill="#fff"/></svg>`,

  // 星月旗（馬家軍）：紅色三角旗、白色新月與星。引用自 PJ Boardgame 陣營操作板。
  ma: `<svg viewBox="0 0 60 40"><polygon points="0,0 60,20 0,40" fill="#e60012"/>
    <circle cx="15" cy="20" r="8.4" fill="#fff"/><circle cx="18.6" cy="20" r="6.9" fill="#e60012"/>
    ${sunRays(24.5, 17, 3.6, 1.5, 5, "#fff")}</svg>`,

  // 旭日旗（日本陸軍）
  jp: `<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#fff"/>
    <g>${Array.from({ length: 16 }, (_, i) => {
      const a = i * 22.5 * Math.PI / 180;
      const w = Math.PI / 32;
      return `<polygon points="30,20 ${(30 + Math.cos(a - w) * 46).toFixed(1)},${(20 + Math.sin(a - w) * 46).toFixed(1)} ${(30 + Math.cos(a + w) * 46).toFixed(1)},${(20 + Math.sin(a + w) * 46).toFixed(1)}" fill="#bc002d"/>`;
    }).join("")}</g>
    <circle cx="30" cy="20" r="7.5" fill="#bc002d"/></svg>`,

  uk: `<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#012169"/>
    <path d="M0,0 60,40 M60,0 0,40" stroke="#fff" stroke-width="8"/><path d="M0,0 60,40 M60,0 0,40" stroke="#C8102E" stroke-width="4"/>
    <path d="M30,0 v40 M0,20 h60" stroke="#fff" stroke-width="13"/><path d="M30,0 v40 M0,20 h60" stroke="#C8102E" stroke-width="7"/></svg>`,

  su: `<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#CE1126"/>
    ${sunRays(13, 11, 6, 2.4, 5, "#FFD700")}
    <g stroke="#FFD700" stroke-width="1.6" fill="none" transform="translate(13,25)"><path d="M-4,4 L4,-4"/><path d="M-4,-2 a6,6 0 0 1 8,4"/></g></svg>`,

  us: `<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#fff"/>${Array.from({ length: 7 }, (_, i) => `<rect y="${i * 5.7}" width="60" height="2.85" fill="#B22234"/>`).join("")}
    <rect width="26" height="20" fill="#3C3B6E"/>${Array.from({ length: 12 }, (_, i) => `<circle cx="${3 + (i % 4) * 7}" cy="${4 + Math.floor(i / 4) * 6}" r="1.5" fill="#fff"/>`).join("")}</svg>`,

  fr: `<svg viewBox="0 0 60 40"><rect width="20" height="40" fill="#0055A4"/><rect x="20" width="20" height="40" fill="#fff"/><rect x="40" width="20" height="40" fill="#EF4135"/></svg>`,

  de: `<svg viewBox="0 0 60 40"><rect width="60" height="13.3" fill="#000"/><rect y="13.3" width="60" height="13.3" fill="#DD0000"/><rect y="26.6" width="60" height="13.4" fill="#FFCE00"/></svg>`,
};

// 奉系、直系、五省聯軍與多數 NPC 都掛北洋五色旗；國民革命軍掛青天白日滿地紅，
// 馬家軍掛回族星月旗。旗幟歸屬與 PJ Boardgame 陣營操作板一致。
export const FACTION_FLAG = {
  F: "wuse", W: "wuse", S: "wuse", N: "roc",
  Y: "wuse", G: "wuse", H: "wuse", C: "wuse", D: "wuse", Q: "wuse",
  M: "ma",
};

// economy/data/banks.json records each bank's power under this name.
export const POWER_FLAG = {
  britain: "uk",
  united_states: "us",
  japan: "jp",
  france: "fr",
  germany: "de",
  soviet_union: "su",
};

export const POWER_NAME = { jp: "日本", su: "蘇聯", uk: "英國", fr: "法國", us: "美國", de: "德國" };

// foreign_powers relation keys are already the flag keys.
export function flagMarkup(key, className = "flag-chip") {
  const svg = FLAG[key];
  if (!svg) return "";
  return `<span class="${className}" aria-hidden="true">${svg}</span>`;
}

export function factionFlagMarkup(code, className = "flag-chip") {
  return flagMarkup(FACTION_FLAG[code], className);
}

export function powerFlagMarkup(power, className = "flag-chip") {
  return flagMarkup(POWER_FLAG[power] || power, className);
}
