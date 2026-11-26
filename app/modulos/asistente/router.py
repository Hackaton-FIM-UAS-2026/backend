"""M2 · Asistente de SEMujeres (equipo de agentes) y canalización desde el chat."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import servicios as sv
from app.auth import Sesion, usuaria
from app.db import servicio
from app.ia import claude
from app.sensible import bitacora, cifrar

from .agentes import responder

router = APIRouter(prefix="/asistente", tags=["asistente (M2)"])


class Turno(BaseModel):
    rol: Literal["usuaria", "asistente"]
    texto: str = Field(max_length=2000)


class MensajeIn(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1000)
    historial: list[Turno] = Field(default_factory=list, max_length=10)


def _llm(system: str, mensaje: str, schema: dict) -> dict | None:
    return claude.usar_herramienta(system, mensaje, "responder", "Respuesta estructurada del agente.", schema,
                                   max_tokens=500)


def _contexto(s: Sesion) -> dict:
    filas = (servicio().table("recursos").select("id,titulo,tipo,proveedor,horario,modalidad,etiquetas")
             .eq("publicada", True).eq("estado_revision", "aprobada").execute().data)
    catalogo = {r["id"]: r for r in filas}
    try:
        rec = sv.recomendaciones(s.token, s.user_id)
        recomendados = [r["id"] for r in rec.get("recursos", []) if r["id"] in catalogo]
    except HTTPException:
        recomendados = []
    return {"recomendados": recomendados, "catalogo": catalogo}


@router.post("/mensaje")
def mensaje(body: MensajeIn, s: Sesion = Depends(usuaria)):
    """La conversación no se guarda: solo se procesa y se responde."""
    return responder(body.mensaje, [t.model_dump() for t in body.historial], _contexto(s), _llm)


class ContactoIn(BaseModel):
    medio: str = Field(max_length=40)
    horario: str = Field(default="", max_length=80)
    mensaje: bool = False


class CanalizarIn(BaseModel):
    area: Literal["juridica", "psicologica", "ambas", "no_se"]
    resumen: str = Field(min_length=1, max_length=600)
    urgencia: Literal["inmediata", "pronta", "informativa"] = "pronta"
    contacto: ContactoIn
    consentimiento: bool


@router.post("/canalizar")
def canalizar(body: CanalizarIn, s: Sesion = Depends(usuaria)):
    if body.consentimiento is not True:
        raise HTTPException(400, "Sin tu consentimiento no guardamos nada.")
    sb = servicio()
    ahora = sv.ahora_iso()
    previo = sb.table("expedientes_sensibles").select("version").eq("usuaria_id", s.user_id).execute().data
    sb.table("expedientes_sensibles").upsert({
        "usuaria_id": s.user_id,
        "datos_cifrados": cifrar({"tipo": body.area, "resumen": body.resumen, "contacto": body.contacto.model_dump()}),
        "version": (previo[0]["version"] + 1) if previo else 1, "consentimiento_at": ahora,
    }).execute()
    caso = sb.table("canalizaciones").insert({
        "usuaria_id": s.user_id, "tipo": body.area, "urgencia": body.urgencia,
        "estado": "nueva", "origen": "asistente"}).execute().data[0]
    sb.table("expediente_eventos").insert({
        "usuaria_id": s.user_id, "version": 0, "fuente": "usuaria", "area": "trabajo_social",
        "texto": f"Pidió apoyo a SEMujeres desde el asistente (folio {caso['folio']})",
        "texto_publico": "Pidió apoyo a SEMujeres"}).execute()
    bitacora(s.user_id, None, "crear", "canalizaciones", caso["folio"], s.user_id)
    return {"folio": caso["folio"]}


class VisitaIn(BaseModel):
    fecha: date
    franja: Literal["mañana", "tarde"]
    modulo: Literal["trabajo_social", "juridico", "psicologia", "economico"] = "trabajo_social"


@router.post("/visita")
def visita(body: VisitaIn, s: Sesion = Depends(usuaria)):
    if body.fecha < date.today():
        raise HTTPException(422, "Elige un día de hoy en adelante.")
    fila = servicio().table("visitas").insert({
        "usuaria_id": s.user_id, "fecha": body.fecha.isoformat(), "franja": body.franja,
        "modulo": body.modulo, "origen": "asistente"}).execute().data[0]
    return {"id": fila["id"]}
