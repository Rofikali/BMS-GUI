# ACCOUNTING_SPEC.md
# CA-Grade Accounting Contract

This document makes the accounting rules implementation-grade. `ACCOUNTING_RULES.md` remains the broader guide; this file is the v1 contract.

---

# 1. Core Equations

```text
Assets = Liabilities + Equity
Total Debits = Total Credits
Profit or Loss = Revenue - Expenses
```

These equations are runtime and test invariants.

---

# 2. Money Rules

- Store money as integer minor units, not floating point.
- Every monetary amount must include currency.
- Rounding must be deterministic and centralized.
- Tax rounding must be documented per jurisdiction.

---

# 3. Journal Entry Rules

Required fields:

| Field | Required |
|---|---|
| journal_id | yes |
| period_id | yes |
| timestamp | yes |
| actor_id | yes |
| source_module | yes |
| source_document_id | yes |
| correlation_id | yes |
| lines | yes |
| description | yes |

Validation:

- at least two lines
- total debit equals total credit
- all accounts exist and are active
- period is open
- source document is traceable
- posting is atomic

---

# 4. Chart Of Accounts Baseline

| Code Range | Type |
|---|---|
| 1000-1999 | Assets |
| 2000-2999 | Liabilities |
| 3000-3999 | Equity |
| 4000-4999 | Revenue |
| 5000-5999 | Expenses |

Required MVP accounts:

- Cash
- Bank
- Accounts Receivable
- Inventory
- GST/Input Tax Receivable if applicable
- GST/Output Tax Payable if applicable
- Accounts Payable
- Sales Revenue
- Cost of Goods Sold
- Inventory Adjustment Expense

---

# 5. Sales Posting

Cash sale:

```text
Dr Cash/Bank
    Cr Sales Revenue
    Cr Output Tax Payable
```

If inventory valuation is enabled:

```text
Dr Cost Of Goods Sold
    Cr Inventory
```

Credit sale:

```text
Dr Accounts Receivable
    Cr Sales Revenue
    Cr Output Tax Payable
```

---

# 6. Refund Posting

Refunds must use reversal or explicit contra entries. Posted sale journals are never edited.

Cash refund:

```text
Dr Sales Returns
Dr Output Tax Payable
    Cr Cash/Bank
```

Inventory return, if stock is returned:

```text
Dr Inventory
    Cr Cost Of Goods Sold
```

---

# 7. Inventory Valuation

MVP default: weighted average cost unless ADR says otherwise.

Rules:

- valuation method is company-level configuration
- method changes require period boundary approval
- every stock movement must carry quantity and value impact
- negative stock is blocked unless explicitly enabled by policy

---

# 8. Period Closing

Closed periods:

- reject direct edits
- allow reversal entries only in an open period
- preserve reports as originally produced
- require admin/accountant approval to reopen

---

# 9. Reconciliation

MVP reconciliation targets:

- cash/bank balance vs system cash/bank ledger
- stock quantity vs inventory ledger
- tax payable report vs tax ledger
- receivables list vs AR control account

