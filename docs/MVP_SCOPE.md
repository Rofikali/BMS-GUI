# MVP_SCOPE.md
# Ruthless MVP Boundary

The MVP is not the platform dream. The MVP is the smallest production-grade kernel that proves the dream is real.

---

# 1. MVP Goal

Prove this lifecycle end to end:

```text
Create Invoice
-> Validate Stock
-> Calculate Tax
-> Post Journal Entry
-> Persist Transaction
-> Write Audit Event
-> Generate Receipt/Report
```

If this lifecycle is correct, durable, auditable, and recoverable, the product has a real foundation.

---

# 2. Included

| Capability | Requirement |
|---|---|
| Billing | create invoice, payment status, refund skeleton |
| Inventory | stock in/out, stock adjustment, low-stock flag |
| Accounting | journal entries, ledgers, trial balance, basic P&L |
| Tax | configurable GST/tax rate, tax payable tracking |
| Audit | immutable action log with actor, timestamp, correlation id |
| Users/Auth | admin, cashier, accountant roles |
| Reporting | invoice list, stock report, ledger report, tax report |
| File Storage | append logs, snapshots, WAL, manifest, checksums |
| Backup | local backup/export and restore validation |
| UI | fast desktop workflow for billing, inventory, reports |

---

# 3. Explicitly Deferred

| Capability | Reason |
|---|---|
| Native plugin ABI | large safety surface; wait for stable core APIs |
| Marketplace | depends on mature plugin model |
| Cloud sync | requires conflict model and identity model |
| Microservices | premature operational cost |
| Assembly optimization | no proven hot path yet |
| Database storage | defer until measured product or scale need |
| Custom B-tree index | defer until measured query/indexing need |
| Advanced AI ops | not needed to prove core business value |

---

# 4. MVP Release Gates

The MVP cannot ship unless:

- every invoice creates accounting impact
- every inventory mutation creates movement history
- trial balance passes after test business flows
- closed periods block edits
- audit trail exists for business-critical actions
- backup restore is tested
- startup validates storage integrity
- append-only file checksums are validated
- WAL recovery rules are tested
- role permissions are enforced
- all non-negotiable invariants pass automated tests

---

# 5. Success Metrics

| Metric | Target |
|---|---|
| invoice creation latency | under 2 seconds in normal local use |
| accounting imbalance rate | zero accepted imbalances |
| backup restore success | 100% in release validation |
| stock accuracy after sale/refund | deterministic and tested |
| operator training time | under 1 day for core billing/inventory |
