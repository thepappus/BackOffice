# jpmarket-ref

An open reference implementation of **publicly documented** Japanese post-trade
calculations, with a conformance vector suite.

This is not a back-office system and does not try to become one. It computes
numbers — given positions, prices, parameters and a date — so that a firm running
I-STAR, a global platform, or something in between can check its own arithmetic
against an independent implementation of the public rules.

Read [SPEC_BOUNDARY.md](SPEC_BOUNDARY.md) first. It states what this project will
never implement, and why that boundary is the reason it can exist at all.

## Why this exists

Every Japanese broker implements the same public rules independently, and
reconciles against JSCC and JASDEC blind — with no shared, citable statement of
what the right answer is. The absence is not in the *connectivity* (vendors solve
that) but in the *calculation*: nobody publishes worked examples of
mark-to-market reference-price selection across an expiry, or of 特定口座 cost
basis surviving a transfer.

The vectors in this repository are an attempt at that shared statement. They may
end up mattering more than the code.

## What works today

| Module | Status |
|---|---|
| `rules` | Effective-dated rule resolution, with generated boundary tests |
| `calendar` | Business days, national holidays, day/night session trade-date rule |
| `money` / `products` | Decimal prices, integer yen, per-product multipliers and explicit rounding |
| `positions` | 新規/返済 matching, 両建て, dual trade-price/帳入値段 tracking |
| `nearai` | Daily mark-to-market, close before expiry, SQ final settlement |
| `vectors` | YAML conformance vectors with provenance, executed by the test suite |

Roadmap, in dependency order: **option lifecycle** (premium, ITM/OTM at SQ,
exercise and assignment allocation), then **VaR margin composition** given JSCC's
published parameters, then **特定口座 cost basis**. 分別管理 is deliberately
excluded — see SPEC_BOUNDARY.md.

## Install

```bash
pip install -e ".[dev]"
pytest
```

Python 3.10+. Runtime dependency: PyYAML. Tests additionally need pytest and
hypothesis.

## Two design decisions worth knowing

**Rules are temporal.** Every calculation is parameterised by the date it applies
to, because the correct answer changes when the rules change: SPAN before
6 November 2023 and VaR after, T+3 before 16 July 2019 and T+2 after. Rule
transitions live in one timeline module and `all_transition_dates()` generates
boundary tests, so a transition cannot be added without being tested on the day
before, the day of, and the day after. This was in the type signature from the
first commit; bolted on later it never works, and it is also what lets the
library restate historical periods.

**Positions carry two prices.** `trade_price` is the original execution price and
never moves; realised P&L and tax are always measured from it. `book_price` is the
帳入値段, re-based to the settlement price by each day's mark; settlement cash is
measured from it. Futures need both because their P&L is realised daily in cash.
Conflating them is how tax reporting goes quietly wrong, and it is the single
most common divergence between implementations.

## The invariant

For any futures position, over any price path of any length:

```
sum(daily mark amounts) + final settlement
    == (final price - trade price) * quantity * multiplier * side
```

Daily marking changes *when* money moves, never how much. This one property
validates reference-price selection, the 帳入値段 carry, sign handling and
rounding together, and it is tested against several hundred generated price paths
in `tests/test_properties.py`. If you are reimplementing any of this, test that
invariant before anything else.

## Vectors

```yaml
id: nearai-futures-carried-then-closed
module: nearai
provenance:
  kind: published_rule      # published_rule | published_data | derived | illustrative
  source: "Daily mark-to-market reference-price rule"
  url: https://...
```

`provenance.kind` is what makes a vector a reference rather than an assertion: it
tells a reader whether the expected number comes from a public rule, is
recomputed from published figures, follows arithmetically, or is merely
illustrative. Being honest about `illustrative` matters — a vector claiming more
authority than it has is worse than no vector.

Adding a YAML file adds a test; no Python change needed. Schema and the list of
edge cases worth covering are in [vectors/SCHEMA.md](vectors/SCHEMA.md).

## Contributing

Two rules beyond the usual:

1. **Never add anything derived from a member-only specification.** Not a record
   layout, not a code table, not a field name. If you know it because your
   employer is a JASDEC or JSCC participant, it does not go here.
2. **Every vector cites its provenance**, and `illustrative` is an honest answer.

Documentation is bilingual where it matters; Japanese terms appear in kanji with
romaji on first use, because the romaji is what people search for and the kanji is
what the rulebooks say.

## Licence

Apache-2.0. No warranty — see SPEC_BOUNDARY.md on why that matters here more than
usual.
