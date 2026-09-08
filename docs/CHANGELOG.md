# Changelog - Trading Bot Backend API

## [2.0.0] - 2025-12-03 - Sistema de Autenticación Completo 🔐

### ✨ Nuevas características principales

#### Sistema de Autenticación (Auth Service Microservice)
- **Registro de usuarios (Sign-up)**
  - Validación de email único
  - Hash seguro de contraseñas con bcrypt
  - Generación automática de código de verificación
  - Envío de email de verificación con template HTML profesional

- **Autenticación (Sign-in/Sign-out)**
  - Login con email y password
  - Generación de JWT tokens (HS256)
  - Sesiones persistentes en MongoDB
  - Invalidación de sesiones (logout)
  - Validación de email verificado antes de login

- **Verificación de Email**
  - Código de 6 dígitos con expiración de 15 minutos
  - Endpoint para reenviar código
  - Email de bienvenida después de verificar
  - Templates HTML profesionales con gradientes

- **Recuperación de Contraseña**
  - Solicitud de reset con envío de email
  - Token JWT con expiración de 1 hora
  - Flow completo de password reset
  - Invalidación de todas las sesiones al resetear

- **Gestión de Sesiones**
  - Almacenamiento en MongoDB con índices optimizados
  - Validación automática en cada request
  - Limpieza de sesiones expiradas (endpoint admin)
  - Token incluye user_id, email, y role

- **Roles de Usuario**
  - `user`: Usuario normal
  - `trader`: Trader con permisos especiales
  - `admin`: Administrador del sistema

- **OAuth (Estructura preparada)**
  - Endpoints definidos para Google y GitHub
  - Schema para cuentas OAuth
  - Base de datos lista (colección `accounts`)

### 🗄️ Base de Datos MongoDB

#### Colecciones
- **users**: email (unique), password_hash, name, role, email_verified, created_at
- **sessions**: user_id, token (unique), expires_at, created_at
- **verifications**: identifier, code, expires_at, created_at
- **accounts**: user_id, [provider, provider_id] (compound unique), created_at

---

## [1.1.0] - 2025-11-25 - Soporte para archivos Excel

### ✨ Nuevas características
- **Soporte para archivos XLSX/XLS**: Ahora el sistema acepta archivos de Excel además de CSV
  - Formatos soportados: `.csv`, `.xlsx`, `.xls`
  - Validación automática de extensiones en el endpoint de upload
  - Detección automática del formato de archivo para procesamiento
- **TradeParserService**: Detección dinámica de cabeceras y soporte bilingüe.
