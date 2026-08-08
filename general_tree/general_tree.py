"""General hierarchy and loyalty helpers for Northern Expedition.

The module mutates a plain JSON-like dict in place and returns the changed
object. That keeps it easy for a future save-file, UI, or event system to call
without needing custom classes.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


UnitBlock = Mapping[str, Any]
GeneralTree = Dict[str, Any]

DEFAULT_FORCE_POINTS = {
    "infantry": 1.0,
    "cavalry": 1.0,
    "machine_gun": 2.0,
    "artillery": 4.0,
}

DEFAULT_SLOTS = {
    "great_general": 3,
    "lieutenant_general": 2,
    "major_general": 0,
}

BODY_GUARD_LEVELS = (None, "low", "high")

CHILD_ROLE = {
    "great_general": "lieutenant_general",
    "lieutenant_general": "major_general",
    "major_general": "major_general",
}


def calculate_force_strength(
    units: UnitBlock,
    *,
    force_points: Mapping[str, float] = DEFAULT_FORCE_POINTS,
) -> float:
    """Return force strength for an army unit block."""

    total = 0.0
    for unit, raw_count in units.items():
        if unit not in force_points:
            raise ValueError(f"unknown unit {unit!r}; expected one of {sorted(force_points)}")
        count = float(raw_count)
        if count < 0:
            raise ValueError(f"unit count cannot be negative: {unit}={raw_count}")
        total += count * float(force_points[unit])
    return total


def validate_tree(tree: GeneralTree) -> GeneralTree:
    """Validate hierarchy slots, parent links, and basic loyalty ranges."""

    generals = _generals(tree)
    great_id = tree.get("great_general_id")
    if great_id not in generals:
        raise ValueError("tree must name an existing great_general_id")
    if generals[great_id].get("role") != "great_general":
        raise ValueError("great_general_id must point to a great_general")

    for general_id, general in generals.items():
        role = general.get("role")
        if role not in DEFAULT_SLOTS:
            raise ValueError(f"{general_id} has unknown role {role!r}")
        loyalty = general.get("loyalty")
        if loyalty is not None and not general.get("loyalty_exempt", False):
            _set_loyalty(general, loyalty)
        if _is_absolute_loyal(general):
            general["loyalty"] = 10
        body_guard_level = general.get("body_guard_level")
        if body_guard_level not in BODY_GUARD_LEVELS:
            raise ValueError(f"{general_id} has invalid body_guard_level {body_guard_level!r}")
        subordinates = _subordinates(general)
        if len(subordinates) > int(general.get("subordinate_slots", DEFAULT_SLOTS[role])):
            raise ValueError(f"{general_id} has more subordinates than slots")
        own_force = calculate_force_strength(general.get("units", {}))
        command_cap = float(general.get("command_cap", 0))
        if own_force > command_cap:
            raise ValueError(f"{general_id} commands {own_force} force over cap {command_cap}")
        for child_id in subordinates:
            if child_id not in generals:
                raise ValueError(f"{general_id} references missing subordinate {child_id}")
            if generals[child_id].get("parent_id") != general_id:
                raise ValueError(f"{child_id} must point back to parent_id {general_id}")
    return tree


def recruit_general(
    tree: GeneralTree,
    *,
    parent_id: str,
    general: Mapping[str, Any],
    starting_units: UnitBlock,
    minimum_force: float = 5.0,
) -> GeneralTree:
    """Append a new general under a parent and create his starting army."""

    generals = _generals(tree)
    parent = _general(tree, parent_id)
    general_id = str(general["id"])
    if general_id in generals:
        raise ValueError(f"general already exists: {general_id}")

    parent_role = str(parent.get("role"))
    role = str(general.get("role", CHILD_ROLE.get(parent_role, "major_general")))
    if role == "great_general":
        raise ValueError("cannot recruit another great_general into this tree")
    if len(_subordinates(parent)) >= int(parent.get("subordinate_slots", DEFAULT_SLOTS[parent_role])):
        raise ValueError(f"{parent_id} has no empty subordinate slot")

    force = calculate_force_strength(starting_units)
    if force < minimum_force:
        raise ValueError(f"new army must start with at least {minimum_force} force strength")
    command_cap = float(general.get("command_cap", force))
    if force > command_cap:
        raise ValueError(f"starting force {force} exceeds command cap {command_cap}")

    new_general = {
        "id": general_id,
        "name": str(general.get("name", general_id)),
        "role": role,
        "faction": str(general.get("faction", parent.get("faction", "unknown"))),
        "core_faction": bool(general.get("core_faction", False)),
        "loyalty": general.get("loyalty"),
        "absolute_loyalty": bool(general.get("absolute_loyalty", False)),
        "loyalty_exempt": bool(general.get("loyalty_exempt", False)),
        "body_guard_level": general.get("body_guard_level"),
        "command_cap": command_cap,
        "traits": list(general.get("traits", [])),
        "skills": list(general.get("skills", [])),
        "units": _clean_units(starting_units),
        "parent_id": parent_id,
        "subordinate_slots": int(general.get("subordinate_slots", DEFAULT_SLOTS[role])),
        "subordinates": list(general.get("subordinates", [])),
        "status": str(general.get("status", "active")),
    }
    if new_general["loyalty"] is not None:
        _set_loyalty(new_general, new_general["loyalty"])
    if _is_absolute_loyal(new_general):
        new_general["loyalty"] = 10

    generals[general_id] = new_general
    _subordinates(parent).append(general_id)
    return validate_tree(tree)


def increase_affiliation_slots(tree: GeneralTree, general_id: str, amount: int = 1) -> GeneralTree:
    """Increase a general's subordinate capacity for event rewards."""

    if amount < 1:
        raise ValueError("amount must be positive")
    general = _general(tree, general_id)
    role = str(general.get("role"))
    if role != "lieutenant_general":
        raise ValueError("only lieutenant generals can gain extra major-general slots")
    current = int(general.get("subordinate_slots", DEFAULT_SLOTS[role]))
    general["subordinate_slots"] = min(3, current + amount)
    return tree


def allocate_troops(
    tree: GeneralTree,
    general_id: str,
    units: UnitBlock,
    *,
    allow_over_cap: bool = False,
) -> GeneralTree:
    """Reinforce a general's army with new troops.

    This only adds troops. There is intentionally no normal troop-removal or
    transfer helper because army allocations should not be freely reversible.
    """

    general = _general(tree, general_id)
    additions = _clean_units(units)
    current_units = _clean_units(general.get("units", {}))
    merged = dict(current_units)
    for unit, count in additions.items():
        merged[unit] = merged.get(unit, 0.0) + count

    new_force = calculate_force_strength(merged)
    command_cap = float(general.get("command_cap", 0))
    if not allow_over_cap and new_force > command_cap:
        raise ValueError(f"allocation would exceed command cap {command_cap}")
    general["units"] = merged
    return tree


def record_battle_loss(
    tree: GeneralTree,
    general_id: str,
    lost_units: UnitBlock,
    *,
    loyalty_loss_per_force_point: float = 0.1,
) -> GeneralTree:
    """Apply casualties and dissent from lost force strength."""

    general = _general(tree, general_id)
    losses = _clean_units(lost_units)
    units = _clean_units(general.get("units", {}))
    actual_lost: Dict[str, float] = {}
    for unit, requested_loss in losses.items():
        loss = min(units.get(unit, 0.0), requested_loss)
        units[unit] = units.get(unit, 0.0) - loss
        actual_lost[unit] = loss
    general["units"] = units

    lost_strength = calculate_force_strength(actual_lost)
    if (
        not general.get("loyalty_exempt", False)
        and not _is_absolute_loyal(general)
        and general.get("loyalty") is not None
    ):
        _set_loyalty(general, float(general["loyalty"]) - lost_strength * loyalty_loss_per_force_point)
    return tree


def add_loyalty(tree: GeneralTree, general_id: str, amount: float) -> GeneralTree:
    """Directly add or remove loyalty for event effects."""

    general = _general(tree, general_id)
    if general.get("loyalty_exempt", False) or _is_absolute_loyal(general) or general.get("loyalty") is None:
        return tree
    _set_loyalty(general, float(general["loyalty"]) + amount)
    return tree


def transfer_troops_between_absolute_loyal_pair(
    tree: GeneralTree,
    *,
    from_general_id: str,
    to_general_id: str,
    units: UnitBlock,
    allow_over_cap: bool = False,
) -> GeneralTree:
    """Move troops between a great general and the faction's absolute loyalist.

    Map adjacency is intentionally checked by the caller. This helper enforces
    only the hierarchy/loyalty exception and command-cap accounting.
    """

    source = _general(tree, from_general_id)
    target = _general(tree, to_general_id)
    pair_roles = {source.get("role"), target.get("role")}
    if pair_roles != {"great_general", "lieutenant_general"}:
        raise ValueError("free transfer requires a great general and one lieutenant general")
    if source.get("faction") != target.get("faction"):
        raise ValueError("free transfer requires the same faction")
    if not (_is_absolute_loyal(source) or _is_absolute_loyal(target)):
        raise ValueError("one side of the transfer must have absolute loyalty")

    moving = _clean_units(units)
    source_units = _clean_units(source.get("units", {}))
    target_units = _clean_units(target.get("units", {}))
    for unit, count in moving.items():
        if count > source_units.get(unit, 0.0):
            raise ValueError(f"not enough {unit} to transfer")
        source_units[unit] -= count
        target_units[unit] += count

    if not allow_over_cap:
        target_force = calculate_force_strength(target_units)
        command_cap = float(target.get("command_cap", 0))
        if target_force > command_cap:
            raise ValueError(f"transfer would exceed command cap {command_cap}")

    source["units"] = source_units
    target["units"] = target_units
    return tree


def set_body_guard_level(tree: GeneralTree, general_id: str, level: Any) -> GeneralTree:
    """Set a general's body guard level to None, low, or high."""

    if level not in BODY_GUARD_LEVELS:
        raise ValueError("body guard level must be None, 'low', or 'high'")
    _general(tree, general_id)["body_guard_level"] = level
    return tree


def loyalty_report(tree: GeneralTree) -> Dict[str, Any]:
    """Return core strength, relative strength, and simple rebellion pressure."""

    validate_tree(tree)
    generals = _generals(tree)
    great = _general(tree, str(tree["great_general_id"]))
    core_faction = str(great["faction"])
    core_strength = sum(
        calculate_force_strength(general.get("units", {}))
        for general in generals.values()
        if str(general.get("faction")) == core_faction
    )

    report = {
        "core_faction": core_faction,
        "core_force_strength": core_strength,
        "generals": {},
    }
    for general_id, general in generals.items():
        command_strength = subtree_force_strength(tree, general_id)
        non_core = str(general.get("faction")) != core_faction
        relative = None
        if non_core:
            relative = command_strength / core_strength if core_strength else 1.0
        loyalty = general.get("loyalty")
        rebellion_pressure = None
        if relative is not None and loyalty is not None and not general.get("loyalty_exempt", False):
            rebellion_pressure = round(relative * (10.0 - float(loyalty)), 4)
        report["generals"][general_id] = {
            "name": general.get("name", general_id),
            "faction": general.get("faction"),
            "command_strength": command_strength,
            "relative_strength": None if relative is None else round(relative, 4),
            "loyalty": loyalty,
            "rebellion_pressure": rebellion_pressure,
        }
    return report


def subtree_force_strength(tree: GeneralTree, general_id: str) -> float:
    """Return force strength commanded by a general and all subordinates."""

    general = _general(tree, general_id)
    total = calculate_force_strength(general.get("units", {}))
    for child_id in _subordinates(general):
        total += subtree_force_strength(tree, child_id)
    return total


def kill_general(tree: GeneralTree, general_id: str) -> GeneralTree:
    """Mark a general killed and drop subordinate major generals' loyalty to 0."""

    general = _general(tree, general_id)
    general["status"] = "killed"
    for child_id in _descendants(tree, general_id):
        child = _general(tree, child_id)
        if child.get("role") == "major_general" and not child.get("loyalty_exempt", False) and not _is_absolute_loyal(child):
            child["loyalty"] = 0
    return tree


def defect_general(tree: GeneralTree, general_id: str, new_faction: str) -> GeneralTree:
    """Move a general's whole branch to another faction.

    Every subordinate in the branch follows. Non-exempt generals in the branch
    are reset to loyalty 1, making the newly defected command unstable.
    """

    for branch_id in (general_id, *_descendants(tree, general_id)):
        general = _general(tree, branch_id)
        general["faction"] = new_faction
        if not general.get("loyalty_exempt", False) and not _is_absolute_loyal(general) and general.get("loyalty") is not None:
            general["loyalty"] = 1
    return tree


def add_trait(tree: GeneralTree, general_id: str, trait_id: str) -> GeneralTree:
    """Append a trait to a general if it is not already present."""

    general = _general(tree, general_id)
    general.setdefault("traits", [])
    if trait_id not in general["traits"]:
        general["traits"].append(trait_id)
    return tree


def add_skill(tree: GeneralTree, general_id: str, skill_id: str) -> GeneralTree:
    """Append a non-natural skill such as pontoon bridge or fortress builder."""

    general = _general(tree, general_id)
    general.setdefault("skills", [])
    if skill_id not in general["skills"]:
        general["skills"].append(skill_id)
    return tree


def _generals(tree: GeneralTree) -> Dict[str, Dict[str, Any]]:
    generals = tree.setdefault("generals", {})
    if not isinstance(generals, dict):
        raise ValueError("tree['generals'] must be an object keyed by general id")
    return generals


def _general(tree: GeneralTree, general_id: str) -> Dict[str, Any]:
    generals = _generals(tree)
    if general_id not in generals:
        raise ValueError(f"unknown general {general_id!r}")
    return generals[general_id]


def _subordinates(general: Dict[str, Any]) -> list[str]:
    general.setdefault("subordinates", [])
    return general["subordinates"]


def _descendants(tree: GeneralTree, general_id: str) -> list[str]:
    result = []
    for child_id in _subordinates(_general(tree, general_id)):
        result.append(child_id)
        result.extend(_descendants(tree, child_id))
    return result


def _set_loyalty(general: Dict[str, Any], value: Any) -> None:
    if _is_absolute_loyal(general):
        general["loyalty"] = 10
        return
    general["loyalty"] = max(0.0, min(10.0, float(value)))


def _is_absolute_loyal(general: Mapping[str, Any]) -> bool:
    return bool(general.get("absolute_loyalty", False))


def _clean_units(units: UnitBlock) -> Dict[str, float]:
    clean = {unit: 0.0 for unit in DEFAULT_FORCE_POINTS}
    for unit, raw_count in units.items():
        if unit not in clean:
            raise ValueError(f"unknown unit {unit!r}; expected one of {sorted(clean)}")
        count = float(raw_count)
        if count < 0:
            raise ValueError(f"unit count cannot be negative: {unit}={raw_count}")
        clean[unit] += count
    return clean
