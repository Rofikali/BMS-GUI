# PLATFORM_SPEC.md
# Canonical Source Of Truth

This document is the authoritative product and engineering contract for the platform. If another document conflicts with this one, this document wins until an ADR changes it.

---

# 1. Product Thesis

Build an offline-first business operating platform for retail and inventory-heavy small businesses that need billing, inventory, accounting, auditability, and operational intelligence in one trustworthy desktop system.

The platform is not a generic CRUD app. Its differentiator is financial correctness plus operational resilience.

---

# 2. Architectural Decision

The platform starts as a modular monolith.

Primary rules:

- keep one deployable application for v1
- isolate business capabilities by module
- communicate through APIs and events
- persist critical workflows transactionally
- design boundaries so future extraction is possible

Future microservices are an option, not a v1 requirement.

---

# 3. Canonical MVP

The first production-grade release must prove one complete business lifecycle:

```text
Invoice -> Inventory Movement -> Journal Entry -> Durable Commit -> Audit Event -> Report
```

MVP modules:

| Module | MVP Status |
|---|---|
| Billing | required |
| Inventory | required |
| Accounting | required |
| Audit | required |
| Users/Auth | required |
| Reporting | required |
| Backup/Export | required |
| File-Based Storage | required |
| Analytics | minimal |
| Plugins | deferred |
| Cloud Sync | deferred |
| Database Storage | deferred |

See `MVP_SCOPE.md`.

MVP storage is file-based by decision. See `FILE_STORAGE_SPEC.md` and `ADR/0002-file-based-storage-for-mvp.md`.

The critical storage and WAL path is implemented in the native C core first. Python and PySide6 sit above this boundary.

The native core is pure C11. C++ is not part of the core architecture.

---

# 4. Non-Negotiable Correctness

The system must never silently accept:

- unbalanced journal entries
- direct edits to posted ledger entries
- inventory mutations without movement records
- invoices without audit records
- closed-period financial mutations
- plugin or UI bypass of accounting validation
- failed durability checks on committed business transactions

See `INVARIANTS.md`.

---

# 5. Accounting Authority

Accounting is a core subsystem, not a report generator.

Every business event that affects money, tax, receivables, payables, stock value, or owner equity must be mapped to explicit accounting impact.

See `ACCOUNTING_SPEC.md`.

---

# 6. Event Authority

Events represent facts that already happened. Commands request work; events record completed facts.

All durable business events must be versioned and schema-owned by a module.

See `EVENT_SCHEMAS.md`.

---

# 7. Business Authority

The first buyer is a retail or inventory-heavy small business that needs reliable local operation, simple billing, trustworthy accounting output, stock control, and audit history.

See `BUSINESS_STRATEGY.md`.

---

# 8. Engineering Bias

Default decisions:

- prefer proven infrastructure for v1
- make domain invariants explicit before optimizing
- ship a correct kernel before a broad platform
- use file-based storage through strict repository contracts for MVP
- defer database storage until product or scale pressure proves the need
- use custom native systems only where they create measurable value
- keep plugin and cloud work behind stable internal contracts

---

# 9. Documentation Governance

Required doc roles:

| Document | Role |
|---|---|
| `VISION.md` | long-term mission |
| `PLATFORM_SPEC.md` | canonical source of truth |
| `MVP_SCOPE.md` | v1 build boundary |
| `DOMAIN_CONTRACTS.md` | module ownership and APIs |
| `ACCOUNTING_SPEC.md` | financial rules |
| `EVENT_SCHEMAS.md` | versioned events |
| `FILE_STORAGE_SPEC.md` | file-based storage contract |
| `INVARIANTS.md` | correctness gates |
| `IMPLEMENTATION_ROADMAP.md` | build order |
| `FIRST_TEST_PLAN.md` | first verification plan |
| `BUSINESS_STRATEGY.md` | market and operating model |
| `ADR/` | decision history |

Every major architectural change requires an ADR.
