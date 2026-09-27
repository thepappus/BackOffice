"""Conformance vector loader.

Vectors are the part of this project most likely to outlive the code. They are
plain YAML, one scenario per file, language-agnostic, and each carries a
`provenance` block saying where its expected values come from. That provenance
field is what makes a vector a reference rather than an assertion: someone
reconciling their own system against it can check whether the number is derived
from a published rule, from a published figure, or is merely illustrative.

Schema is documented in vectors/SCHEMA.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import yaml

from .nearai import (
    CloseTrade,
    DailySettlement,
    Event,
    FinalSettlement,
    LifecycleRun,
    OpenTrade,
    run_lifecycle,
)
from .positions import Side
from .products import Series

VECTORS_ROOT = Path(__file__).resolve().parents[2] / "vectors"

REQUIRED_KEYS = {"id", "module", "description", "provenance", "input", "expected"}
PROVENANCE_KINDS = {"published_rule", "published_data", "derived", "illustrative"}


class VectorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Provenance:
    kind: str
    source: str
    url: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in PROVENANCE_KINDS:
            raise VectorError(
                f"provenance.kind must be one of {sorted(PROVENANCE_KINDS)}, "
                f"got {self.kind!r}"
            )


@dataclass(frozen=True, slots=True)
class Vector:
    id: str
    module: str
    description: str
    effective_date: date | None
    provenance: Provenance
    input: dict[str, Any]
    expected: dict[str, Any]
    path: Path

    def __str__(self) -> str:
        return self.id


def _decimal(value: Any) -> Decimal:
    """Coerce a YAML scalar to Decimal.

    YAML will happily parse `38000.5` as a float, so numbers are re-read from
    their string form. Vector authors are encouraged to quote prices anyway.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def load_vector(path: Path) -> Vector:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise VectorError(f"{path}: top level must be a mapping")

    missing = REQUIRED_KEYS - raw.keys()
    if missing:
        raise VectorError(f"{path}: missing required keys {sorted(missing)}")

    prov = raw["provenance"]
    if not isinstance(prov, dict):
        raise VectorError(f"{path}: provenance must be a mapping")

    eff = raw.get("effective_date")
    if eff is not None and not isinstance(eff, date):
        raise VectorError(f"{path}: effective_date must be a YAML date, got {eff!r}")

    return Vector(
        id=raw["id"],
        module=raw["module"],
        description=raw["description"],
        effective_date=eff,
        provenance=Provenance(
            kind=prov.get("kind", "illustrative"),
            source=prov.get("source", ""),
            url=prov.get("url"),
            note=prov.get("note"),
        ),
        input=raw["input"],
        expected=raw["expected"],
        path=path,
    )


def iter_vectors(module: str | None = None, root: Path | None = None) -> Iterator[Vector]:
    base = root or VECTORS_ROOT
    for path in sorted(base.rglob("*.yaml")):
        vec = load_vector(path)
        if module is None or vec.module == module:
            yield vec


# ---------------------------------------------------------------------------
# Event decoding
# ---------------------------------------------------------------------------


def _series_from(spec: dict[str, Any]) -> Series:
    if "strike" in spec or "option_type" in spec:
        return Series.option(
            product=spec["product"],
            contract_month=spec["contract_month"],
            strike=str(spec["strike"]),
            option_type=spec["option_type"],
        )
    return Series.futures(
        product=spec["product"], contract_month=spec["contract_month"]
    )


def _event_from(raw: dict[str, Any]) -> Event:
    kind = raw["type"]
    d = raw["date"]
    if not isinstance(d, date):
        raise VectorError(f"event date must be a YAML date, got {d!r}")

    if kind == "open":
        return OpenTrade(
            trade_date=d,
            side=Side(raw["side"]),
            quantity=int(raw["quantity"]),
            trade_price=_decimal(raw["price"]),
        )
    if kind == "settlement":
        return DailySettlement(trade_date=d, settlement_price=_decimal(raw["price"]))
    if kind == "close":
        return CloseTrade(
            trade_date=d,
            side=Side(raw["side"]),
            quantity=int(raw["quantity"]),
            close_price=_decimal(raw["price"]),
        )
    if kind == "final_settlement":
        return FinalSettlement(trade_date=d, sq_price=_decimal(raw["price"]))
    raise VectorError(f"unknown event type {kind!r}")


def run_nearai_vector(vec: Vector) -> LifecycleRun:
    """Execute a `nearai` module vector."""
    if vec.module != "nearai":
        raise VectorError(f"{vec.id}: not a nearai vector (module={vec.module})")
    series = _series_from(vec.input["series"])
    events = [_event_from(e) for e in vec.input["events"]]
    return run_lifecycle(
        series,
        events,
        require_business_day=vec.input.get("require_business_day", True),
    )
