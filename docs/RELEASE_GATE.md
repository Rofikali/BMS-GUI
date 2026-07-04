# RELEASE_GATE.md
# MVP-Safe Release Gate

This document defines the minimum bar before a build can be treated as MVP-safe.
It does not replace `PLATFORM_SPEC.md`; it turns the platform invariants into a release checklist.

---

# 1. Release Definition

A build is MVP-safe only when it proves this lifecycle end to end:

```text
Register item
-> Add opening stock
-> Create invoice
-> Create partial refund
-> Validate remaining refundable quantity
-> Validate stock
-> Calculate tax
-> Post journal
-> Persist durable records
-> Write audit and business events
-> Rebuild reports after restart
-> Close accounting period
-> Block closed-period invoice and journal mutations
-> Create backup
-> Restore backup into a clean target
-> Verify restored reports and closed-period guards
```

The release gate is intentionally narrow. Passing it means the kernel is trustworthy enough for continued pilot work, not that the whole product vision is complete.

---

# 2. Required Automated Gate

The full local and CI gate is:

```bash
./scripts/verify
```

On native Windows PowerShell, run the equivalent gate:

```powershell
.\scripts\verify.ps1
```

This gate must pass with no failing tests before a release candidate is tagged.

The verification gate includes the product-level MVP acceptance smoke. It can also be run directly:

```bash
uv run bms-release-check
```

This command creates a clean temporary data root, runs the release lifecycle from section 1, validates the expected business totals, closes the period, verifies backup/restore, and exits non-zero on mismatch.

A skipped UI test is acceptable only when the local host cannot load native Qt libraries. CI should install the Qt/GL system packages required for the PySide6 smoke test.

---

# 3. Blocking Correctness Gates

A release candidate is blocked if any of these fail:

- unbalanced journals are accepted
- invoices complete without journal impact
- invoices complete without audit or business events
- refunds complete without journal impact
- refunds complete without audit or business events
- refunds exceed the original invoice line quantity or value
- partial refund failures with durable side effects are automatically rolled back
- refund reports cannot show refunded and still-refundable quantities
- inventory changes occur without stock movement records
- stock can go negative when the policy disables it
- duplicate invoice, journal, movement, or idempotency keys double-apply effects
- closed periods accept financial mutations
- append-only record checksum verification fails
- WAL startup inspection misses pending or corrupt state
- protected-mode storage allows normal app startup
- backup restore does not reproduce report totals and stock state
- restored record counts differ from the backup manifest
- UI/facade workflows bypass command validation or domain services

---

# 4. Required Test Areas

| Area | Required Proof |
|---|---|
| Native core | append, checksum, sequence, idempotency, snapshot, WAL inspect/recover |
| Accounting | balanced journal, trial balance, ledger balances, closed-period guard |
| Inventory | item registration, stock movement, stock rebuild, negative-stock guard |
| Billing | invoice and refund create stock movement where applicable, journal, audit, event, and durable records |
| Events | known business events validate against schemas before persistence |
| Reporting | invoice, refund, refund availability, stock, ledger, tax, trial balance, and P&L reports rebuild from records |
| Backup | backup manifest validates, restore validates, restored reports match source |
| Runtime | startup health blocks recovery-required and protected storage, including partial refund side effects |
| Facade | raw payloads validate through app command boundary before service calls and role permissions are enforced |
| UI | app shell can run the core inventory, invoice, report, role-management, backup/restore flow |

---

# 5. Manual Desktop Smoke

On a desktop host with Qt native libraries installed, run:

```bash
BMS_DATA_ROOT=/tmp/bms-gui-smoke-data uv run bms-gui
```

Then complete this workflow:

```text
Inventory tab: register item with opening stock
Billing tab: create invoice for that item
Billing tab: create a partial refund for that invoice
Reports tab: confirm invoice total, refund total, still-refundable quantity, stock on hand, tax payable, and balanced trial balance
Reports tab: close the accounting period
Billing tab: confirm a new invoice for that closed period is blocked
Backup tab: create backup
Backup tab: validate restore into a clean target directory
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

Any crash, silent failure, or report mismatch blocks the release candidate.

---

# 6. CI Requirement

GitHub Actions must run the same gate from section 2.

The workflow lives at:

```text
.github/workflows/ci.yml
```

A release candidate must not be tagged from a commit with failing CI.

---

# 7. Not Yet Release-Safe

These items are still outside the current MVP-safe bar and must not be marketed as complete:

- restore-over-live-data workflow
- cloud sync
- plugins or marketplace
- database storage
- custom indexes
- assembly optimization

These can be built after the current kernel remains stable under the release gate.
