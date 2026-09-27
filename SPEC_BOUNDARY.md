# Specification boundary

This project deliberately implements **only publicly documented behaviour**.

## In scope

Pure, deterministic calculation. Given positions, prices, parameters and a date,
produce numbers. No I/O, no network, no message construction.

- Business day calendar and the day/night session trade-date rule
- Money and price primitives with per-product multipliers and explicit rounding
- Position keeping: 新規 / 返済 (shinki / hensai) matching, 両建て (ryodate), 帳入値段 (choiri nedan) carry
- 値洗い (nearai): daily mark-to-market for futures
- SQ (特別清算数値) final settlement
- Option lifecycle: premium, ITM/OTM determination, expiry, exercise
- VaR margin composition, **given** JSCC's published parameters as input
- 特定口座 (tokutei koza) average cost basis and withholding

## Out of scope — permanently

Anything requiring a member-only specification, or anything that talks to a
counterparty:

- JASDEC interface specifications, message layouts, or book-entry instructions
- JSCC clearing participant interface documents or connectivity
- JSDA reporting record layouts or the 報告公表システム feed
- HULFT or any other transport configuration
- Vendor-proprietary code tables (for example I-STAR trade codes)

These are distributed to members under agreement and cannot appear in a public
repository. Each institution builds its own adapters against its own copies.
The boundary is not a limitation to be worked around later; it is the reason
this project can exist at all.

## Out of scope — for now

- **分別管理 (bunbetsu kanri)** — the segregation calculation and 顧客分別金信託
  deposit. Publicly documented in outline, but the reference dates and deposit
  deadlines are operationally entangled. A subtly wrong public implementation of
  a calculation the FSA inspects is worse than no implementation.

## Certification

JASDEC certifies connections and JSCC certifies participant systems. That
certification attaches to a deployment at a named institution, not to a software
package. Nothing in this repository is certified, and no release of it can be.

## Warranty

None. See LICENSE. This is a reference for validating your own numbers, not a
book of record.
