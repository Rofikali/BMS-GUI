# ARCHITECTURE.md

# INDUSTRY-GRADE BUSINESS OPERATING PLATFORM ARCHITECTURE

## Principal Engineer + SRE + CA + MBA Architecture Blueprint

Canonical source of truth: `PLATFORM_SPEC.md`.

Implementation boundaries: `MVP_SCOPE.md`, `DOMAIN_CONTRACTS.md`, `INVARIANTS.md`.

---

# 1. ARCHITECTURE OVERVIEW

## Core Architectural Vision

Build a:

> Modular, Offline-First, Event-Driven, Accounting-Correct, Native-Powered Business Operating Platform.

The architecture is designed to:

- survive long-term evolution,
- remain operationally reliable,
- support future scaling,
- preserve accounting correctness,
- support future distributed extraction.

---

# 2. PRIMARY ARCHITECTURE STYLE

## Primary Pattern

Modular Monolith

## Internal Style

Event-Driven Service-Oriented Modules

## Future Evolution

Microservice-Extractable Architecture

---

# 3. WHY MODULAR MONOLITH

A modular monolith is chosen because it provides:

- simpler deployment
- easier debugging
- lower infrastructure cost
- transactional simplicity
- operational reliability
- faster development velocity

while preserving:

- module boundaries,
- scalability,
- future extraction paths.

---

# 4. ARCHITECTURAL PHILOSOPHY

---

## 4.1 PRINCIPAL ENGINEER PHILOSOPHY

Focus:

- long-term maintainability
- modular boundaries
- controlled complexity
- deterministic behavior
- scalability
- recoverability

Core Principle:

> Architect for extraction, not distribution.

---

## 4.2 SRE PHILOSOPHY

Focus:

- reliability
- observability
- recovery
- operational continuity
- fault tolerance

Core Principle:

> Systems must survive real operational failures.

---

## 4.3 CA PHILOSOPHY

Focus:

- accounting integrity
- auditability
- financial correctness
- traceable transactions

Core Principle:

> Every business transaction must generate accounting impact.

---

## 4.4 MBA PHILOSOPHY

Focus:

- operational intelligence
- profitability
- process optimization
- analytics
- decision support

Core Principle:

> Business operations should be measurable and optimizable.

---

# 5. FINAL SYSTEM LAYERS

```text
+---------------------------+
          GUI Layer          
      PySide6 Desktop UI     
+---------------------------+
               
+-------------+-------------+
       Application Layer     
   Workflow / Orchestration  
+---------------------------+
               
+-------------+-------------+
         Domain Layer        
  Business Rules / Services  
+---------------------------+
               
+-------------+-------------+
       Native Core Layer     
     C / ASM Components      
+---------------------------+
               
+-------------+-------------+
       Storage Layer         
  WAL / Snapshots / Files    
+---------------------------+
```

6. LAYER RESPONSIBILITIES
6.1 GUI LAYER

Responsibilities:

forms
dashboards
user interaction
reporting
visualization

Rules:

no direct storage access
no accounting logic
no transaction ownership

The GUI must remain:

thin,
responsive,
orchestration-oriented.
6.2 APPLICATION LAYER

Responsibilities:

workflow orchestration
command coordination
transaction management
use-case execution

Examples:

complete sale
process refund
generate invoice
6.3 DOMAIN LAYER

Responsibilities:

business rules
validation
accounting logic
inventory logic
pricing rules
operational workflows

This is the:
business intelligence core.

6.4 NATIVE CORE LAYER

Responsibilities:

event bus
storage engine
memory management
serialization
indexing
plugin loading
performance-critical operations

Implemented primarily using:

C
optional Assembly optimizations
6.5 STORAGE LAYER

Responsibilities:

WAL
snapshots
persistence
recovery
checksums
schema management

Storage must remain:

deterministic,
recoverable,
auditable.
7. MODULE ARCHITECTURE
Domain-Oriented Design
/modules
    accounting/
    inventory/
    billing/
    customers/
    suppliers/
    analytics/
    auth/
    reporting/
    notifications/
    audit/

Each module:

owns its business logic,
owns its data contracts,
publishes events,
exposes APIs.
8. INTERNAL MODULE STRUCTURE

Every module follows:

inventory/
    api/
    services/
    domain/
    repository/
    events/
    validators/
    models/
    tests/

Reason:

consistency,
scalability,
maintainability,
testability.
9. MODULE COMMUNICATION MODEL
Core Principle

 Modules communicate through contracts and events, not internals. 

Modules must NEVER:

directly mutate each other s storage,
bypass APIs,
depend on internal implementation details.
10. EVENT-DRIVEN ARCHITECTURE
Internal Event Pipeline
Publisher
-> Event Queue
-> Dispatcher
-> Subscribers
Event Categories
BUSINESS EVENTS
SYSTEM EVENTS
AUDIT EVENTS
ERROR EVENTS
PLUGIN EVENTS
Example Event Flow
SALE_COMPLETED
    -> Inventory Update
    -> Accounting Entry
    -> Analytics Update
    -> Audit Logging

Loose coupling enables:

scalability,
extensibility,
future service extraction.
11. DATA FLOW ARCHITECTURE
Master Flow
USER ACTION
    -> GUI LAYER
    -> APPLICATION SERVICE
    -> DOMAIN VALIDATION
    -> DOMAIN EXECUTION
    -> EVENT CREATION
    -> TRANSACTION ENGINE
    -> WAL WRITE
    -> STATE UPDATE
    -> AUDIT ENTRY
    -> ANALYTICS UPDATE
    -> NOTIFICATION EVENT
12. COMMAND / QUERY SEPARATION
Command Flow

Commands mutate state.

Examples:

create invoice
update stock
process payment

Flow:

Command
-> Validation
-> Transaction
-> Persistence
-> Events
Query Flow

Queries are read-only.

Examples:

search invoice
inventory dashboard
reports

Flow:

Query
-> Read Model
-> Response
13. DATA OWNERSHIP MODEL

Every entity has:
ONE authoritative owner.

Ownership Table
Entity Owner
invoices billing
stock inventory
ledgers accounting
users auth
analytics analytics

Other modules must use:

APIs,
events,
contracts.
14. STORAGE ARCHITECTURE
Storage Model

Initial storage strategy:

file-based,
WAL-backed,
snapshot-driven.
Storage Layout
/data
    /wal
    /snapshots
    /inventory
    /billing
    /accounting
    /customers
    /logs
Storage Principles
atomic writes
WAL-first durability
checksum validation
snapshot recovery
schema versioning
15. WAL ARCHITECTURE
WAL Flow
Operation
-> WAL Append
-> Flush
-> Commit State
-> Mark Complete

Guarantees:

crash recovery,
durability,
transactional safety.
16. TRANSACTION ARCHITECTURE
Transaction Lifecycle
BEGIN
-> VALIDATE
-> EXECUTE
-> WAL
-> COMMIT
-> EVENTS
-> COMPLETE
Transaction Principles
deterministic commits
rollback support
accounting consistency
event consistency
17. ACCOUNTING ARCHITECTURE

Accounting is:
a foundational subsystem.

Accounting Flow
Business Event
    -> Accounting Mapper
    -> Journal Entry Generator
    -> Double Entry Validation
    -> Ledger Update
    -> Trial Balance Check
Accounting Rules
double-entry mandatory
immutable ledgers
reversal-based corrections
audit logging required
reconciliation support
18. INVENTORY ARCHITECTURE
Inventory Flow
Stock Operation
    -> Validation
    -> Movement Record
    -> WAL
    -> Inventory Update
    -> Analytics Event
Inventory Rules
no silent stock mutation
movement history mandatory
reservation-ready architecture
low-stock detection support
19. AUDIT ARCHITECTURE
Audit Flow
Business Action
-> Audit Event
-> Immutable Log
-> Timestamp
-> User ID
-> Before/After State
Audit Principles
immutable history
operator traceability
accounting transparency
operational accountability
20. SECURITY ARCHITECTURE
Security Goals

Need:

RBAC
password hashing
session expiration
permission boundaries
audit trails
plugin isolation
RBAC Roles
ADMIN
MANAGER
CASHIER
ACCOUNTANT
VIEWER
21. PLUGIN ARCHITECTURE
Plugin Types
Native Plugins
inventory.dll
barcode.dll
search.dll
Python Plugins
gst_plugin.py
analytics_plugin.py
backup_plugin.py
Plugin Lifecycle
DISCOVER
-> VALIDATE
-> LOAD
-> INITIALIZE
-> REGISTER
-> RUN
-> SHUTDOWN
Plugin Requirements
ABI validation
capability restrictions
sandboxing
isolated failures
version compatibility
22. THREADING ARCHITECTURE
Thread Model
Main UI Thread
Worker Pool
Storage Thread
Logger Thread
Background Scheduler
Threading Principles
UI never blocks
storage asynchronous
event-driven execution
fine-grained locking
immutable event payloads
23. MEMORY ARCHITECTURE
Memory Philosophy

Need:

deterministic allocation
ownership clarity
minimal fragmentation
predictable lifetime
Allocation Strategy
Stack
-> Arena Allocators
-> Memory Pools
-> Heap (minimal)
24. OBSERVABILITY ARCHITECTURE
Observability Stack

Need:

structured logs
metrics
tracing
crash dumps
diagnostics
Key Metrics
Metric Purpose
invoice latency performance
event queue depth bottlenecks
WAL replay time recovery
plugin crashes extension stability
memory usage leak detection
25. RECOVERY ARCHITECTURE
Recovery Flow
Startup
-> WAL Scan
-> Corruption Check
-> Transaction Replay
-> Snapshot Recovery
-> Integrity Validation
Recovery Goals
automatic recovery
deterministic restoration
corruption detection
operational continuity
26. BACKUP ARCHITECTURE
Backup Flow
Pause Snapshot
-> Flush WAL
-> Create Archive
-> Checksum Validation
-> Resume
Backup Goals
safe recovery
rollback support
disaster recovery
operational continuity
27. ANALYTICS ARCHITECTURE
Analytics Pipeline
Business Events
-> Aggregation Engine
-> KPI Models
-> Dashboard
MBA KPIs
KPI Purpose
inventory turnover efficiency
gross margin profitability
dead stock ratio waste
customer retention loyalty
sales velocity demand
28. DEPLOYMENT ARCHITECTURE
Production Structure
/program
/config
/data
/logs
/plugins
/backups
/temp
Deployment Goals
offline-first
single installer
transactional upgrades
rollback support
backup-before-update
29. FUTURE EVOLUTION STRATEGY
Phase 1

Offline Local System

Phase 2

Plugin Ecosystem

Phase 3

Advanced Analytics

Phase 4

Cloud Sync

Phase 5

Multi-Branch Operations

Phase 6

Microservice Extraction

30. MICROSERVICE EXTRACTION STRATEGY

Core Principle:

 Extract services only when operationally necessary. 

Because modules already have:

contracts,
APIs,
event boundaries,
isolated ownership,

future extraction becomes easier.

Example:

inventory module
-> inventory-service

Minimal rewrite required.

31. ENGINEERING DISCIPLINE

The architecture enforces:

module boundaries
explicit ownership
deterministic workflows
auditability
observability
recovery discipline
accounting correctness

No uncontrolled shortcuts allowed.

32. FINAL CONCLUSION

This architecture combines:

Principal Engineer system design,
SRE operational reliability,
CA-grade accounting correctness,
MBA-grade operational intelligence.

Core architectural values:

modularity
determinism
auditability
recoverability
extensibility
observability
operational survivability

Ultimate Goal:

Build a long-term business operating platform that remains reliable, scalable, financially trustworthy, and maintainable for years.
