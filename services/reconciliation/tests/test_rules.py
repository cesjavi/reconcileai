from datetime import date, timedelta
from decimal import Decimal

from reconciliation import Bank, Deposit, RuleConfig, check_invariants, run_rules, verified_refs

D0 = date(2025, 3, 10)
CFG = RuleConfig(window_days=3, ai_window_days=30)


def bank(i, amt="100.00", days=0, doc="", vch="", desc=""):
    return Bank(i, D0 + timedelta(days=days), Decimal(amt), desc, doc, vch)


def dep(i, amt="100.00", days=0, doc="", vch=""):
    return Deposit(i, D0 + timedelta(days=days), Decimal(amt), doc, vch)


def by_bank(ps):
    return {(p.bank_id, p.deposit_id): p for p in ps}


def test_r1_voucher_and_amount_ignores_dates():
    ps = run_rules([bank(1, vch="123")], [dep(10, vch="123", days=40)], CFG)
    assert [(p.rule, p.ambiguous) for p in ps] == [("R1", False)]


def test_r1_same_voucher_different_amount_is_not_a_match():
    assert run_rules([bank(1, "100.00", vch="123")], [dep(10, "100.01", vch="123")], CFG) == []


def test_r2_window_boundary_inclusive_and_exclusive():
    at_limit = run_rules([bank(1, doc="20123456786")], [dep(10, days=3, doc="20123456786")], CFG)
    beyond = run_rules([bank(1, doc="20123456786")], [dep(10, days=4, doc="20123456786")], CFG)
    assert at_limit[0].rule == "R2" and beyond == []


def test_r3_unique_amount_within_window_and_boundary():
    assert run_rules([bank(1)], [dep(10, days=-3)], CFG)[0].rule == "R3"
    assert run_rules([bank(1)], [dep(10, days=4)], CFG) == []


def test_equal_amounts_make_r3_ambiguous():
    ps = run_rules([bank(1)], [dep(10, days=1), dep(11, days=2)], CFG)
    assert len(ps) == 2 and all(p.ambiguous and p.rule == "R3" for p in ps)


def test_two_banks_one_deposit_ambiguous_on_both():
    ps = run_rules([bank(1), bank(2, days=1)], [dep(10)], CFG)
    assert len(ps) == 2 and all(p.ambiguous for p in ps)


def test_duplicate_voucher_deposits_are_ambiguous_in_r1():
    ps = run_rules([bank(1, vch="9")], [dep(10, vch="9"), dep(11, vch="9")], CFG)
    assert all(p.ambiguous and p.rule == "R1" for p in ps)


def test_earlier_rule_wins_and_reserves_the_deposit():
    banks = [bank(1, vch="55"), bank(2, days=1)]
    deps = [dep(10, vch="55"), dep(11, days=1)]
    got = by_bank(run_rules(banks, deps, CFG))
    assert got[(1, 10)].rule == "R1" and got[(2, 11)].rule == "R3"
    assert (2, 10) not in got


def test_ai_reference_verified_matches_as_r4():
    b = bank(1, days=20, desc="TRANSF REF 000777 CLIENTE")
    ps = run_rules([b], [dep(10, vch="777")], CFG, extract=lambda _b: ["000777"])
    assert [(p.rule, p.evidence["source"]) for p in ps] == [("R4", "ai_verified")]


def test_ai_hallucinated_reference_is_discarded():
    b = bank(1, days=2, desc="TRANSF CLIENTE SA")
    # model "invents" a ref that exists as a deposit voucher but is NOT in the description
    assert run_rules([b], [dep(10, "100.00", days=20, vch="999888")], CFG, extract=lambda _b: ["999888"]) == []


def test_ai_cannot_bypass_amount_or_window():
    b = bank(1, days=0, desc="PAGO REF 123456")
    wrong_amount = [dep(10, "100.50", vch="123456")]
    too_far = [dep(11, "100.00", days=31, vch="123456")]
    assert run_rules([b], wrong_amount, CFG, extract=lambda _b: ["123456"]) == []
    assert run_rules([b], too_far, CFG, extract=lambda _b: ["123456"]) == []


def test_ai_partial_token_does_not_verify():
    assert verified_refs("PAGO REF 0001234", ["123"]) == []
    assert verified_refs("FC A-0001-00012345", ["A000100012345"]) == ["A000100012345"]


def test_ai_not_called_for_banks_resolved_by_earlier_rules():
    calls = []
    run_rules([bank(1, vch="1" * 5, desc="x")], [dep(10, vch="1" * 5)], CFG, extract=lambda b: calls.append(b) or [])
    assert calls == []


def test_check_invariants_rejects_stale_candidates():
    b, d = bank(1, vch="5"), dep(10, vch="5")
    assert check_invariants(b, d, "R1", CFG) is None
    assert check_invariants(b, dep(10, "1.00", vch="5"), "R1", CFG) == "amounts differ"
    assert check_invariants(bank(1), dep(10, days=9), "R3", CFG) == "outside date window"
    assert check_invariants(bank(1, desc="nothing"), dep(10, vch="777"), "R4", CFG) is not None
