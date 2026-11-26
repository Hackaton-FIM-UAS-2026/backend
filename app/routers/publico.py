from fastapi import APIRouter

from .. import servicios as sv
from ..dominio import diccionario

router = APIRouter(tags=["público"])


@router.get("/salud")
def salud():
    """Para despertar el servidor antes de la demo (Render se duerme)."""
    return {"ok": True}


@router.get("/diccionario")
def ver_diccionario():
    """Test base, preguntas de entrevista y etiquetas. Una sola fuente de verdad."""
    return diccionario.publico()


@router.get("/recursos")
def recursos_publicos():
    """Catálogo publicado, sin evaluar (para quien todavía no se registra)."""
    return [sv.recurso_publico(r) for r in sv.leer_catalogo(None)]
