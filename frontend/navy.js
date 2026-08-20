export const NAVY_UNIT_META = {
  gun_boat: { name: "砲艇", short: "砲艇" },
  cargo_boat: { name: "運輸船", short: "運" },
};

export function createInitialNavies(rules, cells, cityById) {
  const gunBoatHp = Number(rules?.units?.gun_boat?.hp || 30);
  const cargoBoatHp = Number(rules?.units?.cargo_boat?.hp || 10);
  return (rules?.initial_divisions || []).map((division) => {
    const city = cityById.get(division.start_city_id);
    const cell = cells[city?.cellKey];
    const gunBoats = Array.from({ length: Number(division.gun_boats || 0) }, (_, index) => ({
      id: `${division.id}-G${index + 1}`,
      hp: gunBoatHp,
      maxHp: gunBoatHp,
    }));
    return {
      id: division.id,
      faction: division.faction,
      name: division.name,
      startCityId: division.start_city_id,
      cellKey: cell?.key || null,
      lon: cell?.lon || city?.lon || 0,
      lat: cell?.lat || city?.lat || 0,
      gunBoats,
      cargoBoats: Number(division.cargo_boats || 0),
      cargoBoatHp: Array.from({ length: Number(division.cargo_boats || 0) }, (_, index) => ({
        id: `${division.id}-C${index + 1}`,
        hp: cargoBoatHp,
        maxHp: cargoBoatHp,
      })),
      retreatMaxGunBoatHp: gunBoatHp * Number(division.gun_boats || 0),
      carriedArmyId: null,
      resolvedTurn: null,
    };
  });
}

export function navyFaction(navy) {
  return navy?.faction || navy?.id?.split("-")[0] || null;
}

export function activeGunBoats(navy, rules) {
  normalizeNavyDivision(navy, rules);
  const floor = Number(rules?.units?.gun_boat?.inactive_below_hp || 15);
  return (navy?.gunBoats || []).filter((boat) => Number(boat.hp || 0) >= floor);
}

export function navyCapacity(navy, rules) {
  normalizeNavyDivision(navy, rules);
  const liveCargo = (navy?.cargoBoatHp || []).filter((boat) => Number(boat.hp || 0) > 0).length;
  return liveCargo * Number(rules?.units?.cargo_boat?.capacity_force_points || 20);
}

export function totalGunBoatHp(navy) {
  normalizeNavyDivision(navy);
  return (navy?.gunBoats || []).reduce((sum, boat) => sum + Math.max(0, Number(boat.hp || 0)), 0);
}

export function maxGunBoatHp(navy) {
  normalizeNavyDivision(navy);
  return (navy?.gunBoats || []).reduce((sum, boat) => sum + Math.max(0, Number(boat.maxHp || 0)), 0);
}

export function totalCargoBoatHp(navy, rules) {
  normalizeNavyDivision(navy, rules);
  return (navy?.cargoBoatHp || []).reduce((sum, boat) => sum + Math.max(0, Number(boat.hp || 0)), 0);
}

export function maxCargoBoatHp(navy, rules) {
  normalizeNavyDivision(navy, rules);
  return (navy?.cargoBoatHp || []).reduce((sum, boat) => sum + Math.max(0, Number(boat.maxHp || 0)), 0);
}

export function normalizeNavyDivision(navy, rules = null) {
  if (!navy) return navy;
  const gunBoatHp = Number(rules?.units?.gun_boat?.hp || 30);
  const cargoBoatHp = Number(rules?.units?.cargo_boat?.hp || 10);
  const normalizedGunBoats = (navy.gunBoats || [])
    .map((boat, index) => ({
      id: boat.id || `${navy.id}-G${index + 1}`,
      hp: Math.max(0, Number(boat.hp ?? gunBoatHp)),
      maxHp: Math.max(1, Number(boat.maxHp || gunBoatHp)),
    }));
  if (!Number.isFinite(Number(navy.retreatMaxGunBoatHp)) || Number(navy.retreatMaxGunBoatHp) <= 0) {
    navy.retreatMaxGunBoatHp = normalizedGunBoats.reduce(
      (sum, boat) => sum + Math.max(0, Number(boat.maxHp || 0)),
      0,
    );
  }
  navy.gunBoats = normalizedGunBoats.filter((boat) => boat.hp > 0);
  if (!Array.isArray(navy.cargoBoatHp)) {
    navy.cargoBoatHp = Array.from({ length: Number(navy.cargoBoats || 0) }, (_, index) => ({
      id: `${navy.id}-C${index + 1}`,
      hp: cargoBoatHp,
      maxHp: cargoBoatHp,
    }));
  }
  navy.cargoBoatHp = navy.cargoBoatHp
    .map((boat, index) => ({
      id: boat.id || `${navy.id}-C${index + 1}`,
      hp: Math.max(0, Number(boat.hp ?? cargoBoatHp)),
      maxHp: Math.max(1, Number(boat.maxHp || cargoBoatHp)),
    }))
    .filter((boat) => boat.hp > 0);
  navy.cargoBoats = navy.cargoBoatHp.length;
  return navy;
}

export function navyCanEnterCell(cell) {
  if (!cell || cell.power) return false;
  if (cell.river || cell.coastalWater || cell.navalRoute) return true;
  if (cell.railBridge) return true;
  return cell.city?.port === "river" || cell.city?.port === "sea";
}

export function navyPath(source, destination, cellNeighbors, rules) {
  if (!source || !destination || !navyCanEnterCell(source) || !navyCanEnterCell(destination)) return null;
  const limit = Number(rules?.move?.tiles_per_turn || 2);
  const queue = [{ cell: source, path: [source] }];
  const visited = new Set([source.key]);
  while (queue.length) {
    const { cell, path } = queue.shift();
    if (cell.key === destination.key) return path;
    if (path.length > limit) continue;
    for (const next of cellNeighbors(cell)) {
      if (visited.has(next.key) || !navyCanEnterCell(next)) continue;
      visited.add(next.key);
      queue.push({ cell: next, path: [...path, next] });
    }
  }
  return null;
}


// 海戰的規則（砲艇失能門檻、傷害分配、退卻判定、艦砲對砲兵、砲兵對艦艇、
// 船上陸軍的裁兵與覆沒、修理補血）都住在後端 navy_system/navy.py，
// 由 /api/navy-duel、/api/army-navy-contact、/api/repair-navy 結算。
// 這個檔案只留下前端真正需要的部分：建立初始艦隊、讀取艦隊現況（血量、載運量）、
// 地圖上的通行與路徑。規則只留一份在後端——前端不再自己算海戰。
