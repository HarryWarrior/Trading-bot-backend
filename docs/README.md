# Backend documentation

Start with [`AGENTS.md`](../AGENTS.md) for the product, stack, commands and golden rules.

| Document | Content |
|---|---|
| [architecture.md](architecture.md) | System context, containers, current vs target, legacy API reference |
| [services-catalog.md](services-catalog.md) | Every service: purpose, status, database, routes, spec |
| [adr/](adr/) | Architecture decision records |
| [integrations/README.md](integrations/README.md) | External repos and APIs evaluated |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [../specs/README.md](../specs/README.md) | Work in progress and planned (specs) |
| [../.agents/rules/](../.agents/rules/) | How to build (architecture, contracts, security, testing, git) |

## Decisions so far

| ADR | Decision |
|---|---|
| [0001](adr/0001-hexagonal-microservices.md) | Every tool is a microservice with hexagonal architecture |
| [0002](adr/0002-mt5-ea-bridge.md) | MT5 connectivity through an EA bridge; no broker passwords stored |
| [0003](adr/0003-two-repos-docs-in-repo.md) | Two repos (backend, frontend); docs, specs and agent rules live in each |
