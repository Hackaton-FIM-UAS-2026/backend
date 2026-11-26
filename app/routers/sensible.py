"""Chat del agente (M12) y canalización jurídica/psicológica (M13).

Reglas del documento de diseño:
  * Nunca se pregunta de entrada; solo cuando ella lo plantea.
  * Claude solo clasifica y PROPONE; ella decide. Si no acepta, no se guarda nada.
  * La conversación NO se guarda ni se registra en logs.
  * Peligro inmediato: emergencia sin formularios.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import servicios as sv
from ..auth import Sesion, usuaria
from ..db import como, servicio
from ..dominio.motor_ruta import NOMBRE_RUTA
from ..ia import claude
from ..ia.plantillas import CONTACTO_EMERGENCIA, PLANTILLAS, combinar, senal_por_palabras
from ..sensible import bitacora, cifrar

router = APIRouter(tags=["chat y canalización"])

TIPO_IN = {"Orientación jurídica": "juridica", "Apoyo psicológico": "psicologica", "Ambas": "ambas",
           "juridica": "juridica", "psicologica": "psicologica", "ambas": "ambas"}


class MensajeIn(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)


class Contacto(BaseModel):
    medio: Literal["Llamada", "Mensaje de texto", "Solo dentro de la app"]
    horario: str = Field(default="", max_length=120)
    mensaje: Literal["si", ""] = ""          # ¿se puede dejar mensaje?
    telefono_seguro: str | None = Field(default=None, max_length=30)


class CanalizacionIn(BaseModel):
    tipo: str                                 # "Orientación jurídica" | "Apoyo psicológico" | "Ambas"
    contacto: Contacto
    consentimiento: bool
    resumen: str | None = Field(default=None, max_length=600)   # solo si ella lo aprueba
    urgencia: Literal["inmediata", "pronta", "informativa"] = "pronta"


@router.get("/emergencia")
def emergencia():
    """Público y sin sesión: el atajo de peligro inmediato no pide nada."""
    return CONTACTO_EMERGENCIA


@router.post("/chat")
def chat(body: MensajeIn, s: Sesion = Depends(usuaria)):
    senal = combinar(claude.clasificar_senal(body.mensaje), senal_por_palabras(body.mensaje))

    if senal["urgencia"] == "inmediata":
        return {"respuesta": PLANTILLAS["inmediata"], "senal": senal, "proponer_canalizacion": True,
                "emergencia": CONTACTO_EMERGENCIA, "recurso_ids": []}
    if senal["tipo"] != "ninguna":
        return {"respuesta": PLANTILLAS["propuesta"], "senal": senal, "proponer_canalizacion": True,
                "emergencia": None, "recurso_ids": []}

    # Chat económico: contexto = su ruta + sus recursos (la IA no puede mencionar otros)
    try:
        rec = sv.recomendaciones(s.token, s.user_id)
        contexto = {
            "ruta": NOMBRE_RUTA[rec["ruta"]["principal"]],
            "puente": NOMBRE_RUTA.get(rec["ruta"].get("puente")),
            "recursos": [{"id": r["id"], "titulo": r["titulo"], "tipo": r["tipo"], "modalidad": r.get("modalidad"),
                          "horario": r.get("horario")} for r in rec["recursos"]],
        }
    except HTTPException:
        contexto = {"recursos": []}
    out = claude.responder_chat(body.mensaje, contexto)
    return {"respuesta": out["texto"] if out else PLANTILLAS["economica_respaldo"], "senal": senal,
            "proponer_canalizacion": False, "emergencia": None, "recurso_ids": out["recurso_ids"] if out else []}


@router.post("/me/canalizaciones")
def canalizar(body: CanalizacionIn, s: Sesion = Depends(usuaria)):
    if not body.consentimiento:
        raise HTTPException(400, "Sin tu consentimiento no guardamos nada.")
    tipo = TIPO_IN.get(body.tipo)
    if not tipo:
        raise HTTPException(422, "Tipo de apoyo no válido")

    ahora = sv.ahora_iso()
    datos = {"contacto": body.contacto.model_dump(), "resumen": body.resumen, "tipo": tipo}
    previo = servicio().table("expedientes_sensibles").select("version").eq("usuaria_id", s.user_id).execute().data
    servicio().table("expedientes_sensibles").upsert({
        "usuaria_id": s.user_id, "datos_cifrados": cifrar(datos),
        "version": (previo[0]["version"] + 1) if previo else 1, "consentimiento_at": ahora,
    }).execute()
    caso = servicio().table("canalizaciones").insert(
        {"usuaria_id": s.user_id, "tipo": tipo, "urgencia": body.urgencia}).execute().data[0]
    bitacora(s.user_id, None, "crear", "canalizaciones", caso["folio"], s.user_id)
    # Notificación neutra: nunca el tema
    return {"folio": caso["folio"], "estado": caso["estado"], "mensaje": "Recibimos tu solicitud. Tienes una actualización pendiente."}


@router.get("/me/canalizaciones")
def mis_canalizaciones(s: Sesion = Depends(usuaria)):
    with como(s.token) as db:
        filas = db.from_("canalizaciones").select("folio,estado,created_at,updated_at") \
            .eq("usuaria_id", s.user_id).order("created_at", desc=True).execute().data
    return [{"folio": f["folio"], "estado": f["estado"], "fecha": sv.fecha_corta(f["updated_at"])} for f in filas]


@router.delete("/me/expediente-sensible")
def borrar_sensible(s: Sesion = Depends(usuaria)):
    """Ella puede borrar su expediente sensible y sus casos cuando quiera."""
    servicio().table("canalizaciones").delete().eq("usuaria_id", s.user_id).execute()
    servicio().table("expedientes_sensibles").delete().eq("usuaria_id", s.user_id).execute()
    bitacora(s.user_id, None, "borrar", "expedientes_sensibles", None, s.user_id)
    return {"ok": True}
