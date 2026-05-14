# BMS-GUI Documentation

Start here. This folder has vision documents, architecture blueprints, and implementation-grade contracts.

---

# Reading Order

1. `VISION.md` - long-term mission and product ambition
2. `PLATFORM_SPEC.md` - canonical source of truth
3. `MVP_SCOPE.md` - v1 build boundary
4. `DOMAIN_CONTRACTS.md` - module ownership and public contracts
5. `ACCOUNTING_SPEC.md` - implementation-grade accounting rules
6. `EVENT_SCHEMAS.md` - versioned durable event contracts
7. `FILE_STORAGE_SPEC.md` - file-based MVP storage contract
8. `INVARIANTS.md` - release-blocking correctness gates
9. `IMPLEMENTATION_ROADMAP.md` - first build order
10. `FIRST_TEST_PLAN.md` - first verification plan
11. `BUSINESS_STRATEGY.md` - target customer and business model

---

# Reference Documents

| Document | Purpose |
|---|---|
| `ARCHITECTURE.md` | broad architecture blueprint |
| `HLD_LLD_COMPLETE_ARCHITECTURE.md` | high-level and low-level design notes |
| `MODULE_MAP.md` | module catalog and dependencies |
| `EVENT_CATALOG.md` | conceptual event catalog |
| `PLUGIN_ABI.md` | plugin architecture and ABI direction |
| `ACCOUNTING_RULES.md` | accounting domain guide |
| `OPERATIONS.md` | operational and SRE guide |
| `SECURITY_GUIDE.md` | security and auditability guide |
| `TESTING.md` | quality and release validation guide |
| `BACKUP_RECOVERY.md` | backup and recovery blueprint |
| `ENGINEERING_DESIGN.md` | DSA, patterns, and performance notes |
| `industry_grade_business_platform_master_blueprint.md` | original master blueprint |
| `FILE_STORAGE_SPEC.md` | MVP file storage contract |
| `IMPLEMENTATION_ROADMAP.md` | build sequence |
| `FIRST_TEST_PLAN.md` | first test sequence |

---

# Decision Records

Architectural decisions live in `ADR/`.

Current ADRs:

- `ADR/0001-modular-monolith-first.md`
- `ADR/0002-file-based-storage-for-mvp.md`

---

# Governance

If documents conflict:

1. `PLATFORM_SPEC.md` wins.
2. ADRs explain why major decisions changed.
3. Implementation specs win over conceptual guides for build behavior.
4. Conceptual guides should be updated after any accepted contract change.
