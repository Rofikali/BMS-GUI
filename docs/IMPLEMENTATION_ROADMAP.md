# IMPLEMENTATION_ROADMAP.md
# First Build Roadmap

This roadmap turns the docs into implementation order. The goal is one correct vertical slice before broad feature work.

---

# 1. Engineering Constitution

This project is native-core-first and C-only for the core.

Rules:

- core code is ISO C11, not C++
- no C++ runtime, STL, exceptions, templates, or name mangling in the core
- public APIs live under `core/include/bms`
- implementation lives under `core/src`
- Python/PySide6 never bypasses the C durability path
- Assembly is allowed only after profiling proves a narrow hot path

---

# 2. Architecture Used

Primary architecture:

- modular monolith
- native C core
- Python application orchestration
- PySide6 UI
- file-based append-only persistence

Internal architecture patterns:

| Pattern | Where Used | Why |
|---|---|---|
| Layered Architecture | UI -> Python services -> C core -> files | keeps boundaries understandable |
| Ports/Adapters | repositories and future bindings | allows file storage now, DB later |
| Repository Pattern | storage access | prevents domain modules opening files directly |
| Command Pattern | business workflows | supports validation, WAL, rollback/replay |
| Append-Only Log | journals, audit, events, stock movements | preserves financial and operational history |
| Write-Ahead Log | critical transactions | crash recovery and durability |
| Snapshot Read Model | stock-on-hand, balances, indexes | fast reads from rebuildable state |
| Facade Pattern | C API and Python service API | stable boundary for UI/bindings |
| Observer/Event Pattern | durable business events | loose coupling and future extraction |

---

# 3. DSA Choices

Use boring, predictable data structures first.

| Need | MVP DSA | Later Upgrade |
|---|---|---|
| append durable records | append-only file / log | segmented log |
| scan records | linear scan | indexed scan |
| prevent duplicate idempotency key | linear scan for MVP | hash index or persisted idempotency index |
| current stock/balances | snapshot map encoded as JSON | B-tree or embedded DB index |
| event dispatch | in-memory queue | ring buffer or durable queue |
| metrics counters | fixed struct counters | registry/hash table |
| manifest lookup | small JSON file | parsed in-memory map |
| reporting | snapshot + log scan | materialized read models |

Principle:

- correctness first
- measure before introducing complex indexing
- keep append-only truth separate from derived read models

---

# 4. Observability Strategy

The C core owns low-level observability for durability-sensitive paths.

Required MVP observability:

- structured JSONL logs
- counters for storage/WAL operations
- correlation id propagation
- checksum failure logs
- WAL recovery logs
- protected-mode entry logs

Initial C observability API:

```text
bms_logger_init
bms_logger_write
bms_counter_init
bms_counter_inc
bms_counter_to_json
```

Metrics to add as the core grows:

| Metric | Reason |
|---|---|
| storage.records_appended | write throughput |
| storage.checksum_failures | corruption detection |
| wal.pending_appended | transaction intent visibility |
| wal.committed_appended | commit visibility |
| wal.recovery_runs | startup recovery health |
| snapshot.rebuild_count | read-model health |
| accounting.journal_rejected | financial guardrail |

---

# 5. Phase 0: Repository Skeleton

Create:

```text
core/
  include/
    bms/
  src/
    observability/
    storage/
    wal/
bindings/
  python/
src/
  bms/
    app/
    domain/
      accounting/
      billing/
      inventory/
      audit/
      users/
    storage/
      file_store/
    services/
    ui/
tests/
  core/
  unit/
  integration/
  fixtures/
data.example/
```

Add:

- Python package setup
- test runner
- formatting/linting baseline
- sample config
- empty data directory generator

---

# 6. Phase 1: Native C File Storage Kernel

The durability path belongs in the C core. Python may orchestrate it later, but Python does not own the critical persistence guarantees.

Build:

- data directory initializer
- manifest loader/writer
- structured logger
- basic metrics counters
- append-only JSONL writer
- checksum helper
- atomic snapshot writer
- WAL append/commit/recovery skeleton
- C API headers under `core/include/bms`
- C tests under `tests/core`

Acceptance:

- can append and read records
- checksum failure is detected
- snapshot write is atomic
- pending WAL is detected on startup
- duplicate idempotency keys are rejected
- structured logs can be written
- counters can be emitted as JSON
- C tests pass through CTest

---

# 7. Phase 2: Accounting Kernel

Build:

- chart of accounts model
- journal entry model
- journal posting service
- ledger balance read model
- trial balance calculation
- period open/close guard

Acceptance:

- unbalanced journal is rejected
- balanced journal is persisted
- posted journal cannot be edited
- trial balance passes after sample sale

---

# 8. Phase 3: Inventory Kernel

Build:

- item model
- stock movement model
- stock-on-hand snapshot
- stock adjustment service
- stock reservation/commit skeleton

Acceptance:

- every stock change creates movement record
- negative stock policy is enforced
- stock snapshot rebuilds from movement log

---

# 9. Phase 4: Billing Vertical Slice

Build:

- invoice model
- invoice line model
- tax calculation
- create invoice service
- sale transaction orchestration

Critical workflow:

```text
Create invoice
-> validate stock
-> create stock movement
-> post journal
-> write audit
-> publish durable event
```

Acceptance:

- invoice cannot complete without journal
- invoice cannot complete without audit
- stock is reduced exactly once
- duplicate idempotency key does not double-post

---

# 10. Phase 5: Reporting And Backup

Build:

- invoice report
- stock report
- ledger report
- tax report
- backup create
- backup validate
- restore to temp directory

Acceptance:

- reports derive from source-of-truth records
- backup validation rebuilds snapshots
- restored data passes invariants

---

# 11. Phase 6: PySide6 MVP UI

Build only after domain tests pass:

- item management
- stock adjustment
- create invoice
- invoice list
- journal view
- stock movement view
- audit trail view

UI rule:

- UI calls application services only
- UI never writes files directly
- UI never bypasses the C core durability path

---

# 12. Native/Python Boundary

Build order:

```text
C core storage/WAL
-> C tests
-> stable C API
-> Python bindings
-> Python application services
-> PySide6 UI
```

Assembly is deferred until profiling proves a narrow hot path.

---

# 13. Definition Of Done

A milestone is done only when:

- tests pass
- invariants pass
- docs are updated if contracts changed
- sample data can be rebuilt from append logs
- no module bypasses repository boundaries
- C core remains C-only
- observability exists for new critical paths
