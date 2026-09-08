# 🚀 Trading Bot Backend API

Sistema profesional de análisis de operaciones de trading con autenticación completa y gestión de usuarios. Backend construido con **FastAPI** + **MongoDB** para procesar datos históricos de MT5 y calcular métricas analíticas avanzadas.

## 📋 Características

### 🔐 Sistema de Autenticación (Auth Service)
- ✅ **Registro y Login**: Sign-up/Sign-in con email y password
- ✅ **Gestión de Sesiones**: JWT tokens con MongoDB
- ✅ **Verificación de Email**: Código de 6 dígitos con templates profesionales
- ✅ **Recuperación de Contraseña**: Flow completo de password reset
- ✅ **Seguridad**: Bcrypt para passwords, JWT para tokens
- ✅ **OAuth Ready**: Estructura preparada para Google y GitHub
- ✅ **Roles de Usuario**: User, Trader, Admin

### 📊 Análisis Profesional de Trading
- ✅ **KPIs Completos**: Win rate, Profit Factor, Payoff Ratio, Drawdown
- ✅ **Análisis por Símbolo**: Estadísticas desglosadas por par (EURUSD, GBPUSD, etc)
- ✅ **Series Temporales**: Curva de capital, profit diario/mensual
- ✅ **Análisis de Rachas**: Mayor racha ganadora/perdedora
- ✅ **Heatmaps**: Rentabilidad por hora del día
- ✅ **Distribuciones**: Histogramas de ganancias y duraciones

---

## 🏗️ Arquitectura

### Patrón MVC (Modelo-Vista-Controlador)

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
│                                                          │
│  ┌────────────────┐  ┌────────────────┐                │
│  │  Auth Service  │  │ Analytics Srvc │                │
│  │  (Microserv.)  │  │                │                │
│  └────────┬───────┘  └────────┬───────┘                │
│           │                   │                          │
│  ┌────────▼───────────────────▼───────┐                │
│  │         MongoDB Database            │                │
│  │  - users, sessions, trades, etc.    │                │
│  └─────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
```

### Tecnologías

- **Framework**: FastAPI 0.104+
- **Database**: MongoDB (Motor async driver)
- **Authentication**: JWT + bcrypt
- **Data Processing**: Pandas, NumPy
- **Email**: SMTP (Gmail, SendGrid, Mailgun)
- **Server**: Uvicorn (ASGI)

---

## 📁 Estructura del Proyecto

```
trading-bot-backend/
├── app/
│   ├── main.py                         # FastAPI app principal
│   │
│   ├── api/v1/endpoints/
│   │   ├── auth.py                     # 🔐 Auth endpoints
│   │   └── analytics.py                # 📊 Analytics endpoints
│   │
│   ├── services/
│   │   ├── auth_service.py             # Lógica de autenticación
│   │   ├── analytics_service.py        # Cálculo de KPIs
│   │   └── trade_parser_service.py     # Parser CSV/XLSX
│   │
│   ├── schemas/
│   │   ├── auth.py                     # Modelos de autenticación
│   │   ├── trade.py                    # Modelo Trade
│   │   └── analytics.py                # Modelo Analytics
│   │
│   ├── config/
│   │   └── database.py                 # Conexión MongoDB
│   │
│   └── utils/
│       ├── security.py                 # Hash, JWT, tokens
│       └── email.py                    # Envío de emails
│
├── data/
│   ├── raw/                            # CSV originales
│   ├── processed/                      # Datos procesados
│   └── cache/                          # KPIs cacheados
│
├── docs/
│   ├── README.md                       # Documentación principal
│   ├── CHANGELOG.md                    # Historial de versiones
│   ├── project-spec.md                 # Especificación de proyecto (SDD)
│   └── tech-spec.md                    # Especificación técnica (SDD)
│
├── tests/
│   ├── test_auth.py
│   └── test_analytics.py
│
├── .env.example                        # Variables de entorno
├── requirements.txt                    # Dependencias
└── pyproject.toml                      # Configuración de Ruff
```

---

## 🚀 Instalación y Configuración

### 1. Clonar el Repositorio

```bash
git clone <repository-url>
cd trading-bot-backend
```

### 2. Crear Entorno Virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno

```bash
cp .env.example .env
```

Editar `.env` con tus configuraciones:

```env
# MongoDB
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=trading_bot_db

# JWT Security
JWT_SECRET_KEY=your-super-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7 días

# Email (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com

# Frontend URL
FRONTEND_URL=http://localhost:3000
```

### 5. Configurar MongoDB

**Opción A: MongoDB Local**
```bash
# Instalar MongoDB Community Edition
# https://www.mongodb.com/try/download/community

# Iniciar servicio
mongod
```

**Opción B: MongoDB Atlas (Cloud - Recomendado)**
1. Crear cuenta en [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Crear cluster gratuito (M0)
3. Obtener connection string
4. Actualizar `MONGODB_URL` en `.env`

---

## ▶️ Ejecutar el Servidor

```bash
# Opción 1: Uvicorn directo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Opción 2: Python module
python -m app.main
```

El servidor estará disponible en: http://localhost:8000

---

## 📖 Documentación API

Una vez iniciado el servidor, accede a:

- **Swagger UI** (interactivo): http://localhost:8000/docs
- **ReDoc** (documentación): http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## 🔑 Endpoints Principales

### Autenticación (`/api/v1/auth`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/sign-up` | Registrar nuevo usuario |
| POST | `/sign-in` | Iniciar sesión |
| POST | `/sign-out` | Cerrar sesión |
| GET | `/session` | Obtener sesión actual |
| POST | `/verify-email` | Verificar email con código |
| POST | `/resend-verification` | Reenviar código de verificación |
| POST | `/forgot-password` | Solicitar reset de password |
| POST | `/reset-password` | Resetear password con token |
| GET | `/oauth/{provider}` | Iniciar OAuth (Google/GitHub) |

### Analytics (`/api/v1/analytics`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/upload-trades` | Subir CSV/XLSX de MT5 |
| GET | `/trades` | Listar operaciones paginadas |
| GET | `/summary` | Resumen KPIs completo |
| GET | `/filter` | Filtrar operaciones |
| GET | `/timeseries` | Series temporales |
| GET | `/by-symbol` | Stats por símbolo |
| GET | `/hourly-heatmap` | Heatmap horario |
| GET | `/daily-stats` | Estadísticas diarias |
| GET | `/monthly-stats` | Estadísticas mensuales |

---

## 🔒 Seguridad

- Password hashing con bcrypt (work factor $\ge 12$)
- JWT tokens con expiración y verificación de firma
- Sesiones en MongoDB
- Verificación por código OTP de 6 dígitos
- CORS configurado

---

## 🧪 Testing y Calidad

```bash
# Ejecutar tests
pytest tests/

# Linter y Formatter con Ruff
ruff check .
ruff format .
```
