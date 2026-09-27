"""Position keeping: 新規 / 返済 (shinki / hensai) matching.

The central fact this module encodes is that **Japanese listed derivatives do not
net automatically**. Every order carries an open/close designation. A customer
holding one long contract who sells one contract as 新規 (shinki, open) ends up
holding one long and one short — 両建て (ryodate) — not a flat position. Only a
返済 (hensai, close) order reduces an existing position.

The second fact is that each lot carries **two prices**:

- `trade_price` — the original execution price. Realised P&L and tax are
  calculated against this, always.
- `book_price` — 帳入値段 (choiri nedan), reset to the settlement price by each
  day's mark-to-market. Settlement cash flows are calculated against this.

Futures need both because their P&L is realised daily in cash; conflating them is
how tax reporting silently goes wrong. Options carry a `book_price` equal to the
premium for their whole life, because they are never marked to market.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from enum import Enum
from itertools import count
from typing import Iterator, Literal, Optional, Sequence

from .money import price
from .products import Series


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        """+1 for long, -1 for short.

        A long gains when the price rises; a short gains when it falls.
        """
        return 1 if self is Side.LONG else -1

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self is Side.LONG else Side.LONG


CloseMethod = Literal["fifo", "lifo"]


@dataclass(frozen=True, slots=True)
class Lot:
    """An open position, or part of one.

    Lots are immutable; operations return new lots. `quantity` is always
    positive — direction lives in `side`.
    """

    lot_id: int
    series: Series
    side: Side
    quantity: int
    trade_price: Decimal
    book_price: Decimal
    trade_date: date

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"lot quantity must be positive, got {self.quantity}")

    def with_quantity(self, quantity: int) -> "Lot":
        return replace(self, quantity=quantity)

    def with_book_price(self, book_price: Decimal) -> "Lot":
        return replace(self, book_price=book_price)


@dataclass(frozen=True, slots=True)
class CloseResult:
    """The outcome of closing against one lot.

    Two amounts, deliberately separate:

    - `realized_pnl_jpy` — measured from `open_trade_price`. This is the number
      that goes to customer P&L and tax.
    - `settlement_jpy` — measured from `book_price_at_close`. This is the cash
      that moves on the closing day, because everything before it has already
      been settled by daily marks.

    For an option, or for a futures position closed on its open day, the two are
    equal because no mark-to-market has intervened.
    """

    lot_id: int
    series: Series
    side: Side
    quantity: int
    open_trade_price: Decimal
    book_price_at_close: Decimal
    close_price: Decimal
    close_date: date
    realized_pnl_jpy: int
    settlement_jpy: int


@dataclass
class PositionLedger:
    """Lots for one account, keyed by series.

    Long and short lots in the same series coexist (ryodate) and are held in
    separate queues, because a close must specify which side it is closing.
    """

    _lots: dict[tuple[Series, Side], list[Lot]] = field(default_factory=dict)
    _ids: Iterator[int] = field(default_factory=lambda: count(1))

    # -- queries ----------------------------------------------------------

    def lots(self, series: Optional[Series] = None, side: Optional[Side] = None) -> list[Lot]:
        out: list[Lot] = []
        for (s, sd), lots in self._lots.items():
            if series is not None and s != series:
                continue
            if side is not None and sd != side:
                continue
            out.extend(lots)
        return sorted(out, key=lambda lot: lot.lot_id)

    def quantity(self, series: Series, side: Side) -> int:
        return sum(lot.quantity for lot in self._lots.get((series, side), ()))

    def net_quantity(self, series: Series) -> int:
        """Signed net. Note this is *reporting* convenience only — it is not how
        positions are held, and a net of zero does not mean there is nothing to
        report. A ryodate position of one long and one short nets to zero while
        both legs remain open and both consume margin."""
        return self.quantity(series, Side.LONG) - self.quantity(series, Side.SHORT)

    def is_ryodate(self, series: Series) -> bool:
        return (
            self.quantity(series, Side.LONG) > 0
            and self.quantity(series, Side.SHORT) > 0
        )

    # -- 新規 (shinki) ----------------------------------------------------

    def open(
        self,
        series: Series,
        side: Side,
        quantity: int,
        trade_price: Decimal | str,
        trade_date: date,
    ) -> Lot:
        """Open a new position (新規).

        Never nets against an existing opposite-side position — that is the whole
        point of the open/close designation.
        """
        if quantity <= 0:
            raise ValueError("open quantity must be positive")
        p = series.spec.validate_price(price(trade_price))
        lot = Lot(
            lot_id=next(self._ids),
            series=series,
            side=side,
            quantity=quantity,
            trade_price=p,
            book_price=p,
            trade_date=trade_date,
        )
        self._lots.setdefault((series, side), []).append(lot)
        return lot

    # -- 返済 (hensai) ----------------------------------------------------

    def close(
        self,
        series: Series,
        side: Side,
        quantity: int,
        close_price: Decimal | str,
        close_date: date,
        method: CloseMethod = "fifo",
        lot_id: Optional[int] = None,
    ) -> list[CloseResult]:
        """Close an existing position (返済).

        `side` is the side being *closed*, not the side of the closing order. To
        close a long you sell, but you pass `Side.LONG`.

        `lot_id` closes a specific lot, which is what a customer designating a
        particular 建玉 does. Otherwise lots are consumed in `method` order.
        """
        if quantity <= 0:
            raise ValueError("close quantity must be positive")

        key = (series, side)
        available = self.quantity(series, side)
        if available < quantity:
            raise ValueError(
                f"cannot close {quantity} of {series} {side.value}: "
                f"only {available} open. Closing more than is open is not netting — "
                "it would need a separate 新規 order on the opposite side."
            )

        p = series.spec.validate_price(price(close_price))
        queue = self._lots[key]

        if lot_id is not None:
            chosen = [lot for lot in queue if lot.lot_id == lot_id]
            if not chosen:
                raise ValueError(f"lot {lot_id} is not open in {series} {side.value}")
            if chosen[0].quantity < quantity:
                raise ValueError(
                    f"lot {lot_id} holds {chosen[0].quantity}, cannot close {quantity}"
                )
            order = chosen
        else:
            order = list(queue) if method == "fifo" else list(reversed(queue))

        results: list[CloseResult] = []
        remaining = quantity

        for lot in order:
            if remaining == 0:
                break
            take = min(lot.quantity, remaining)
            remaining -= take

            pnl_points = (p - lot.trade_price) * side.sign
            settle_points = (p - lot.book_price) * side.sign

            results.append(
                CloseResult(
                    lot_id=lot.lot_id,
                    series=series,
                    side=side,
                    quantity=take,
                    open_trade_price=lot.trade_price,
                    book_price_at_close=lot.book_price,
                    close_price=p,
                    close_date=close_date,
                    realized_pnl_jpy=series.spec.move_to_yen(pnl_points, take),
                    settlement_jpy=series.spec.move_to_yen(settle_points, take),
                )
            )

            if take == lot.quantity:
                queue.remove(lot)
            else:
                queue[queue.index(lot)] = lot.with_quantity(lot.quantity - take)

        if not queue:
            del self._lots[key]

        return results

    # -- mark-to-market book price carry ---------------------------------

    def set_book_price(self, series: Series, book_price: Decimal | str) -> list[Lot]:
        """Reset 帳入値段 on every open lot in a series.

        Called by the nearai engine after each day's mark. Only futures lots
        should ever be re-based this way; options keep their premium as book
        price for life.
        """
        if series.is_option:
            raise ValueError(
                f"{series} is an option series: option book price stays at the "
                "premium for the life of the position, since options are not "
                "marked to market"
            )
        p = series.spec.validate_price(price(book_price))
        updated: list[Lot] = []
        for side in (Side.LONG, Side.SHORT):
            key = (series, side)
            if key not in self._lots:
                continue
            self._lots[key] = [lot.with_book_price(p) for lot in self._lots[key]]
            updated.extend(self._lots[key])
        return updated

    # -- reporting -------------------------------------------------------

    def open_interest_report(self) -> list[tuple[Series, Side, int]]:
        """Gross open positions by series and side.

        This is the shape reported to JSCC as 建玉申告 (tategyoku shinkoku):
        gross, by side, never netted, because JSCC needs to know both legs of a
        ryodate position to margin them.
        """
        rows = [
            (series, side, sum(lot.quantity for lot in lots))
            for (series, side), lots in self._lots.items()
            if lots
        ]
        return sorted(rows, key=lambda r: (str(r[0]), r[1].value))


def total_realized(results: Sequence[CloseResult]) -> int:
    return sum(r.realized_pnl_jpy for r in results)


def total_settlement(results: Sequence[CloseResult]) -> int:
    return sum(r.settlement_jpy for r in results)
