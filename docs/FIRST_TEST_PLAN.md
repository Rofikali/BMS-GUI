# FIRST_TEST_PLAN.md
# Initial Test Plan

The first tests should protect business correctness before UI polish.

---

# 1. Native Core Storage Tests

These tests run against the C core first. Python tests come after bindings exist.

Required tests:

- append JSONL record
- reject corrupt checksum
- preserve sequence ordering
- detect duplicate idempotency key
- write snapshot atomically
- detect pending WAL on startup
- recover committed transaction with missing snapshot

---

# 2. Accounting Tests

Required tests:

- reject journal where debit does not equal credit
- post valid cash sale journal
- post valid credit sale journal
- reject posting into closed period
- calculate trial balance from journal lines
- prevent mutation of posted journal
- calculate P&L basics from revenue and expense accounts

---

# 3. Inventory Tests

Required tests:

- create item
- add stock
- deduct stock for sale
- reject negative stock when policy is disabled
- create stock movement for every quantity change
- rebuild stock-on-hand from movement log

---

# 4. Billing Integration Tests

Required tests:

- create invoice with stock and cash payment
- invoice creates stock movement
- invoice creates balanced journal
- invoice creates audit record
- invoice publishes `billing.sale_completed.v1`
- repeated idempotency key does not duplicate invoice, stock, or journal
- refund references original invoice

---

# 5. Backup And Recovery Tests

Required tests:

- backup includes all source-of-truth files
- backup validation verifies checksums
- restore rebuilds snapshots
- restored trial balance passes
- restored stock-on-hand matches movement log

---

# 6. Release Gate

Before an MVP release candidate:

```text
storage tests
-> accounting tests
-> inventory tests
-> billing integration tests
-> backup/restore tests
-> UI smoke test
```

Any invariant failure blocks release.
