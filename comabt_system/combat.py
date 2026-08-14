"""Army-level combat resolver for Northern Expedition.

The model is intentionally coarse.  It resolves battalion pools instead of
individual board pieces, so later systems can call it from map turns, events,
or a UI without running a full tactical battle.

Expected army JSON shape:

{
    "name": "National Revolutionary Army",
    "units": {
        "infantry": 10,
        "cavalry": 2,
        "artillery": 1,
        "machine_gun": 3
    },
    "focus": "Enemy Front Army",
    "tactic": "normal_advance",
    "modifiers": [
        {"stat": "attack", "unit": "infantry", "multiplier": 1.10},
        {"stat": "hp", "unit": "cavalry", "multiplier": 1.20},
        {"stat": "attack", "unit": "artillery", "target": "machine_gun", "multiplier": 0.75}
    ]
}

Call ``simulate_battle(army_a, army_b)`` to get per-round logs and the
remaining sides. Each side contains one or more armies; reinforcements join as
separate allied armies with their own JSON, tactic, modifiers, HP, and
casualty state.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import floor
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


UnitName = str
ArmyJson = Mapping[str, Any]

UNITS: Tuple[UnitName, ...] = ("infantry", "cavalry", "artillery", "machine_gun")

UNIT_ALIASES = {
    "inf": "infantry",
    "infantry": "infantry",
    "步": "infantry",
    "步兵": "infantry",
    "cav": "cavalry",
    "cavalry": "cavalry",
    "騎": "cavalry",
    "騎兵": "cavalry",
    "art": "artillery",
    "artillery": "artillery",
    "炮": "artillery",
    "砲": "artillery",
    "砲兵": "artillery",
    "mg": "machine_gun",
    "machine gun": "machine_gun",
    "machine_gun": "machine_gun",
    "machinegun": "machine_gun",
    "機": "machine_gun",
    "機槍": "machine_gun",
    "機槍兵": "machine_gun",
}

SECTION_UNITS = {
    "line": ("infantry", "machine_gun"),
    "cavalry": ("cavalry",),
    "artillery": ("artillery",),
}

UNIT_SECTION = {
    "infantry": "line",
    "machine_gun": "line",
    "cavalry": "cavalry",
    "artillery": "artillery",
}

ATTACK_PRIORITY = {
    "infantry": ("line", "cavalry", "artillery"),
    "machine_gun": ("line", "cavalry", "artillery"),
    "cavalry": ("cavalry", "artillery", "line"),
    "artillery": ("artillery", "line", "cavalry"),
}

# Experimental battalion stats. These are deliberately simple and should be
# playtested before becoming final board-game values. Attack values live only
# in ATTACK_MATRIX because each source unit hits each target unit differently.
BASE_STATS = {
    "infantry": {"hp": 4.0, "force_points": 1.0},
    "cavalry": {"hp": 3.0, "force_points": 1.0},
    "artillery": {"hp": 2.0, "force_points": 4.0},
    "machine_gun": {"hp": 3.0, "force_points": 2.0},
}

ATTACK_MATRIX = {
    "infantry": {
        "infantry": 1.0,
        "cavalry": 1.0,
        "artillery": 1.0,
        "machine_gun": 1.0,
    },
    "cavalry": {
        "infantry": 2.0,
        "cavalry": 2.0,
        "artillery": 3.0,
        "machine_gun": 1.0,
    },
    "artillery": {
        "infantry": 3.0,
        "cavalry": 1.0,
        "artillery": 2.0,
        "machine_gun": 3.0,
    },
    "machine_gun": {
        "infantry": 2.0,
        "cavalry": 3.0,
        "artillery": 2.0,
        "machine_gun": 2.0,
    },
}

DEFAULT_BREAK_THRESHOLD = 0.30

FORCE_POINTS = {unit: stats["force_points"] for unit, stats in BASE_STATS.items()}

TACTICS = {
    "normal_advance": {
        "attack_multiplier": 1.00,
        "harm_taken_multiplier": 1.00,
        "threshold": DEFAULT_BREAK_THRESHOLD,
    },
    "probing_attack": {
        "attack_multiplier": 0.35,
        "harm_taken_multiplier": 0.45,
        "threshold": 0.25,
    },
    "layered_delaying": {
        "attack_multiplier": 0.55,
        "harm_taken_multiplier": 0.55,
        "threshold": 0.40,
    },
    "all_out_offense": {
        "attack_multiplier": 1.70,
        "harm_taken_multiplier": 1.45,
        "threshold": 0.25,
    },
    "last_stand": {
        "attack_multiplier": 1.10,
        "harm_taken_multiplier": 1.15,
        "threshold": 0.90,
    },
    "pinning_attack": {
        "attack_multiplier": 0.90,
        "harm_taken_multiplier": 0.70,
        "threshold": 0.20,
    },
}


@dataclass
class ArmyState:
    name: str
    tactic: str
    modifiers: List[Mapping[str, Any]]
    counts: Dict[UnitName, float]
    current_hp: Dict[UnitName, float]
    initial_hp: Dict[UnitName, float]
    unit_hp: Dict[UnitName, float]
    thresholds: Dict[str, float]
    section_state: Dict[str, str]
    focus_armies: Tuple[str, ...]


@dataclass
class SideState:
    label: str
    armies: List[ArmyState]


def simulate_battle(
    army_a: ArmyJson,
    army_b: ArmyJson,
    *,
    max_rounds: int = 20,
    reinforcements: Optional[Iterable[Mapping[str, Any]]] = None,
    pursuit_casualty_per_cavalry: float = 0.05,
) -> Dict[str, Any]:
    """Resolve a battle and return progress plus remaining armies.

    ``reinforcements`` may contain allied army entries like:

    {
        "round": 3,
        "side": "A",
        "army": {
            "name": "Allied 2nd Army",
            "units": {"infantry": 2},
            "tactic": "probing_attack",
            "modifiers": [{"stat": "attack", "unit": "infantry", "multiplier": 1.10}]
        }
    }

    Reinforcing armies keep their own tactic, modifiers, thresholds, HP, and
    casualty state. They join before that round's attacks.
    """

    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")

    a = SideState(label="A", armies=[_build_army(army_a, fallback_name="A main army")])
    b = SideState(label="B", armies=[_build_army(army_b, fallback_name="B main army")])
    events = _index_reinforcements(reinforcements or [])
    log: List[Dict[str, Any]] = []
    winner: Optional[str] = None

    for round_no in range(1, max_rounds + 1):
        round_log: Dict[str, Any] = {"round": round_no, "reinforcements": [], "attacks": []}

        for side_label, side in (("A", a), ("B", b)):
            for index, reinforcement in enumerate(events.get((round_no, side_label), []), start=1):
                army = _build_army(reinforcement, fallback_name=f"{side_label} reinforcement {index}")
                side.armies.append(army)
                round_log["reinforcements"].append(
                    {
                        "side": side_label,
                        "army": army.name,
                        "tactic": army.tactic,
                        "units": _clean_counts(reinforcement.get("units", {})),
                    }
                )

        _refresh_side(a)
        _refresh_side(b)

        if not _side_has_fighting_sections(a) or not _side_has_fighting_sections(b):
            winner = _winner_label(a, b)
            break

        artillery_contacts = {
            "A": _artillery_contact_map(contacting_side=b, artillery_side=a),
            "B": _artillery_contact_map(contacting_side=a, artillery_side=b),
        }
        attacks_a = _plan_side_attacks(attacker=a, defender=b, artillery_contacts=artillery_contacts["A"])
        attacks_b = _plan_side_attacks(attacker=b, defender=a, artillery_contacts=artillery_contacts["B"])

        for attack in attacks_a:
            _apply_damage(b, attack)
        for attack in attacks_b:
            _apply_damage(a, attack)

        _refresh_side(a)
        _refresh_side(b)

        round_log["artillery_contacts"] = artillery_contacts
        round_log["attacks"] = attacks_a + attacks_b
        round_log["remaining"] = {"A": _side_snapshot(a), "B": _side_snapshot(b)}
        round_log["time_to_breakdown"] = {
            "A": _time_to_breakdown(a, attacks_b),
            "B": _time_to_breakdown(b, attacks_a),
        }
        log.append(round_log)

        winner = _winner_label(a, b)
        if winner:
            break

        if not attacks_a and not attacks_b:
            winner = "stalemate"
            break

    _snap_side_to_integer_counts(a)
    _snap_side_to_integer_counts(b)

    pursuit_log = None
    if winner == "A":
        pursuit_log = _apply_cavalry_pursuit(
            loser=b,
            winner=a,
            loser_label="B",
            winner_label="A",
            casualty_per_cavalry=pursuit_casualty_per_cavalry,
        )
    elif winner == "B":
        pursuit_log = _apply_cavalry_pursuit(
            loser=a,
            winner=b,
            loser_label="A",
            winner_label="B",
            casualty_per_cavalry=pursuit_casualty_per_cavalry,
        )

    if pursuit_log:
        log.append(pursuit_log)

    return {
        "winner": winner or "undecided",
        "rounds": len([entry for entry in log if "round" in entry]),
        "log": log,
        "remaining": {"A": _side_snapshot(a), "B": _side_snapshot(b)},
    }


def _build_army(payload: ArmyJson, *, fallback_name: str) -> ArmyState:
    units = _clean_counts(payload.get("units", payload.get("army", {})))
    initial_units = _clean_counts(payload.get("initial_units", units))
    tactic = str(payload.get("tactic", "normal_advance"))
    if tactic not in TACTICS:
        raise ValueError(f"unknown tactic {tactic!r}; choose one of {sorted(TACTICS)}")

    modifiers = list(payload.get("modifiers", []))
    unit_hp = {}
    counts = {unit: float(units.get(unit, 0)) for unit in UNITS}

    for unit in UNITS:
        unit_hp[unit] = _modified_stat(
            base=BASE_STATS[unit]["hp"],
            modifiers=modifiers,
            stat="hp",
            unit=unit,
        )

    current_hp = {unit: counts[unit] * unit_hp[unit] for unit in UNITS}
    initial_hp = {
        unit: max(counts[unit], float(initial_units.get(unit, 0))) * unit_hp[unit]
        for unit in UNITS
    }
    thresholds = {}
    for section in SECTION_UNITS:
        thresholds[section] = _modified_threshold(
            base=TACTICS[tactic]["threshold"],
            modifiers=modifiers,
            section=section,
        )

    army = ArmyState(
        name=str(payload.get("name", fallback_name)),
        tactic=tactic,
        modifiers=modifiers,
        counts=counts,
        current_hp=current_hp,
        initial_hp=initial_hp,
        unit_hp=unit_hp,
        thresholds=thresholds,
        section_state={section: "fighting" for section in SECTION_UNITS},
        focus_armies=_clean_focus_armies(payload),
    )
    _refresh_sections(army)
    return army


def _clean_counts(units: Mapping[str, Any]) -> Dict[UnitName, float]:
    clean = {unit: 0.0 for unit in UNITS}
    for raw_name, raw_count in units.items():
        unit = UNIT_ALIASES.get(str(raw_name).strip().lower(), str(raw_name).strip().lower())
        if unit not in clean:
            raise ValueError(f"unknown unit {raw_name!r}; expected {', '.join(UNITS)}")
        count = float(raw_count)
        if count < 0:
            raise ValueError(f"unit count cannot be negative: {raw_name}={raw_count}")
        clean[unit] += count
    return clean


def calculate_force_strength(units: Mapping[str, Any]) -> float:
    """Return total force strength using the current unit force-point table."""

    counts = _clean_counts(units)
    return sum(counts[unit] * FORCE_POINTS[unit] for unit in UNITS)


def _clean_focus_armies(payload: ArmyJson) -> Tuple[str, ...]:
    focus = payload.get("focus", payload.get("focus_fire", payload.get("target_army")))
    if not focus:
        return ()
    if isinstance(focus, str):
        return (focus,)
    if isinstance(focus, Mapping):
        army = focus.get("army", focus.get("target_army", focus.get("name")))
        return (str(army),) if army else ()
    if isinstance(focus, Iterable):
        return tuple(str(item) for item in focus if str(item))
    return (str(focus),)


def _modified_stat(
    *,
    base: float,
    modifiers: Iterable[Mapping[str, Any]],
    stat: str,
    unit: UnitName,
    target: Optional[UnitName] = None,
) -> float:
    value = base
    for modifier in modifiers:
        if modifier.get("stat") != stat:
            continue
        mod_unit = _normalize_optional_unit(modifier.get("unit", "all"))
        mod_target = _normalize_optional_unit(modifier.get("target", "all"))
        if mod_unit not in ("all", unit):
            continue
        if target is None and mod_target != "all":
            continue
        if target is not None and mod_target not in ("all", target):
            continue
        value *= float(modifier.get("multiplier", 1.0))
        value += float(modifier.get("add", 0.0))
        value *= 1.0 + float(modifier.get("add_pct", 0.0))
    return max(value, 0.0)


def _modified_threshold(
    *,
    base: float,
    modifiers: Iterable[Mapping[str, Any]],
    section: str,
) -> float:
    value = base
    for modifier in modifiers:
        if modifier.get("stat") != "threshold":
            continue
        mod_unit = _normalize_optional_unit(modifier.get("unit", "all"))
        if mod_unit != "all" and UNIT_SECTION.get(mod_unit) != section:
            continue
        value *= float(modifier.get("multiplier", 1.0))
        value += float(modifier.get("add", 0.0))
        value *= 1.0 + float(modifier.get("add_pct", 0.0))
    return min(max(value, 0.01), 1.0)


def _normalize_optional_unit(value: Any) -> str:
    if value is None:
        return "all"
    raw = str(value).strip().lower()
    if raw in ("*", "all", "any"):
        return "all"
    return UNIT_ALIASES.get(raw, raw)


def _index_reinforcements(events: Iterable[Mapping[str, Any]]) -> Dict[Tuple[int, str], List[Mapping[str, Any]]]:
    indexed: Dict[Tuple[int, str], List[Mapping[str, Any]]] = {}
    for event in events:
        round_no = int(event["round"])
        side = str(event["side"]).upper()
        if side not in ("A", "B"):
            raise ValueError("reinforcement side must be 'A' or 'B'")
        indexed.setdefault((round_no, side), []).append(event.get("army", event))
    return indexed


def _refresh_sections(army: ArmyState) -> None:
    for section, units in SECTION_UNITS.items():
        initial = sum(army.initial_hp[unit] for unit in units)
        current = sum(army.current_hp[unit] for unit in units)
        if initial <= 0 or current <= 0:
            army.section_state[section] = "gone"
            continue
        casualties = initial - current
        break_hp = initial * army.thresholds[section]
        army.section_state[section] = "fleeing" if casualties + 1e-9 >= break_hp else "fighting"


def _refresh_side(side: SideState) -> None:
    for army in side.armies:
        _refresh_sections(army)


def _side_has_fighting_sections(side: SideState) -> bool:
    return any(
        state == "fighting"
        for army in side.armies
        for state in army.section_state.values()
    )


def _winner_label(a: SideState, b: SideState) -> Optional[str]:
    a_fights = _side_has_fighting_sections(a)
    b_fights = _side_has_fighting_sections(b)
    if a_fights and not b_fights:
        return "A"
    if b_fights and not a_fights:
        return "B"
    if not a_fights and not b_fights:
        return "draw"
    return None


def _plan_side_attacks(
    *,
    attacker: SideState,
    defender: SideState,
    artillery_contacts: Mapping[str, Tuple[str, ...]],
) -> List[Dict[str, Any]]:
    attacks = []
    for army in attacker.armies:
        attacks.extend(
            _plan_army_attacks(
                attacker=army,
                defender=defender,
                attacker_label=attacker.label,
                artillery_contacts=artillery_contacts,
            )
        )
    return attacks


def _plan_army_attacks(
    *,
    attacker: ArmyState,
    defender: SideState,
    attacker_label: str,
    artillery_contacts: Mapping[str, Tuple[str, ...]],
) -> List[Dict[str, Any]]:
    tactic = TACTICS[attacker.tactic]
    attacks = []
    for unit in UNITS:
        if attacker.section_state[UNIT_SECTION[unit]] != "fighting":
            continue
        count = _hp_to_count(attacker.current_hp[unit], attacker.unit_hp[unit])
        if count <= 0:
            continue
        forced_contact = False
        target_section = _choose_target_section(unit, defender)
        target_army_names = _valid_focus_armies(attacker, defender, unit)
        if unit == "artillery":
            contacting_cavalry = _valid_contacting_cavalry_armies(
                defender,
                artillery_contacts.get(attacker.name, ()),
            )
            if contacting_cavalry:
                forced_contact = True
                target_section = "cavalry"
                target_army_names = contacting_cavalry
        if target_army_names and not forced_contact:
            target_section = _choose_target_section(unit, defender, target_army_names=target_army_names)
        if not target_section:
            continue
        target_units = _living_fighting_units(defender, target_section, target_army_names=target_army_names)
        damage_by_target = _target_damage_allocations(
            attacker=attacker,
            defender=defender,
            source_unit=unit,
            source_count=count,
            target_units=target_units,
            attack_multiplier=tactic["attack_multiplier"],
            target_army_names=target_army_names,
        )
        attack_value = sum(target["damage"] for target in damage_by_target)
        if attack_value <= 0:
            continue
        attacks.append(
            {
                "attacker": attacker_label,
                "attacker_army": attacker.name,
                "defender": defender.label,
                "source_unit": unit,
                "target_section": target_section,
                "target_units": target_units,
                "target_armies": _target_army_names(defender, target_units, target_army_names=target_army_names),
                "focus": list(attacker.focus_armies),
                "forced_contact": forced_contact,
                "damage": round(attack_value, 4),
                "damage_by_target": [
                    {**target, "damage": round(target["damage"], 4)}
                    for target in damage_by_target
                ],
            }
        )
    return attacks


def _artillery_contact_map(*, contacting_side: SideState, artillery_side: SideState) -> Dict[str, Tuple[str, ...]]:
    contacts: Dict[str, List[str]] = {}
    for army in contacting_side.armies:
        if army.section_state["cavalry"] != "fighting":
            continue
        if _hp_to_count(army.current_hp["cavalry"], army.unit_hp["cavalry"]) <= 0:
            continue
        target_army_names = _valid_focus_armies(army, artillery_side, "cavalry")
        target_section = _choose_target_section("cavalry", artillery_side)
        if target_army_names:
            target_section = _choose_target_section("cavalry", artillery_side, target_army_names=target_army_names)
        if target_section != "artillery":
            continue
        target_units = _living_fighting_units(
            artillery_side,
            "artillery",
            target_army_names=target_army_names,
        )
        for target_army in _target_army_names(artillery_side, target_units, target_army_names=target_army_names):
            contacts.setdefault(target_army, [])
            if army.name not in contacts[target_army]:
                contacts[target_army].append(army.name)
    return {army_name: tuple(contacting_armies) for army_name, contacting_armies in contacts.items()}


def _valid_contacting_cavalry_armies(defender: SideState, army_names: Iterable[str]) -> Tuple[str, ...]:
    valid = []
    for army_name in army_names:
        army = _find_army(defender, str(army_name))
        if not army:
            continue
        if army.section_state["cavalry"] != "fighting":
            continue
        if _hp_to_count(army.current_hp["cavalry"], army.unit_hp["cavalry"]) <= 0:
            continue
        valid.append(army.name)
    return tuple(valid)


def _valid_focus_armies(attacker: ArmyState, defender: SideState, source_unit: UnitName) -> Tuple[str, ...]:
    if not attacker.focus_armies:
        return ()
    focused = tuple(name for name in attacker.focus_armies if _find_army(defender, name))
    if not focused:
        return ()
    if _choose_target_section(source_unit, defender, target_army_names=focused):
        return focused
    return ()


def _target_damage_allocations(
    *,
    attacker: ArmyState,
    defender: SideState,
    source_unit: UnitName,
    source_count: float,
    target_units: Iterable[UnitName],
    attack_multiplier: float,
    target_army_names: Tuple[str, ...] = (),
) -> List[Dict[str, Any]]:
    weights = _target_weights(defender, set(target_units), target_army_names=target_army_names)
    allocations = []

    for army, target_unit, weight in weights:
        attack = _modified_stat(
            base=_base_attack(source_unit, target_unit),
            modifiers=attacker.modifiers,
            stat="attack",
            unit=source_unit,
            target=target_unit,
        )
        damage = source_count * weight * attack * attack_multiplier
        damage *= TACTICS[army.tactic]["harm_taken_multiplier"]
        damage = _army_modified_incoming_harm(army, damage, target_unit)
        if damage > 0:
            allocations.append({"army": army.name, "unit": target_unit, "damage": damage})
    return allocations


def _army_modified_incoming_harm(army: ArmyState, damage: float, target_unit: UnitName) -> float:
    adjusted = damage
    for modifier in army.modifiers:
        if modifier.get("stat") != "harm_taken":
            continue
        mod_unit = _normalize_optional_unit(modifier.get("unit", "all"))
        if mod_unit not in ("all", target_unit):
            continue
        adjusted *= float(modifier.get("multiplier", 1.0))
        adjusted += float(modifier.get("add", 0.0))
        adjusted *= 1.0 + float(modifier.get("add_pct", 0.0))
    return adjusted


def _base_attack(source_unit: UnitName, target_unit: UnitName) -> float:
    try:
        return ATTACK_MATRIX[source_unit][target_unit]
    except KeyError as exc:
        raise ValueError(f"missing attack matrix value for {source_unit} attacking {target_unit}") from exc


def _choose_target_section(
    source_unit: UnitName,
    defender: SideState,
    *,
    target_army_names: Tuple[str, ...] = (),
) -> Optional[str]:
    for section in ATTACK_PRIORITY[source_unit]:
        if (
            _side_section_state(defender, section, target_army_names=target_army_names) == "fighting"
            and _side_section_hp(defender, section, target_army_names=target_army_names) > 0
        ):
            return section
    return None


def _living_fighting_units(
    side: SideState,
    section: str,
    *,
    target_army_names: Tuple[str, ...] = (),
) -> List[UnitName]:
    return [
        unit
        for unit in SECTION_UNITS[section]
        if _side_unit_count(side, unit, fighting_only=True, target_army_names=target_army_names) > 0
    ]


def _apply_damage(defender: SideState, attack: Mapping[str, Any]) -> None:
    actual_damage = 0.0
    for target in attack.get("damage_by_target", ()):
        army = _find_army(defender, str(target["army"]))
        unit = str(target["unit"])
        if not army or unit not in UNITS:
            continue
        section = UNIT_SECTION[unit]
        _refresh_sections(army)
        if army.section_state[section] != "fighting":
            target["applied_damage"] = 0.0
            continue
        initial_section_hp = sum(army.initial_hp[item] for item in SECTION_UNITS[section])
        current_section_hp = sum(army.current_hp[item] for item in SECTION_UNITS[section])
        retreat_floor = initial_section_hp * (1.0 - army.thresholds[section])
        damage_before_retreat = max(0.0, current_section_hp - retreat_floor)
        applied = min(float(target["damage"]), army.current_hp[unit], damage_before_retreat)
        army.current_hp[unit] = max(0.0, army.current_hp[unit] - applied)
        target["applied_damage"] = applied
        actual_damage += applied
        _refresh_sections(army)
    if isinstance(attack, dict):
        attack["applied_damage"] = actual_damage


def _time_to_breakdown(side: SideState, incoming_attacks: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    incoming_by_section = {section: 0.0 for section in SECTION_UNITS}
    incoming_by_army_section: Dict[str, Dict[str, float]] = {}
    for attack in incoming_attacks:
        section = str(attack["target_section"])
        damage = float(attack["damage"])
        incoming_by_section[section] += damage
        for target in attack.get("damage_by_target", ()):
            incoming_by_army_section.setdefault(str(target["army"]), {}).setdefault(section, 0.0)
            incoming_by_army_section[str(target["army"])][section] += float(target["damage"])

    aggregate: Dict[str, Optional[float]] = {}
    by_army: Dict[str, Dict[str, Optional[float]]] = {}

    for section, units in SECTION_UNITS.items():
        fighting = [army for army in side.armies if army.section_state[section] == "fighting"]
        if not fighting:
            aggregate[section] = 0.0
            continue

        incoming = incoming_by_section[section]
        if incoming <= 0:
            aggregate[section] = None
            continue

        times = []
        for army in fighting:
            army_incoming = incoming_by_army_section.get(army.name, {}).get(section, 0.0)
            army_time = _army_time_to_breakdown(army, section, army_incoming)
            by_army.setdefault(army.name, {})[section] = army_time
            if army_time is not None:
                times.append(army_time)
        aggregate[section] = min(times) if times else None

    for army in side.armies:
        by_army.setdefault(army.name, {})
        for section in SECTION_UNITS:
            if section not in by_army[army.name]:
                by_army[army.name][section] = 0.0 if army.section_state[section] != "fighting" else None

    return {"aggregate": aggregate, "armies": by_army}


def _army_time_to_breakdown(army: ArmyState, section: str, incoming: float) -> Optional[float]:
    if army.section_state[section] != "fighting":
        return 0.0
    if incoming <= 0:
        return None
    units = SECTION_UNITS[section]
    initial = sum(army.initial_hp[unit] for unit in units)
    current = sum(army.current_hp[unit] for unit in units)
    remaining_break_hp = max(0.0, (initial * army.thresholds[section]) - (initial - current))
    return round(remaining_break_hp / incoming, 4)


def _apply_cavalry_pursuit(
    *,
    loser: SideState,
    winner: SideState,
    loser_label: str,
    winner_label: str,
    casualty_per_cavalry: float,
) -> Dict[str, Any]:
    cavalry_count = _side_display_count(winner, "cavalry")
    loser_cavalry = _side_display_count(loser, "cavalry")
    before = _side_snapshot(loser)
    damage_by_target: List[Dict[str, Any]] = []

    def apply_unit_damage(unit: UnitName, planned_damage: float, source: str) -> float:
        total_unit_hp = sum(army.current_hp[unit] for army in loser.armies)
        if planned_damage <= 0 or total_unit_hp <= 0:
            return 0.0
        max_unit_damage = total_unit_hp * 0.50
        capped_damage = min(planned_damage, max_unit_damage)
        applied_total = 0.0
        for army in loser.armies:
            unit_hp = army.current_hp[unit]
            if unit_hp <= 0:
                continue
            army_damage = min(unit_hp, capped_damage * (unit_hp / total_unit_hp))
            army.current_hp[unit] = max(0.0, unit_hp - army_damage)
            applied_total += army_damage
            damage_by_target.append(
                {
                    "army": army.name,
                    "unit": unit,
                    "source": source,
                    "attack": _base_attack("cavalry", unit),
                    "planned_damage": round(planned_damage * (unit_hp / total_unit_hp), 4),
                    "cap": round(max_unit_damage * (unit_hp / total_unit_hp), 4),
                    "applied_damage": round(army_damage, 4),
                }
            )
        return applied_total

    def apply_spillover_damage(spillover_damage: float) -> float:
        spillover_units = [unit for unit in UNITS if unit != "cavalry" and _side_display_count(loser, unit) > 0]
        total_hp = sum(sum(army.current_hp[unit] for army in loser.armies) for unit in spillover_units)
        if spillover_damage <= 0 or total_hp <= 0:
            return 0.0
        applied_total = 0.0
        for unit in spillover_units:
            unit_hp = sum(army.current_hp[unit] for army in loser.armies)
            applied_total += apply_unit_damage(unit, spillover_damage * (unit_hp / total_hp), "cavalry_cover_spillover")
        return applied_total

    if cavalry_count <= 0:
        return {
            "phase": "pursuit",
            "winner": winner_label,
            "loser": loser_label,
            "cavalry": 0,
            "loser_cavalry": loser_cavalry,
            "eligible": False,
            "reason": "winner has no cavalry",
            "damage_by_target": [],
            "before": before,
            "after": deepcopy(before),
        }
    spillover_damage = 0.0
    if loser_cavalry > 0:
        planned_damage = cavalry_count * _base_attack("cavalry", "cavalry")
        applied_damage = apply_unit_damage("cavalry", planned_damage, "cavalry_cover")
        spillover_damage = max(0.0, planned_damage - applied_damage)
        apply_spillover_damage(spillover_damage)
    else:
        target_units = [unit for unit in UNITS if _side_display_count(loser, unit) > 0]
        for unit in target_units:
            planned_damage = cavalry_count * _base_attack("cavalry", unit)
            apply_unit_damage(unit, planned_damage, "open_pursuit")
    _snap_side_to_integer_counts(loser)

    return {
        "phase": "pursuit",
        "winner": winner_label,
        "loser": loser_label,
        "cavalry": cavalry_count,
        "loser_cavalry": loser_cavalry,
        "eligible": True,
        "covering_cavalry": loser_cavalry > 0,
        "spillover_damage": round(spillover_damage, 4),
        "formula": "winner_cavalry_count * ATTACK_MATRIX['cavalry'][target_unit]",
        "cap": "50% of each loser unit type's remaining HP",
        "damage_by_target": damage_by_target,
        "before": before,
        "after": _side_snapshot(loser),
    }


def _section_hp(army: ArmyState, section: str) -> float:
    return sum(army.current_hp[unit] for unit in SECTION_UNITS[section])


def _side_section_hp(
    side: SideState,
    section: str,
    *,
    target_army_names: Tuple[str, ...] = (),
) -> float:
    return sum(
        _section_hp(army, section)
        for army in _targetable_armies(side, target_army_names)
        if army.section_state[section] == "fighting"
    )


def _side_section_state(
    side: SideState,
    section: str,
    *,
    target_army_names: Tuple[str, ...] = (),
) -> str:
    states = [army.section_state[section] for army in _targetable_armies(side, target_army_names)]
    if any(state == "fighting" for state in states):
        return "fighting"
    if any(state == "fleeing" for state in states):
        return "fleeing"
    return "gone"


def _side_unit_count(
    side: SideState,
    unit: UnitName,
    *,
    fighting_only: bool,
    target_army_names: Tuple[str, ...] = (),
) -> float:
    total = 0.0
    for army in _targetable_armies(side, target_army_names):
        if fighting_only and army.section_state[UNIT_SECTION[unit]] != "fighting":
            continue
        total += _hp_to_count(army.current_hp[unit], army.unit_hp[unit])
    return total


def _target_weights(
    side: SideState,
    target_units: Iterable[UnitName],
    *,
    target_army_names: Tuple[str, ...] = (),
) -> List[Tuple[ArmyState, UnitName, float]]:
    targets = set(target_units)
    weights: List[Tuple[ArmyState, UnitName, float]] = []
    eligible_armies = []
    for army in _targetable_armies(side, target_army_names):
        army_total = 0.0
        for unit in targets:
            if army.section_state[UNIT_SECTION[unit]] != "fighting":
                continue
            army_total += _hp_to_count(army.current_hp[unit], army.unit_hp[unit])
        if army_total > 0:
            eligible_armies.append((army, army_total))

    if not eligible_armies:
        return weights

    army_share = 1.0 / len(eligible_armies)
    for army, army_total in eligible_armies:
        for unit in targets:
            if army.section_state[UNIT_SECTION[unit]] != "fighting":
                continue
            count = _hp_to_count(army.current_hp[unit], army.unit_hp[unit])
            if count > 0:
                weights.append((army, unit, army_share * (count / army_total)))
    return weights


def _target_army_names(
    side: SideState,
    target_units: Iterable[UnitName],
    *,
    target_army_names: Tuple[str, ...] = (),
) -> List[str]:
    names = []
    for army, _, _ in _target_weights(side, target_units, target_army_names=target_army_names):
        if army.name not in names:
            names.append(army.name)
    return names


def _targetable_armies(side: SideState, target_army_names: Tuple[str, ...] = ()) -> List[ArmyState]:
    if not target_army_names:
        return list(side.armies)
    wanted = set(target_army_names)
    return [army for army in side.armies if army.name in wanted]


def _find_army(side: SideState, name: str) -> Optional[ArmyState]:
    for army in side.armies:
        if army.name == name:
            return army
    return None


def _hp_to_count(hp: float, unit_hp: float) -> float:
    if unit_hp <= 0:
        return 0.0
    return max(0.0, hp / unit_hp)


def _display_count(hp: float, unit_hp: float) -> int:
    return _round_half_down(_hp_to_count(hp, unit_hp))


def _side_display_count(side: SideState, unit: UnitName) -> int:
    return sum(_display_count(army.current_hp[unit], army.unit_hp[unit]) for army in side.armies)


def _snap_army_to_integer_counts(army: ArmyState) -> None:
    previous_states = dict(army.section_state)
    for unit in UNITS:
        army.current_hp[unit] = float(_display_count(army.current_hp[unit], army.unit_hp[unit])) * army.unit_hp[unit]
    _refresh_sections(army)
    for section, previous_state in previous_states.items():
        if previous_state == "fleeing" and army.section_state.get(section) == "fighting":
            army.section_state[section] = "fleeing"


def _snap_side_to_integer_counts(side: SideState) -> None:
    for army in side.armies:
        _snap_army_to_integer_counts(army)


def _round_half_down(value: float) -> int:
    """Round to nearest battalion, with .5 rounded down.

    This follows Owen's pursuit example: 1.5 -> 1, 1.7 -> 2.
    """

    return max(0, int(floor(value + 0.499999)))


def _army_snapshot(army: ArmyState) -> Dict[str, Any]:
    return {
        "name": army.name,
        "tactic": army.tactic,
        "focus": list(army.focus_armies),
        "units": {unit: _display_count(army.current_hp[unit], army.unit_hp[unit]) for unit in UNITS},
        "raw_hp": {unit: round(army.current_hp[unit], 4) for unit in UNITS},
        "sections": dict(army.section_state),
    }


def _side_snapshot(side: SideState) -> Dict[str, Any]:
    return {
        "label": side.label,
        "units": {unit: _side_display_count(side, unit) for unit in UNITS},
        "raw_hp": {
            unit: round(sum(army.current_hp[unit] for army in side.armies), 4)
            for unit in UNITS
        },
        "sections": {section: _side_section_state(side, section) for section in SECTION_UNITS},
        "armies": [_army_snapshot(army) for army in side.armies],
    }


if __name__ == "__main__":
    example_a = {
        "name": "A",
        "units": {"infantry": 10, "cavalry": 3, "artillery": 2, "machine_gun": 3},
        "tactic": "normal_advance",
    }
    example_b = {
        "name": "B",
        "units": {"infantry": 7, "cavalry": 0, "artillery": 1, "machine_gun": 2},
        "tactic": "probing_attack",
    }
    print(simulate_battle(example_a, example_b, max_rounds=5))
