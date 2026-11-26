"""M7 · Datos públicos de la landing: empresas aliadas."""
from fastapi import APIRouter

from app.db import servicio

router = APIRouter(prefix="/publico", tags=["landing (M7)"])


def aliadas(filas: list[dict]) -> list[dict]:
    return sorted(({"nombre": f["nombre"], "logo_url": f["logo_url"]} for f in filas
                   if f.get("estado") == "aprobada" and f.get("logo_url")), key=lambda x: x["nombre"])


@router.get("/empresas-aliadas")
def empresas_aliadas():
    return aliadas(servicio().table("empresas").select("nombre,estado,logo_url").execute().data)
