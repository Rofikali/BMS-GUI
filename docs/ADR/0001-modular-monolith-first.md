# ADR 0001: Modular Monolith First

Status: Accepted

Date: 2026-05-13

---

# Context

The platform needs billing, inventory, accounting, audit, reporting, and recovery. These domains must be isolated but do not require separate deployment in v1.

---

# Decision

Start as a modular monolith with strict module contracts and event-driven internal boundaries.

---

# Consequences

Benefits:

- simpler deployment
- faster local development
- easier debugging
- lower operational burden
- strong consistency for accounting and inventory

Tradeoffs:

- requires discipline to prevent hidden coupling
- future extraction requires stable contracts
- module ownership must be enforced by tests and reviews

---

# Review Trigger

Revisit when:

- one module requires independent scaling
- cloud sync becomes a committed product requirement
- deployment boundaries become a customer requirement
- team ownership demands independent release cycles
