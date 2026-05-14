# FILE_STORAGE_SPEC.md

# MVP File-Based Storage Contract

This document is the authoritative file storage contract for the MVP. It implements ADR 0002.

---

# 1. Storage Goals

The file storage layer must provide:

- deterministic business writes
- inspectable local data
- WAL-first durability for critical workflows
- append-only financial and audit history
- checksum-based corruption detection
- snapshot-based fast startup
- simple backup and restore
- future migration path to an embedded database

---

# 2. Storage Root

Default local layout:

```text
data/
  manifest.json
  wal/
    current.wal.jsonl
    archive/
  events/
    business_events.jsonl
  accounting/
    journal_entries.jsonl
    journal_lines.jsonl
    periods.json
    chart_of_accounts.json
    snapshots/
      ledger_balances.json
      trial_balance.json
  inventory/
    items.json
    stock_movements.jsonl
    snapshots/
      stock_on_hand.json
  billing/
    invoices.jsonl
    invoice_lines.jsonl
    refunds.jsonl
    snapshots/
      invoice_index.json
  audit/
    audit_records.jsonl
    audit_manifest.json
  users/
    users.json
    roles.json
  tax/
    tax_rates.json
  reports/
    generated/
  backups/
  temp/
```

---

# 3. Source Of Truth

Append-only files are the source of truth:

| Domain | Source Of Truth |
|---|---|
| accounting journals | `accounting/journal_entries.jsonl`, `accounting/journal_lines.jsonl` |
| stock history | `inventory/stock_movements.jsonl` |
| invoices | `billing/invoices.jsonl`, `billing/invoice_lines.jsonl` |
| refunds | `billing/refunds.jsonl` |
| audit | `audit/audit_records.jsonl` |
| durable events | `events/business_events.jsonl` |

Snapshot files are read models. They can be rebuilt from source-of-truth files.

---

# 4. Standard Record Envelope

Every append-only record uses this envelope:

```json
{
  "schema_version": 1,
  "record_id": "rec_01",
  "record_type": "accounting.journal_entry",
  "sequence": 1,
  "created_at": "2026-05-13T00:00:00Z",
  "actor_id": "usr_01",
  "correlation_id": "corr_01",
  "idempotency_key": "invoice_INV-1001",
  "payload": {},
  "checksum": "sha256:..."
}
```

Rules:

- `sequence` is monotonic per file.
- `checksum` covers every field except `checksum` and MUST be computed as SHA-256 over a canonical JSON serialization of the record (stable key ordering, UTF-8, no insignificant whitespace); representation format: `sha256:<hex>`.
- `idempotency_key` prevents duplicate workflow commits.
- `correlation_id` links invoice, inventory, accounting, event, and audit records.

---

# 5. WAL Flow

Critical workflow write order:

```text
1. Validate command
2. Build full transaction bundle
3. Append WAL record: pending
4. fsync WAL
5. Append domain records
6. fsync domain files
7. Append audit records
8. Append durable events
9. Update snapshots atomically
10. Mark WAL record committed
11. fsync WAL
```

Recovery rule:

- pending WAL with no domain records: rollback
- pending WAL with complete domain records: finish commit
- committed WAL with missing snapshot: rebuild snapshot
- checksum failure: enter protected read-only mode

---

# 6. Atomic Snapshot Write

Snapshots use atomic replacement:

```text
write temp file
fsync temp file
rename temp file over snapshot
fsync parent directory when supported
```

Snapshots must include:

- `schema_version`
- `generated_at`
- `source_files`
- `last_applied_sequence`
- `checksum`

---

# 7. MVP Record Types

Required append-only record types:

- `billing.invoice`
- `billing.invoice_line`
- `billing.refund`
- `inventory.stock_movement`
- `accounting.journal_entry`
- `accounting.journal_line`
- `audit.record`
- `event.business`

Required snapshot types:

- `inventory.stock_on_hand`
- `accounting.ledger_balances`
- `accounting.trial_balance`
- `billing.invoice_index`

---

# 8. Repository Boundary

Domain services must never open storage files directly.

The MVP storage implementation lives in the native C core. Python services call it through bindings after the C API is stable.

The native core is pure C11. Do not introduce C++ into the core build.

Required repositories:

```text
InvoiceRepository
InventoryRepository
AccountingRepository
AuditRepository
EventRepository
ManifestRepository
```

All repositories are implemented by the file storage layer in MVP. A later database implementation must satisfy the same contracts.

Initial C API surface:

```text
bms_record_compute_checksum
bms_record_to_json_line
bms_record_verify_json_line
bms_jsonl_append_record
bms_jsonl_append_record_with_telemetry
bms_jsonl_verify_file
bms_jsonl_verify_file_with_telemetry
bms_jsonl_next_sequence
bms_wal_append_pending
bms_wal_append_pending_with_telemetry
bms_wal_append_committed
bms_wal_append_committed_with_telemetry
```

---

# 9. Observability Requirements

Every critical storage/WAL operation must be observable.

Required logs:

- record append success/failure
- checksum verification failure
- duplicate idempotency rejection
- WAL pending append
- WAL committed append
- recovery decision
- protected read-only mode entry

Required counters:

- `storage.records_appended`
- `storage.verify_success`
- `storage.checksum_failures`
- `storage.duplicate_idempotency_keys`
- `wal.pending_appended`
- `wal.committed_appended`

Logs are JSONL and must carry:

- timestamp
- level
- module
- correlation id
- message

---

# 10. Backup Rules

Backup includes:

- complete `data/` directory
- manifest
- source-of-truth append logs
- latest snapshots
- schema version metadata

Backup validation must:

- verify checksums
- replay append-only records into a temp directory
- rebuild snapshots
- run accounting and inventory invariants

---

# 11. Performance Boundaries

MVP is optimized for correctness first.

Initial targets:

| Operation | Target |
|---|---|
| create invoice | under 2 seconds local |
| startup with snapshots | under 5 seconds for MVP data |
| trial balance rebuild | under 10 seconds for MVP data |
| backup validation | acceptable as maintenance operation |

If targets are missed, add indexes/snapshots before changing storage architecture.
