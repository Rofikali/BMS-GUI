# DOMAIN_CONTRACTS.md
# Module Ownership And Contracts

Each module owns its data, rules, APIs, and events. Other modules must use public contracts only.

---

# 1. Ownership Matrix

| Entity | Owner | Notes |
|---|---|---|
| Invoice | Billing | source of sale document truth |
| Payment | Billing | reconciled into accounting |
| Stock Quantity | Inventory | changed only through inventory service |
| Stock Movement | Inventory | immutable operational history |
| Journal Entry | Accounting | immutable after posting |
| Ledger Balance | Accounting | derived from posted entries |
| User | Auth | identity and role source |
| Audit Record | Audit | immutable trace history |
| Tax Rule | Taxation | effective-dated configuration |

---

# 2. Forbidden Coupling

Forbidden:

- UI writing storage directly
- Billing mutating ledger tables directly
- Inventory posting journals directly without accounting API
- Plugins mutating domain internals
- Reporting changing business state
- Analytics becoming source of truth

---

# 3. Required Service Contracts

## Billing

```text
Billing_CreateInvoice(request) -> InvoiceResult
Billing_ProcessRefund(request) -> RefundResult
Billing_GetInvoice(invoice_id) -> Invoice
```

Publishes:

- `billing.invoice_created.v1`
- `billing.sale_completed.v1`
- `billing.refund_processed.v1`

## Inventory

```text
Inventory_ReserveStock(request) -> ReservationResult
Inventory_CommitMovement(request) -> MovementResult
Inventory_AdjustStock(request) -> AdjustmentResult
```

Publishes:

- `inventory.stock_reserved.v1`
- `inventory.stock_moved.v1`
- `inventory.low_stock_detected.v1`

## Accounting

```text
Accounting_PostJournal(command) -> JournalResult
Accounting_GetTrialBalance(period) -> TrialBalance
Accounting_ClosePeriod(command) -> CloseResult
```

Publishes:

- `accounting.journal_posted.v1`
- `accounting.trial_balance_failed.v1`
- `accounting.period_closed.v1`

## Audit

```text
Audit_Record(event) -> AuditRecordId
Audit_Query(filter) -> AuditRecord[]
```

Publishes:

- `audit.record_created.v1`
- `audit.tamper_detected.v1`

---

# 4. Transaction Boundary

For MVP, the application service owns workflow orchestration. Domain modules validate and execute their own rules.

Critical sale transaction:

```text
Billing Application Service
-> Inventory reservation
-> Tax calculation
-> Accounting journal command
-> Durable persistence
-> Audit record
-> Event publication
```

Failure rule: if accounting cannot post, the sale must not complete.

---

# 5. Storage Boundary

All repositories are implemented by the file storage layer in MVP. A later database implementation must satisfy the same contracts.

Authoritative MVP storage contract: `FILE_STORAGE_SPEC.md`.
