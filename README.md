# BMS-GUI

BMS-GUI is an offline-first desktop business management system for retail and inventory-heavy businesses. The goal is not a simple billing app; it is an accounting-correct operating platform that can grow into a durable business, inventory, audit, and reporting system.

The product is designed from three perspectives:

- CA: accounting correctness, auditability, reconciliation, tax readiness, and ledger integrity.
- MBA: operational intelligence, profitability, inventory visibility, and business decision support.
- Engineer: native durability, clear module boundaries, testable contracts, and long-term maintainability.

## Architecture

The platform starts as a modular monolith:

```text
PySide6 UI -> Python services -> C API -> native C11 core -> file-based durable storage
```

Core storage and durability code lives in `core/` and is implemented in pure C11. Assembly is allowed only for narrow hot paths after profiling proves it is needed. Python and PySide6 sit above the native boundary and must not bypass the C durability path.

MVP storage is file-based first, using append-only records, checksums, WAL support, and rebuildable read models. The decision is documented in [docs/ADR/0002-file-based-storage-for-mvp.md](docs/ADR/0002-file-based-storage-for-mvp.md) and [docs/FILE_STORAGE_SPEC.md](docs/FILE_STORAGE_SPEC.md).

## Documentation

Start at [docs/README.md](docs/README.md).

The canonical product and engineering source of truth is [docs/PLATFORM_SPEC.md](docs/PLATFORM_SPEC.md). If other documents conflict with it, the platform spec wins until an ADR changes the decision.

Useful entry points:

- [docs/VISION.md](docs/VISION.md) - long-term mission and product ambition
- [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) - first production-grade release boundary
- [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) - first build order
- [docs/FIRST_TEST_PLAN.md](docs/FIRST_TEST_PLAN.md) - first verification plan
- [docs/RELEASE_GATE.md](docs/RELEASE_GATE.md) - MVP-safe release checklist
- [docs/BUSINESS_STRATEGY.md](docs/BUSINESS_STRATEGY.md) - target customer and business model

## Build And Test

Build the native core:

```bash
./scripts/verify
```

The verification script configures the C build, runs native C tests, and runs the Python unit and integration tests. It uses Ninja when available and falls back to Unix Makefiles.

Run only the native core tests after configuring a build:

```bash
ctest --test-dir build/verify --output-on-failure
```

Run checksum-focused tests:

```bash
ctest --test-dir build/verify -R checksum --output-on-failure
```

Run Python tests through the project environment:

```bash
uv run python -m unittest discover tests
```

Run the desktop app:

```bash
uv run bms-gui
```

Inspect or recover storage when normal startup is blocked:

```bash
uv run bms-recovery inspect --data-root data
uv run bms-recovery report --data-root data
uv run bms-recovery recover --data-root data
uv run bms-recovery reconcile --data-root data --transaction-id txn_... --decision accepted_existing_records --actor-id usr_admin --reason "Reviewed durable records"
uv run bms-recovery resolve-accounting-adjustment --data-root data --transaction-id txn_... --actor-id usr_admin --reason "Posted correction journal" --journal-json '{"journal_id":"JRN-REC-1","period_id":"FY2026-05","timestamp":"2026-05-14T03:05:00Z","actor_id":"usr_admin","source_module":"recovery","source_document_id":"txn_...","correlation_id":"corr_txn","description":"Recovery accounting adjustment","lines":[{"account_code":"4000","debit_minor":100000,"currency":"INR"},{"account_code":"2100","debit_minor":18000,"currency":"INR"},{"account_code":"1000","credit_minor":118000,"currency":"INR"}]}'
```

Run the full local verification gate:

```bash
./scripts/verify
```

CI runs the same verification gate in `.github/workflows/ci.yml`.
