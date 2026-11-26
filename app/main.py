import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .modulos import registrar
from .routers import admin, publico, sensible, usuaria

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(
    title="API · Canalización económica para mujeres",
    version="0.1.0",
    description="Documentación viva de los endpoints. Contratos acordados con el front.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins,
    allow_origin_regex=r"https://.*\.(vercel\.app|netlify\.app|onrender\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def tiempo(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    resp.headers["X-Tiempo-ms"] = f"{ms:.0f}"
    # Solo método, ruta y tiempo: nunca el cuerpo (puede traer datos sensibles)
    log.info("%s %s %s %.0fms", request.method, request.url.path, resp.status_code, ms)
    return resp


@app.exception_handler(Exception)
async def error_general(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Algo salió mal. Intenta de nuevo."})


app.include_router(publico.router)
app.include_router(usuaria.router)
app.include_router(sensible.router)
app.include_router(admin.router)

# Módulos M1–M7: cada carpeta de app/modulos/ con router.py se registra sola.
registrar(app)
