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

export function retreatBaselineGunBoatHp(navy, rules = null) {
  normalizeNavyDivision(navy, rules);
  const baseline = Number(navy?.retreatMaxGunBoatHp || 0);
  return Math.max(0, baseline || maxGunBoatHp(navy));
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

export function navyRetreatThresholdReached(navy, rules) {
  normalizeNavyDivision(navy, rules);
  const maxHp = retreatBaselineGunBoatHp(navy, rules);
  if (maxHp <= 0) return true;
  const lossRatio = Number(rules?.land_interaction?.navy_retreat_gun_boat_hp_loss_ratio || 0.5);
  return totalGunBoatHp(navy) <= maxHp * (1 - lossRatio);
}

export function restoreHpToFloor(navy, targetHp) {
  const target = Math.max(0, Number(targetHp || 0));
  let restored = 0;
  normalizeNavyDivision(navy);
  for (const boat of [...(navy?.gunBoats || []), ...(navy?.cargoBoatHp || [])]) {
    const maxHp = Number(boat.maxHp || 0);
    const next = Math.min(maxHp, Math.max(Number(boat.hp || 0), target));
    restored += Math.max(0, next - Number(boat.hp || 0));
    boat.hp = next;
  }
  return Math.round(restored);
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

export function applyGunBoatDamage(navy, damage) {
  normalizeNavyDivision(navy);
  let remaining = Math.max(0, Number(damage || 0));
  const damaged = [];
  const targets = [
    ...(navy?.gunBoats || []).map((boat) => ({ boat, type: "gun_boat" })),
    ...(navy?.cargoBoatHp || []).map((boat) => ({ boat, type: "cargo_boat" })),
  ].sort((a, b) => {
    if (a.type !== b.type) return a.type === "gun_boat" ? -1 : 1;
    return Number(b.boat.hp || 0) - Number(a.boat.hp || 0);
  });
  for (const target of targets) {
    if (remaining <= 0) break;
    const { boat, type } = target;
    const before = Math.max(0, Number(boat.hp || 0));
    if (before <= 0) continue;
    const applied = Math.min(before, remaining);
    boat.hp = before - applied;
    remaining -= applied;
    damaged.push({ boat_id: boat.id, type, before, after: boat.hp, damage: applied, sunk: boat.hp <= 0 });
  }
  normalizeNavyDivision(navy);
  return { applied: Math.max(0, Number(damage || 0)) - remaining, damaged };
}

export function resolveArmyNavyContact(armyUnits, navy, rules) {
  const artilleryBefore = Math.max(0, Math.round(Number(armyUnits?.artillery || 0)));
  const activeBoats = activeGunBoats(navy, rules);
  const boatDamage = artilleryBefore * Number(rules?.land_interaction?.artillery_attack_to_gun_boat || 1);
  const gunBoatAttack = activeBoats.length * Number(rules?.units?.gun_boat?.attack?.artillery || 2);
  const gunBoatDamage = applyGunBoatDamage(navy, boatDamage);
  const artilleryLost = Math.min(artilleryBefore, Math.ceil(gunBoatAttack / 2));
  const artilleryAfter = Math.max(0, artilleryBefore - artilleryLost);
  // An army with any artillery left holds the contact tile.  The old
  // percentage-loss check made a viable artillery force back away after a
  // single exchange and caused army/navy contacts to stall.
  const landRetreat = artilleryAfter <= 0;
  const navyRetreat = navyRetreatThresholdReached(navy, rules) || activeGunBoats(navy, rules).length === 0;
  return {
    kind: "army_navy",
    activeGunBoats: activeBoats.length,
    navyFired: activeBoats.length > 0,
    boatDamage: gunBoatDamage.applied,
    boatDamageDetail: gunBoatDamage,
    artilleryBefore,
    artilleryLost,
    artilleryAfter,
    landRetreat,
    navyRetreat,
  };
}

export function resolveNavyDuel(attacker, defender, rules) {
  // Fire eligibility is fixed at the start of the exchange.  A division with
  // no active gunboat takes the enemy salvo without returning fire.
  const activeA = activeGunBoats(attacker, rules).length;
  const activeB = activeGunBoats(defender, rules).length;
  const attackA = activeA * Number(rules?.units?.gun_boat?.attack?.gun_boat || 5);
  const attackB = activeB * Number(rules?.units?.gun_boat?.attack?.gun_boat || 5);
  const damageToA = applyGunBoatDamage(attacker, attackB);
  const damageToB = applyGunBoatDamage(defender, attackA);
  let attackerRetreat = activeGunBoats(attacker, rules).length === 0 || navyRetreatThresholdReached(attacker, rules);
  let defenderRetreat = activeGunBoats(defender, rules).length === 0 || navyRetreatThresholdReached(defender, rules);
  let tileWinner = null;
  if (attackerRetreat && defenderRetreat) {
    const attackerHp = totalGunBoatHp(attacker);
    const defenderHp = totalGunBoatHp(defender);
    if (attackerHp > defenderHp) {
      attackerRetreat = false;
      tileWinner = "attacker";
    } else if (defenderHp > attackerHp) {
      defenderRetreat = false;
      tileWinner = "defender";
    } else {
      tileWinner = "draw";
    }
  } else if (attackerRetreat !== defenderRetreat) {
    tileWinner = attackerRetreat ? "defender" : "attacker";
  }
  return {
    kind: "navy_duel",
    attackerActiveGunBoats: activeA,
    defenderActiveGunBoats: activeB,
    attackerDamage: damageToB.applied,
    attackerDamageDetail: damageToB,
    defenderDamage: damageToA.applied,
    defenderDamageDetail: damageToA,
    attackerRetreat,
    defenderRetreat,
    tileWinner,
  };
}
