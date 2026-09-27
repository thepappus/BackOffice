# Option vectors — next module

Empty by design. The option lifecycle is the next module on the roadmap, and
vectors land with the code that satisfies them, not before.

When it arrives, these are the cases that carry the value:

- **Premium settlement** — paid in full up front, so there is a cash movement at
  trade time and none thereafter. Contrast with futures, where only margin moves.
- **ITM at SQ** — automatic exercise, settlement at intrinsic value, exercise fee,
  position removed. Both directions: a long receives, a short pays.
- **ATM at SQ** — intrinsic value exactly zero. The boundary case that separates
  a correct ITM/OTM test from an off-by-one comparison.
- **OTM at SQ** — expires worthless, no cash, no fee, realised loss equal to the
  full premium for a buyer and gain equal to the full premium for a seller.
- **Short ITM with insufficient cash** — the settlement obligation is computed and
  debited before surplus margin is released, so the account can go negative. This
  is the main operational risk on SQ day and the ordering must be explicit.
- **Assignment allocation** — for American-style equity options, JSCC assigns at
  the account level and the broker allocates across short customers by its
  documented method. Lottery and pro-rata are both legitimate and must be
  pluggable strategies, not a hard-coded choice.
- **Realised P&L from the original premium** — never from any interim price,
  because no mark-to-market ever intervened.

Note that a Nikkei 225 option series is identified by product, contract month,
strike **and** put/call. A 38,000 call cannot close a 39,000 call even though the
two offset economically — see `tests/test_positions.py::TestSeriesIdentity`.
