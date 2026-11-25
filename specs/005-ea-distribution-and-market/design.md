# 005 — EA distribution, MQL5 Market and selling (design)

- **Status:** draft (stub; designed after 002 works end to end)
- **Date:** 2026-11-24
- **Depends on:** 002 (EA bridge), 003 (bot, optional)

## 1. Intent

Turn the working EA from 002 into a polished product other traders can install and, later, buy: signed
builds, versioning and auto-update notice, publishing on the MQL5 Market, licensing and billing.

## 2. To research before designing

- MQL5 Market rules for EAs that call external servers (WebRequest allowed? review requirements).
- Code signing / `.ex5` protection, license-key validation, per-account locking.
- Billing options (own Stripe/MercadoPago vs. MQL5 Market sales).
- Broker/prop-firm policies on third-party EAs.

## 3. Open questions

Pricing model, support obligations, whether the web SaaS and the Market EA are sold together.
