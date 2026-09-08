# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Importar routers
from app.api.v1.endpoints import analytics, auth, mt5

# Importar configuración de MongoDB
from app.config.database import MongoDB

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Crear app FastAPI
app = FastAPI(
    title="Trading Bot Backend API",
    description="API profesional para análisis de trading y gestión de usuarios con autenticación completa",
    version="2.0.2",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios exactos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Eventos de ciclo de vida
@app.on_event("startup")
async def startup_db_client():
    """Conectar a MongoDB al iniciar"""
    logger.info("🔌 Conectando a MongoDB...")
    await MongoDB.connect_db()
    logger.info("✅ MongoDB conectado")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Cerrar conexión a MongoDB al apagar"""
    logger.info("🔌 Cerrando conexión a MongoDB...")
    await MongoDB.close_db()
    logger.info("✅ MongoDB desconectado")

# Incluir routers
app.include_router(
    analytics.router,
    prefix="/api/v1/analytics",
    tags=["Analytics"]
)

app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    mt5.router,
    prefix="/api/v1/mt5",
    tags=["MetaTrader 5"]
)

# Health check
@app.get("/")
async def root():
    """Endpoint raíz - Health check"""
    return {
        "status": "online",
        "service": "Trading Portfolio Analytics API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check detallado"""
    return {
        "status": "healthy",
        "service": "Trading Portfolio Analytics",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Iniciando Trading Portfolio Analytics API...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
