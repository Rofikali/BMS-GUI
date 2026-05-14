# BUSINESS_STRATEGY.md
# Business Strategy And Operating Model

This document keeps the engineering roadmap tied to business outcomes.

---

# 1. Target Customer

Initial customer:

- single-location retail shop
- distributor or wholesaler with stock movement
- small business that needs billing plus inventory plus accounting traceability

Avoid in v1:

- complex enterprise ERP deployments
- multi-country tax engines
- large franchise workflows
- custom marketplace ecosystem

---

# 2. Value Proposition

The product promise:

```text
Fast local billing, trustworthy stock, accounting-ready records, and recoverable business data.
```

Differentiators:

- offline-first operation
- accounting-correct workflows
- audit trail by default
- inventory intelligence
- simple local ownership of data
- future extensibility

---

# 3. Buyer Metrics

| Metric | Why It Matters |
|---|---|
| invoice speed | cashier productivity |
| stock accuracy | working capital control |
| gross margin | profitability |
| tax report confidence | compliance |
| backup restore success | business continuity |
| operator mistakes caught | operational trust |

---

# 4. Commercial Assumptions

Recommended v1 model:

- paid desktop license or subscription
- optional paid support
- optional migration/import service
- later plugin marketplace only after stable core

Do not make cloud subscription mandatory for the first promise. Offline-first is a strategic wedge.

---

# 5. Go-To-Market Wedge

Start with a narrow vertical:

- retail store
- pharmacy-like inventory
- hardware store
- wholesale counter sales

Pick one workflow-heavy segment before generalizing.

---

# 6. Product Risks

| Risk | Mitigation |
|---|---|
| overbuilding platform before product fit | ship MVP kernel first |
| accounting mistakes | invariant tests and accountant review |
| storage corruption | use proven storage or aggressive recovery tests |
| weak onboarding | optimize billing/inventory workflows |
| plugin complexity | defer until core contracts stabilize |

