"""M4 · Expediente único por mujer (CURP), Trabajo Social y especialistas."""
import re
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import servicios as sv
from app.auth import Sesion, con_rol
from app.db import servicio
from app.dominio import diccionario
from app.sensible import bitacora, cifrar, descifrar

from .permisos import CONFIDENCIALES, area_de_rol, franja_de, ocultar_curp, puede_abrir, vista_expediente

router = APIRouter(prefix="/panel", tags=["expediente (M4)"])

TS = con_rol("trabajo_social")
CASOS = con_rol("trabajo_social", "especialista_juridica", "especialista_psicologica")
LECTORES = con_rol("trabajo_social", "especialista_juridica", "especialista_psicologica", "asesora_economica", "coordinacion")
NOTAS = CASOS

ORDEN_URG = {"inmediata": 0, "pronta": 1, "informativa": 2}
AREA_TEXTO = {"juridica": "jurídica", "psicologica": "psicológica", "ambas": "jurídica y psicológica"}
AREA_EVENTO = {"juridica": "juridico", "psicologica": "psicologia", "ambas": "trabajo_social"}
GENERALES = ("edad", "municipio", "municipio_otro", "escolaridad", "cuidados", "horas_semana", "dispositivo")
ESPECIALIDAD = {"especialista_juridica": {"juridica", "ambas"}, "especialista_psicologica": {"psicologica", "ambas"}}


def hace(iso: str | None) -> str:
    if not iso:
        return ""
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    m = int((datetime.now(timezone.utc) - d).total_seconds() // 60)
    if m < 60:
        return f"{max(m, 1)} min"
    if m < 60 * 24:
        return f"{m // 60} h"
    return f"{m // (60 * 24)} d"


def legible(campo: str, valor) -> tuple[str, str]:
    etq = diccionario.CAMPOS.get(campo, {}).get("etiqueta", campo.replace("_", " ").capitalize())
    return etq, ", ".join(valor) if isinstance(valor, list) else str(valor)


def _nombres(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    filas = servicio().table("perfiles").select("usuaria_id,nombre,curp,colonia,municipio").in_("usuaria_id", ids).execute().data
    return {f["usuaria_id"]: f for f in filas}


@router.get("/solicitudes")
def solicitudes(s: Sesion = Depends(TS)):
    casos = servicio().table("canalizaciones").select("folio,usuaria_id,origen,urgencia,created_at") \
        .eq("estado", "nueva").execute().data
    per = _nombres(list({c["usuaria_id"] for c in casos}))
    bitacora(s.user_id, s.rol, "listar", "canalizaciones")
    out = [{"folio": c["folio"], "usuaria_id": c["usuaria_id"], "nombre": (per.get(c["usuaria_id"]) or {}).get("nombre") or "Sin nombre",
            "origen": c["origen"], "urgencia": c["urgencia"], "hace": hace(c["created_at"]), "_t": c["created_at"]} for c in casos]
    out.sort(key=lambda c: (ORDEN_URG.get(c["urgencia"], 9), c["_t"]))
    return [{k: v for k, v in c.items() if k != "_t"} for c in out]


def _contactos(ids: list[str]) -> dict[str, dict]:
    """Correo, teléfono y forma segura de contacto (la que eligió al pedir apoyo)."""
    if not ids:
        return {}
    sb = servicio()
    per = {p["usuaria_id"]: p for p in sb.table("perfiles").select("usuaria_id,nombre,correo,telefono").in_("usuaria_id", ids).execute().data}
    sens = {x["usuaria_id"]: (descifrar(x["datos_cifrados"]) or {}) for x in
            sb.table("expedientes_sensibles").select("usuaria_id,datos_cifrados").in_("usuaria_id", ids).execute().data}
    out = {}
    for uid in ids:
        p, c = per.get(uid, {}), (sens.get(uid, {}).get("contacto") or {})
        correo = p.get("correo") if p.get("correo") and not p["correo"].endswith("@sin-correo.demo.example") else None
        out[uid] = {"nombre": p.get("nombre") or "Sin nombre", "correo": correo, "telefono": p.get("telefono"),
                    "medio": c.get("medio") or None, "horario": c.get("horario") or None, "dejar_mensaje": bool(c.get("mensaje"))}
    return out


def _cita(c: dict) -> dict | None:
    return {"fecha": c["cita_at"], "modalidad": c.get("cita_modalidad"), "nota": c.get("cita_nota")} if c.get("cita_at") else None


@router.get("/casos")
def casos(s: Sesion = Depends(CASOS)):
    filas = servicio().table("canalizaciones").select("folio,usuaria_id,area_asignada,estado,urgencia,updated_at,cita_at,cita_modalidad,cita_nota") \
        .neq("estado", "nueva").neq("estado", "cerrada").execute().data
    if s.rol in ESPECIALIDAD:
        filas = [f for f in filas if f["area_asignada"] in ESPECIALIDAD[s.rol]]
    con = _contactos(list({f["usuaria_id"] for f in filas}))
    bitacora(s.user_id, s.rol, "listar", "canalizaciones")
    filas.sort(key=lambda f: (f["cita_at"] is None, f["cita_at"] or "", ORDEN_URG.get(f["urgencia"], 9)))
    return [{"folio": f["folio"], "usuaria_id": f["usuaria_id"], **con.get(f["usuaria_id"], {}),
             "area": AREA_TEXTO.get(f["area_asignada"], "por definir"), "estado": f["estado"], "urgencia": f["urgencia"],
             "fecha": sv.fecha_corta(f["updated_at"]), "cita": _cita(f)} for f in filas]


class CitaIn(BaseModel):
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    modalidad: Literal["presencial", "llamada", "videollamada"] = "presencial"
    nota: str | None = Field(default=None, max_length=300)


@router.patch("/casos/{folio}/cita")
def programar_cita(folio: str, body: CitaIn, s: Sesion = Depends(CASOS)):
    """La especialista (o Trabajo Social) programa la cita. Si es presencial, Recepción la ve como visita prevista."""
    if body.fecha < date.today():
        raise HTTPException(422, "Elige una fecha de hoy en adelante.")
    sb = servicio()
    c = sb.table("canalizaciones").select("id,usuaria_id,area_asignada,estado").eq("folio", folio).limit(1).execute().data
    if not c:
        raise HTTPException(404, "Caso no encontrado")
    c = c[0]
    if s.rol in ESPECIALIDAD and c["area_asignada"] not in ESPECIALIDAD[s.rol]:
        raise HTTPException(403, "Este caso no está asignado a tu área")
    cita_at = f"{body.fecha.isoformat()}T{body.hora}:00-07:00"   # hora de Sinaloa
    cambios = {"cita_at": cita_at, "cita_modalidad": body.modalidad, "cita_nota": (body.nota or "").strip() or None}
    if c["estado"] == "asignada":
        cambios["estado"] = "contactada"
    sb.table("canalizaciones").update(cambios).eq("id", c["id"]).execute()
    if body.modalidad == "presencial":
        modulo = {"especialista_juridica": "juridico", "especialista_psicologica": "psicologia"}.get(s.rol, "trabajo_social")
        sb.table("visitas").insert({"usuaria_id": c["usuaria_id"], "fecha": body.fecha.isoformat(), "franja": franja_de(body.hora),
                                    "modulo": modulo, "origen": "personal"}).execute()
    area = {"especialista_juridica": "juridico", "especialista_psicologica": "psicologia"}.get(s.rol, "trabajo_social")
    sb.table("expediente_eventos").insert({"usuaria_id": c["usuaria_id"], "version": 0, "fuente": "personal_semujeres", "autor": s.user_id,
                                           "area": area, "texto": f"Cita {body.modalidad} el {sv.fecha_corta(cita_at)} a las {body.hora} ({folio})",
                                           "texto_publico": f"Tiene cita con SEMujeres el {sv.fecha_corta(cita_at)}"}).execute()
    bitacora(s.user_id, s.rol, "actualizar", "canalizaciones", folio, c["usuaria_id"])
    return {"folio": folio, "cita": {"fecha": cita_at, "modalidad": body.modalidad, "nota": cambios["cita_nota"]}}


@router.get("/expedientes")
def buscar(q: str = Query(default="", max_length=60), s: Sesion = Depends(LECTORES)):
    t = q.strip()
    base = servicio().table("perfiles").select("usuaria_id,nombre,curp,colonia,municipio")
    if s.rol in ESPECIALIDAD:   # Jurídico y Psicología: solo los expedientes que Trabajo Social les asignó
        ids = [c["usuaria_id"] for c in servicio().table("canalizaciones").select("usuaria_id,area_asignada").execute().data
               if c["area_asignada"] in ESPECIALIDAD[s.rol]]
        base = base.in_("usuaria_id", list(set(ids)) or ["00000000-0000-0000-0000-000000000000"])
    if re.fullmatch(r"[A-Za-z]{4}\d{6}[A-Za-z0-9]{8}", t):
        filas = base.eq("curp", t.upper()).execute().data
    elif t:
        filas = base.ilike("nombre", f"%{t}%").limit(20).execute().data
    else:
        filas = base.order("created_at", desc=True).limit(20).execute().data
    bitacora(s.user_id, s.rol, "listar", "perfiles")
    return [{**f, "curp": ocultar_curp(f.get("curp"))} for f in filas if f.get("nombre") is not None or f.get("curp")]


def _armar(usuaria_id: str) -> dict:
    sb = servicio()
    p = sb.table("perfiles").select("*").eq("usuaria_id", usuaria_id).limit(1).execute().data
    if not p:
        raise HTTPException(404, "Expediente no encontrado")
    p = p[0]
    exp = (sb.table("expedientes").select("campos,ruta").eq("usuaria_id", usuaria_id).limit(1).execute().data or [{}])[0]
    vals = sv.valores_de({"campos": exp.get("campos") or {}})
    recursos = sb.table("recursos_usuaria").select("recurso_id,estado,updated_at").eq("usuaria_id", usuaria_id).execute().data
    titulos = {r["id"]: r["titulo"] for r in sb.table("recursos").select("id,titulo")
               .in_("id", [r["recurso_id"] for r in recursos] or ["-"]).execute().data}
    canal = sb.table("canalizaciones").select("folio,area_asignada,urgencia,estado,created_at,cita_at,cita_modalidad,cita_nota") \
        .eq("usuaria_id", usuaria_id).order("created_at", desc=True).execute().data
    sens = sb.table("expedientes_sensibles").select("datos_cifrados").eq("usuaria_id", usuaria_id).execute().data
    datos_s = descifrar(sens[0]["datos_cifrados"]) if sens else {}
    ev = sb.table("expediente_eventos").select("area,texto,texto_publico,fuente,created_at") \
        .eq("usuaria_id", usuaria_id).order("created_at", desc=True).limit(60).execute().data

    eventos, notas = [], []
    for e in ev:
        if e["fuente"] == "nota":
            notas.append({"area": e["area"], "texto": descifrar(e["texto"], como_json=False), "fecha": sv.fecha_corta(e["created_at"])})
        else:
            eventos.append({"area": e["area"], "texto": e["texto"], "texto_publico": e.get("texto_publico"),
                            "fecha": sv.fecha_corta(e["created_at"])})
    return {
        "id": usuaria_id,
        "general": {
            "nombre": p.get("nombre"), "curp": ocultar_curp(p.get("curp")), "colonia": p.get("colonia"),
            "municipio": p.get("municipio"), "desde": sv.fecha_corta(p.get("created_at")),
            "contacto": _contactos([usuaria_id]).get(usuaria_id),
            "datos": [legible(k, vals[k]) for k in GENERALES if k in vals],
        },
        "economico": {
            "datos": [legible(k, v) for k, v in vals.items() if k not in GENERALES],
            "recursos": [{"titulo": titulos.get(r["recurso_id"], r["recurso_id"]), "estado": r["estado"],
                          "fecha": sv.fecha_corta(r["updated_at"])} for r in recursos],
        },
        "solicitudes": [{"folio": c["folio"], "area_asignada": c["area_asignada"], "urgencia": c["urgencia"],
                         "estado": c["estado"], "fecha": sv.fecha_corta(c["created_at"]),
                         "resumen": (datos_s or {}).get("resumen"), "contacto": (datos_s or {}).get("contacto"),
                         "cita": _cita(c)} for c in canal],
        "eventos": eventos,
        "notas": notas,
    }


@router.get("/expedientes/{usuaria_id}")
def ver(usuaria_id: str, s: Sesion = Depends(LECTORES)):
    if s.rol in ESPECIALIDAD:
        canal = servicio().table("canalizaciones").select("area_asignada,estado").eq("usuaria_id", usuaria_id).execute().data
        if not puede_abrir(s.rol, canal):
            raise HTTPException(403, "Este expediente no está asignado a tu área. Trabajo Social decide a qué área va cada caso.")
    exp = _armar(usuaria_id)
    if s.rol not in ("trabajo_social", *ESPECIALIDAD):
        exp["general"].pop("contacto", None)
    bitacora(s.user_id, s.rol, "leer", "expedientes", usuaria_id, usuaria_id)
    return {"id": exp["id"], "rol": s.rol, **vista_expediente(s.rol, exp)}


class AsignarIn(BaseModel):
    area: Literal["juridica", "psicologica", "ambas"]


@router.post("/solicitudes/{folio}/asignar")
def asignar(folio: str, body: AsignarIn, s: Sesion = Depends(TS)):
    sb = servicio()
    c = sb.table("canalizaciones").select("id,usuaria_id,estado").eq("folio", folio).limit(1).execute().data
    if not c:
        raise HTTPException(404, "Solicitud no encontrada")
    if c[0]["estado"] != "nueva":
        raise HTTPException(409, "Esta solicitud ya fue asignada")
    sb.table("canalizaciones").update({"estado": "asignada", "area_asignada": body.area, "asignada_por": s.user_id}) \
        .eq("id", c[0]["id"]).execute()
    hoy = sv.fecha_corta(sv.ahora_iso())
    publico = f"En atención {AREA_TEXTO[body.area]} desde {hoy}"
    sb.table("expediente_eventos").insert({
        "usuaria_id": c[0]["usuaria_id"], "version": 0, "fuente": "personal_semujeres", "autor": s.user_id,
        "area": AREA_EVENTO[body.area], "texto": f"Trabajo Social asignó la solicitud {folio} a atención {AREA_TEXTO[body.area]}",
        "texto_publico": publico}).execute()
    bitacora(s.user_id, s.rol, "actualizar", "canalizaciones", folio, c[0]["usuaria_id"])
    return {"folio": folio, "estado": "asignada", "area": body.area}


class NotaIn(BaseModel):
    texto: str = Field(min_length=1, max_length=1500)


@router.post("/expedientes/{usuaria_id}/notas")
def nota(usuaria_id: str, body: NotaIn, s: Sesion = Depends(NOTAS)):
    area = area_de_rol(s.rol)
    if area not in CONFIDENCIALES:
        raise HTTPException(403, "Tu rol no guarda notas aquí")
    servicio().table("expediente_eventos").insert({
        "usuaria_id": usuaria_id, "version": 0, "fuente": "nota", "autor": s.user_id, "area": area,
        "texto": cifrar(body.texto.strip())}).execute()
    bitacora(s.user_id, s.rol, "crear", "notas", None, usuaria_id)
    return ver(usuaria_id, s)


class AltaIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    curp: str = Field(pattern=r"^[A-Za-z]{4}\d{6}[A-Za-z0-9]{8}$")
    telefono: str | None = Field(default=None, max_length=20)


def abrir_o_crear(nombre: str, curp: str, telefono: str | None, autor: str, rol: str) -> tuple[str, bool]:
    """Busca el expediente por CURP; si no existe, lo crea. Regresa (usuaria_id, ya_existia)."""
    sb = servicio()
    curp = curp.upper()
    hay = sb.table("perfiles").select("usuaria_id").eq("curp", curp).limit(1).execute().data
    if hay:
        return hay[0]["usuaria_id"], True
    u = sb.auth.admin.create_user({"email": f"{curp.lower()}@sin-correo.demo.example", "email_confirm": True,
                                   "user_metadata": {"nombre": nombre}})
    uid = u.user.id
    sb.table("perfiles").upsert({"usuaria_id": uid, "nombre": nombre, "curp": curp, "telefono": telefono}).execute()
    sb.table("expediente_eventos").insert({"usuaria_id": uid, "version": 0, "fuente": "personal_semujeres", "autor": autor,
                                           "area": "general", "texto": "Se abrió su expediente en SEMujeres (llegó en persona)"}).execute()
    bitacora(autor, rol, "crear", "perfiles", None, uid)
    return uid, False


@router.post("/expedientes")
def alta(body: AltaIn, s: Sesion = Depends(TS)):
    """Mujer que llegó en persona: si su CURP ya existe se abre su expediente; si no, se crea."""
    uid, existia = abrir_o_crear(body.nombre, body.curp, body.telefono, s.user_id, s.rol)
    return {"usuaria_id": uid, "existente": existia}


# ---------------------------------------------------------------- resumen por área
@router.get("/resumen")
def resumen(s: Sesion = Depends(CASOS)):
    """Métricas solo del área de quien pregunta (Trabajo Social ve todas las solicitudes)."""
    from datetime import date
    from .resumen import resumen_area
    sb = servicio()
    casos = sb.table("canalizaciones").select("folio,usuaria_id,area_asignada,estado,urgencia,created_at,cita_at,cita_modalidad,cita_nota").execute().data
    visitas = sb.table("visitas").select("modulo,fecha").eq("fecha", date.today().isoformat()).execute().data
    r = resumen_area(s.rol, casos, visitas, date.today())
    mios = [c for c in casos if c["estado"] not in ("cerrada",) and (s.rol not in ESPECIALIDAD or c["area_asignada"] in ESPECIALIDAD[s.rol])]
    mios.sort(key=lambda c: (ORDEN_URG.get(c["urgencia"], 9), c["created_at"]))
    per = _nombres(list({c["usuaria_id"] for c in mios[:6]}))
    r["recientes"] = [{"folio": c["folio"], "usuaria_id": c["usuaria_id"], "nombre": (per.get(c["usuaria_id"]) or {}).get("nombre") or "Sin nombre",
                       "estado": c["estado"], "urgencia": c["urgencia"], "hace": hace(c["created_at"]), "cita": _cita(c)} for c in mios[:6]]
    hoy = date.today().isoformat()
    r["citas_proximas"] = sum(1 for c in mios if c.get("cita_at") and c["cita_at"][:10] >= hoy)
    bitacora(s.user_id, s.rol, "listar", "canalizaciones")
    return r


# ---------------------------------------------------------------- derivar (Trabajo Social)
class DerivarIn(BaseModel):
    area: Literal["juridica", "psicologica", "ambas", "economico"]
    valoracion: str = Field(min_length=10, max_length=1500)
    urgencia: Literal["inmediata", "pronta", "informativa"] = "pronta"


@router.post("/expedientes/{usuaria_id}/derivar")
def derivar(usuaria_id: str, body: DerivarIn, s: Sesion = Depends(TS)):
    """Después de valorar su situación, Trabajo Social decide a qué departamento va el expediente."""
    sb = servicio()
    if not sb.table("perfiles").select("usuaria_id").eq("usuaria_id", usuaria_id).limit(1).execute().data:
        raise HTTPException(404, "Expediente no encontrado")
    hoy = sv.fecha_corta(sv.ahora_iso())
    # La valoración es nota de Trabajo Social (cifrada, solo la ve su área)
    sb.table("expediente_eventos").insert({"usuaria_id": usuaria_id, "version": 0, "fuente": "nota", "autor": s.user_id,
                                           "area": "trabajo_social", "texto": cifrar(f"Valoración: {body.valoracion.strip()}")}).execute()
    if body.area == "economico":
        sb.table("perfiles").update({"estado_seguimiento": "Nueva"}).eq("usuaria_id", usuaria_id).execute()
        sb.table("expediente_eventos").insert({"usuaria_id": usuaria_id, "version": 0, "fuente": "personal_semujeres", "autor": s.user_id,
                                               "area": "economico", "texto": "Trabajo Social la envió a Empoderamiento económico",
                                               "texto_publico": f"En seguimiento de Empoderamiento económico desde {hoy}"}).execute()
        bitacora(s.user_id, s.rol, "actualizar", "perfiles", None, usuaria_id)
        return {"area": "economico"}
    nueva = sb.table("canalizaciones").select("id,folio").eq("usuaria_id", usuaria_id).eq("estado", "nueva").limit(1).execute().data
    if nueva:
        folio = nueva[0]["folio"]
        sb.table("canalizaciones").update({"estado": "asignada", "area_asignada": body.area, "asignada_por": s.user_id,
                                           "urgencia": body.urgencia}).eq("id", nueva[0]["id"]).execute()
    else:
        folio = sb.table("canalizaciones").insert({"usuaria_id": usuaria_id, "tipo": body.area, "area_asignada": body.area,
                                                   "estado": "asignada", "origen": "personal", "urgencia": body.urgencia,
                                                   "asignada_por": s.user_id}).execute().data[0]["folio"]
    # Si llegó en persona no hay resumen: la especialista recibe la valoración como contexto
    if not sb.table("expedientes_sensibles").select("usuaria_id").eq("usuaria_id", usuaria_id).execute().data:
        tel = (sb.table("perfiles").select("telefono").eq("usuaria_id", usuaria_id).limit(1).execute().data or [{}])[0].get("telefono")
        sb.table("expedientes_sensibles").insert({"usuaria_id": usuaria_id, "consentimiento_at": sv.ahora_iso(),
            "datos_cifrados": cifrar({"tipo": body.area, "resumen": body.valoracion.strip(),
                                      "contacto": {"medio": "Llamada" if tel else "En persona", "horario": "", "mensaje": False}})}).execute()
    sb.table("expediente_eventos").insert({
        "usuaria_id": usuaria_id, "version": 0, "fuente": "personal_semujeres", "autor": s.user_id,
        "area": AREA_EVENTO[body.area], "texto": f"Trabajo Social valoró y envió el expediente a atención {AREA_TEXTO[body.area]} ({folio})",
        "texto_publico": f"En atención {AREA_TEXTO[body.area]} desde {hoy}"}).execute()
    bitacora(s.user_id, s.rol, "actualizar", "canalizaciones", folio, usuaria_id)
    return {"area": body.area, "folio": folio}
