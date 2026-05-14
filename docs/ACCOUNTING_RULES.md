# ACCOUNTING_RULES.md
# INDUSTRY-GRADE ACCOUNTING ENGINE
## Accounting Rules, Financial Integrity & Ledger Architecture
### Principal Engineer + SRE + CA + MBA Perspective

Implementation-grade accounting contract: `ACCOUNTING_SPEC.md`.

---

# 1. ACCOUNTING SYSTEM OVERVIEW

The platform contains a:

> CA-Grade Double-Entry Accounting Engine.

Accounting is NOT:
- a reporting add-on,
- an afterthought,
- a side module.

Accounting is:
- a core foundational subsystem,
- a transactional integrity layer,
- a business truth engine.

---

# 2. ACCOUNTING PHILOSOPHY

---

## 2.1 CA PERSPECTIVE

Core Principle:

> Every business event must produce financial impact. 

Every:
- sale,
- purchase,
- refund,
- expense,
- adjustment,
- payment

must generate:
- journal entries,
- ledger impact,
- audit records,
- traceable accounting flows.

---

## 2.2 PRINCIPAL ENGINEER PERSPECTIVE

Accounting must remain:
- deterministic,
- auditable,
- immutable,
- transaction-safe,
- recoverable.

Core Principle:

> Financial correctness is more important than feature velocity. 

---

## 2.3 SRE PERSPECTIVE

Accounting must survive:
- crashes,
- partial writes,
- WAL replay,
- storage corruption,
- rollback recovery.

Financial state must NEVER:
- become inconsistent,
- lose committed transactions,
- silently corrupt.

---

## 2.4 MBA PERSPECTIVE

Accounting data should drive:
- profitability analysis,
- operational intelligence,
- decision-making,
- financial forecasting,
- business optimization.

---

# 3. CORE ACCOUNTING PRINCIPLES

---

# 3.1 DOUBLE-ENTRY ACCOUNTING

Every transaction requires:
minimum two entries.

Core Rule:

> Total Debit = Total Credit

---

## Example

Sale:

```text
Cash A/C              Dr   1000
    To Sales A/C           1000
```

---

# 3.2 ACCOUNTING EQUATION

Core accounting equation:

Assets = Liabilities + Equity

The system must NEVER violate:
this equation.

---

# 3.3 IMMUTABLE LEDGERS

Posted ledger entries:
must NEVER be modified directly.

Corrections require:
- reversal entries,
- adjustment entries,
- audit trails.

---

# 3.4 AUDITABILITY

Every accounting operation must generate:
- timestamps
- operator tracking
- transaction IDs
- correlation IDs
- before/after states

---

# 3.5 DETERMINISTIC ACCOUNTING

The same input must ALWAYS generate:
the same financial output.

No hidden mutations allowed.

---

# 4. ACCOUNT TYPES

---

# 4.1 ASSETS

Resources owned by business.

Examples:
- cash
- bank
- inventory
- receivables
- equipment

Increase:
```text
DEBIT
```

Decrease:
```text
CREDIT
```

---

# 4.2 LIABILITIES

Business obligations.

Examples:
- loans
- payables
- taxes payable

Increase:
```text
CREDIT
```

Decrease:
```text
DEBIT
```

---

# 4.3 EQUITY

Owner s residual interest.

Examples:
- capital
- retained earnings

Increase:
```text
CREDIT
```

Decrease:
```text
DEBIT
```

---

# 4.4 REVENUE

Business income.

Examples:
- sales
- service income

Increase:
```text
CREDIT
```

Decrease:
```text
DEBIT
```

---

# 4.5 EXPENSES

Business operational costs.

Examples:
- rent
- salary
- electricity

Increase:
```text
DEBIT
```

Decrease:
```text
CREDIT
```

---

# 5. CHART OF ACCOUNTS (COA)

## Purpose

Standardized financial account hierarchy.

---

## Example Structure

```text
1000 - Assets
    1100 - Cash
    1200 - Bank
    1300 - Inventory

2000 - Liabilities
    2100 - GST Payable
    2200 - Accounts Payable

3000 - Equity
    3100 - Owner Capital

4000 - Revenue
    4100 - Sales

5000 - Expenses
    5100 - Rent
    5200 - Salary
```

---

# 6. JOURNAL ENTRY RULES

---

# 6.1 MANDATORY FIELDS

Every journal entry must contain:

```text
entry_id
timestamp
operator_id
correlation_id
debit_accounts
credit_accounts
amount
description
```

---

# 6.2 VALIDATION RULES

Mandatory validations:

| Rule | Required |
|---|---|
| debit = credit | YES |
| valid account | YES |
| active account | YES |
| transaction id | YES |
| timestamp | YES |

---

# 6.3 NO PARTIAL JOURNALS

Journal posting must be:
atomic.

Either:
- entire journal posts,
or
- nothing posts.

---

# 7. LEDGER RULES

---

# 7.1 GENERAL LEDGER

Master accounting book.

Contains:
- all journal entries,
- balances,
- transaction references.

---

# 7.2 SUB-LEDGERS

Specialized ledgers:

```text
Accounts Receivable
Accounts Payable
Inventory Ledger
Tax Ledger
Cash Ledger
```

---

# 7.3 LEDGER IMMUTABILITY

Ledger history must NEVER:
- be silently edited,
- be overwritten,
- lose historical traceability.

---

# 8. TRIAL BALANCE RULES

Purpose:
validate accounting integrity.

---

# 8.1 CORE RULE

Total Debits = Total Credits

---

# 8.2 FAILURE CONDITION

If imbalance occurs:

```text
TRIAL_BALANCE_FAILED
```

must trigger:
- diagnostics
- audit alerts
- recovery checks

---

# 9. SALES ACCOUNTING RULES

---

# 9.1 CASH SALE

Example:

```text
Cash A/C              Dr
    To Sales A/C
```

---

# 9.2 CREDIT SALE

Example:

```text
Accounts Receivable Dr
    To Sales A/C
```

---

# 9.3 GST SALE

Example:

```text
Cash A/C              Dr
    To Sales A/C
    To GST Payable A/C
```

---

# 10. PURCHASE ACCOUNTING RULES

---

# 10.1 CASH PURCHASE

```text
Inventory A/C         Dr
    To Cash A/C
```

---

# 10.2 CREDIT PURCHASE

```text
Inventory A/C         Dr
    To Accounts Payable A/C
```

---

# 11. EXPENSE ACCOUNTING RULES

---

# 11.1 RENT EXPENSE

```text
Rent Expense A/C      Dr
    To Cash A/C
```

---

# 11.2 SALARY EXPENSE

```text
Salary Expense A/C    Dr
    To Cash A/C
```

---

# 12. INVENTORY ACCOUNTING RULES

Inventory must support:
- quantity tracking
- valuation tracking
- movement tracking

---

# 12.1 INVENTORY MOVEMENTS

Every inventory movement requires:
- stock update
- audit event
- accounting impact

---

# 12.2 INVENTORY VALUATION METHODS

Supported future methods:

```text
FIFO
LIFO
Weighted Average
```

---

# 12.3 INVENTORY SHRINKAGE

Losses require:

```text
Inventory Loss Expense Dr
    To Inventory A/C
```

---

# 13. REFUND ACCOUNTING RULES

Refunds must:
- reverse original revenue,
- restore inventory if applicable,
- preserve traceability.

---

## Example

```text
Sales Return A/C      Dr
    To Cash A/C
```

---

# 14. GST / TAXATION RULES

---

# 14.1 GST TRACKING

GST must support:
- input GST
- output GST
- reconciliation
- filing reports

---

# 14.2 GST PAYABLE

```text
Cash A/C              Dr
    To GST Payable A/C
```

---

# 14.3 TAX REPORTING

The system must generate:
- GST reports
- tax summaries
- reconciliation reports

---

# 15. ACCOUNTING TRANSACTION FLOW

## Full Financial Flow

```text
Business Action
    -> Validation
    -> Journal Creation
    -> Double Entry Validation
    -> WAL Append
    -> Ledger Posting
    -> Trial Balance Check
    -> Audit Record
    -> Analytics Update
```

---

# 16. ACCOUNTING EVENT FLOW

---

## Example: Sale

```text
SALE_COMPLETED
    -> Accounting Mapper
    -> Journal Entry
    -> Ledger Update
    -> TRIAL_BALANCE_CHECK
    -> AUDIT_EVENT_CREATED
```

---

# 17. ACCOUNTING RECOVERY RULES

Accounting must support:
- WAL replay
- crash recovery
- snapshot restore
- transaction recovery

---

# 17.1 WAL-FIRST GUARANTEE

Financial operations must NEVER:
commit before WAL append.

---

# 17.2 RECOVERY VALIDATION

After recovery:

mandatory validations:
- trial balance
- ledger integrity
- journal consistency
- checksum validation

---

# 18. ACCOUNTING AUDIT RULES

---

# 18.1 REQUIRED AUDIT DATA

Every financial operation requires:

```text
operator
timestamp
transaction_id
correlation_id
before_state
after_state
```

---

# 18.2 TAMPER DETECTION

Any attempt to:
- modify ledgers,
- bypass journals,
- delete accounting history

must trigger:

```text
AUDIT_TAMPERING_DETECTED
```

---

# 19. ACCOUNTING SECURITY RULES

---

# 19.1 RBAC REQUIREMENTS

Only authorized roles may:
- post journals
- close periods
- reverse entries
- generate reports

---

# 19.2 CRITICAL ROLES

```text
ACCOUNTANT
FINANCE_MANAGER
ADMIN
```

---

# 20. PERIOD CLOSING RULES

Financial periods support:
- monthly close
- yearly close
- audit freeze

---

# 20.1 CLOSED PERIOD RESTRICTIONS

Closed periods must NOT allow:
- silent modifications
- backdated mutations
- untracked edits

---

# 20.2 CORRECTION STRATEGY

Corrections require:
- reversal entries
- adjustment journals
- audit approval

---

# 21. ACCOUNTING REPORTING RULES

The system must support:

```text
Trial Balance
Balance Sheet
Profit & Loss
Cash Flow
GST Reports
Ledger Reports
Expense Reports
```

---

# 22. BALANCE SHEET RULES

The balance sheet must ALWAYS satisfy:

Assets = Liabilities + Equity

If violated:
system enters:
- diagnostics mode
- integrity validation workflow

---

# 23. PROFIT & LOSS RULES

P&L computes:

Revenue - Expenses = Net Profit or Loss

---

# 24. MBA-GRADE ANALYTICS RULES

Accounting data should support:
- profitability analysis
- margin analysis
- cash-flow forecasting
- expense optimization
- inventory ROI analysis

---

## Key KPIs

| KPI | Purpose |
|---|---|
| gross profit margin | profitability |
| net margin | efficiency |
| expense ratio | operational control |
| inventory turnover | stock efficiency |
| receivable aging | cash flow |

---

# 25. ACCOUNTING FAILURE CONDITIONS

Critical accounting failures:

```text
TRIAL_BALANCE_FAILED
LEDGER_CORRUPTION
JOURNAL_MISMATCH
WAL_FAILURE
AUDIT_TAMPERING_DETECTED
```

These require:
- diagnostics
- recovery workflows
- operator alerts

---

# 26. FUTURE ACCOUNTING EVOLUTION

Future capabilities:
- multi-company accounting
- multi-currency
- branch accounting
- IFRS support
- automated reconciliation
- AI anomaly detection

---

# 27. FINAL PRINCIPAL ENGINEER CONCLUSION

This accounting architecture establishes:

- CA-grade financial correctness,
- deterministic accounting behavior,
- operational survivability,
- auditability,
- long-term scalability.

Core accounting goals:
- integrity
- traceability
- recoverability
- immutability
- operational safety
- financial correctness

Ultimate Principle:

> Accounting is the financial nervous system of the platform and must remain deterministic, auditable, recoverable, and mathematically correct under all operational conditions.
