"""Panel CEMujeres (M14) + roles y bitácora (M15).

Lecturas con el JWT de quien pide → RLS decide. Cada acceso a un expediente
queda en bitacora_accesos. Las respuestas tienen la forma de frontend/src/data/admin.js.
"""
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import servicios as sv
from ..auth import ESPECIALISTAS, PERSONAL, Sesion, con_rol
from ..db import como, servicio
from ..dominio import diccionario
from ..dominio.fusion import valores as valores_de
from ..dominio.motor_ruta import RUTAS
from ..ia import embeddings
from ..sensible import bitacora, cifrar, descifrar

router = APIRouter(prefix="/admin", tags=["panel"])

ASESORA = con_rol("asesora_economica")
CATALOGO = con_rol("asesora_economica", "coordinacion")
ESPECIALISTA = con_rol(*ESPECIALISTAS)
CUALQUIERA = con_rol(*PERSONAL)
COORD = con_rol("coordinacion")

TIPO_OUT = {"juridica": "Jurídica", "psicologica": "Psicológica", "ambas": "Ambas"}
ESTADOS_USUARIA = ["Nueva", "Inscrita", "En curso", "Contratada", "Curso terminado", "Negocio registrado", "Baja"]
# Campos que se muestran en la ficha (como en data/admin.js)
CAMPOS_FICHA = ["edad", "escolaridad", "horas_semana", "horario", "cuidados", "dispositivo", "negocio",
                "situacion", "meta", "habilidades", "documentos", "tiene_rfc", "habilidad_excel", "estado_programa"]


# ------------------------------------------------------------------ quién soy
@router.get("/yo")
def yo(s: Sesion = Depends(CUALQUIERA)):
    return {"id": s.user_id, "nombre": s.nombre_personal, "rol": s.rol}


# ------------------------------------------------------------------ usuarias
def _ficha(p: dict, exp: dict | None, historial: list | None = None) -> dict:
    exp = exp or {"campos": {}, "version": 0, "ruta": None}
    ruta = (exp.get("ruta") or {})
    campos = {}
    for c in CAMPOS_FICHA:
        if c in (exp.get("campos") or {}):
            v = exp["campos"][c]["valor"]
            campos[diccionario.etiqueta(c)] = ", ".join(v) if isinstance(v, list) else v
    return {
        "id": p["usuaria_id"],
        "nombre": p.get("nombre") or (p.get("correo") or "Sin nombre").split("@")[0],
        "contacto": {"telefono": p.get("telefono") or "", "correo": p.get("correo") or "",
                     "medio": p.get("medio_contacto") or "", "horario": p.get("horario_contacto") or ""},
        "ruta": (ruta.get("manual") or {}).get("principal") or ruta.get("principal"),
        "puente": (ruta.get("manual") or {}).get("puente") if ruta.get("manual") else ruta.get("puente"),
        "estado": p.get("estado_seguimiento") or "Nueva",
        "municipio": p.get("municipio") or "",
        "version": exp.get("version", 0),
        "ultima": sv.fecha_corta(p.get("updated_at")),
        "ultima_iso": p.get("updated_at"),
        "campos": campos,
        "conflictos": exp.get("conflictos") or [],
        "historial": historial or [],
    }


@router.get("/usuarias")
def usuarias(s: Sesion = Depends(ASESORA)):
    with como(s.token) as db:
        perfiles = db.from_("perfiles").select("*").order("updated_at", desc=True).limit(500).execute().data
        exps = db.from_("expedientes").select("usuaria_id,campos,ruta,version,conflictos").execute().data
    por_id = {e["usuaria_id"]: e for e in exps}
    bitacora(s.user_id, s.rol, "listar", "perfiles")
    return [_ficha(p, por_id.get(p["usuaria_id"])) for p in perfiles]


@router.get("/usuarias/{usuaria_id}")
def ficha(usuaria_id: str, s: Sesion = Depends(ASESORA)):
    with como(s.token) as db:
        p = db.from_("perfiles").select("*").eq("usuaria_id", usuaria_id).limit(1).execute().data
        if not p:
            raise HTTPException(404, "Usuaria no encontrada")
        exp = db.from_("expedientes").select("usuaria_id,campos,ruta,version,conflictos").eq("usuaria_id", usuaria_id).execute().data
        evs = db.from_("expediente_eventos").select("texto,fuente,created_at,version") \
            .eq("usuaria_id", usuaria_id).order("created_at", desc=True).limit(50).execute().data
        recs = db.from_("recursos_usuaria").select("recurso_id,estado,updated_at,recursos(titulo,tipo)") \
            .eq("usuaria_id", usuaria_id).execute().data
    bitacora(s.user_id, s.rol, "leer", "expedientes", usuaria_id, usuaria_id)
    historial = [{"fecha": sv.fecha_corta(e["created_at"]), "texto": e["texto"], "fuente": e["fuente"]} for e in evs]
    out = _ficha(p[0], exp[0] if exp else None, historial)
    out["recursos"] = [{"id": r["recurso_id"], "estado": r["estado"], "titulo": (r.get("recursos") or {}).get("titulo"),
                        "fecha": sv.fecha_corta(r["updated_at"])} for r in recs]
    return out


class SituacionIn(BaseModel):
    estado: str = Field(max_length=40)
    nota: str | None = Field(default=None, max_length=500)
    ruta: Literal["empleabilidad", "emprendimiento", "capacitacion"] | None = None
    puente: Literal["empleabilidad", "emprendimiento", "capacitacion"] | None = None
    motivo: str | None = Field(default=None, max_length=300)
    campos: dict[str, Any] | None = None   # datos que la asesora confirmó (fuente personal_cemujeres)


@router.post("/usuarias/{usuaria_id}/situacion")
def actualizar_situacion(usuaria_id: str, body: SituacionIn, s: Sesion = Depends(ASESORA)):
    """'Actualizar situación': entra al expediente con fuente personal_cemujeres y la versión sube.
    Si choca con algo que dijo ella, no se sobrescribe: queda en `conflictos`."""
    if body.ruta and not body.motivo:
        raise HTTPException(422, "Para cambiar la ruta escribe el motivo")
    nuevos = {"estado_programa": body.estado, **(body.campos or {})}
    exp = sv.aplicar_campos(s.token, usuaria_id, nuevos, "personal_cemujeres", autor=s.user_id)
    if body.ruta:
        ruta = {**(exp.get("ruta") or {}),
                "manual": {"principal": body.ruta, "puente": body.puente, "motivo": body.motivo,
                           "autor": s.user_id, "fecha": sv.ahora_iso()}}
        servicio().table("expedientes").update({"ruta": ruta}).eq("usuaria_id", usuaria_id).execute()
        sv.evento(usuaria_id, f"Asesora cambió la ruta a {body.ruta} — {body.motivo}", "personal_cemujeres",
                  s.user_id, exp["version"])
    servicio().table("perfiles").update({"estado_seguimiento": body.estado}).eq("usuaria_id", usuaria_id).execute()
    sv.evento(usuaria_id, f"Asesora registró: {body.estado.lower()}{f' — {body.nota}' if body.nota else ''}",
              "personal_cemujeres", s.user_id, exp["version"])
    bitacora(s.user_id, s.rol, "actualizar", "expedientes", usuaria_id, usuaria_id)
    return ficha(usuaria_id, s)


class ContactoIn(BaseModel):
    medio: str = Field(max_length=40)
    resultado: str = Field(max_length=60)
    nota: str | None = Field(default=None, max_length=500)


@router.post("/usuarias/{usuaria_id}/contactos")
def registrar_contacto(usuaria_id: str, body: ContactoIn, s: Sesion = Depends(ASESORA)):
    exp = sv.leer_expediente(s.token, usuaria_id)  # confirma permiso vía RLS
    texto = f"Contacto por {body.medio.lower()}: {body.resultado.lower()}{f' — {body.nota}' if body.nota else ''}"
    sv.evento(usuaria_id, texto, "personal_cemujeres", s.user_id, exp["version"])
    with como(s.token) as db:
        p = db.from_("perfiles").select("estado_seguimiento").eq("usuaria_id", usuaria_id).execute().data
    if p and p[0]["estado_seguimiento"] == "Nueva" and body.resultado == "Contestó":
        servicio().table("perfiles").update({"estado_seguimiento": "Inscrita"}).eq("usuaria_id", usuaria_id).execute()
    else:
        servicio().table("perfiles").update({"updated_at": sv.ahora_iso()}).eq("usuaria_id", usuaria_id).execute()
    bitacora(s.user_id, s.rol, "actualizar", "expediente_eventos", usuaria_id, usuaria_id)
    return ficha(usuaria_id, s)


# ------------------------------------------------------------------ catálogo
class RequisitoIn(BaseModel):
    campo: str
    label: str = Field(min_length=1, max_length=120)
    duro: bool = False
    op: str | None = None
    valor: Any = None
    ok: Any = None  # el editor del front lo manda; se ignora


class RecursoIn(BaseModel):
    id: str | None = None
    titulo: str = Field(min_length=2, max_length=200)
    proveedor: str = Field(min_length=2, max_length=200)
    tipo: Literal["curso", "vacante", "beca", "apoyo", "financiamiento"] = "vacante"
    rutas: list[Literal["empleabilidad", "emprendimiento", "capacitacion"]] = ["empleabilidad"]
    modalidad: str | None = None
    horario: str | None = None
    horas_semana: int | None = Field(default=None, ge=1, le=60)
    costo: str | None = None
    ubicacion: str | None = None
    municipios: list[str] = []
    fecha_cierre: str | None = None
    requisitos: list[RequisitoIn] = []
    descripcion: str | None = None
    url_accion: str | None = "#"
    publicada: bool = True


@router.get("/recursos")
def catalogo(s: Sesion = Depends(CUALQUIERA)):
    return [sv.recurso_publico(r) for r in sv.leer_catalogo(s.token)]


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower())[:40].strip("-")


@router.post("/recursos")
def guardar_recurso(body: RecursoIn, s: Sesion = Depends(CATALOGO)):
    """Crea (sin id) o actualiza (con id). Recalcula el embedding."""
    d = body.model_dump()
    d["requisitos"] = [{k: v for k, v in r.items() if k != "ok"} for r in d["requisitos"]]
    nuevo = not d.get("id")
    d["id"] = d.get("id") or f"o-{_slug(body.titulo)}-{sv.ahora_iso()[11:19].replace(':', '')}"
    d["verificado_el"] = sv.ahora_iso()[:7]
    d["actualizada_el"] = sv.ahora_iso()
    if not d.get("fecha_cierre"):
        d["fecha_cierre"] = None
    v = embeddings.embed(embeddings.texto_recurso(d))
    if v:
        d["embedding"] = embeddings.como_texto(v)
    guardado = servicio().table("recursos").upsert(d).execute().data[0]
    bitacora(s.user_id, s.rol, "crear" if nuevo else "actualizar", "recursos", d["id"])
    guardado.pop("embedding", None)
    return sv.recurso_publico(guardado)


class PublicacionIn(BaseModel):
    publicada: bool


@router.patch("/recursos/{recurso_id}/publicacion")
def publicar(recurso_id: str, body: PublicacionIn, s: Sesion = Depends(CATALOGO)):
    r = servicio().table("recursos").update({"publicada": body.publicada, "actualizada_el": sv.ahora_iso()}) \
        .eq("id", recurso_id).execute().data
    if not r:
        raise HTTPException(404, "No existe ese recurso")
    bitacora(s.user_id, s.rol, "actualizar", "recursos", recurso_id)
    r[0].pop("embedding", None)
    return sv.recurso_publico(r[0])


# ------------------------------------------------------------------ canalizaciones
def _caso(c: dict, sensible: dict | None) -> dict:
    contacto = (sensible or {}).get("contacto") or {}
    return {
        "id": c["folio"],
        "uuid": c["id"],
        "usuaria": f"Usuaria {c['folio']}",   # anónima en la bandeja
        "urgencia": c["urgencia"],
        "tipo": TIPO_OUT[c["tipo"]],
        "medio": contacto.get("medio", ""),
        "horario": contacto.get("horario", ""),
        "estado": c["estado"],
        "fecha": sv.fecha_corta(c["created_at"]),
        "asignada_a": c.get("asignada_a"),
    }


_ORDEN_URG = {"inmediata": 0, "pronta": 1, "informativa": 2}


@router.get("/canalizaciones")
def bandeja(s: Sesion = Depends(ESPECIALISTA)):
    """Tarjetas ordenadas por urgencia. RLS filtra por tipo según el rol."""
    with como(s.token) as db:
        casos = db.from_("canalizaciones").select("*").order("created_at", desc=True).execute().data
        ids = list({c["usuaria_id"] for c in casos})
        sens = db.from_("expedientes_sensibles").select("usuaria_id,datos_cifrados") \
            .in_("usuaria_id", ids).execute().data if ids else []
    datos = {x["usuaria_id"]: descifrar(x["datos_cifrados"]) for x in sens}
    bitacora(s.user_id, s.rol, "listar", "canalizaciones")
    out = [_caso(c, datos.get(c["usuaria_id"])) for c in casos]
    return sorted(out, key=lambda c: (c["estado"] == "cerrada", _ORDEN_URG.get(c["urgencia"], 9)))


@router.get("/canalizaciones/{folio}")
def caso(folio: str, s: Sesion = Depends(ESPECIALISTA)):
    with como(s.token) as db:
        c = db.from_("canalizaciones").select("*").eq("folio", folio).limit(1).execute().data
        if not c:
            raise HTTPException(404, "Caso no encontrado")
        sens = db.from_("expedientes_sensibles").select("datos_cifrados,consentimiento_at") \
            .eq("usuaria_id", c[0]["usuaria_id"]).execute().data
        notas = db.from_("canalizacion_notas").select("nota_cifrada,created_at,autor") \
            .eq("canalizacion_id", c[0]["id"]).order("created_at").execute().data
    datos = descifrar(sens[0]["datos_cifrados"]) if sens else {}
    bitacora(s.user_id, s.rol, "leer", "expedientes_sensibles", folio, c[0]["usuaria_id"])
    return {**_caso(c[0], datos), "contacto": (datos or {}).get("contacto"), "resumen": (datos or {}).get("resumen"),
            "consentimiento": sens[0]["consentimiento_at"] if sens else None,
            "notas": [{"texto": descifrar(n["nota_cifrada"], como_json=False), "fecha": sv.fecha_corta(n["created_at"])}
                      for n in notas]}


class CasoIn(BaseModel):
    estado: Literal["nueva", "contactada", "en atención", "cerrada"] | None = None
    nota: str | None = Field(default=None, max_length=1000)
    asignar_a_mi: bool = False


@router.patch("/canalizaciones/{folio}")
def actualizar_caso(folio: str, body: CasoIn, s: Sesion = Depends(ESPECIALISTA)):
    with como(s.token) as db:  # si RLS no la deja verlo, no lo puede tocar
        c = db.from_("canalizaciones").select("id").eq("folio", folio).limit(1).execute().data
    if not c:
        raise HTTPException(404, "Caso no encontrado")
    cambios = {}
    if body.estado:
        cambios["estado"] = body.estado
    if body.asignar_a_mi:
        cambios["asignada_a"] = s.user_id
    if cambios:
        servicio().table("canalizaciones").update(cambios).eq("id", c[0]["id"]).execute()
    if body.nota:
        servicio().table("canalizacion_notas").insert(
            {"canalizacion_id": c[0]["id"], "autor": s.user_id, "nota_cifrada": cifrar(body.nota)}).execute()
    bitacora(s.user_id, s.rol, "actualizar", "canalizaciones", folio)
    return caso(folio, s)


# ------------------------------------------------------------------ métricas y bitácora
@router.get("/metricas")
def metricas(s: Sesion = Depends(CUALQUIERA)):
    with como(s.token) as db:
        return db.rpc("metricas", {}).execute().data


@router.get("/bitacora")
def ver_bitacora(s: Sesion = Depends(COORD)):
    with como(s.token) as db:
        return db.from_("bitacora_accesos").select("*").order("created_at", desc=True).limit(200).execute().data
