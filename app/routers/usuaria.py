"""App de la usuaria (M2, M5, M7, M9, M10). Todo bajo /me requiere sesión de usuaria."""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import servicios as sv
from ..auth import Sesion, usuaria
from ..db import como, servicio
from ..dominio import diccionario
from ..dominio.acciones import decidir_accion, es_evento_de_accion
from ..dominio.fusion import valores as valores_de
from ..dominio.matching import recomendar

router = APIRouter(prefix="/me", tags=["usuaria"])


class Registro(BaseModel):
    acepto_privacidad: bool
    nombre: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)


class CamposIn(BaseModel):
    campos: dict[str, Any]
    fuente: Literal["test_base", "entrevista", "usuaria_edito"] = "test_base"


class Accion(BaseModel):
    accion: Literal["aplicar", "guardar"]


@router.post("/registro")
def registro(body: Registro, s: Sesion = Depends(usuaria)):
    """Se llama justo después de signUp/signIn. Guarda el consentimiento (LFPDPPP)."""
    if not body.acepto_privacidad:
        raise HTTPException(400, "Se necesita aceptar el aviso de privacidad")
    previo = servicio().table("perfiles").select("nombre,acepto_privacidad_at").eq("usuaria_id", s.user_id) \
        .limit(1).execute().data
    previo = previo[0] if previo else {}
    datos = {"usuaria_id": s.user_id, "correo": s.correo}
    # La fecha del consentimiento es la de la PRIMERA vez que aceptó: no se pisa en cada inicio de sesión
    if not previo.get("acepto_privacidad_at"):
        datos["acepto_privacidad_at"] = sv.ahora_iso()
    if body.nombre:
        datos["nombre"] = body.nombre.strip()
    if body.telefono:
        datos["telefono"] = body.telefono.strip()
    servicio().table("perfiles").upsert(datos).execute()
    # Por si el trigger no corrió (usuarias creadas antes de la migración)
    servicio().table("expedientes").upsert({"usuaria_id": s.user_id}, ignore_duplicates=True).execute()
    # Las cuentas de Google llegan sin nombre: el front lo pide si aquí regresa vacío
    return {"ok": True, "nombre": datos.get("nombre") or previo.get("nombre") or None}


@router.get("/expediente")
def leer(s: Sesion = Depends(usuaria)):
    return sv.expediente_publico(sv.leer_expediente(s.token, s.user_id))


@router.patch("/expediente")
def guardar(body: CamposIn, s: Sesion = Depends(usuaria)):
    """Test base (fuente=test_base), respuestas al agente (entrevista) o ediciones (usuaria_edito)."""
    exp = sv.aplicar_campos(s.token, s.user_id, body.campos, body.fuente)
    return {**sv.expediente_publico(exp), "ruta": sv.formato_ruta(exp["ruta"]) if exp.get("ruta") else None}


@router.get("/ruta")
def ruta(s: Sesion = Depends(usuaria)):
    """Ruta principal + puente + explicación (la escribe Claude; si falla, plantilla)."""
    return sv.ruta_con_explicacion(sv.leer_expediente(s.token, s.user_id))


@router.get("/recomendaciones")
def recomendaciones(s: Sesion = Depends(usuaria)):
    """Top 10 para el dashboard, ya evaluados contra su expediente."""
    return sv.recomendaciones(s.token, s.user_id)


@router.get("/recursos/{recurso_id}")
def detalle(recurso_id: str, s: Sesion = Depends(usuaria)):
    """Detalle con 'lo que ya tienes / lo que te falta' y de 1 a 3 preguntas del agente."""
    exp = sv.leer_expediente(s.token, s.user_id)
    vals = valores_de(exp)
    ruta = sv.ruta_efectiva(exp)
    with como(s.token) as db:
        filas = db.from_("recursos").select(sv.CAMPOS_RECURSO).eq("id", recurso_id).limit(1).execute().data
    if not filas:
        raise HTTPException(404, "No encontramos este recurso")
    r = filas[0]
    # Reutiliza el matching para tener porque/es_puente aunque no esté en su top 10
    evaluado = (recomendar([r], vals, {**ruta, "puente": ruta.get("puente")}, limite=1) or [None])[0] \
        or {**sv.recurso_publico(r, vals), "porque": [], "es_puente": False}
    with como(s.token) as db:
        mio = db.from_("recursos_usuaria").select("estado").eq("recurso_id", recurso_id).execute().data
    return {
        **evaluado,
        "preguntas": sv.preguntas_para(evaluado["faltantes"], r, vals),
        "explicacion": sv.explicar_recurso(evaluado, vals, ruta),
        "mi_estado": mio[0]["estado"] if mio else None,
    }


@router.post("/recursos/{recurso_id}/accion")
def accion(recurso_id: str, body: Accion, s: Sesion = Depends(usuaria)):
    with como(s.token) as db:
        r = db.from_("recursos").select("id,titulo,url_accion").eq("id", recurso_id).limit(1).execute().data
    if not r:
        raise HTTPException(404, "No encontramos este recurso")
    sb = servicio()
    previo = sb.table("recursos_usuaria").select("estado").eq("usuaria_id", s.user_id) \
        .eq("recurso_id", recurso_id).limit(1).execute().data
    # Picar dos veces no duplica, y "Guardar" no baja a quien ya aplicó
    estado, nuevo = decidir_accion(previo[0]["estado"] if previo else None, body.accion)
    if nuevo:
        fila = {"usuaria_id": s.user_id, "recurso_id": recurso_id, "estado": estado, "updated_at": sv.ahora_iso()}
        # "Guardar" solo crea la fila: si otra petición ya la escribió (p. ej. "Aplicar"), no la pisa
        escrito = sb.table("recursos_usuaria").upsert(fila, ignore_duplicates=estado == "guardado").execute().data
        if not escrito:
            return {"estado": "aplicado", "nuevo": False, "titulo": r[0]["titulo"], "url_accion": r[0]["url_accion"]}
        verbo = "Aplicó a" if estado == "aplicado" else "Guardó"
        sv.evento(s.user_id, f"{verbo} «{r[0]['titulo']}»", "usuaria_edito")
    return {"estado": estado, "nuevo": nuevo, "titulo": r[0]["titulo"], "url_accion": r[0]["url_accion"]}


@router.get("/seguimiento")
def seguimiento(s: Sesion = Depends(usuaria)):
    """'Mi avance': versión, cuántos datos, línea de tiempo y estado de sus recursos."""
    exp = sv.leer_expediente(s.token, s.user_id)
    with como(s.token) as db:
        # Nunca lo confidencial (canalizaciones, notas): un celular puede ser compartido
        evs = db.from_("expediente_eventos").select("texto,fuente,created_at") \
            .eq("usuaria_id", s.user_id).in_("area", ["general", "economico"]).neq("fuente", "nota") \
            .order("created_at", desc=True).limit(30).execute().data
        mios = db.from_("recursos_usuaria").select("recurso_id,estado,updated_at,recursos(titulo,tipo)") \
            .eq("usuaria_id", s.user_id).execute().data
    n = sum(1 for c in (exp.get("campos") or {}) if c in diccionario.CAMPOS and diccionario.CAMPOS[c]["tipo"] != "texto")
    linea = []
    for e in evs:
        texto = e["texto"]
        if es_evento_de_accion(texto):
            continue  # ya aparece en la lista de sus recursos
        if e["fuente"] == "personal_semujeres":
            texto = texto.replace("Asesora registró:", "Tu asesora registró:")
        linea.append({"fecha": sv.fecha_corta(e["created_at"]), "texto": texto, "fuente": e["fuente"]})
    return {
        "version": exp.get("version", 0),
        "datos_guardados": n,
        "total": diccionario.TOTAL_PERFIL,
        "historial": linea,
        "recursos": [{"id": m["recurso_id"], "estado": m["estado"], "titulo": (m.get("recursos") or {}).get("titulo"),
                      "tipo": (m.get("recursos") or {}).get("tipo"),
                      "fecha": sv.fecha_corta(m["updated_at"])} for m in mios],
        "por_revisar": exp.get("conflictos") or [],
    }
