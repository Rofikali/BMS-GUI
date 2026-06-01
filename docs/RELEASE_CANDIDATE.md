# RELEASE_CANDIDATE.md
# MVP-Safe Release Candidate Notes

Current candidate date: 2026-05-30

This note defines the current MVP-safe checkpoint. It is intentionally narrower than the full platform vision.

---

# Proven Workflows

The automated gate proves:

- item registration and opening stock
- invoice creation with stock-out movement
- tax calculation and balanced journal posting
- partial refund creation with optional stock return
- refund quantity/value guard against the original invoice and prior refunds
- refund availability reporting from durable invoice and refund lines
- P&L summary reporting from durable ledger balances
- audit records and business events for billing, inventory, accounting, and recovery
- restart-safe invoice, refund, stock, ledger, tax, trial balance, and availability reports
- closed-period mutation guards
- admin role-management UI with last-active-admin protection
- backup creation and restore validation
- startup health, WAL inspection, protected mode, and recovery diagnostics
- partial invoice/refund failure detection when durable side effects exist
- Qt-backed desktop smoke flow when native Qt libraries are available

---

# Release Gate Evidence

| Gate | Status | Automated proof |
|---|---|---|
| Register item and opening stock | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_inventory_service.py` |
| Invoice creates stock, journal, audit, and business event impact | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_billing_service.py` |
| Partial refund references original invoice and posts accounting impact | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_billing_service.py` |
| Refund quantity/value cannot exceed remaining refundable amount | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_billing_service.py` |
| Reports rebuild after restart and restore | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_reporting_service.py` |
| P&L report derives revenue, returns, expenses, and net income from ledger balances | Proven | `tests/unit/test_reporting_service.py`, `tests/unit/test_application_command_facade.py`, `tests/unit/test_ui_main.py` |
| Closed periods block invoice and journal mutations at service and facade boundaries | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_accounting_service.py`, `tests/unit/test_application_command_facade.py` |
| Role permissions are enforced at the facade boundary | Proven | `tests/unit/test_application_command_facade.py` |
| Role-management UI updates existing user roles without allowing admin lockout | Proven | `tests/unit/test_ui_main.py`, `tests/unit/test_application_command_facade.py` |
| UI/facade workflow uses command validation and operator guardrails | Proven | `tests/unit/test_ui_main.py`, `tests/unit/test_application_command_facade.py` |
| Append-only checksums and WAL recovery rules are tested | Proven | `tests/core/test_bms_core_storage.c`, `tests/unit/test_core_file_store.py`, `tests/unit/test_application_recovery.py` |
| Protected-mode storage blocks normal startup | Proven | `tests/unit/test_startup_health_service.py`, `tests/unit/test_application_command_facade.py` |
| Backup restore validates counts and restored business state | Proven | `tests/integration/test_mvp_integrity_gate.py`, `tests/unit/test_backup_service.py` |
| Restore-over-live-data fails closed pending a guarded replacement workflow | Proven | `tests/unit/test_backup_service.py`, `docs/BACKUP_RECOVERY.md` |
| Manual desktop smoke on native host | Required before tag | Run the checklist below with `uv run bms-gui` |

The current release-blocking gap is manual, not architectural: a human must still run the native desktop smoke on a machine with Qt libraries and compare the visible reports to the expected lifecycle results.

---

# Required Gate

Before tagging this candidate, run:

```bash
./scripts/verify
```

The gate must pass with:

- native C storage/observability tests passing
- Python unit and integration tests passing
- no skipped UI smoke except on hosts that cannot load native Qt libraries

---

# Manual Desktop Smoke

On a desktop host with Qt native libraries installed:

```bash
BMS_DATA_ROOT=/tmp/bms-gui-smoke-data uv run bms-gui
```

Headless environments such as Codespaces usually cannot run the interactive
desktop smoke because Qt has no display server. A failure like `could not
connect to display` or `Could not load the Qt platform plugin "xcb"` means the
manual smoke must be run on a real desktop host. In that environment, run the
offscreen UI smoke as a partial check:

```bash
QT_QPA_PLATFORM=offscreen BMS_DATA_ROOT=/tmp/bms-gui-smoke-data uv run python -m unittest tests.unit.test_ui_main
```

The offscreen smoke does not replace the manual desktop smoke before tagging a
human-facing release candidate.

Complete this workflow:

```text
Inventory tab: register the generated default item with opening stock
Billing tab: create an invoice for the registered item
Billing tab: create a partial refund for that invoice
Reports tab: confirm invoice total, refund total, still-refundable quantity, stock, tax, and balanced trial balance
Reports tab: close the accounting period
Billing tab: confirm a new invoice for that closed period is blocked
Backup tab: create backup
Backup tab: validate clean restore into a clean target directory
```

Expected visible results after the invoice and one-unit refund:

| Check | Expected value |
|---|---|
| Invoice total | `118000` |
| Refund total | `59000` |
| Refundable remaining | `50000` |
| Stock on hand | `4` |
| Tax payable | `9000` |
| Trial balance | `Balanced` |
| Closed-period invoice attempt | blocked with a closed-period error |

Any crash, silent failure, or report mismatch blocks release.

---

# Explicitly Not Supported Yet

- restore-over-live-data workflow
- cloud sync
- database storage
- plugin marketplace
- custom index engine
- assembly optimization

---

# Operational Risks To Watch

- Recovery workflows are intentionally conservative: pending financial transactions with durable side effects require operator reconciliation.
- Refunds are cash-style reversals in the current MVP accounting model; richer payment-provider integration is deferred.
- Reporting is rebuilt from append-only records; any source-of-truth corruption must be treated as protected-mode work.
- Manual desktop smoke is still required before a human-facing release because CI can prove the UI path only through automated offscreen smoke.
