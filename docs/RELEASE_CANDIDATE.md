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
- audit records and business events for billing, inventory, accounting, and recovery
- restart-safe invoice, refund, stock, ledger, tax, trial balance, and availability reports
- closed-period mutation guards
- backup creation and restore validation
- startup health, WAL inspection, protected mode, and recovery diagnostics
- partial invoice/refund failure detection when durable side effects exist
- Qt-backed desktop smoke flow when native Qt libraries are available

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
uv run bms-gui
```

Complete this workflow:

```text
Inventory tab: register ITEM-1 with opening stock
Billing tab: create invoice INV-1001
Billing tab: create partial refund REF-1001
Reports tab: confirm invoice total, refund total, refundable remaining, stock, tax, and trial balance
Backup tab: create backup
Backup tab: validate restore into a clean target directory
```

Any crash, silent failure, or report mismatch blocks release.

---

# Explicitly Not Supported Yet

- role-management UI
- P&L report completion
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
