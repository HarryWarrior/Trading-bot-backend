# 0001 — Every tool is a hexagonal microservice

- **Status:** accepted
- **Date:** 2026-11-23
- **Spec:** `specs/000-agents-foundation/`

## Context

The product is becoming a SaaS of many trading tools (journal, analytics, broker sync, backtesting,
live execution, AI). Development is done largely by AI agents, and each one invented its own
structure. The owner wants every tool to be a microservice, built the same way, with clean
boundaries so external tools can be integrated or replaced easily. Considered: modular monolith with
only externals as services (simpler, rejected by owner), microservices without a shared template
(inconsistent).

## Decision

- Each capability is a service under `services/<name>/`, created by copying `services/_template`.
- Inside each service: hexagonal architecture — `domain`, `application` (ports, use cases),
  `adapters` (inbound/outbound), `bootstrap.py` as composition root.
- Each service owns its logical MongoDB database; services communicate via HTTP through a gateway.
- Cross-cutting code lives in `libs/shared` (envelope, errors, settings, logging; later JWT, Mongo).

## Consequences

- Consistent structure for agents; external systems swap by adapter.
- More deployables and some duplication of small DTOs (accepted).
- Needs a gateway, compose setup and local JWT verification (spec 001).
- An architecture test in every service guards the dependency rule.
