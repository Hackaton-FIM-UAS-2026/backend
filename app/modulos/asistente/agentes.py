"""Equipo de agentes del asistente: lógica pura, con la IA inyectable (`llm`).

llm(system: str, mensaje: str, schema: dict) -> dict | None
Si la IA falla (None), el asistente sigue funcionando: la emergencia siempre
muestra la línea de SEMujeres y las oportunidades salen de lo recomendado.
"""
import json
import re
import unicodedata
from typing import Callable

from app.ia.plantillas import CONTACTO_EMERGENCIA, senal_por_palabras

from . import instrucciones as I

LLM = Callable[[str, str, dict], dict | None]
AREAS = {"juridica", "psicologica", "ambas", "no_se"}
URGENCIAS = {"inmediata", "pronta", "informativa"}
CHIPS_INICIO = ["Busco trabajo", "Quiero un curso", "Necesito apoyo", "Hablar con una persona"]
OPCIONES_CONTACTO = ["WhatsApp", "Llamada", "Solo aquí", "Prefiero ir en persona"]

# Respaldo mínimo SOLO para cuando la IA no responde (sin IA no hay quien redacte).
_RESPALDO = {
    "recepcion": "Puedo ayudarte con empleo, cursos, becas, apoyos o con contactar a SEMujeres. ¿Qué buscas?",
    "oportunidades": "Estas opciones pueden servirte:",
    "canalizacion": "SEMujeres puede ayudarte, gratis. ¿Quieres que una persona del equipo te contacte?",
    "emergencia": "Tu seguridad es primero. Si puedes, ve a un lugar con más gente. Aquí sigo contigo.",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"[̀-ͯ]", "", t)


_PERSONA = re.compile(
    r"(hablar|platicar|comunicar|contactar)(me)? con (una |un |alguien|la |el )?"
    r"(persona|alguien|humano|humana|licenciad[ao]|abogad[ao]|psicolog[ao]|trabajadora|asesora|de verdad|real)"
    r"|(me pasas|pasame|comunicame) con"
    r"|persona real|con un humano|con una humana")


_OPORTUNIDAD = re.compile(
    r"trabaj|emple|vacant|chamba|sueldo|curso|taller|aprend|estudi|beca|apoyo|negocio|vender|emprend"
    r"|requisit|horario|aplicar|inscrib|capacit|dinero|credito|prestamo")


def parece_oportunidad(texto: str) -> bool:
    """Respaldo sin IA: ¿habla de trabajo, cursos, becas o apoyos?"""
    return bool(_OPORTUNIDAD.search(_norm(texto)))


def pide_persona(texto: str) -> bool:
    """¿Pidió hablar con una persona? Siempre se respeta (caso 4)."""
    return bool(_PERSONA.search(_norm(texto)))


def filtrar_recursos(ids: list[str], catalogo: dict[str, dict]) -> list[dict]:
    """Solo recursos que existen en el catálogo publicado; sin repetidos y en el orden dado."""
    vistos, out = set(), []
    for i in ids or []:
        if i in catalogo and i not in vistos:
            vistos.add(i)
            r = catalogo[i]
            out.append({k: r.get(k) for k in ("id", "titulo", "tipo", "proveedor", "horario")})
    return out


def datos_emergencia() -> dict:
    d = CONTACTO_EMERGENCIA["semujeres_24h"]
    return {"nombre": d["nombre"], "telefono": d["telefono"], "tel": d.get("tel"), "respaldo": "911"}


def _conversacion(mensaje: str, historial: list[dict]) -> str:
    lineas = [f"{'Usuaria' if h.get('rol') == 'usuaria' else 'Asistente'}: {h.get('texto', '')}" for h in historial[-10:]]
    lineas.append(f"Usuaria: {mensaje}")
    return "\n".join(lineas)


def _respuesta(agente: str, texto: str | None, recursos=None, acciones=None, emergencia=None) -> dict:
    return {"agente": agente, "texto": (texto or "").strip() or _RESPALDO[agente],
            "recursos": recursos or [], "acciones": acciones or [], "emergencia": emergencia}


def _emergencia(conv: str, llm: LLM) -> dict:
    out = llm(I.EMERGENCIA, conv, I.SCHEMA_EMERGENCIA) or {}
    return _respuesta("emergencia", out.get("texto"), emergencia=datos_emergencia())


def _canalizacion(conv: str, llm: LLM, senal: dict, forzar_no_se: bool = False) -> dict:
    out = llm(I.CANALIZACION, conv, I.SCHEMA_CANALIZACION) or {}
    area = out.get("area") if out.get("area") in AREAS else None
    if area is None:
        area = "no_se" if forzar_no_se or senal["tipo"] == "ninguna" else senal["tipo"]
    urgencia = out.get("urgencia") if out.get("urgencia") in URGENCIAS else (
        "pronta" if senal["urgencia"] in ("ninguna", None) else senal["urgencia"])
    resumen = (out.get("resumen") or "").strip() or "Pidió que alguien de SEMujeres la contacte."
    acciones = [
        {"tipo": "confirmar_canalizacion", "area": area, "resumen": resumen, "urgencia": urgencia},
        {"tipo": "elegir_contacto", "opciones": OPCIONES_CONTACTO},
    ]
    return _respuesta("canalizacion", out.get("texto"), acciones=acciones)


def _oportunidades(conv: str, contexto: dict, llm: LLM) -> dict:
    catalogo = contexto.get("catalogo", {})
    recomendados = contexto.get("recomendados", [])
    datos = {
        "recomendados_para_ella": recomendados,
        "catalogo": [{k: r.get(k) for k in ("id", "titulo", "tipo", "horario", "modalidad", "etiquetas")}
                     for r in catalogo.values()],
    }
    out = llm(I.OPORTUNIDADES, f"{conv}\n\nCATÁLOGO:\n{json.dumps(datos, ensure_ascii=False)}",
              I.SCHEMA_OPORTUNIDADES)
    if out:
        return _respuesta("oportunidades", out.get("texto"), recursos=filtrar_recursos(out.get("recurso_ids"), catalogo))
    return _respuesta("oportunidades", None, recursos=filtrar_recursos(recomendados[:3], catalogo))


def responder(mensaje: str, historial: list[dict], contexto: dict, llm: LLM) -> dict:
    conv = _conversacion(mensaje, historial)
    senal = senal_por_palabras(mensaje)

    # 1. Peligro detectado por palabras: emergencia aunque la IA no responda.
    if senal["urgencia"] == "inmediata":
        return _emergencia(conv, llm)
    # 2. Pidió una persona: siempre se canaliza.
    if pide_persona(mensaje):
        return _canalizacion(conv, llm, senal, forzar_no_se=True)
    # 3. Enrutador (IA).
    ruta = llm(I.ENRUTADOR, conv, I.SCHEMA_ENRUTADOR) or {}
    cat = ruta.get("categoria")
    if cat is None:  # la IA no respondió: respaldo por palabras
        cat = ("canalizacion" if senal["tipo"] != "ninguna"
               else "oportunidades" if parece_oportunidad(mensaje) else "fuera_de_tema")
    if senal["tipo"] != "ninguna" and cat in ("oportunidades", "fuera_de_tema"):
        cat = "canalizacion"  # gana la lectura más protectora
    if cat == "emergencia":
        return _emergencia(conv, llm)
    if cat == "canalizacion":
        return _canalizacion(conv, llm, senal)
    if cat == "fuera_de_tema":
        return _respuesta("recepcion", ruta.get("texto"), acciones=[{"tipo": "chips", "opciones": CHIPS_INICIO[:3]}])
    return _oportunidades(conv, contexto, llm)
