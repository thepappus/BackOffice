"""Conformance runner: executes every vector under vectors/ as a test.

This is the file that makes the vectors load-bearing rather than documentation.
Adding a YAML file adds a test; no Python change is needed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jpmarket.vectors import Vector, iter_vectors, run_nearai_vector

ALL_VECTORS = list(iter_vectors())
NEARAI_VECTORS = [v for v in ALL_VECTORS if v.module == "nearai"]


def test_vectors_exist():
    assert ALL_VECTORS, "no vectors found — check VECTORS_ROOT resolution"


@pytest.mark.parametrize("vec", ALL_VECTORS, ids=lambda v: v.id)
def test_vector_metadata_is_wellformed(vec: Vector):
    assert vec.id, f"{vec.path}: empty id"
    assert vec.description.strip(), f"{vec.id}: empty description"
    assert vec.provenance.source.strip(), (
        f"{vec.id}: provenance.source is empty. Every vector must say where its "
        "expected values come from — see vectors/SCHEMA.md"
    )


def test_vector_ids_are_unique():
    ids = [v.id for v in ALL_VECTORS]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate vector ids: {sorted(dupes)}"


def test_vector_id_matches_filename():
    for vec in ALL_VECTORS:
        # id is prefixed by module, filename is not; compare the tail.
        assert vec.id.endswith(vec.path.stem), (
            f"{vec.path.name}: id {vec.id!r} should end with the filename stem "
            f"{vec.path.stem!r} so a failing test names its own file"
        )


@pytest.mark.parametrize("vec", NEARAI_VECTORS, ids=lambda v: v.id)
def test_nearai_vector(vec: Vector):
    run = run_nearai_vector(vec)
    exp = vec.expected

    exp_marks = exp.get("marks", [])
    assert len(run.marks) == len(exp_marks), (
        f"{vec.id}: expected {len(exp_marks)} marks, got {len(run.marks)}: "
        f"{[(m.trade_date.isoformat(), m.side.value, m.amount_jpy) for m in run.marks]}"
    )

    for i, (got, want) in enumerate(zip(run.marks, exp_marks)):
        ctx = f"{vec.id} mark[{i}]"
        assert got.trade_date == want["date"], f"{ctx}: date"
        assert got.amount_jpy == want["amount_jpy"], f"{ctx}: amount_jpy"
        if "kind" in want:
            assert got.kind.value == want["kind"], f"{ctx}: kind"
        if "side" in want:
            assert got.side.value == want["side"], f"{ctx}: side"
        if "quantity" in want:
            assert got.quantity == want["quantity"], f"{ctx}: quantity"
        if "reference_price" in want:
            assert got.reference_price == Decimal(want["reference_price"]), (
                f"{ctx}: reference_price"
            )
        if "mark_price" in want:
            assert got.mark_price == Decimal(want["mark_price"]), f"{ctx}: mark_price"

    exp_closes = exp.get("closes", [])
    assert len(run.closes) == len(exp_closes), (
        f"{vec.id}: expected {len(exp_closes)} closes, got {len(run.closes)}"
    )

    for i, (got, want) in enumerate(zip(run.closes, exp_closes)):
        ctx = f"{vec.id} close[{i}]"
        assert got.close_date == want["date"], f"{ctx}: date"
        assert got.settlement_jpy == want["settlement_jpy"], f"{ctx}: settlement_jpy"
        assert got.realized_pnl_jpy == want["realized_pnl_jpy"], (
            f"{ctx}: realized_pnl_jpy"
        )
        if "side" in want:
            assert got.side.value == want["side"], f"{ctx}: side"
        if "quantity" in want:
            assert got.quantity == want["quantity"], f"{ctx}: quantity"
        if "open_trade_price" in want:
            assert got.open_trade_price == Decimal(want["open_trade_price"]), (
                f"{ctx}: open_trade_price"
            )
        if "book_price_at_close" in want:
            assert got.book_price_at_close == Decimal(want["book_price_at_close"]), (
                f"{ctx}: book_price_at_close — this is the 帳入値段 carry, the "
                "most common place an implementation diverges"
            )
        if "close_price" in want:
            assert got.close_price == Decimal(want["close_price"]), f"{ctx}: close_price"

    if "total_cash_jpy" in exp:
        assert run.total_cash_jpy == exp["total_cash_jpy"], f"{vec.id}: total_cash_jpy"
    if "total_realized_jpy" in exp:
        assert run.total_realized_jpy == exp["total_realized_jpy"], (
            f"{vec.id}: total_realized_jpy"
        )

    if exp.get("invariant_holds"):
        run.check_invariant()
