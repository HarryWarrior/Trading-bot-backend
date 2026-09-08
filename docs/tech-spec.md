# Technical Specification (Tech Spec) - Trading Bot Backend API

> **Purpose:** This technical specification serves as the authoritative architectural blueprint for AI coding agents and backend engineers implementing, refactoring, and maintaining the Trading Bot Backend API.

---

## 1. System Architecture & Component Design

The backend is structured into modular layers adhering to Clean Architecture principles:

```
app/
├── main.py                     # ASGI entry point, lifecycle events, global middlewares
├── api/v1/endpoints/
│   ├── auth.py                 # Authentication and user management endpoints
│   └── analytics.py            # Trade ingestion and portfolio analytics endpoints
├── services/
│   ├── auth_service.py         # IAM business logic, password hashing, session tokens
│   ├── analytics_service.py    # Vectorized KPI computations & time-series aggregation
│   └── trade_parser_service.py # MT5 CSV/XLSX cleansing & normalization engine
├── schemas/                    # Pydantic v2 domain & request/response contracts
│   ├── auth.py                 # UserCreate, UserLogin, SessionResponse, OTP schemas
│   ├── trade.py                # Normalized Trade entity schema
│   └── analytics.py            # Analytics, DailyStats, MonthlyStats schemas
├── config/
│   └── database.py             # Motor AsyncIOMotorClient singleton & index management
└── utils/
    ├── security.py             # Bcrypt hashing, JWT encoding/decoding
    └── email.py                # SMTP email dispatcher with HTML templates
```

---

## 2. Technical Stack & Dependencies

* **Runtime:** Python 3.10+ / 3.11+
* **Framework:** FastAPI `0.104.1` with Starlette ASGI toolkit
* **Server:** Uvicorn `0.24.0`
* **Database Driver:** Motor `3.3.2` (Asynchronous MongoDB driver)
* **Data Processing & Analytics:** Pandas `2.1.3`, NumPy `1.26.2`, OpenPyXL `3.1.2`
* **Security & Auth:** Passlib `1.7.4` (`bcrypt`), PyJWT `2.8.0`, python-jose `3.3.0`
* **Validation & Serialization:** Pydantic v2
* **Code Quality & Linter:** Ruff (Linter and Formatter)

---

## 3. Data Persistence & Schema Strategy

> Detailed Pydantic class definitions are located directly in [`app/schemas/`](file:///c:/Users/HarrysonDanielGuerre/Documents/Harry/Trading-bot-backend/app/schemas). Do not duplicate schema code; refer to the respective schema files for field-level modifications.

### 3.1 MongoDB Storage Models & Indexes

The database uses asynchronous Motor client connections managed via [`app/config/database.py`](file:///c:/Users/HarrysonDanielGuerre/Documents/Harry/Trading-bot-backend/app/config/database.py):

| Collection | Key Fields | Indexes |
| :--- | :--- | :--- |
| `users` | `email`, `password_hash`, `name`, `role`, `email_verified`, `created_at` | `email` (Unique), `created_at` |
| `sessions` | `user_id`, `token`, `expires_at`, `created_at` | `token` (Unique), `user_id`, `expires_at` |
| `verifications` | `identifier`, `code`, `expires_at`, `created_at` | `identifier`, `expires_at` |
| `accounts` | `user_id`, `provider`, `provider_id`, `created_at` | `[provider, provider_id]` (Compound Unique), `user_id` |

---

## 4. API Endpoints & Contract Specifications

### 4.1 Analytics & Ingestion Domain (`/api/v1/analytics`)

* **`POST /api/v1/analytics/upload-trades`**
  * **Input:** `multipart/form-data` with `file` (`.csv`, `.xlsx`, `.xls` $\le 10\text{MB}$).
  * **Output (200 OK):**
    ```json
    {
      "success": true,
      "trades_count": 150,
      "file_path": "data/raw/trades.csv",
      "message": "150 trades loaded successfully"
    }
    ```
  * **Errors:** `400 Bad Request` (unsupported format or missing required headers).

* **`GET /api/v1/analytics/summary`**
  * **Output (200 OK):** Serialized `Analytics` schema containing all aggregate KPIs, win rates, drawdown metrics, hourly distribution, daily/monthly summaries, and equity curves.
  * **Errors:** `404 Not Found` if no trades dataset exists.

* **`GET /api/v1/analytics/trades`**
  * **Query Params:** `limit: Optional[int]`, `offset: int = 0`, `symbol: Optional[str]`, `status: Optional[str]` (`GANADOR`, `PERDEDOR`, `BREAK_EVEN`).
  * **Output (200 OK):** `List[Trade]`.

* **`GET /api/v1/analytics/filter`**
  * **Query Params:** `symbol`, `status`, `date_from`, `date_to`, `min_profit`, `max_profit`.
  * **Output (200 OK):** `{ filters_applied: dict, results_count: int, trades: List[Trade] }`.

* **`GET /api/v1/analytics/timeseries`**
  * **Query Params:** `metric: str = "equity"`, `groupby: str = "day"`.
  * **Output (200 OK):** `{ metric: str, groupby: str, dates: List[str], values: List[float] }`.

* **`GET /api/v1/analytics/by-symbol`**
  * **Output (200 OK):** `{ symbols: Dict[str, dict], total_symbols: int }`.

* **`GET /api/v1/analytics/hourly-heatmap`**
  * **Output (200 OK):** `{ data: Dict[str, { total: float, average: float, count: int }], best_hour: int }`.

* **`GET /api/v1/analytics/daily-stats` & `GET /api/v1/analytics/monthly-stats`**
  * **Output (200 OK):** `{ daily_stats: List[DailyStats] }` / `{ monthly_stats: List[MonthlyStats] }`.

---

### 4.2 Identity & Access Management Domain (`/api/v1/auth`)

* **`POST /api/v1/auth/sign-up`** $\rightarrow$ Creates user account, hashes password, generates 6-digit verification code, and dispatches verification email. Returns HTTP 201.
* **`POST /api/v1/auth/sign-in`** $\rightarrow$ Authenticates credentials, verifies `email_verified == True`, persists session in MongoDB, and returns Bearer token.
* **`POST /api/v1/auth/sign-out`** $\rightarrow$ Invalidates active session from MongoDB using Bearer token from `Authorization` header.
* **`GET /api/v1/auth/session`** $\rightarrow$ Validates token and returns current user details.
* **`POST /api/v1/auth/verify-email`** $\rightarrow$ Validates 6-digit OTP and marks user account as verified.
* **`POST /api/v1/auth/resend-verification`** $\rightarrow$ Generates and sends a fresh 6-digit OTP code.
* **`POST /api/v1/auth/forgot-password`** $\rightarrow$ Sends secure reset token via email.
* **`POST /api/v1/auth/reset-password`** $\rightarrow$ Resets password and invalidates all existing user sessions.

---

## 5. Algorithmic Specifications & Implementation Details

### 5.1 Dynamic Header Detection & Column Normalization
MT5 reports often feature metadata rows before the actual data table, as well as identical column names for entry and exit values (`Time` vs `Time.1`, `Price` vs `Price.1`).

```python
# Scan raw sheet rows until both 'time' and 'symbol' are found (case-insensitive)
header_row_idx = -1
for idx, row in df_temp.iterrows():
    row_str = row.astype(str).str.lower().tolist()
    if "time" in row_str and "symbol" in row_str:
        header_row_idx = idx
        break
```

Duplicate columns are systematically normalized to:
* `Time` $\rightarrow$ `open_time`, `Time.1` $\rightarrow$ `close_time`
* `Price` $\rightarrow$ `open_price`, `Price.1` $\rightarrow$ `close_price`
* `Profit` / `Ganancias` $\rightarrow$ `profit_usd`
* `Type` / `Tipo` $\rightarrow$ `order_type`

### 5.2 Streak Clustering Algorithm
Streaks are computed using vectorized sign changes to prevent iterative loops:
```python
df["sign"] = np.sign(df["profit_usd"])
# Group sequential trades with identical sign
df["streak_group"] = (df["sign"] != df["sign"].shift()).cumsum()
streaks = df.groupby("streak_group").size()

win_streaks = streaks[df.groupby("streak_group")["profit_usd"].sum() > 0]
loss_streaks = streaks[df.groupby("streak_group")["profit_usd"].sum() < 0]

longest_win = int(win_streaks.max()) if len(win_streaks) > 0 else 0
longest_loss = int(loss_streaks.max()) if len(loss_streaks) > 0 else 0
```

---

## 6. Code Quality, Linter, and Git Hooks

### 6.1 Coding Standards for AI Agents
* **Language:** All identifiers, docstrings, error messages, and logs MUST be in **English**.
* **Comments:** Do not write redundant or obvious `# comments`. Only comment non-obvious algorithms or numerical transformations.
* **Docstrings:** Use Google-style docstrings with `Args:`, `Returns:`, and `Raises:` sections.

### 6.2 Ruff Linting & Formatting Pre-Push Hook
A Git pre-push hook is configured to enforce linting and formatting before any push:
```bash
# Executed in .git/hooks/pre-push or .githooks/pre-push
ruff check .
ruff format --check .
```
