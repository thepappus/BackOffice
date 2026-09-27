# Vector schema

One scenario per file. Plain YAML, no anchors, no includes — a vector should be
readable and reimplementable by someone working in another language who has never
seen this repository.

## Required keys

| Key | Meaning |
|---|---|
| `id` | Unique, kebab-case, stable. Never renamed once published. |
| `module` | Which calculation this exercises: `nearai`, `positions`, `options`, `margin`, `tax`. |
| `description` | One line, in English, saying what makes this case interesting. |
| `provenance` | Where the expected values come from. See below. |
| `input` | Everything the calculation needs. |
| `expected` | Everything it must produce. |

Optional: `effective_date` — the date whose rules apply. Required for any
calculation that has changed over time (margin method, settlement cycle).

## Provenance

This is the field that makes a vector a reference rather than an assertion. It
tells a reader how much weight the expected value carries.

```yaml
provenance:
  kind: published_rule        # published_rule | published_data | derived | illustrative
  source: "JSCC futures/options daily mark-to-market rules"
  url: "https://..."
  note: "Prices are illustrative; the reference-price selection rule is the point."
```

- **`published_rule`** — the behaviour is stated in a public rule or exchange
  document. The strongest kind.
- **`published_data`** — the expected number is recomputed from published figures
  (JSCC settlement prices, margin parameters, SQ values; JSDA daily tables).
  Verifiable end to end.
- **`derived`** — follows arithmetically from a published rule applied to inputs
  chosen here.
- **`illustrative`** — the *shape* is right and the arithmetic is internally
  consistent, but the inputs are invented. Useful for exercising a code path;
  carries no authority about real market values.

Be honest about `illustrative`. A vector that claims more provenance than it has
is worse than no vector.

## Prices

Quote every price as a string. YAML parses `38000.5` as a float, and while the
loader re-reads numbers from their string form, quoting makes the intent explicit
and survives other people's parsers.

## `nearai` module

```yaml
input:
  series:
    product: NK225           # code from jpmarket.products.REGISTRY
    contract_month: "2026-12"
  events:
    - { type: open,             date: 2026-06-01, side: long, quantity: 1, price: "38000" }
    - { type: settlement,       date: 2026-06-01, price: "38200" }
    - { type: settlement,       date: 2026-06-02, price: "37900" }
    - { type: close,            date: 2026-06-03, side: long, quantity: 1, price: "38500" }
    # or, for a position held to expiry:
    - { type: final_settlement, date: 2026-06-12, price: "38500" }

expected:
  marks:
    - { date: 2026-06-01, kind: open_day, reference_price: "38000", mark_price: "38200", amount_jpy: 200000 }
  closes:
    - { date: 2026-06-03, settlement_jpy: 600000, realized_pnl_jpy: 500000 }
  total_cash_jpy: 500000
  total_realized_jpy: 500000
  invariant_holds: true
```

`invariant_holds` should be `true` for any vector where every position ends
closed. Set it `false` only for a vector that deliberately ends with an open
position, where daily marks legitimately exceed realised P&L.

## Edge cases worth a vector

Value concentrates here, not in the happy path:

- Position opened and closed the same day (no mark ever applies)
- Position opened and carried, then closed mid-life
- Partial close, remainder still marking
- 両建て (ryodate) — long and short in the same series, closed in each order
- SQ with a late print (SQ not final until all constituents open)
- Option expiring exactly at the strike (zero intrinsic value)
- 移管 (ikan) arriving without acquisition cost
- Corporate action on a margin position
- Any rule transition date: the day before, the day of, the day after
