# EVENT_SCHEMAS.md
# Versioned Event Contracts

Events are facts. They are immutable, versioned, and owned by the publishing module.

---

# 1. Standard Envelope

```json
{
  "event_id": "evt_01",
  "event_type": "billing.sale_completed.v1",
  "version": 1,
  "occurred_at": "2026-05-13T00:00:00Z",
  "source_module": "billing",
  "actor_id": "usr_01",
  "correlation_id": "corr_01",
  "idempotency_key": "sale_INV-1001",
  "ordering_key": "invoice_INV-1001",
  "payload": {}
}
```

Required envelope fields apply to every durable event.

---

# 2. Delivery Classes

| Class | Use | Durability |
|---|---|---|
| critical | accounting, recovery, corruption | durable |
| business | billing, inventory, payments | durable |
| operational | logs, diagnostics, plugin lifecycle | best effort or durable by policy |
| analytical | dashboard and KPI refresh | best effort |

---

# 3. MVP Events

## `billing.sale_completed.v1`

Owner: Billing

Class: business

Payload:

```json
{
  "invoice_id": "INV-1001",
  "customer_id": "CUS-1",
  "currency": "INR",
  "subtotal_minor": 100000,
  "tax_minor": 18000,
  "total_minor": 118000,
  "payment_method": "cash",
  "line_count": 3
}
```

Subscribers:

- Inventory
- Accounting
- Audit
- Reporting
- Analytics

## `inventory.stock_moved.v1`

Owner: Inventory

Class: business

Payload:

```json
{
  "movement_id": "MOV-1",
  "sku": "SKU-1",
  "movement_type": "sale",
  "quantity_delta": -2,
  "unit_cost_minor": 5000,
  "source_document_id": "INV-1001"
}
```

Subscribers:

- Accounting
- Audit
- Reporting

## `accounting.journal_posted.v1`

Owner: Accounting

Class: critical

Payload:

```json
{
  "journal_id": "JRN-1",
  "period_id": "FY2026-05",
  "source_document_id": "INV-1001",
  "debit_total_minor": 118000,
  "credit_total_minor": 118000,
  "currency": "INR"
}
```

Subscribers:

- Audit
- Reporting
- Diagnostics

## `audit.record_created.v1`

Owner: Audit

Class: critical

Payload:

```json
{
  "audit_id": "AUD-1",
  "action": "invoice.created",
  "actor_id": "usr_01",
  "target_type": "invoice",
  "target_id": "INV-1001",
  "hash": "sha256:..."
}
```

Subscribers:

- Diagnostics
- Reporting

---

# 4. Schema Evolution

- Additive fields are minor-compatible.
- Removed or renamed fields require a new event version.
- Subscribers must reject unknown major versions.
- Critical events require fixture tests for every schema version.

