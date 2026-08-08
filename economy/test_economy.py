"""Rule-by-rule tests for the loan book and the city output rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economy import LoanBook, treaty_port_bonus, scaled_city_value, is_settlement_turn, is_river_port, city_level
from economy.loans import TIER_BLOCKED, TIER_PREFERRED, TIER_STANDARD


class TierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = LoanBook()

    def test_band_boundaries(self) -> None:
        for relation in range(-10, -3):
            self.assertEqual(self.book.tier_for_relation(relation), TIER_BLOCKED, relation)
        for relation in range(-3, 6):
            self.assertEqual(self.book.tier_for_relation(relation), TIER_STANDARD, relation)
        for relation in range(6, 11):
            self.assertEqual(self.book.tier_for_relation(relation), TIER_PREFERRED, relation)

    def test_five_is_standard_and_six_is_preferred(self) -> None:
        self.assertEqual(self.book.tier_for_relation(5), TIER_STANDARD)
        self.assertEqual(self.book.tier_for_relation(6), TIER_PREFERRED)

    def test_standard_terms(self) -> None:
        terms = self.book.terms_for_bank("hsbc", {"uk": 0})
        self.assertEqual(terms["term_turns"], 3)
        self.assertAlmostEqual(terms["interest_per_turn"], 0.05)
        self.assertEqual(terms["limit"], 30)

    def test_preferred_terms(self) -> None:
        terms = self.book.terms_for_bank("hsbc", {"uk": 9})
        self.assertEqual(terms["term_turns"], 6)
        self.assertAlmostEqual(terms["interest_per_turn"], 0.03)
        self.assertEqual(terms["limit"], 65)

    def test_blocked_bank_offers_no_terms(self) -> None:
        self.assertIsNone(self.book.terms_for_bank("hsbc", {"uk": -4}))

    def test_german_bank_is_neutral_and_fixed(self) -> None:
        for relation in (-10, 0, 10):
            terms = self.book.terms_for_bank("deutsch_asiatische", {"de": relation})
            self.assertEqual(terms["term_turns"], 3)
            self.assertAlmostEqual(terms["interest_per_turn"], 0.03)
            self.assertEqual(terms["limit"], 20)

    def test_soviet_union_has_no_bank(self) -> None:
        self.assertNotIn("su", {b.get("relations_key") for b in self.book.data["banks"]})
        rows = self.book.offers({"su": 10}, [], turn=1)
        soviet = [r for r in rows if r["power"] == "soviet_union"][0]
        self.assertFalse(soviet["can_borrow"])


class BorrowingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = LoanBook()
        self.loans: list = []

    def test_limit_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            self.book.borrow(self.loans, "hsbc", 31, {"uk": 0}, turn=1, next_loan_id=1)
        self.book.borrow(self.loans, "hsbc", 30, {"uk": 0}, turn=1, next_loan_id=1)
        self.assertEqual(len(self.loans), 1)

    def test_outstanding_debt_consumes_the_limit(self) -> None:
        self.book.borrow(self.loans, "hsbc", 20, {"uk": 0}, turn=1, next_loan_id=1)
        self.assertEqual(self.book.available_credit("hsbc", {"uk": 0}, self.loans), 10)
        with self.assertRaises(ValueError):
            self.book.borrow(self.loans, "hsbc", 11, {"uk": 0}, turn=1, next_loan_id=2)

    def test_cannot_borrow_from_a_hostile_power(self) -> None:
        with self.assertRaises(ValueError):
            self.book.borrow(self.loans, "yokohama_specie", 5, {"jp": -7}, turn=1, next_loan_id=1)

    def test_due_turn_follows_the_term(self) -> None:
        loan = self.book.borrow(self.loans, "hsbc", 10, {"uk": 9}, turn=4, next_loan_id=1)
        self.assertEqual(loan["due_turn"], 10)
        self.assertEqual(loan["term_turns"], 6)

    def test_non_positive_amount_rejected(self) -> None:
        for amount in (0, -5):
            with self.assertRaises(ValueError):
                self.book.borrow(self.loans, "hsbc", amount, {"uk": 0}, turn=1, next_loan_id=1)


class AccrualTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = LoanBook()
        self.loans: list = []

    def test_interest_applies_every_turn(self) -> None:
        # 匯豐 standard: limit 30, 5% a turn.
        self.book.borrow(self.loans, "hsbc", 30, {"uk": 0}, turn=1, next_loan_id=1)
        self.book.accrue_interest(self.loans)
        self.assertEqual(self.loans[0]["outstanding"], 32)  # 30 + round(1.5)
        self.book.accrue_interest(self.loans)
        self.assertEqual(self.loans[0]["outstanding"], 34)  # 32 + round(1.6)

    def test_preferred_rate_is_lower(self) -> None:
        # Same principal, preferred tier: 3% instead of 5%.
        self.book.borrow(self.loans, "hsbc", 30, {"uk": 9}, turn=1, next_loan_id=1)
        self.book.accrue_interest(self.loans)
        self.assertEqual(self.loans[0]["outstanding"], 31)  # 30 + round(0.9)

    def test_overdue_is_flagged_after_the_due_turn(self) -> None:
        self.book.borrow(self.loans, "hsbc", 10, {"uk": 0}, turn=1, next_loan_id=1)
        self.assertEqual(self.loans[0]["due_turn"], 4)
        self.assertEqual(self.book.mark_overdue(self.loans, 4), [])
        self.assertEqual(len(self.book.mark_overdue(self.loans, 5)), 1)
        self.assertTrue(self.loans[0]["overdue"])

    def test_relation_collapse_calls_the_loan_in(self) -> None:
        self.book.borrow(self.loans, "yokohama_specie", 20, {"jp": 3}, turn=1, next_loan_id=1)
        called = self.book.call_in_bank(self.loans, "yokohama_specie")
        self.assertEqual(len(called), 1)
        self.assertTrue(self.loans[0]["overdue"])
        self.assertTrue(self.loans[0]["called_in"])


class RepaymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = LoanBook()
        self.loans: list = []

    def test_oldest_loan_is_cleared_first(self) -> None:
        self.book.borrow(self.loans, "hsbc", 20, {"uk": 0}, turn=1, next_loan_id=1)
        self.book.borrow(self.loans, "citibank", 20, {"us": 0}, turn=3, next_loan_id=2)
        result = self.book.repay(self.loans, 20)
        self.assertEqual(result["paid"], 20)
        self.assertEqual(result["cleared"], ["L1"])
        self.assertEqual([loan["bank"] for loan in self.loans], ["citibank"])

    def test_partial_payment_leaves_the_remainder(self) -> None:
        self.book.borrow(self.loans, "hsbc", 20, {"uk": 0}, turn=1, next_loan_id=1)
        self.book.repay(self.loans, 8)
        self.assertEqual(self.loans[0]["outstanding"], 12)

    def test_overpayment_reports_the_unused_amount(self) -> None:
        self.book.borrow(self.loans, "hsbc", 10, {"uk": 0}, turn=1, next_loan_id=1)
        result = self.book.repay(self.loans, 25)
        self.assertEqual(result["paid"], 10)
        self.assertEqual(result["unused"], 15)
        self.assertEqual(self.loans, [])

    def test_overdue_only_payment_skips_current_loans(self) -> None:
        self.book.borrow(self.loans, "hsbc", 20, {"uk": 0}, turn=1, next_loan_id=1)
        self.book.borrow(self.loans, "citibank", 20, {"us": 0}, turn=1, next_loan_id=2)
        self.loans[1]["overdue"] = True
        result = self.book.repay(self.loans, 50, overdue_only=True)
        self.assertEqual(result["paid"], 20)
        self.assertEqual([loan["bank"] for loan in self.loans], ["hsbc"])

    def test_repaying_frees_the_credit_line(self) -> None:
        self.book.borrow(self.loans, "hsbc", 30, {"uk": 0}, turn=1, next_loan_id=1)
        self.assertEqual(self.book.available_credit("hsbc", {"uk": 0}, self.loans), 0)
        self.book.repay(self.loans, 30)
        self.assertEqual(self.book.available_credit("hsbc", {"uk": 0}, self.loans), 30)


class OutputTests(unittest.TestCase):
    def test_ports_pay_nothing(self) -> None:
        """港口已無任何經濟加成。"""
        self.assertEqual(treaty_port_bonus({"port": "river"}), {"cash": 0, "factory": 0})
        self.assertEqual(treaty_port_bonus({}), {"cash": 0, "factory": 0})

    def test_concession_pays_regardless_of_port(self) -> None:
        with_port = treaty_port_bonus({"concession": ["uk"], "port": "river"})
        without_port = treaty_port_bonus({"concession": ["uk"]})
        self.assertEqual(with_port, {"cash": 2, "factory": 2})
        self.assertEqual(with_port, without_port)

    def test_concession_powers_do_not_change_the_bonus(self) -> None:
        one = treaty_port_bonus({"concession": ["uk"]})
        four = treaty_port_bonus({"concession": ["uk", "us", "fr", "jp"]})
        self.assertEqual(one, four)

    def test_river_port_is_only_a_label(self) -> None:
        self.assertTrue(is_river_port({"port": "river"}))
        self.assertFalse(is_river_port({}))
        self.assertFalse(is_river_port({"port": "sea"}))  # 海港分類已移除

    def test_settlement_turns(self) -> None:
        self.assertEqual([t for t in range(1, 10) if is_settlement_turn(t)], [3, 6, 9])

    def test_output_comes_from_level(self) -> None:
        """1 級 cash 2 / factory 1，每升一級各 +1。"""
        expected = {1: (2, 1), 2: (3, 2), 3: (4, 3), 4: (5, 4), 5: (6, 5)}
        for level, (cash, factory) in expected.items():
            city = {"level": level}
            self.assertEqual(scaled_city_value(city, "cash"), cash, level)
            self.assertEqual(scaled_city_value(city, "factory"), factory, level)

    def test_level_is_clamped(self) -> None:
        self.assertEqual(city_level({"level": 0}), 1)
        self.assertEqual(city_level({"level": 9}), 5)
        self.assertEqual(city_level({}), 1)
        self.assertEqual(scaled_city_value({"level": 9}, "cash"), 6)

    def test_raw_cash_field_is_ignored(self) -> None:
        """產出只看等級，資料檔裡的 cash/factory 欄位不再參與計算。"""
        self.assertEqual(
            scaled_city_value({"level": 2, "cash": 14, "factory": 5}, "cash"),
            scaled_city_value({"level": 2}, "cash"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
