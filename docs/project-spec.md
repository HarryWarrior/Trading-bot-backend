# Project Specification (Project Spec) - Trading Bot Backend API

> **Target Audience for this Document:** AI Agents, System Architects, and Software Engineers building, extending, and maintaining the Trading Bot Backend API.

---

## 1. System Vision & Domain Overview

The **Trading Bot Backend API** is an asynchronous, high-performance financial analytics and user management service. It processes historical trading logs exported from MetaTrader 5 (MT5) and other trading platforms in CSV and XLSX formats, standardizes execution data, and generates advanced portfolio metrics, risk indicators, and temporal distributions.

The system is architected around **Microservice Boundaries**, **Clean Architecture**, and **SOLID Design Principles**, ensuring that ingestion, analytics processing, and identity/access management operate with clear separation of concerns.

---

## 2. Architectural Boundaries & Microservice Design

The backend is organized into decoupled domain modules:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI API Gateway Layer                       │
│                     (Routing, CORS, Global Middlewares)                 │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
    ┌──────────────────────────────┐ ┌─────────────────────────────────┐
    │     Auth / IAM Domain        │ │     Analytics & Ingestion       │
    │  (app/api/v1/endpoints/auth) │ │ (app/api/v1/endpoints/analytics)│
    └──────────────┬───────────────┘ └────────────────┬────────────────┘
                   │                                  │
                   ▼                                  ▼
    ┌──────────────────────────────┐ ┌─────────────────────────────────┐
    │         AuthService          │ │ AnalyticsService / TradeParser  │
    │  (Password Hashing, Tokens,  │ │ (KPIs, Drawdown, Streaks,       │
    │   Sessions, OTP Lifecycle)   │ │  Header Detection, Data Cleansing│
    └──────────────┬───────────────┘ └────────────────┬────────────────┘
                   │                                  │
                   ▼                                  ▼
    ┌──────────────────────────────┐ ┌─────────────────────────────────┐
    │     MongoDB Collections      │ │        File Store / Cache       │
    │ (users, sessions, verifs)    │ │           (data/raw/)           │
    └──────────────────────────────┘ └─────────────────────────────────┘
```

### Domain Responsibilities:
1. **Identity & Access Management (IAM):** Handles registration, bcrypt password hashing, 6-digit email OTP verification, JWT session tokens, and role-based permissions (`user`, `trader`, `admin`).
2. **Trade Ingestion & Normalization:** Ingests unformatted `.csv` / `.xlsx` MT5 reports, resolves duplicate and bilingual column headers, filters out non-trade rows (deposits/withdrawals), and converts records into standardized `Trade` entities.
3. **Analytics Engine:** Computes risk/return ratios (Profit Factor, Payoff Ratio), drawdown trajectories, win/loss streak clusters, hourly performance heatmaps, and time series aggregations using vectorized NumPy/Pandas pipelines.

---

## 3. SOLID Principles & Engineering Guidelines

### 3.1 SOLID Implementation in Python
* **Single Responsibility Principle (SRP):**
  * Routers (`app/api/v1/endpoints/`) ONLY handle HTTP request validation, status codes, and response serialization.
  * Services (`app/services/`) contain pure business logic with no direct coupling to HTTP transport.
  * Parsers (`app/services/trade_parser_service.py`) ONLY transform external file formats into internal domain models.
* **Open/Closed Principle (OCP):**
  * Ingestion logic is designed to support new report formats (e.g., cTrader, TradingView, NinjaTrader) by registering parser strategies without modifying analytics calculation algorithms.
* **Liskov Substitution Principle (LSP):**
  * Storage and repository abstractions guarantee consistent asynchronous interfaces across storage backends.
* **Interface Segregation Principle (ISP):**
  * Separate Pydantic schemas for request payloads (`UserCreate`, `UserLogin`), database entities (`UserInDB`), and public response representations (`UserResponse`, `SessionResponse`).
* **Dependency Inversion Principle (DIP):**
  * Endpoints receive database sessions, configuration instances, and current authenticated user contexts via FastAPI's `Depends()` injection.

---

## 4. API Standards, Pagination & Return Patterns

All API responses must follow predictable envelopes, standardized pagination, and standard HTTP semantics.

### 4.1 Mandatory Pagination & Search Contract
* **Rule:** Every endpoint returning collections (`/trades`, `/users`, `/reports`) MUST accept pagination query parameters:
  * `page: int = 1` (1-indexed)
  * `page_size: int = 20` (maximum allowed: 100)
  * `sort_by: str = "open_time"`
  * `sort_dir: str = "desc"` (`"asc"` | `"desc"`)
  * `q: Optional[str] = None` (Full-text query filtering symbol, comment, ID)

### 4.2 Standard Paginated Response Envelope
```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 150,
      "total_pages": 8,
      "has_next": true,
      "has_prev": false
    }
  },
  "message": "Operation completed successfully",
  "meta": {
    "timestamp": "2026-09-08T12:00:00Z",
    "version": "2.0.0"
  }
}
```

### 4.3 Error Response Envelope (RFC 7807 Compatible)
```json
{
  "success": false,
  "error": {
    "code": "INVALID_FILE_FORMAT",
    "message": "The uploaded file format is not supported. Please provide a .csv or .xlsx file.",
    "details": null
  }
}
```

### 4.4 HTTP Status Code Conventions
* `200 OK`: Successful retrieval, update, or general operation.
* `201 Created`: Resource successfully created (e.g., user registration).
* `400 Bad Request`: Malformed payload, invalid file structure, or business validation failure.
* `401 Unauthorized`: Missing, invalid, or expired Bearer token.
* `403 Forbidden`: Authenticated user lacks required role/permission or email is unverified.
* `404 Not Found`: Resource or file does not exist.
* `422 Unprocessable Entity`: Schema validation error (Pydantic).
* `500 Internal Server Error`: Unhandled server-side exception.

---

## 5. Financial Data Integrity & Numerical Precision

1. **Monetary Precision:** All realized P&L and balance amounts in USD must be strictly rounded to **2 decimal places** (`round(val, 2)`).
2. **Asset Price Precision:** Forex currency pairs must preserve 4 to 5 decimal places; cryptocurrency assets must support up to 8 decimal places.
3. **Avoid Float Leaks:** Raw floating-point inaccuracies (e.g. `1.0850000000000002`) must be eliminated during schema serialization.
4. **Ingestion Idempotency:** The system computes a SHA-256 hash of each uploaded report. If an identical file is uploaded by the same user, cached analysis results are returned.
5. **Correlation ID & Traceability:** Every request receives an `X-Request-ID` header for end-to-end tracing in logs.

---

## 6. Security & Protection Specification

1. **Password Protection:** Passwords MUST be hashed using `bcrypt` with automatic salting and a minimum cost factor of 12. Plaintext passwords must never be logged or stored.
2. **Token & Session Management:**
   * JWT tokens signed using `HS256` with a high-entropy secret key (`JWT_SECRET_KEY`).
   * Active sessions stored and indexed in MongoDB (`sessions` collection) with `expires_at` TTL checks.
   * On password reset, all active user sessions must be invalidated immediately.
3. **Email OTP Verification:**
   * 6-digit numeric codes generated with cryptographically secure random generators.
   * Expiration window: 15 minutes.
   * One-time use: Deleted or invalidated immediately upon successful verification.
4. **File Ingestion Protection:**
   * Strict file extension validation (`.csv`, `.xlsx`, `.xls`).
   * Maximum file size limit: 10 MB.
   * Secure file path resolution to prevent directory traversal attacks (`../`).
5. **CORS & Headers:** Explicitly whitelisted frontend origin (`FRONTEND_URL`) in production.

---

## 7. Coding & AI Agent Interaction Rules

1. **Language Standard:**
   * **ALL** code, function names, variable names, class names, file names, docstrings, log messages, error messages, and API response strings MUST be in **English**.
2. **Docstring Format:**
   * All modules, classes, and public functions must have English docstrings following Google Python Style Guide conventions.
3. **Comment Philosophy:**
   * **STRICTLY FORBIDDEN:** Obvious or trivial comments (e.g., `# import libraries`, `# define router`, `# return response`, `# set status`).
   * **MANDATORY:** Comments are ONLY permitted to explain non-trivial algorithmic logic, mathematical formulas, edge-case workarounds, or performance optimizations.
4. **Formatting & Linting:**
   * Python code must conform to `ruff` rules (`ruff check` and `ruff format`).
   * Version updates and changelog entries must be managed with `python scripts/update_changelog.py`.
