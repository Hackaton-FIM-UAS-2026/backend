"""Claude con salidas estructuradas (tool use + JSON Schema).

Reglas:
  * Claude NUNCA decide la ruta ni inventa recursos: recibe hechos y devuelve
    preguntas o frases. Todo lo que regresa se valida contra lo que existe.
  * Si falla o tarda más de LLM_TIMEOUT_S, se regresa None y quien llama usa
    una plantilla. La app sigue funcionando sin llave de Anthropic.
  * Nunca se registra en logs el texto de la usuaria.
"""
import json
import logging
from functools import lru_cache

from ..config import settings

log = logging.getLogger("ia")

ESTILO = (
    "Escribes para mujeres de Sinaloa, México, con poca escolaridad y poco tiempo. "
    "Lectura fácil: frases cortas, palabras comunes, sin tecnicismos, sin anglicismos, de tú. "
    "Nada de emojis. Nunca prometas algo que no esté en los hechos que te dan."
)


@lru_cache
def _cliente():
    s = settings()
    if not s.anthropic_api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_s, max_retries=0)


def usar_herramienta(system: str, mensaje: str, nombre: str, descripcion: str, schema: dict,
                     max_tokens: int = 400) -> dict | None:
    cliente = _cliente()
    if cliente is None:
        return None
    try:
        r = cliente.messages.create(
            model=settings().claude_model,
            max_tokens=max_tokens,
            system=f"{ESTILO}\n\n{system}",
            tools=[{"name": nombre, "description": descripcion, "input_schema": schema}],
            tool_choice={"type": "tool", "name": nombre},
            messages=[{"role": "user", "content": mensaje}],
        )
        for b in r.content:
            if b.type == "tool_use" and b.name == nombre:
                return b.input
    except Exception as e:
        log.warning("Claude no respondió (%s): %s", nombre, type(e).__name__)
    return None


# ------------------------------------------------------------------ M9
def preguntas_faltantes(faltantes: list[dict], contexto: dict) -> list[dict] | None:
    """faltantes: [{campo, pregunta, opciones}] del diccionario.
    Claude solo reescribe el TEXTO de la pregunta para este recurso; las opciones
    y el campo salen del diccionario, así la respuesta siempre se puede validar.
    """
    campos = [f["campo"] for f in faltantes]
    out = usar_herramienta(
        system="Generas de 1 a 3 preguntas para saber si la usuaria cumple los requisitos de un recurso. "
               "Cada pregunta corresponde a exactamente un campo de la lista. Máximo 12 palabras por pregunta.",
        mensaje=json.dumps({"recurso": contexto.get("titulo"), "campos_faltantes": faltantes}, ensure_ascii=False),
        nombre="hacer_preguntas",
        descripcion="Regresa las preguntas para los campos faltantes.",
        schema={
            "type": "object",
            "properties": {"preguntas": {
                "type": "array", "minItems": 1, "maxItems": 3,
                "items": {"type": "object", "required": ["campo", "pregunta"], "properties": {
                    "campo": {"type": "string", "enum": campos},
                    "pregunta": {"type": "string", "maxLength": 120},
                }},
            }},
            "required": ["preguntas"],
        },
    )
    if not out:
        return None
    por_campo = {f["campo"]: f for f in faltantes}
    vistas, res = set(), []
    for p in out.get("preguntas", []):
        c = p.get("campo")
        if c in por_campo and c not in vistas and p.get("pregunta"):
            vistas.add(c)
            res.append({**por_campo[c], "pregunta": p["pregunta"].strip()})
    return res or None


# ------------------------------------------------------------------ M10
def redactar(hechos: dict, instruccion: str) -> str | None:
    out = usar_herramienta(
        system="Redactas en 2 o 3 frases (máximo 45 palabras) usando SOLO los hechos que te dan. "
               "No agregues datos, cifras, lugares ni beneficios que no estén en los hechos. " + instruccion,
        mensaje=json.dumps(hechos, ensure_ascii=False),
        nombre="explicar",
        descripcion="Regresa la explicación en lectura fácil.",
        schema={"type": "object", "properties": {"texto": {"type": "string", "maxLength": 320}}, "required": ["texto"]},
        max_tokens=250,
    )
    texto = (out or {}).get("texto", "").strip()
    return texto or None


# ------------------------------------------------------------------ M12
def clasificar_senal(mensaje: str) -> dict | None:
    return usar_herramienta(
        system="Clasificas si el mensaje sugiere que la usuaria podría necesitar apoyo jurídico (violencia, "
               "pareja que no la deja trabajar, pensión, despojo, amenazas) o psicológico (angustia, 'ya no puedo más'). "
               "Solo clasificas; no aconsejas. urgencia 'inmediata' SOLO si dice que está en peligro ahora o que "
               "alguien la va a lastimar pronto. Ante la duda entre 'ninguna' y una señal, elige la señal: "
               "la usuaria decide después si quiere apoyo.",
        mensaje=mensaje[:2000],
        nombre="clasificar",
        descripcion="Clasifica la señal del mensaje.",
        schema={
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["ninguna", "juridica", "psicologica", "ambas"]},
                "urgencia": {"type": "string", "enum": ["ninguna", "informativa", "pronta", "inmediata"]},
            },
            "required": ["tipo", "urgencia"],
        },
        max_tokens=100,
    )


def responder_chat(mensaje: str, contexto: dict) -> dict | None:
    """Chat económico. Solo puede mencionar recursos de `contexto['recursos']`."""
    ids = [r["id"] for r in contexto.get("recursos", [])]
    out = usar_herramienta(
        system="Eres el asistente de una app que ayuda a mujeres a encontrar cursos, vacantes, becas y apoyos. "
               "Responde en máximo 3 frases. Solo puedes recomendar recursos de la lista que te dan, por su id. "
               "Si te preguntan algo que no sabes o fuera de tema, dilo con amabilidad y sugiere ver sus recursos. "
               "No das asesoría legal, médica ni psicológica.",
        mensaje=json.dumps({"mensaje_usuaria": mensaje[:2000], "contexto": contexto}, ensure_ascii=False),
        nombre="responder",
        descripcion="Regresa la respuesta y los ids de recursos mencionados.",
        schema={
            "type": "object",
            "properties": {
                "texto": {"type": "string", "maxLength": 500},
                "recurso_ids": {"type": "array", "items": {"type": "string", "enum": ids or ["_"]}},
            },
            "required": ["texto"],
        },
    )
    if not out or not out.get("texto"):
        return None
    out["recurso_ids"] = [i for i in out.get("recurso_ids", []) if i in ids]  # la IA no inventa recursos
    return out
