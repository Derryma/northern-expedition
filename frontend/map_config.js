// Extract map data from original 北伐風雲_地圖.html
// This preserves the realistic China map with provinces, rivers, and cities

// Faction definitions
const FACTIONS = {
  F: { name: '張', leader: '張作霖', color: '#546e7a', flag: '🚩' },
  W: { name: '吳', leader: '吳佩孚', color: '#6a1b9a', flag: '🚩' },
  S: { name: '孫', leader: '孫傳芳', color: '#2e7d32', flag: '🚩' },
  N: { name: '蔣', leader: '蔣介石', color: '#f9a825', flag: '🚩' },
  Y: { name: '晉系', leader: '閻錫山', color: '#6d4c41', flag: '🚩' },
  G: { name: '西北軍', leader: '馮玉祥', color: '#ad1457', flag: '🚩' },
  M: { name: '馬家軍', leader: '馬麒', color: '#00897b', flag: '🚩' },
  H: { name: '湘軍', leader: '唐生智', color: '#9e9d24', flag: '🚩' },
  C: { name: '川軍', leader: '劉湘', color: '#ef6c00', flag: '🚩' },
  D: { name: '滇系', leader: '唐繼堯', color: '#5e35b1', flag: '🚩' },
  Q: { name: '黔系', leader: '王家烈', color: '#827717', flag: '🚩' },
};

// Rivers for realistic map (lon/lat polylines)
const RIVERS = [
  { name: '黃河', pts: [[103.8,36.1],[106,37.3],[109,40.3],[110.5,40.4],[110.7,37.6],[110.4,34.9],[112.5,34.8],[114.3,34.8],[116.5,35.5],[118,37],[119,37.9]] },
  { name: '長江', pts: [[106.5,29.6],[108.4,30.7],[111.3,30.7],[114.3,30.6],[116.5,30.2],[118.8,32.1],[120.4,32],[121.8,31.4]] },
  { name: '珠江', pts: [[108.3,22.8],[111.3,23.5],[112.5,23.2],[113.3,23.1],[113.6,22.4]] },
];

// Provinces (realistic 1926 administrative regions)
const PROVINCES = [
  { name: '山東', bounds: [114.8,122.8,34.3,38.5], faction: 'F' },
  { name: '直隸', bounds: [113.5,120,36.5,41], faction: 'F' },
  { name: '河南', bounds: [110.3,116.7,31.3,35.0], faction: 'W' },
  { name: '山西', bounds: [110.2,114.6,34.6,40.3], faction: 'Y' },
  { name: '陝西', bounds: [105.5,111.3,31.7,39.6], faction: 'G' },
  { name: '湖北', bounds: [108.3,116.2,29.6,33.3], faction: 'W' },
  { name: '湖南', bounds: [108.7,114.3,25.8,30.2], faction: 'H' },
  { name: '江蘇', bounds: [116.3,122,30.7,35.2], faction: 'S' },
  { name: '安徽', bounds: [114.8,119.7,29.4,34.7], faction: 'S' },
  { name: '浙江', bounds: [118,123,27.1,31.2], faction: 'S' },
  { name: '福建', bounds: [117.4,120.5,23.5,28.4], faction: 'S' },
  { name: '江西', bounds: [113.5,118.5,24.4,30.1], faction: 'S' },
  { name: '廣東', bounds: [108.5,117.6,17.8,25.5], faction: 'N' },
  { name: '廣西', bounds: [104.4,112.1,21.3,26.4], faction: 'N' },
  { name: '四川', bounds: [97.3,110.2,26,34], faction: 'C' },
  { name: '雲南', bounds: [97.5,106.2,21.1,29.3], faction: 'D' },
  { name: '貴州', bounds: [103.5,109.6,24.6,29.3], faction: 'Q' },
  { name: '甘肅', bounds: [98,108.8,32.5,40.5], faction: 'G' },
  { name: '奉天', bounds: [119,125.5,38.7,43], faction: 'F' },
  { name: '吉林', bounds: [124,132,43,45.5], faction: 'F' },
];

// Key cities with coordinates
const CITIES = [
  { lon: 116.4, lat: 39.9, name: '北京', faction: 'F', level: 4 },
  { lon: 121.5, lat: 31.2, name: '上海', faction: 'S', level: 5 },
  { lon: 113.3, lat: 23.1, name: '廣州', faction: 'N', level: 5 },
  { lon: 114.3, lat: 30.6, name: '武漢', faction: 'W', level: 5 },
  { lon: 118.8, lat: 32.1, name: '南京', faction: 'S', level: 4 },
  { lon: 123.4, lat: 41.8, name: '瀋陽', faction: 'F', level: 5 },
  { lon: 112.5, lat: 37.9, name: '太原', faction: 'Y', level: 3 },
  { lon: 104.1, lat: 30.7, name: '成都', faction: 'C', level: 4 },
  { lon: 102.7, lat: 25, name: '昆明', faction: 'D', level: 3 },
  { lon: 108.9, lat: 34.3, name: '西安', faction: 'W', level: 3 },
];

// Army initial positions (番號 system)
let armies = [
  { id: 'army_1', designation: '第一軍', general: 'chiang_kai_shek', faction: 'N',
    location: { lon: 113.3, lat: 23.1 }, // 廣州
    units: { infantry: 18, cavalry: 2, artillery: 3, machine_gun: 4 },
    movement_points: 2, has_moved: false },
  { id: 'army_2', designation: '第二軍', general: 'he_yingqin', faction: 'N',
    location: { lon: 119.3, lat: 26.1 }, // 福州
    units: { infantry: 14, cavalry: 2, artillery: 2, machine_gun: 4 },
    movement_points: 2, has_moved: false },
  { id: 'army_3', designation: '第三軍', general: 'bai_chongxi', faction: 'N',
    location: { lon: 108.3, lat: 22.8 }, // 南寧
    units: { infantry: 12, cavalry: 2, artillery: 2, machine_gun: 3 },
    movement_points: 2, has_moved: false },
  { id: 'army_4', designation: '第四軍', general: 'tang_shengzhi', faction: 'N',
    location: { lon: 112.9, lat: 28.2 }, // 長沙
    units: { infantry: 10, cavalry: 3, artillery: 1, machine_gun: 2 },
    movement_points: 2, has_moved: false },
];

// Map projection: lon/lat to screen x/y
function lonLatToXY(lon, lat, bounds) {
  const { minLon, maxLon, minLat, maxLat, width, height } = bounds;
  const x = ((lon - minLon) / (maxLon - minLon)) * width;
  const y = height - ((lat - minLat) / (maxLat - minLat)) * height; // flip Y axis
  return { x, y };
}

// Map bounds (focus on China mainland)
const MAP_BOUNDS = {
  minLon: 97,  // West: exclude most of Tibet/Xinjiang
  maxLon: 123, // East: exclude Japan
  minLat: 18,  // South: Hainan
  maxLat: 43,  // North: Manchuria
  width: 1200,
  height: 900,
};
