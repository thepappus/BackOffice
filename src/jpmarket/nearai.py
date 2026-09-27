"""値洗い (nearai) — daily mark-to-market for futures.

Futures are marked to market every business day. Each position's gain or loss
against a reference price is paid or received in cash, and the position's
帳入値段 (choiri nedan, book price) is reset to the day's settlement price. The
position is, in accounting terms, closed at the old price and reopened at the new
one — which is why futures are sometimes called settled-to-market.

The reference price is the only thing that varies:

- **Open day** — the position's own trade price.
- **Carried** — the previous business day's settlement price.
- **Closed before expiry** — the previous reference, marked to the actual
  closing trade price rather than the settlement price.
- **Held to expiry** — the previous settlement, marked to the SQ
  (特別清算数値, tokubetsu seisan suchi).

In this implementation the reference price is not a special case at all: it is
simply `lot.book_price`, which equals the trade price on the open day and the
previous settlement thereafter. That is what makes the invariant below hold for
free.

**The invariant.** For any position, over any sequence of days:

    sum(daily mark amounts) + final settlement == (final price - trade price)
                                                  * quantity * multiplier * side

Daily marking changes *when* money moves, never how much. This property is
tested exhaustively in `tests/test_properties.py`, and it is the single strongest
check on the whole futures chain.

Options are deliberately absent from this module. They are not marked to market:
the premium settles once and the position keeps its original price until it is
closed, exercised or expires. See the roadmap in README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Sequence

from .calendar import is_business_day
from .money import price
from .positions import CloseResult, Lot, PositionLedger, Side, total_settlement
from .products import Series


class MarkKind(str, Enum):
    """Why a given mark used the reference price it did.

    Carried purely for explanation and reconciliation output — the arithmetic is
    identical in every case.
    """

    OPEN_DAY = "open_day"
    CARRIED = "carried"
    FINAL_SQ = "final_sq"


@dataclass(frozen=True, slots=True)
class MarkResult:
    """One lot's mark-to-market on one day."""

    trade_date: date
    series: Series
    lot_id: int
    side: Side
    quantity: int
    kind: MarkKind
    reference_price: Decimal
    mark_price: Decimal
    amount_jpy: int

    @property
    def points(self) -> Decimal:
        """Signed price move captured by this mark."""
        return (self.mark_price - self.reference_price) * self.side.sign


def mark_lot(
    lot: Lot,
    mark_price: Decimal,
    trade_date: date,
    kind: MarkKind | None = None,
) -> MarkResult:
    """Mark one lot to `mark_price`, referencing its current book price."""
    if lot.series.is_option:
        raise ValueError(
            f"{lot.series} is an option series: options are not marked to market. "
            "Option risk is reflected in the margin requirement instead."
        )
    spec = lot.series.spec
    mp = spec.validate_price(price(mark_price))

    if kind is None:
        kind = MarkKind.OPEN_DAY if lot.trade_date == trade_date else MarkKind.CARRIED

    points = (mp - lot.book_price) * lot.side.sign
    return MarkResult(
        trade_date=trade_date,
        series=lot.series,
        lot_id=lot.lot_id,
        side=lot.side,
        quantity=lot.quantity,
        kind=kind,
        reference_price=lot.book_price,
        mark_price=mp,
        amount_jpy=spec.move_to_yen(points, lot.quantity),
    )


def mark_to_market(
    ledger: PositionLedger,
    series: Series,
    settlement_price: Decimal | str,
    trade_date: date,
    *,
    require_business_day: bool = True,
) -> list[MarkResult]:
    """Run one business day's nearai over every open lot in a series.

    Lots opened today are marked from their trade price; carried lots from the
    previous settlement. Both happen in the same pass because both are just the
    lot's book price.

    Book prices are re-based afterwards, so calling this twice for the same day
    would double-count. The caller owns the daily schedule.
    """
    if require_business_day and not is_business_day(trade_date):
        raise ValueError(
            f"{trade_date.isoformat()} is not a business day; "
            "nearai runs on business days only "
            "(pass require_business_day=False to override for testing)"
        )

    lots = ledger.lots(series=series)
    if not lots:
        return []

    marks = [mark_lot(lot, price(settlement_price), trade_date) for lot in lots]
    ledger.set_book_price(series, price(settlement_price))
    return marks


def final_settlement(
    ledger: PositionLedger,
    series: Series,
    sq_price: Decimal | str,
    sq_date: date,
) -> list[CloseResult]:
    """Settle every open lot in a series at the SQ and remove the positions.

    The final step is one more mark, from the previous settlement price to the
    SQ, after which the position ceases to exist. There is nothing to carry
    forward, so this is a close rather than a mark: each result carries both the
    final day's cash (`settlement_jpy`) and the position's whole-life realised
    P&L measured from the original trade price (`realized_pnl_jpy`).

    The SQ is not the exchange's ordinary daily settlement price. It is
    calculated from the opening prices of the index constituents on SQ day and is
    not final until every constituent has opened, which is why the expiry batch
    cannot run on the normal end-of-day schedule.
    """
    if series.is_option:
        raise ValueError(
            f"{series} is an option series: use the option lifecycle for "
            "exercise and expiry at SQ, not futures final settlement"
        )

    results: list[CloseResult] = []
    for side in (Side.LONG, Side.SHORT):
        qty = ledger.quantity(series, side)
        if qty:
            results.extend(
                ledger.close(series, side, qty, price(sq_price), sq_date)
            )
    return results


# ---------------------------------------------------------------------------
# Lifecycle runner — the form the conformance vectors use
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenTrade:
    trade_date: date
    side: Side
    quantity: int
    trade_price: Decimal


@dataclass(frozen=True, slots=True)
class DailySettlement:
    trade_date: date
    settlement_price: Decimal


@dataclass(frozen=True, slots=True)
class CloseTrade:
    trade_date: date
    side: Side
    quantity: int
    close_price: Decimal


@dataclass(frozen=True, slots=True)
class FinalSettlement:
    trade_date: date
    sq_price: Decimal


Event = OpenTrade | DailySettlement | CloseTrade | FinalSettlement


@dataclass(frozen=True, slots=True)
class LifecycleRun:
    """Everything a sequence of events produced, in order."""

    series: Series
    marks: tuple[MarkResult, ...]
    closes: tuple[CloseResult, ...]

    @property
    def mark_total_jpy(self) -> int:
        return sum(m.amount_jpy for m in self.marks)

    @property
    def close_settlement_jpy(self) -> int:
        return total_settlement(self.closes)

    @property
    def total_cash_jpy(self) -> int:
        """All cash that moved, daily marks plus closing settlements."""
        return self.mark_total_jpy + self.close_settlement_jpy

    @property
    def total_realized_jpy(self) -> int:
        """Whole-life P&L measured from original trade prices."""
        return sum(c.realized_pnl_jpy for c in self.closes)

    def check_invariant(self) -> None:
        """Assert that daily marking moved money without changing the total.

        Only meaningful once every position has been closed; an open position's
        marks legitimately exceed its realised P&L, because the rest is still
        unrealised.
        """
        if self.total_cash_jpy != self.total_realized_jpy:
            raise AssertionError(
                "nearai invariant violated for "
                f"{self.series}: daily marks + closing settlement = "
                f"{self.total_cash_jpy} but realised P&L from trade price = "
                f"{self.total_realized_jpy}"
            )


def run_lifecycle(
    series: Series,
    events: Sequence[Event],
    *,
    ledger: PositionLedger | None = None,
    require_business_day: bool = True,
) -> LifecycleRun:
    """Apply a sequence of events to one series and collect the results."""
    led = ledger if ledger is not None else PositionLedger()
    marks: list[MarkResult] = []
    closes: list[CloseResult] = []

    for ev in events:
        if isinstance(ev, OpenTrade):
            led.open(series, ev.side, ev.quantity, ev.trade_price, ev.trade_date)
        elif isinstance(ev, DailySettlement):
            marks.extend(
                mark_to_market(
                    led,
                    series,
                    ev.settlement_price,
                    ev.trade_date,
                    require_business_day=require_business_day,
                )
            )
        elif isinstance(ev, CloseTrade):
            closes.extend(
                led.close(series, ev.side, ev.quantity, ev.close_price, ev.trade_date)
            )
        elif isinstance(ev, FinalSettlement):
            closes.extend(final_settlement(led, series, ev.sq_price, ev.trade_date))
        else:  # pragma: no cover - exhaustive over Event
            raise TypeError(f"unknown event {ev!r}")

    return LifecycleRun(series=series, marks=tuple(marks), closes=tuple(closes))
