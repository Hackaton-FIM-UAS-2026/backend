"""M6 · Empresas: registro, vacantes con revisión humana, candidatas con perfil limitado."""
import secrets
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import servicios as sv
from app.auth import Sesion, con_rol, empresa, sesion
from app.db import servicio
from app.ia import claude
from app.sensible import bitacora

from .reglas import alerta, perfil_laboral, publicable

router = APIRouter(tags=["empresas (M6)"])
REVISA = con_rol("asesora_economica", "coordinacion")
CAMPOS_VACANTE = "id,titulo,descripcion,horario,sueldo,ubicacion,requisitos,estado_revision,motivo_revision,alerta_ia,publicada,creada_el,empresa_id"


def _llm(system, mensaje, schema):
    return claude.usar_herramienta(system, mensaje, "revisar", "Señales de la vacante.", schema, max_tokens=200)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- empresa
class RegistroIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    rfc: str = Field(pattern=r"^[A-Za-zÑñ&]{3,4}\d{6}[A-Za-z0-9]{3}$")
    giro: str = Field(min_length=2, max_length=80)
    contacto_nombre: str = Field(min_length=2, max_length=120)
    telefono: str = Field(min_length=7, max_length=20)
    logo_url: str | None = Field(default=None, max_length=500)


@router.post("/empresas/registro")
def registro(body: RegistroIn, s: Sesion = Depends(sesion)):
    if s.rol:
        raise HTTPException(403, "Las cuentas del personal no registran empresas")
    if s.empresa_id:
        raise HTTPException(409, "Esta cuenta ya tiene una empresa registrada")
    sb = servicio()
    fila = sb.table("empresas").insert({**body.model_dump(), "rfc": body.rfc.upper(), "user_id": s.user_id,
                                        "correo": s.correo, "estado": "pendiente"}).execute().data[0]
    sb.table("perfiles").delete().eq("usuaria_id", s.user_id).execute()  # no es usuaria
    return {"id": fila["id"], "estado": fila["estado"]}


@router.get("/empresas/yo")
def yo(s: Sesion = Depends(empresa)):
    e = servicio().table("empresas").select("id,nombre,estado,motivo,logo_url,giro,contacto_nombre,telefono,rfc") \
        .eq("id", s.empresa_id).limit(1).execute().data
    if not e:
        raise HTTPException(404, "Empresa no encontrada")
    return e[0]


@router.get("/empresas/vacantes")
def mis_vacantes(s: Sesion = Depends(empresa)):
    sb = servicio()
    vac = sb.table("recursos").select(CAMPOS_VACANTE).eq("empresa_id", s.empresa_id).order("creada_el", desc=True).execute().data
    ids = [v["id"] for v in vac]
    post = sb.table("recursos_usuaria").select("recurso_id").in_("recurso_id", ids or ["-"]) \
        .in_("estado", ["aplicado", "contratada"]).execute().data
    cuenta = {}
    for p in post:
        cuenta[p["recurso_id"]] = cuenta.get(p["recurso_id"], 0) + 1
    return [{**{k: v[k] for k in ("id", "titulo", "horario", "sueldo", "ubicacion", "estado_revision", "motivo_revision")},
             "candidatas": cuenta.get(v["id"], 0)} for v in vac]


ESCOLARIDAD = ("Primaria", "Secundaria", "Preparatoria", "Universidad")


class VacanteIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=100)
    descripcion: str = Field(min_length=10, max_length=1200)
    horario: Literal["Mañanas", "Tardes", "Noches", "Fines de semana", "Flexible"]
    sueldo: str = Field(min_length=2, max_length=60)
    ubicacion: str = Field(min_length=2, max_length=120)
    escolaridad_minima: Literal["Primaria", "Secundaria", "Preparatoria", "Universidad"] | None = None
    documentos: list[Literal["CURP", "INE", "RFC", "Cuenta bancaria"]] = Field(default_factory=list)


def requisitos_de(body: VacanteIn) -> list[dict]:
    req = [{"campo": "edad", "op": ">=", "valor": "18 a 24", "duro": True, "label": "Ser mayor de 18"}]
    if body.escolaridad_minima:
        req.append({"campo": "escolaridad", "op": ">=", "valor": body.escolaridad_minima, "duro": True,
                    "label": f"{body.escolaridad_minima} terminada"})
    if body.documentos:
        req.append({"campo": "documentos", "op": "contains", "valor": body.documentos, "duro": False,
                    "label": "Tener " + ", ".join(body.documentos)})
    return req


@router.post("/empresas/vacantes")
def crear_vacante(body: VacanteIn, s: Sesion = Depends(empresa)):
    sb = servicio()
    emp = sb.table("empresas").select("nombre,estado").eq("id", s.empresa_id).limit(1).execute().data[0]
    v = {
        "id": f"e-{secrets.token_hex(4)}", "titulo": body.titulo, "descripcion": body.descripcion, "proveedor": emp["nombre"],
        "tipo": "vacante", "rutas": ["empleabilidad"], "modalidad": "Presencial", "horario": body.horario,
        "costo": "Sueldo", "sueldo": body.sueldo, "ubicacion": body.ubicacion, "municipios": ["Ahome"],
        "requisitos": requisitos_de(body), "url_accion": "#", "verificado_el": date.today().strftime("%Y-%m"),
        "empresa_id": s.empresa_id, "estado_revision": "pendiente", "publicada": False,
        "etiquetas": {"pide": ["edad"], "da": [], "temas": []},
    }
    v["alerta_ia"] = alerta(v, _llm)
    sb.table("recursos").insert(v).execute()
    return {"id": v["id"], "estado_revision": "pendiente"}


def _vacante_propia(vacante_id: str, s: Sesion) -> dict:
    v = servicio().table("recursos").select("id,empresa_id").eq("id", vacante_id).limit(1).execute().data
    if not v or v[0]["empresa_id"] != s.empresa_id:
        raise HTTPException(404, "Vacante no encontrada")
    return v[0]


@router.get("/empresas/vacantes/{vacante_id}/candidatas")
def candidatas(vacante_id: str, s: Sesion = Depends(empresa)):
    _vacante_propia(vacante_id, s)
    sb = servicio()
    post = sb.table("recursos_usuaria").select("usuaria_id,estado").eq("recurso_id", vacante_id) \
        .in_("estado", ["aplicado", "contratada"]).execute().data
    ids = [p["usuaria_id"] for p in post] or ["00000000-0000-0000-0000-000000000000"]
    perfiles = {p["usuaria_id"]: p for p in sb.table("perfiles").select("usuaria_id,nombre,telefono").in_("usuaria_id", ids).execute().data}
    exps = {e["usuaria_id"]: sv.valores_de({"campos": e["campos"] or {}})
            for e in sb.table("expedientes").select("usuaria_id,campos").in_("usuaria_id", ids).execute().data}
    return [{**perfil_laboral(perfiles.get(p["usuaria_id"], {}), exps.get(p["usuaria_id"], {})),
             "usuaria_id": p["usuaria_id"], "estado": p["estado"]} for p in post]


class ContratadaIn(BaseModel):
    estado: Literal["contratada"]


@router.patch("/empresas/vacantes/{vacante_id}/candidatas/{usuaria_id}")
def contratada(vacante_id: str, usuaria_id: str, body: ContratadaIn, s: Sesion = Depends(empresa)):
    _vacante_propia(vacante_id, s)
    r = servicio().table("recursos_usuaria").update({"estado": body.estado, "updated_at": _ahora()}) \
        .eq("recurso_id", vacante_id).eq("usuaria_id", usuaria_id).execute().data
    if not r:
        raise HTTPException(404, "Esa candidata no aplicó a esta vacante")
    sv.evento(usuaria_id, "¡La contrataron!", "empresa")
    return {"estado": body.estado}


# ---------------------------------------------------------------- revisión (personal)
@router.get("/panel/revision")
def pendientes(s: Sesion = Depends(REVISA)):
    sb = servicio()
    emps = sb.table("empresas").select("id,nombre,rfc,giro,contacto_nombre,telefono,correo,logo_url,estado,created_at") \
        .eq("estado", "pendiente").order("created_at").execute().data
    vac = sb.table("recursos").select(CAMPOS_VACANTE).eq("estado_revision", "pendiente").not_.is_("empresa_id", "null") \
        .order("creada_el").execute().data
    nombres = {e["id"]: e for e in sb.table("empresas").select("id,nombre,estado")
               .in_("id", list({v["empresa_id"] for v in vac}) or ["00000000-0000-0000-0000-000000000000"]).execute().data}
    return {
        "empresas": emps,
        "vacantes": [{**v, "empresa": nombres.get(v["empresa_id"], {}).get("nombre"),
                      "empresa_estado": nombres.get(v["empresa_id"], {}).get("estado")} for v in vac],
    }


class DecisionIn(BaseModel):
    decision: Literal["aprobar", "rechazar"]
    motivo: str | None = Field(default=None, max_length=400)


def _motivo(body: DecisionIn) -> str | None:
    if body.decision == "rechazar" and not (body.motivo or "").strip():
        raise HTTPException(422, "Escribe el motivo para que la empresa sepa qué corregir.")
    return (body.motivo or "").strip() or None


@router.post("/panel/revision/empresas/{empresa_id}")
def revisar_empresa(empresa_id: str, body: DecisionIn, s: Sesion = Depends(REVISA)):
    motivo = _motivo(body)
    sb = servicio()
    estado = "aprobada" if body.decision == "aprobar" else "rechazada"
    r = sb.table("empresas").update({"estado": estado, "motivo": motivo, "revisada_por": s.user_id,
                                     "revisada_el": _ahora()}).eq("id", empresa_id).execute().data
    if not r:
        raise HTTPException(404, "Empresa no encontrada")
    # Sus vacantes ya aprobadas se publican (o se retiran) según la empresa
    for v in sb.table("recursos").select("id,estado_revision").eq("empresa_id", empresa_id).execute().data:
        sb.table("recursos").update({"publicada": publicable(v, {"estado": estado})}).eq("id", v["id"]).execute()
    bitacora(s.user_id, s.rol, "actualizar", "empresas", empresa_id)
    return {"id": empresa_id, "estado": estado}


@router.post("/panel/revision/vacantes/{vacante_id}")
def revisar_vacante(vacante_id: str, body: DecisionIn, s: Sesion = Depends(REVISA)):
    motivo = _motivo(body)
    sb = servicio()
    v = sb.table("recursos").select("id,empresa_id").eq("id", vacante_id).limit(1).execute().data
    if not v or not v[0]["empresa_id"]:
        raise HTTPException(404, "Vacante no encontrada")
    emp = sb.table("empresas").select("estado").eq("id", v[0]["empresa_id"]).limit(1).execute().data[0]
    estado = "aprobada" if body.decision == "aprobar" else "rechazada"
    sb.table("recursos").update({"estado_revision": estado, "motivo_revision": motivo, "revisada_por": s.user_id,
                                 "publicada": publicable({"estado_revision": estado}, emp)}).eq("id", vacante_id).execute()
    bitacora(s.user_id, s.rol, "actualizar", "recursos", vacante_id)
    return {"id": vacante_id, "estado_revision": estado, "publicada": publicable({"estado_revision": estado}, emp)}
