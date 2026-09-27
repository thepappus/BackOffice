# Position vectors

Empty for now. Position-keeping behaviour is currently asserted through the
`nearai` vectors, which exercise 新規/返済 matching, 両建て and partial closes as a
side effect of running a lifecycle, and through `tests/test_positions.py`.

A standalone `positions` vector module earns its place when there is a runner for
sequences that are *not* a mark-to-market lifecycle — specifically:

- 移管 (ikan) carry-in of a position with its acquisition cost and date, and the
  failure mode when cost basis is absent
- Close-method selection (FIFO, LIFO, specific 建玉 designation) across many lots
- 建玉申告 (tategyoku shinkoku) roll-up from customer lots to account-category
  gross positions, which is the shape reported to JSCC
- Corporate action adjustments to strike, contract size and cost basis

The first and last of those are better built alongside the tax module, since both
exist mainly to keep 特定口座 cost basis correct.
