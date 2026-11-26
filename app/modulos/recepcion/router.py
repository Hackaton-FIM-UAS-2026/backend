"""M5 · Recepción: visitas previstas (quién llega, cuándo y a qué módulo)."""
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import Sesion, con_rol
from app.db import servicio
from app.sensible import bitacora

from .vista import fila_visita, ordenar

router = APIRouter(prefix="/panel/visitas", tags=["recepción (M5)"])
LEER = con_rol("recepcion", "trabajo_social", "coordinacion")
MARCAR = con_rol("recepcion")


@router.get("")
def visitas(cuando: Literal["hoy", "proximos"] = "hoy", s: Sesion = Depends(LEER)):
    hoy = date.today()
    q = servicio().table("visitas").select("id,usuaria_id,fecha,franja,modulo,estado")
    q = q.eq("fecha", hoy.isoformat()) if cuando == "hoy" else \
        q.gt("fecha", hoy.isoformat()).lte("fecha", (hoy + timedelta(days=14)).isoformat())
    filas = q.execute().data
    ids = list({v["usuaria_id"] for v in filas})
    nombres = {p["usuaria_id"]: p["nombre"] for p in (servicio().table("perfiles").select("usuaria_id,nombre")
                                                       .in_("usuaria_id", ids).execute().data if ids else [])}
    bitacora(s.user_id, s.rol, "listar", "visitas")
    return [fila_visita(v, nombres.get(v["usuaria_id"]) or "Sin nombre") for v in ordenar(filas)]


class MarcarIn(BaseModel):
    estado: Literal["llego", "no_vino", "por_llegar"]


@router.patch("/{visita_id}")
def marcar(visita_id: int, body: MarcarIn, s: Sesion = Depends(MARCAR)):
    r = servicio().table("visitas").update({"estado": body.estado}).eq("id", visita_id).execute().data
    if not r:
        raise HTTPException(404, "Visita no encontrada")
    bitacora(s.user_id, s.rol, "actualizar", "visitas", str(visita_id))
    return {"id": visita_id, "estado": body.estado}
