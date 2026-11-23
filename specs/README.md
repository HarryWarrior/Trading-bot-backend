# Specs

Every non-trivial piece of work has a spec. Workflow and rules:
[`.agents/rules/docs-and-specs.md`](../.agents/rules/docs-and-specs.md).

```
design (draft) → owner approves (approved) → plan.md → execute with TDD (in-progress) → verify → done
```

- Folder: `specs/NNN-short-slug/` with `design.md` and, after approval, `plan.md`.
- Templates: `.agents/templates/spec-design.md`, `.agents/templates/spec-plan.md`.
- Numbers are shared with `trading-bot-frontend`; the backend design is the source of truth for intent.
- **Next free number: 005.**

## Index

| # | Title | Status | Backend | Frontend |
|---|---|---|---|---|
| 000 | Agents foundation (rules, templates, docs, spec workflow) | in-progress | [design](000-agents-foundation/design.md) · [plan](000-agents-foundation/plan.md) | yes |
| 001 | Migrate legacy app to services + security debt | draft | [design](001-service-migration/design.md) | yes |
| 002 | MT5 automatic sync via EA bridge | draft | [design](002-mt5-ea-bridge-sync/design.md) | yes |
| 003 | Strategy → backtest → paper → live bot | draft | [design](003-strategy-backtest-live/design.md) | yes |
| 004 | AI-filled journal (MCP / API) | draft | [design](004-ai-journal/design.md) | yes |
