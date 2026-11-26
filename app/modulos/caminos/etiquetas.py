"""M3 · Etiquetas de cada recurso (qué pide, qué enseña o da, de qué tema es), hechas por la IA.

Se guardan en `recursos.etiquetas` y se pueden revisar; los caminos solo cruzan etiquetas.
"""
from app.dominio.diccionario import CAMPOS

SYSTEM = """Etiquetas recursos (vacantes, cursos, becas y apoyos) de una plataforma para mujeres de Ahome, Sinaloa.
Solo puedes usar estos campos del perfil: {campos}.
- `pide`: campos que el recurso exige o pide (según sus requisitos y descripción).
- `da`: campos que la persona GANA al terminarlo (un curso de Excel da "habilidad_excel"; un taller del SAT para sacar el RFC da "tiene_rfc"; un curso práctico puede dar "tiene_experiencia"). Las vacantes casi nunca dan nada.
- `temas`: de 1 a 3 temas cortos en minúsculas (por ejemplo "contabilidad", "alimentos", "atención al cliente").
No inventes campos fuera de la lista."""

SCHEMA = {
    "type": "object",
    "properties": {
        "pide": {"type": "array", "items": {"type": "string"}},
        "da": {"type": "array", "items": {"type": "string"}},
        "temas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["pide", "da", "temas"],
}


def _validos(lista) -> list[str]:
    return list(dict.fromkeys(c for c in (lista or []) if c in CAMPOS))


def etiquetar(recurso: dict, llm) -> dict:
    """llm(system, mensaje, schema) -> dict | None. Sin IA: `pide` sale de los requisitos."""
    desde_requisitos = _validos(q.get("campo") for q in recurso.get("requisitos") or [])
    texto = (f"Título: {recurso.get('titulo')}\nTipo: {recurso.get('tipo')}\nDescripción: {recurso.get('descripcion', '')}\n"
             f"Requisitos: {[q.get('label') for q in recurso.get('requisitos') or []]}")
    out = llm(SYSTEM.format(campos=", ".join(CAMPOS)), texto, SCHEMA) or {}
    temas = [str(t).strip().lower() for t in out.get("temas") or [] if str(t).strip()][:3]
    return {"pide": _validos(out.get("pide")) or desde_requisitos, "da": _validos(out.get("da")), "temas": temas}
