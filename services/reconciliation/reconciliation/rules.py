"""Deterministic, ordered matching rules. Pure functions: no DB, no network.

R1 voucher + amount            (exact)
R2 document + amount + date window
R3 unique amount inside the date window
R4 references proposed by AI, accepted only after deterministic verification:
   the reference must appear as a literal token(s) of the bank description, equal a deposit
   voucher/document, and the amount and a (wider) date window must still match.

A bank transaction is resolved by the first rule that yields any pair. If that bank has several
candidate deposits, or a deposit has several candidate banks, every pair is flagged ambiguous.
The AI can only add proposals to R4; it can never relax amount/date checks nor auto-match.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

RULE_ORDER = ("R1", "R2", "R3", "R4")


def norm_ref(value: str | None) -> str:
    """Canonical voucher form: upper-case alphanumerics without leading zeros."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper()).lstrip("0")


@dataclass(frozen=True)
class Bank:
    id: int
    date: date
    amount: Decimal
    description: str = ""
    document: str = ""
    voucher: str = ""


@dataclass(frozen=True)
class Deposit:
    id: int
    date: date
    amount: Decimal
    document: str = ""
    voucher: str = ""


@dataclass
class Proposal:
    bank_id: int
    deposit_id: int
    rule: str
    ambiguous: bool
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RuleConfig:
    window_days: int = 3
    ai_window_days: int = 30


Pair = tuple[Bank, Deposit, dict]
Extractor = Callable[[Bank], list[str]]


def days_apart(a: date, b: date) -> int:
    return abs((a - b).days)


def verified_refs(description: str, refs: list[str]) -> list[str]:
    """Keep only proposed refs that are literally present (as one or several adjacent tokens) in the text."""
    tokens = re.findall(r"[A-Z0-9]+", (description or "").upper())
    seen: set[str] = set()
    for i in range(len(tokens)):
        acc = ""
        for j in range(i, min(i + 6, len(tokens))):
            acc += tokens[j]
            seen.add(acc)
    out: list[str] = []
    for ref in refs or []:
        raw = re.sub(r"[^A-Z0-9]", "", str(ref).upper())
        if len(raw) >= 4 and raw in seen and norm_ref(raw):
            out.append(norm_ref(raw))
    return list(dict.fromkeys(out))


def _index(deposits: list[Deposit]) -> dict[Decimal, list[Deposit]]:
    idx: dict[Decimal, list[Deposit]] = defaultdict(list)
    for d in deposits:
        idx[d.amount].append(d)
    return idx


def _r1(banks, idx, cfg) -> list[Pair]:
    return [(b, d, {"voucher": b.voucher})
            for b in banks if b.voucher
            for d in idx.get(b.amount, []) if d.voucher and d.voucher == b.voucher]


def _r2(banks, idx, cfg) -> list[Pair]:
    pairs = []
    for b in banks:
        if not b.document:
            continue
        for d in idx.get(b.amount, []):
            gap = days_apart(b.date, d.date)
            if d.document == b.document and gap <= cfg.window_days:
                pairs.append((b, d, {"document": b.document, "date_diff_days": gap}))
    return pairs


def _r3(banks, idx, cfg) -> list[Pair]:
    pairs = []
    for b in banks:
        for d in idx.get(b.amount, []):
            gap = days_apart(b.date, d.date)
            if gap <= cfg.window_days:
                pairs.append((b, d, {"date_diff_days": gap}))
    return pairs


def _r4(banks, idx, cfg, extract: Extractor | None) -> list[Pair]:
    if extract is None:
        return []
    pairs: dict[tuple[int, int], Pair] = {}
    for b in banks:
        if not b.description:
            continue
        refs = verified_refs(b.description, extract(b))
        for ref in refs:
            for d in idx.get(b.amount, []):
                gap = days_apart(b.date, d.date)
                if gap > cfg.ai_window_days:
                    continue
                if ref in (norm_ref(d.voucher), norm_ref(d.document)):
                    pairs.setdefault((b.id, d.id), (b, d, {"ai_reference": ref, "date_diff_days": gap,
                                                           "source": "ai_verified"}))
    return list(pairs.values())


def _flag(rule: str, pairs: list[Pair]) -> list[Proposal]:
    bank_n = Counter(b.id for b, _, _ in pairs)
    dep_n = Counter(d.id for _, d, _ in pairs)
    return [Proposal(b.id, d.id, rule, bank_n[b.id] > 1 or dep_n[d.id] > 1, {**ev, "rule": rule})
            for b, d, ev in pairs]


def run_rules(banks: list[Bank], deposits: list[Deposit], cfg: RuleConfig | None = None,
              extract: Extractor | None = None, excluded: set[tuple[int, int]] | None = None) -> list[Proposal]:
    """`excluded` holds (bank_id, deposit_id) pairs a human already rejected; they are never proposed again."""
    cfg = cfg or RuleConfig()
    excluded = excluded or set()
    banks_left, deps_left = list(banks), list(deposits)
    out: list[Proposal] = []
    for rule in RULE_ORDER:
        if not banks_left or not deps_left:
            break
        idx = _index(deps_left)
        if rule == "R4":
            pairs = _r4(banks_left, idx, cfg, extract)
        else:
            pairs = {"R1": _r1, "R2": _r2, "R3": _r3}[rule](banks_left, idx, cfg)
        pairs = [p for p in pairs if (p[0].id, p[1].id) not in excluded]
        if not pairs:
            continue
        out.extend(_flag(rule, pairs))
        used_b = {b.id for b, _, _ in pairs}
        used_d = {d.id for _, d, _ in pairs}
        banks_left = [b for b in banks_left if b.id not in used_b]
        deps_left = [d for d in deps_left if d.id not in used_d]
    return out


def check_invariants(bank: Bank, deposit: Deposit, rule: str, cfg: RuleConfig) -> str | None:
    """Re-validate a stored candidate before approval. Returns an error message or None."""
    if bank.amount != deposit.amount:
        return "amounts differ"
    gap = days_apart(bank.date, deposit.date)
    if rule == "R1":
        return None if bank.voucher and bank.voucher == deposit.voucher else "voucher differs"
    if rule == "R2":
        if not (bank.document and bank.document == deposit.document):
            return "document differs"
        return None if gap <= cfg.window_days else "outside date window"
    if rule == "R3":
        return None if gap <= cfg.window_days else "outside date window"
    if rule == "R4":
        if gap > cfg.ai_window_days:
            return "outside AI date window"
        refs = verified_refs(bank.description, [norm_ref(deposit.voucher), norm_ref(deposit.document)])
        return None if refs else "reference not verifiable in bank description"
    return f"unknown rule {rule}"
