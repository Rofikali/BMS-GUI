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

This gate must pass with no failing tests before a release candidate is tagged.

A skipped UI test is acceptable only when the local host cannot load native Qt libraries. CI should install the Qt/GL system packages required for the PySide6 smoke test.

---

# 3. Blocking Correctness Gates

A release candidate is blocked if any of these fail:

- unbalanced journals are accepted
- invoices complete without journal impact
- invoices complete without audit or business events
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
| Billing | invoice creates stock movement, journal, audit, event, and durable records |
| Events | known business events validate against schemas before persistence |
| Reporting | invoice, stock, ledger, tax, and trial balance reports rebuild from records |
| Backup | backup manifest validates, restore validates, restored reports match source |
| Runtime | startup health blocks recovery-required and protected storage |
| Facade | raw payloads validate through app command boundary before service calls |
| UI | app shell can run the core inventory, invoice, report, backup/restore flow |

---

# 5. Manual Desktop Smoke

On a desktop host with Qt native libraries installed, run:

```bash
uv run bms-gui
```

Then complete this workflow:

```text
Inventory tab: register item with opening stock
Billing tab: create invoice for that item
Reports tab: confirm invoice total, stock on hand, tax payable, and balanced trial balance
Backup tab: create backup
Backup tab: validate restore into a clean target directory
```

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

- role-based permissions UI
- refund completion workflow
- P&L report completion
- restore-over-live-data workflow
- cloud sync
- plugins or marketplace
- database storage
- custom indexes
- assembly optimization

These can be built after the current kernel remains stable under the release gate.
