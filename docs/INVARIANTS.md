# INVARIANTS.md
# Non-Negotiable System Invariants

These are mandatory correctness gates. They should exist as tests, runtime guards, and release checks.

---

# 1. Accounting Invariants

- Total debits must equal total credits for every posted journal.
- Posted journals are immutable.
- Corrections use reversal or adjustment entries.
- Closed periods reject direct financial mutations.
- Every financial document has a source document id and correlation id.
- Trial balance failure blocks release and triggers diagnostics.

---

# 2. Inventory Invariants

- Every quantity change creates a stock movement.
- Every stock movement has actor, timestamp, reason, and source document.
- Negative stock is blocked unless company policy explicitly enables it.
- Inventory valuation changes require period-boundary approval.
- Sale completion cannot skip inventory validation.

---

# 3. Billing Invariants

- A completed invoice cannot be silently deleted.
- A completed sale must create accounting impact.
- Refunds must reference the original invoice.
- Tax calculations must be reproducible.
- Receipt totals must equal invoice totals.

---

# 4. Audit Invariants

- Critical business actions create audit records.
- Audit records are append-only.
- Audit records include actor, timestamp, action, target, and correlation id.
- Tamper detection failure enters protected mode.

---

# 5. Security Invariants

- UI permissions are not security boundaries; service APIs enforce RBAC.
- Admin-only actions require explicit role checks.
- Passwords are never stored in plaintext.
- Sessions expire and are auditable.
- Plugins cannot bypass service APIs.

---

# 6. Release Blocking Conditions

Any of these blocks release:

- unbalanced accounting entry accepted
- data restore fails
- invoice can complete without journal entry
- inventory can mutate without movement record
- closed-period edit succeeds
- audit tamper check fails silently
- critical event schema test fails

---

# 7. File Storage Invariants

- Append-only source-of-truth records are never edited in place.
- Every append-only record has a valid checksum.
- Every critical workflow writes WAL before domain records.
- Snapshot files are rebuildable from append-only records.
- Corrupt source-of-truth files force protected read-only mode.
- Domain modules never open storage files directly.
