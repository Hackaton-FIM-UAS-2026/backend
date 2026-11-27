"""Perfil: validación de identidad y entrevista dinámica (la IA elige el orden y el tono)."""
import json
import re

from app.dominio import diccionario

_CURP = re.compile(r"^[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d$")
_RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


def curp_valida(curp: str | None) -> bool:
    return bool(curp) and bool(_CURP.match(curp.strip().upper()))


def rfc_valido(rfc: str | None) -> bool:
    return bool(rfc) and bool(_RFC.match(rfc.strip().upper()))


# Orden de respaldo (sin IA): primero lo del test que falte, luego lo más útil para recomendar
_ORDEN = [c["campo"] for c in diccionario.TEST_BASE] + [
    "experiencia_anios", "tiene_experiencia", "intereses", "nivel_computacion", "inicio", "transporte",
    "apoyo_cuidados", "tiene_rfc", "habilidad_excel", "ingles"]


def _relevante(campo: str, v: dict) -> bool:
    cuida = [x for x in (v.get("cuidados") or []) if x != "Ninguna"]
    if campo == "apoyo_cuidados":
        return bool(cuida)
    if campo == "habilidad_excel":   # solo si usa la computadora o el celular para algo más que mensajes
        return v.get("nivel_computacion") != "Casi nada"
    if campo == "tiene_rfc":          # ya lo dijo al marcar sus documentos
        return "RFC" not in (v.get("documentos") or [])
    if campo == "tiene_experiencia":  # ya se sabe por los años de experiencia
        return "experiencia_anios" not in v
    return True


def candidatas(valores: dict) -> list[dict]:
    """Preguntas que faltan y vienen al caso, en el orden de respaldo."""
    por_campo = {c["campo"]: c for c in diccionario.TEST_BASE + diccionario.ENTREVISTA}
    return [por_campo[c] for c in _ORDEN if c in por_campo and c not in valores and _relevante(c, valores)]


SYSTEM = """Eres la entrevistadora de Empoderate (SEMujeres Ahome). Platicas con una mujer para conocerla mejor
y recomendarle trabajo, cursos, becas o apoyos. Hablas de tú, cálida y breve, sin tecnicismos.
Recibes lo que ya sabes de ella y la lista de preguntas pendientes (campo + pregunta base).
Elige la SIGUIENTE pregunta más útil según lo que ya contó (por ejemplo, si busca empleo, primero su experiencia
y cuándo puede empezar; si quiere un negocio, sus intereses). Reescribe la pregunta para que suene natural y,
si viene al caso, conéctala con algo que ya dijo (máximo 20 palabras). En `porque` explica en una frase corta
para qué sirve. Usa exactamente uno de los campos pendientes. La pregunta DEBE poder contestarse con las
opciones de ese campo (no cambies su sentido)."""
SCHEMA = {"type": "object", "properties": {"campo": {"type": "string"}, "pregunta": {"type": "string"}, "porque": {"type": "string"}},
          "required": ["campo", "pregunta"]}


def siguiente_pregunta(valores: dict, llm) -> dict | None:
    """llm(system, mensaje, schema) -> dict | None. Regresa {campo, pregunta, porque, tipo, opciones, faltan} o None."""
    pend = candidatas(valores)
    if not pend:
        return None
    out = llm(SYSTEM, json.dumps({"ya_se": valores, "pendientes": [{"campo": c["campo"], "pregunta": c["pregunta"], "opciones": c["opciones"]} for c in pend]},
                                 ensure_ascii=False), SCHEMA) or {}
    elegida = next((c for c in pend if c["campo"] == out.get("campo")), pend[0])
    usar_ia = elegida["campo"] == out.get("campo") and (out.get("pregunta") or "").strip()
    return {
        "campo": elegida["campo"], "tipo": elegida["tipo"], "opciones": elegida["opciones"],
        "pregunta": out["pregunta"].strip() if usar_ia else elegida["pregunta"],
        "porque": (out.get("porque") or "").strip() if usar_ia else None,
        "faltan": len(pend),
    }
