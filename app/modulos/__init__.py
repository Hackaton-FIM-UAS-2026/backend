"""Registro automático de módulos.

Cada módulo vive en `app/modulos/<nombre>/` y expone `router: APIRouter` en
`router.py`. `main.py` llama `registrar(app)` y ya no se edita al agregar un
módulo: así cada rama solo toca su propia carpeta.
"""
import importlib
import logging
import os
import pkgutil
from pathlib import Path

from fastapi import APIRouter, FastAPI

log = logging.getLogger("modulos")


def registrar(app: FastAPI) -> list[str]:
    """Incluye el `router` de cada subpaquete con `router.py`. Regresa los nombres."""
    nombres = []
    en_prueba = os.getenv("EMPODERATE_TEST") == "1"
    for m in sorted(pkgutil.iter_modules([str(Path(__file__).parent)]), key=lambda m: m.name):
        if not m.ispkg or (m.name.startswith("_") and not en_prueba):
            continue
        if not (Path(__file__).parent / m.name / "router.py").exists():
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}.router")
        router = getattr(mod, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
            nombres.append(m.name)
            log.info("Módulo registrado: %s", m.name)
    return nombres
