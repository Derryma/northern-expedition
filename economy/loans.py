"""Loan book for the Northern Expedition playtest.

Every rule here comes from the design brief:

* A loan's tier is decided by the borrower's relation with the bank's power.
  -10..-4 cannot borrow at all, -3..5 borrows on standard terms (3 turns, 5% a
  turn), 6..10 borrows on preferred terms (6 turns, 3% a turn).
* 德華銀行 is neutral: no relation, always 3 turns at 5%.
* 蘇聯 does not lend commercially and has no bank.
* Interest is added once at the start of every turn, to each outstanding loan.
  That accrued figure is the debt for the rest of the turn.
* Repayment always clears the oldest loan first.
* Available credit at a bank is its tier limit minus what the player still owes
  that bank, so an unpaid loan blocks new borrowing.
* If a loan is still outstanding after its due turn, the player stops choosing:
  cash on hand is seized at the start of that turn, and if that is not enough
  every following turn's income is seized too until the arrears clear.
* If relations collapse into the blocked band, that bank's loans all fall due at
  the start of the next turn.

The module owns no game state. It reads and writes the player payload dict that
the engine already keeps, under the "loans" key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DATA_PATH = Path(__file__).resolve().parent / "data" / "banks.json"

TIER_BLOCKED = "blocked"
TIER_STANDARD = "standard"
TIER_PREFERRED = "preferred"


def load_bank_data(path: Optional[Path] = None) -> Dict[str, Any]:
    with (path or DATA_PATH).open(encoding="utf-8") as handle:
        return json.load(handle)


class LoanBook:
    """Pure rules engine over a player's list of loans."""

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        self.data = data or load_bank_data()
        self.tiers = self.data["tiers"]
        self.banks = {bank["id"]: bank for bank in self.data["banks"]}

    # ---- tier and terms -------------------------------------------------

    def tier_for_relation(self, relation: int) -> str:
        for name in (TIER_BLOCKED, TIER_STANDARD, TIER_PREFERRED):
            tier = self.tiers[name]
            if tier["relation_min"] <= relation <= tier["relation_max"]:
                return name
        # Relations are clamped to the scale, so this only fires on bad data.
        raise ValueError(f"relation {relation} falls outside every tier")

    def tier_for_bank(self, bank_id: str, relations: Dict[str, int]) -> str:
        bank = self.banks[bank_id]
        if bank.get("neutral"):
            return TIER_STANDARD
        relation = int(relations.get(bank["relations_key"], 0))
        return self.tier_for_relation(relation)

    def terms_for_bank(self, bank_id: str, relations: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """Term length and rate, or None when the bank will not lend."""
        bank = self.banks[bank_id]
        tier = self.tier_for_bank(bank_id, relations)
        if tier == TIER_BLOCKED:
            return None
        if bank.get("fixed_terms"):
            terms = dict(bank["fixed_terms"])
        else:
            terms = {
                "term_turns": self.tiers[tier]["term_turns"],
                "interest_per_turn": self.tiers[tier]["interest_per_turn"],
            }
        terms["tier"] = tier
        terms["limit"] = int(bank["limits"].get(tier, 0))
        return terms

    # ---- credit availability -------------------------------------------

    @staticmethod
    def owed_to(loans: Iterable[Dict[str, Any]], bank_id: str) -> int:
        """Debt at one bank that counts against its credit line.

        A loan flagged `off_quota` was negotiated by a function card outside the
        bank's normal facility: still owed, but it does not block new borrowing.
        """
        return sum(
            int(loan["outstanding"])
            for loan in loans
            if loan["bank"] == bank_id and not loan.get("off_quota")
        )

    def available_credit(self, bank_id: str, relations: Dict[str, int], loans: List[Dict[str, Any]]) -> int:
        terms = self.terms_for_bank(bank_id, relations)
        if terms is None:
            return 0
        return max(0, terms["limit"] - self.owed_to(loans, bank_id))

    def offers(self, relations: Dict[str, int], loans: List[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
        """One row per bank, ready for the borrowing panel."""
        rows = []
        for bank in self.data["banks"]:
            bank_id = bank["id"]
            tier = self.tier_for_bank(bank_id, relations)
            terms = self.terms_for_bank(bank_id, relations)
            relation = None if bank.get("neutral") else int(relations.get(bank["relations_key"], 0))
            rows.append({
                "bank": bank_id,
                "name": bank["name"],
                "power": bank["power"],
                "relations_key": bank.get("relations_key"),
                "relation": relation,
                "tier": tier,
                "tier_label": self.tiers[tier]["label"] if tier == TIER_BLOCKED else self.tiers[tier]["label"],
                "limit": int(bank["limits"].get(tier, 0)) if terms else 0,
                "outstanding": self.owed_to(loans, bank_id),
                "available": self.available_credit(bank_id, relations, loans),
                "interest_per_turn": terms["interest_per_turn"] if terms else None,
                "term_turns": terms["term_turns"] if terms else None,
                "can_borrow": bool(terms) and self.available_credit(bank_id, relations, loans) > 0,
            })
        for blocked in self.data.get("no_commercial_lending", []):
            rows.append({
                "bank": None,
                "name": {"soviet_union": "蘇聯"}.get(blocked["power"], blocked["power"]),
                "power": blocked["power"],
                "relations_key": blocked.get("relations_key"),
                "relation": int(relations.get(blocked.get("relations_key"), 0)) if blocked.get("relations_key") else None,
                "tier": None,
                "tier_label": blocked["reason"],
                "limit": 0,
                "outstanding": 0,
                "available": 0,
                "interest_per_turn": None,
                "term_turns": None,
                "can_borrow": False,
            })
        return rows

    # ---- borrowing ------------------------------------------------------

    def borrow(
        self,
        loans: List[Dict[str, Any]],
        bank_id: str,
        amount: int,
        relations: Dict[str, int],
        turn: int,
        next_loan_id: int,
        *,
        source: str = "bank",
    ) -> Dict[str, Any]:
        if bank_id not in self.banks:
            raise ValueError(f"unknown bank {bank_id!r}")
        amount = int(amount)
        if amount <= 0:
            raise ValueError("借款金額必須大於 0")
        terms = self.terms_for_bank(bank_id, relations)
        if terms is None:
            raise ValueError(f"{self.banks[bank_id]['name']}因關係交惡不承作放款")
        available = self.available_credit(bank_id, relations, loans)
        if amount > available:
            raise ValueError(f"超過可用額度，{self.banks[bank_id]['name']}目前可借 {available}")
        loan = {
            "id": f"L{next_loan_id}",
            "bank": bank_id,
            "bank_name": self.banks[bank_id]["name"],
            "principal": amount,
            "outstanding": amount,
            "interest_per_turn": terms["interest_per_turn"],
            "term_turns": terms["term_turns"],
            "tier": terms["tier"],
            "taken_turn": turn,
            "due_turn": turn + terms["term_turns"],
            "overdue": False,
            "source": source,
        }
        loans.append(loan)
        return loan

    # ---- per-turn accrual ----------------------------------------------

    def accrue_interest(self, loans: List[Dict[str, Any]]) -> int:
        """Add one turn of interest to every loan. Returns the total added."""
        total = 0
        for loan in loans:
            interest = int(round(int(loan["outstanding"]) * float(loan["interest_per_turn"])))
            loan["outstanding"] = int(loan["outstanding"]) + interest
            total += interest
        return total

    @staticmethod
    def mark_overdue(loans: List[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
        newly = []
        for loan in loans:
            if not loan.get("overdue") and turn > int(loan["due_turn"]):
                loan["overdue"] = True
                newly.append(loan)
        return newly

    def call_in_bank(self, loans: List[Dict[str, Any]], bank_id: str) -> List[Dict[str, Any]]:
        """Relations collapsed: every loan from this bank falls due at once."""
        called = []
        for loan in loans:
            if loan["bank"] == bank_id and not loan.get("overdue"):
                loan["overdue"] = True
                loan["called_in"] = True
                called.append(loan)
        return called

    # ---- repayment ------------------------------------------------------

    @staticmethod
    def total_outstanding(loans: Iterable[Dict[str, Any]]) -> int:
        return sum(int(loan["outstanding"]) for loan in loans)

    @staticmethod
    def overdue_outstanding(loans: Iterable[Dict[str, Any]]) -> int:
        return sum(int(loan["outstanding"]) for loan in loans if loan.get("overdue"))

    @staticmethod
    def repay(loans: List[Dict[str, Any]], amount: int, *, overdue_only: bool = False) -> Dict[str, Any]:
        """Pay `amount` against the oldest loans first. Returns what was paid."""
        remaining = int(amount)
        paid = 0
        cleared = []
        # Oldest first: the turn it was taken, then the order it was recorded in.
        order = sorted(
            range(len(loans)),
            key=lambda i: (int(loans[i]["taken_turn"]), i),
        )
        for index in order:
            if remaining <= 0:
                break
            loan = loans[index]
            if overdue_only and not loan.get("overdue"):
                continue
            due = int(loan["outstanding"])
            if due <= 0:
                continue
            payment = min(due, remaining)
            loan["outstanding"] = due - payment
            remaining -= payment
            paid += payment
            if loan["outstanding"] == 0:
                cleared.append(loan["id"])
        loans[:] = [loan for loan in loans if int(loan["outstanding"]) > 0]
        return {"paid": paid, "cleared": cleared, "unused": remaining}
