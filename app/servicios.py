"""Orquestación: lee con RLS, aplica el dominio, escribe con service role."""
from datetime import date, datetime, timezone

from fastapi import HTTPException

from .db import como, servicio
from .dominio import diccionario
from .dominio.fusion import fusionar, valores as valores_de
from .dominio.matching import recomendar
from .dominio.motor_ruta import NOMBRE_RUTA, calcular_ruta, explicacion_respaldo
from .dominio.requisitos import evaluar_recurso
from .ia import claude, embeddings

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(iso: str | None) -> str:
    if not iso:
        return ""
    d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return f"{d.day} {MESES[d.month - 1]}"


# ============================================================ expediente
def leer_expediente(token: str, usuaria_id: str) -> dict:
    """Lee con el JWT de quien pide: si RLS no la deja verlo, es 404."""
    with como(token) as db:
        filas = db.from_("expedientes").select("usuaria_id,campos,ruta,conflictos,version,embedding_version") \
            .eq("usuaria_id", usuaria_id).limit(1).execute().data
    if not filas:
        raise HTTPException(404, "Expediente no encontrado")
    return filas[0]


def ruta_efectiva(exp: dict) -> dict:
    """Ruta calculada por el código; si el personal la cambió a mano (con motivo), esa gana."""
    vals = valores_de(exp)
    calc = calcular_ruta(vals)
    manual = (exp.get("ruta") or {}).get("manual")
    if manual:
        calc = {**calc, "principal": manual["principal"], "puente": manual.get("puente"), "manual": manual}
    return calc


def aplicar_campos(token: str, usuaria_id: str, nuevos: dict, fuente: str,
                   autor: str | None = None, confianza: float = 1.0) -> dict:
    """Fusiona y guarda con control de versión optimista (un reintento)."""
    for _ in range(2):
        exp = leer_expediente(token, usuaria_id)
        try:
            res = fusionar(exp, nuevos, fuente, confianza=confianza, autor=autor)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if not res["cambio"]:
            return {**exp, "ruta": exp.get("ruta") or ruta_efectiva(exp)}
        nuevo = res["expediente"]
        ruta = ruta_efectiva(nuevo)
        anterior = exp.get("ruta") or {}
        ruta_guardada = {**ruta, "version": nuevo["version"]}
        if anterior.get("manual"):
            ruta_guardada["manual"] = anterior["manual"]
        upd = servicio().table("expedientes").update({
            "campos": nuevo["campos"],
            "conflictos": nuevo["conflictos"],
            "version": nuevo["version"],
            "ruta": ruta_guardada,
        }).eq("usuaria_id", usuaria_id).eq("version", exp["version"]).execute()
        if not upd.data:
            continue  # alguien más guardó en medio: releer y volver a fusionar
        filas = [{**e, "usuaria_id": usuaria_id} for e in res["eventos"]]
        for c in res["conflictos_nuevos"]:
            filas.append({"usuaria_id": usuaria_id, "version": nuevo["version"], "campo": c["campo"],
                          "valor_anterior": c["valor_usuaria"], "valor_nuevo": c["valor_personal"],
                          "fuente": "personal_semujeres", "autor": autor,
                          "texto": f"Para revisar con ella: {diccionario.etiqueta(c['campo']).lower()}"})
        if filas:
            servicio().table("expediente_eventos").insert(filas).execute()
        if "municipio" in nuevos:
            servicio().table("perfiles").update({"municipio": nuevos["municipio"]}).eq("usuaria_id", usuaria_id).execute()
        return {**nuevo, "ruta": ruta_guardada}
    raise HTTPException(409, "El expediente cambió mientras guardabas. Intenta de nuevo.")


def evento(usuaria_id: str, texto: str, fuente: str, autor: str | None = None, version: int = 0) -> None:
    servicio().table("expediente_eventos").insert({
        "usuaria_id": usuaria_id, "version": version, "texto": texto, "fuente": fuente, "autor": autor,
    }).execute()


def expediente_publico(exp: dict) -> dict:
    """Forma que entiende el front (services/expediente.js)."""
    return {"version": exp.get("version", 0), "campos": exp.get("campos") or {},
            "conflictos": exp.get("conflictos") or []}


# ============================================================ ruta
def ruta_con_explicacion(exp: dict) -> dict:
    ruta = ruta_efectiva(exp)
    guardada = exp.get("ruta") or {}
    if guardada.get("explicacion") and guardada.get("version") == exp.get("version") and not ruta.get("manual"):
        explicacion = guardada["explicacion"]
    else:
        hechos = {
            "ruta_principal": NOMBRE_RUTA[ruta["principal"]],
            "ruta_puente": NOMBRE_RUTA.get(ruta.get("puente")),
            "factores": [f["texto"] for f in ruta["factores"][:4]],
        }
        explicacion = claude.redactar(
            hechos, "Explica por qué se le sugiere esa ruta y, si hay ruta puente, que es un paso intermedio."
        ) or explicacion_respaldo(ruta)
        try:
            servicio().table("expedientes").update(
                {"ruta": {**guardada, **{k: v for k, v in ruta.items() if k != "manual"},
                          "explicacion": explicacion, "version": exp.get("version")}}
            ).eq("usuaria_id", exp["usuaria_id"]).eq("version", exp.get("version")).execute()
        except Exception:
            pass  # el caché es opcional
    return formato_ruta(ruta, explicacion)


def formato_ruta(ruta: dict, explicacion: str | None = None) -> dict:
    return {
        "principal": ruta["principal"],
        "puente": ruta.get("puente"),
        "puntajes": ruta.get("puntajes", {}),
        "factores": [f["texto"] for f in ruta.get("factores", [])],   # igual que el front: lista de textos
        "factores_detalle": ruta.get("factores", []),
        "manual": ruta.get("manual"),
        "explicacion": explicacion,
    }


# ============================================================ catálogo
CAMPOS_RECURSO = ("id,titulo,proveedor,tipo,rutas,modalidad,horario,horas_semana,costo,ubicacion,municipios,"
                  "fecha_cierre,requisitos,descripcion,url_accion,verificado_el,publicada,creada_el,"
                  "sueldo,etiquetas,estado_revision,empresa_id")


def leer_catalogo(token: str | None = None) -> list[dict]:
    """Con token de personal regresa también lo pausado (lo decide RLS)."""
    with como(token) as db:
        return db.from_("recursos").select(CAMPOS_RECURSO).order("creada_el", desc=True).execute().data


def recurso_publico(r: dict, vals: dict | None = None) -> dict:
    ev = evaluar_recurso(r.get("requisitos") or [], vals or {})
    if vals is None:
        for q in ev["requisitos"]:
            q["ok"] = None
    return {**r, "requisitos": ev["requisitos"], "faltantes": ev["faltantes"] if vals is not None else [],
            "cumple": ev["cumple"] if vals is not None else None}


def similitudes(token: str, exp: dict, vals: dict, ruta: dict) -> dict:
    """Embedding del resumen del expediente (cacheado por versión) vs. recursos con pgvector."""
    vec = None
    if exp.get("embedding_version") == exp.get("version"):
        fila = servicio().table("expedientes").select("embedding").eq("usuaria_id", exp["usuaria_id"]).execute().data
        vec = fila[0]["embedding"] if fila and fila[0].get("embedding") else None
    if vec is None:
        v = embeddings.embed(embeddings.texto_expediente(vals, ruta), "RETRIEVAL_QUERY")
        if v is None:
            return {}
        vec = embeddings.como_texto(v)
        servicio().table("expedientes").update({"embedding": vec, "embedding_version": exp.get("version")}) \
            .eq("usuaria_id", exp["usuaria_id"]).execute()
    try:
        with como(token) as db:
            filas = db.rpc("match_recursos", {"query_embedding": vec, "match_count": 60}).execute().data
        return {f["id"]: max(0.0, float(f["similitud"])) for f in filas}
    except Exception:
        return {}


def recomendaciones(token: str, usuaria_id: str) -> dict:
    exp = leer_expediente(token, usuaria_id)
    vals = valores_de(exp)
    ruta = ruta_efectiva(exp)
    sims = similitudes(token, exp, vals, ruta)
    recs = recomendar(leer_catalogo(token), vals, ruta, similitudes=sims, hoy=date.today())
    return {"ruta": formato_ruta(ruta, (exp.get("ruta") or {}).get("explicacion")), "recursos": recs,
            "con_embeddings": bool(sims)}


# Preguntas que vienen al caso según el tipo de opción, además de lo que pide el recurso
EXTRA_POR_TIPO = {
    "vacante": ["experiencia_anios", "inicio", "transporte"],
    "curso": ["nivel_computacion", "intereses"],
    "beca": ["intereses", "inicio"],
    "apoyo": ["intereses"],
    "financiamiento": ["intereses"],
}


def preguntas_para(faltantes: list[str], recurso: dict, vals: dict | None = None) -> list[dict]:
    """Hasta 5 preguntas, cada una amarrada a un campo del diccionario: primero lo que pide el
    recurso y después lo que viene al caso para ese tipo de opción (si todavía no lo sabemos)."""
    vals = vals or {}
    extra = [c for c in EXTRA_POR_TIPO.get(recurso.get("tipo"), []) if c not in vals and c not in faltantes]
    base = [{"campo": c, "pregunta": diccionario.CAMPOS[c]["pregunta"], "opciones": diccionario.CAMPOS[c]["opciones"],
             "tipo": diccionario.CAMPOS[c]["tipo"]}
            for c in list(dict.fromkeys(faltantes + extra)) if c in diccionario.CAMPOS and "opciones" in diccionario.CAMPOS[c]][:5]
    if not base:
        return []
    return claude.preguntas_faltantes(base, recurso) or base


def explicar_recurso(r: dict, vals: dict, ruta: dict) -> str:
    hechos = {
        "recurso": r["titulo"], "tipo": r["tipo"], "modalidad": r.get("modalidad"), "horario": r.get("horario"),
        "razones_verificadas": r.get("porque", []),
        "requisitos_que_cumple": [q["label"] for q in r["requisitos"] if q["ok"] is True],
        "requisitos_que_faltan": [q["label"] for q in r["requisitos"] if q["ok"] is not True],
        "es_ruta_puente": r.get("es_puente", False),
    }
    texto = claude.redactar(hechos, "Empieza con 'Es para ti porque'. Si faltan requisitos, menciónalo al final.")
    if texto:
        return texto
    razones = r.get("porque") or []
    return ("Es para ti porque " + razones[0][0].lower() + razones[0][1:] + ".") if razones \
        else f"Te ayuda en tu ruta de {NOMBRE_RUTA[ruta['principal']]}."


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
