# ADR 0002: File-Based Storage For MVP

Status: Accepted

Date: 2026-05-13

---

# Context

The platform is offline-first and must preserve accounting correctness, inventory traceability, auditability, and recoverability. A database can provide many of these properties, but the product direction intentionally starts with an inspectable file-based storage engine so the platform owns its storage semantics from the beginning.

The MVP must not become an unstructured collection of JSON files. File-based storage still needs explicit contracts, write ordering, checksums, recovery behavior, and schema versions.

---

# Decision

Use file-based storage for the MVP.

The MVP storage model uses:

- append-only JSON Lines for ledgers, stock movements, audit records, and domain events
- JSON snapshot files for current read models and configuration
- a simple write-ahead log for transaction intent and recovery
- manifest files for schema versions, checksums, and last applied sequence numbers
- atomic file replacement for snapshots

SQLite and other embedded databases are deferred until there is a measured need or a product requirement.

---

# Consequences

Benefits:

- data is inspectable and portable
- backup/export is straightforward
- storage behavior is explicit and teachable
- recovery semantics can be designed around accounting invariants
- future migration to a database can be done through repository interfaces

Tradeoffs:

- indexing and query performance must be managed carefully
- concurrent writes must be strictly serialized
- corruption detection must be built deliberately
- compaction and snapshotting become product responsibilities
- schema migration needs first-class discipline

---

# Non-Negotiable Rules

- No direct file writes from UI or domain modules.
- All writes go through the storage service.
- Critical records are append-only.
- Every durable record includes schema version, record id, timestamp, correlation id, and checksum.
- Business transaction writes are WAL-first.
- Snapshot files are derived state, never the source of financial truth.
- Posted journal entries and audit records are never modified in place.

---

# Review Trigger

Revisit this decision when:

- file scans become too slow for expected customer data size
- multi-user concurrent writes become a committed requirement
- reporting requires complex ad hoc queries
- corruption recovery becomes too expensive to maintain safely
- a migration to SQLite or another embedded store reduces risk without weakening offline-first operation
