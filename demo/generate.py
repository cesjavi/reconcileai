"""Generate the synthetic demo dataset (fictional customers, no real bank data) and its expected results.

    python demo/generate.py

Outputs bank.csv, deposits.csv and expected.json. Deterministic (fixed seed). The expected results are
derived from how each case is built, NOT from running the engine, so tests compare engine vs. intent.
Expected values assume window_days=3, ai_window_days=30, auto_match_rules=R1 and the mock extractor.
"""
import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

random.seed(2026)
OUT = Path(__file__).parent
BASE = date(2025, 3, 3)
W = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
FIRST = ["MARIA", "JUAN", "LUCIA", "PEDRO", "ANA", "DIEGO", "SOFIA", "MARTIN", "VALERIA", "HUGO", "CARLA", "RAUL"]
LAST = ["GOMEZ", "PEREZ", "ROSSI", "LOPEZ", "DIAZ", "SOSA", "ACOSTA", "MEDINA", "RIOS", "VEGA", "PAZ", "LUNA"]


def cuit(n):
    while True:
        body = random.choice(["20", "27", "30"]) + f"{random.randint(10_000_000, 99_999_999)}"
        c = 11 - sum(int(a) * b for a, b in zip(body, W)) % 11
        c = 0 if c == 11 else c
        if c != 10:
            return body + str(c)


CUSTOMERS = [{"name": f"{FIRST[i]} {LAST[i]}", "doc": cuit(i)} for i in range(12)]
_k = [0]


def amount():
    _k[0] += 1
    return Decimal(_k[0]) * Decimal("113.37") + Decimal("1000.01")


def fmt_doc(d, i):
    return f"{d[:2]}-{d[2:10]}-{d[10]}" if i % 3 == 0 else d


def fmt_amt(a, i):
    if i % 7 == 0:  # es-AR style
        whole, cents = f"{a:.2f}".split(".")
        return f"{int(whole):,}".replace(",", ".") + "," + cents
    return f"{a:.2f}"


def fmt_date(d, i):
    return d.strftime("%d/%m/%Y") if i % 5 == 0 else d.isoformat()


bank, dep, exp_b, exp_d = [], [], {}, {}


def add_bank(d, a, desc, doc="", voucher=""):
    bid = f"B{len(bank) + 1:04d}"
    bank.append((bid, d, a, desc, doc, voucher))
    return bid


def add_dep(d, a, doc="", voucher="", desc="Acreditacion sistema"):
    did = f"D{len(dep) + 1:04d}"
    dep.append((did, d, a, desc, doc, voucher))
    return did


def rdate():
    return BASE + timedelta(days=random.randint(0, 60))


def cust():
    return random.choice(CUSTOMERS)


# A. R1: voucher + amount (auto MATCHED). Formatting differs between files; dates may differ a lot.
for n in range(40):
    c, d, a = cust(), rdate(), amount()
    v = f"A-0001-{10000 + n:08d}"
    bid = add_bank(d, a, f"TRANSF DE {c['name']} FC {v}", c["doc"] if n % 2 else "", v)
    did = add_dep(d + timedelta(days=random.randint(0, 10)), a, c["doc"], v.lower().replace("-", " ") if n % 4 == 0 else v)
    exp_b[bid] = {"status": "MATCHED", "rule": "R1", "deposits": [did]}
    exp_d[did] = {"status": "MATCHED"}

# B. R2: document + amount + date window (SUGGESTED). Every 4th case sits exactly on the window limit (3 days).
for n in range(20):
    c, d, a = cust(), rdate(), amount()
    gap = 3 if n % 4 == 0 else random.randint(0, 2)
    bid = add_bank(d, a, "TRANSFERENCIA RECIBIDA", c["doc"])
    did = add_dep(d + timedelta(days=gap * random.choice([1, -1])), a, c["doc"])
    exp_b[bid] = {"status": "SUGGESTED", "rule": "R2", "deposits": [did]}
    exp_d[did] = {"status": "SUGGESTED"}

# C. Same document and amount but 4 days apart (one day outside the window): no candidate.
for n in range(4):
    c, d, a = cust(), rdate(), amount()
    bid = add_bank(d, a, "TRANSFERENCIA RECIBIDA", c["doc"])
    did = add_dep(d + timedelta(days=4), a, c["doc"])
    exp_b[bid] = {"status": "UNMATCHED", "rule": None, "deposits": []}
    exp_d[did] = {"status": "UNMATCHED"}

# D. R3: unique amount inside the window, no voucher or document on the bank side (SUGGESTED).
for n in range(15):
    d, a = rdate(), amount()
    gap = 3 if n % 5 == 0 else random.randint(0, 2)
    bid = add_bank(d, a, "DEPOSITO VENTANILLA")
    did = add_dep(d + timedelta(days=gap), a, cust()["doc"] if n % 2 else "")
    exp_b[bid] = {"status": "SUGGESTED", "rule": "R3", "deposits": [did]}
    exp_d[did] = {"status": "SUGGESTED"}

# E. Ambiguous: one bank movement, two deposits with the same amount inside the window.
for n in range(4):
    d, a = rdate(), amount()
    bid = add_bank(d, a, "DEPOSITO VENTANILLA")
    d1, d2 = add_dep(d + timedelta(days=1), a, cust()["doc"]), add_dep(d + timedelta(days=2), a, cust()["doc"])
    exp_b[bid] = {"status": "AMBIGUOUS", "rule": "R3", "deposits": [d1, d2]}
    exp_d[d1] = exp_d[d2] = {"status": "AMBIGUOUS"}

# F. Ambiguous: two bank movements compete for one deposit.
for n in range(3):
    d, a = rdate(), amount()
    b1, b2 = add_bank(d, a, "DEPOSITO VENTANILLA"), add_bank(d + timedelta(days=1), a, "DEPOSITO VENTANILLA")
    did = add_dep(d, a, "")
    exp_b[b1] = {"status": "AMBIGUOUS", "rule": "R3", "deposits": [did]}
    exp_b[b2] = {"status": "AMBIGUOUS", "rule": "R3", "deposits": [did]}
    exp_d[did] = {"status": "AMBIGUOUS"}

# G. R4: reference only in the free-text description, 10-25 days apart (needs the extractor; SUGGESTED, never auto).
for n in range(6):
    c, d, a = cust(), rdate(), amount()
    v = 2000 + n
    desc = f"TRANSF REF {v:07d} CLIENTE" if n % 2 == 0 else f"PAGO FC A-0002-{v:08d} DE {c['name']}"
    voucher_dep = str(v) if n % 2 == 0 else f"A-0002-{v:08d}"
    bid = add_bank(d, a, desc)
    did = add_dep(d + timedelta(days=random.randint(10, 25)), a, c["doc"], voucher_dep)
    exp_b[bid] = {"status": "SUGGESTED", "rule": "R4", "deposits": [did]}
    exp_d[did] = {"status": "SUGGESTED"}

# G2. A reference in the text that matches no deposit: stays unmatched.
for n in range(2):
    bid = add_bank(rdate(), amount(), f"TRANSF REF {555000 + n} CLIENTE")
    exp_b[bid] = {"status": "UNMATCHED", "rule": None, "deposits": []}

# H. Same voucher, amounts differ by 0.01 and dates far apart: not a match.
for n in range(4):
    d, a = rdate(), amount()
    v = f"A-0003-{n + 1:08d}"
    bid = add_bank(d, a, "TRANSFERENCIA RECIBIDA", "", v)
    did = add_dep(d + timedelta(days=40), a + Decimal("0.01"), "", v)
    exp_b[bid] = {"status": "UNMATCHED", "rule": None, "deposits": []}
    exp_d[did] = {"status": "UNMATCHED"}

# I. Bank-only and J. deposit-only movements.
for n in range(8):
    bid = add_bank(rdate(), amount(), "COMISION MANTENIMIENTO")
    exp_b[bid] = {"status": "UNMATCHED", "rule": None, "deposits": []}
for n in range(8):
    did = add_dep(rdate(), amount(), cust()["doc"])
    exp_d[did] = {"status": "UNMATCHED"}


def write(name, rows, desc_col):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "amount", "description", "document", "voucher"])
        for i, (rid, d, a, desc, doc, v) in enumerate(rows):
            w.writerow([rid, fmt_date(d, i), fmt_amt(a, i), desc, fmt_doc(doc, i) if doc else "", v])
        if name == "bank.csv":  # one exact duplicate line: must be reported, not imported twice
            rid, d, a, desc, doc, v = rows[0]
            w.writerow([rid, fmt_date(d, 0), fmt_amt(a, 0), desc, fmt_doc(doc, 0) if doc else "", v])


write("bank.csv", bank, 3)
write("deposits.csv", dep, 3)


def counts(m):
    out = {}
    for v in m.values():
        out[v["status"]] = out.get(v["status"], 0) + 1
    return out


expected = {
    "params": {"window_days": 3, "ai_window_days": 30, "auto_match_rules": "R1", "extractor": "mock"},
    "rows": {"bank_lines": len(bank) + 1, "bank_unique": len(bank), "deposits": len(dep), "duplicates_in_file": 1},
    "bank": exp_b, "deposits": exp_d,
    "bank_status_counts": counts(exp_b), "deposit_status_counts": counts(exp_d),
}
(OUT / "expected.json").write_text(json.dumps(expected, indent=1), encoding="utf-8")
print(f"bank={len(bank)} (+1 duplicate line) deposits={len(dep)}", expected["bank_status_counts"], expected["deposit_status_counts"])
