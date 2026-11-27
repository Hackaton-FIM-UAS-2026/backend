"""M5 · Recepción: visitas previstas (quién llega, cuándo y a qué módulo)."""
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


class LlegadaIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    curp: str = Field(pattern=r"^[A-Za-z]{4}\d{6}[HMXhmx][A-Za-z]{5}[A-Za-z0-9]\d$")
    telefono: str | None = Field(default=None, max_length=20)


@router.post("/llegada")
def llegada(body: LlegadaIn, s: Sesion = Depends(MARCAR)):
    """Recepción registra a una mujer que llegó sin cita: abre (o encuentra) su expediente por CURP y la
    manda a Trabajo Social, que valora y decide el área. Recepción no ve ni pregunta el motivo."""
    from app.modulos.expediente.router import abrir_o_crear
    if len(body.nombre.split()) < 2:
        raise HTTPException(422, "Escribe su nombre completo.")
    uid, existia = abrir_o_crear(" ".join(body.nombre.split()), body.curp, body.telefono, s.user_id, s.rol)
    sb = servicio()
    abierta = sb.table("canalizaciones").select("folio").eq("usuaria_id", uid).eq("estado", "nueva").limit(1).execute().data
    folio = abierta[0]["folio"] if abierta else sb.table("canalizaciones").insert(
        {"usuaria_id": uid, "tipo": "no_se", "urgencia": "pronta", "estado": "nueva", "origen": "persona"}).execute().data[0]["folio"]
    sb.table("visitas").insert({"usuaria_id": uid, "fecha": date.today().isoformat(), "franja": "mañana" if __import__("datetime").datetime.now().hour < 13 else "tarde",
                                "modulo": "trabajo_social", "estado": "llego", "origen": "personal"}).execute()
    bitacora(s.user_id, s.rol, "crear", "canalizaciones", folio, uid)
    return {"folio": folio, "existente": existia}
