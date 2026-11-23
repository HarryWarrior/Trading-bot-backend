# 0003 — Two repositories, docs and specs inside each

- **Status:** accepted
- **Date:** 2026-11-23
- **Spec:** `specs/000-agents-foundation/`

## Context

Backend and frontend live in two GitHub repos. A monorepo and a separate docs repo were considered
and rejected by the owner.

## Decision

- Keep `Trading-bot-backend` and `trading-bot-frontend`.
- Each repo has `AGENTS.md`, `.agents/`, `docs/` and `specs/`, all committed.
- Spec numbers are shared: a feature touching both repos has `specs/NNN-slug/` in each; the frontend
  design links to the backend one (the source of truth for intent).
- Same git workflow in both: work branches from `dev`, PR to `dev`, `main` for releases.

## Consequences

- Docs stay next to the code they describe and are versioned with it.
- Cross-repo features need two PRs, coordinated by spec number.
- Shared policies (git workflow, spec workflow) are duplicated in both repos and must be kept in sync.
