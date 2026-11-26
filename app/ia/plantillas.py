"""Plantillas FIJAS del flujo sensible (Claude solo clasifica y elige, no redacta).

A validar con CEMujeres antes de usarse con usuarias reales.
"""
import re
import unicodedata

PLANTILLAS = {
    "propuesta": "Gracias por contármelo. Hay personas que te pueden apoyar. ¿Quieres que te conecte con ellas? Tú decides.",
    "inmediata": "Si estás en peligro ahora, llama al 911. También puedes llamar al área jurídica de la Secretaría de las Mujeres de Sinaloa. No tienes que llenar nada.",
    "economica_respaldo": "Gracias. Lo tomo en cuenta para tus recomendaciones. Puedes ver tus recursos en el inicio.",
}

# Respaldo por palabras clave si Claude no responde. Se suma a lo que diga Claude
# (si cualquiera de los dos detecta algo, se PROPONE; ella decide).
_JURIDICA = ["mi pareja no me deja", "no me deja trabajar", "me golpea", "me pega", "violencia", "me amenaza",
             "pension", "pensión alimenticia", "me quito a mis hijos", "me corrio de la casa", "denunciar"]
_PSICO = ["ya no puedo mas", "no puedo mas", "me siento sola", "no quiero vivir", "estoy desesperada",
          "tengo mucho miedo", "ansiedad", "depresion"]
_INMEDIATA = ["me va a matar", "estoy en peligro", "me quiere matar", "ahorita me esta", "esta afuera de mi casa",
              "no quiero vivir", "me voy a matar", "quitarme la vida"]

CONTACTO_EMERGENCIA = {
    "telefono_911": "911",
    # Línea nacional de crisis emocional (verificar número vigente antes de la demo).
    "linea_de_la_vida": {"nombre": "Línea de la Vida", "telefono": "800 911 2000", "horario": "24 horas"},
    # PENDIENTE (líder de producto): teléfono y horario oficiales, tomados del sitio de la Secretaría.
    "secretaria_mujeres_sinaloa": {"nombre": "Área jurídica · Secretaría de las Mujeres de Sinaloa",
                                   "telefono": None, "horario": None},
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[̀-ͯ]", "", t)


def senal_por_palabras(mensaje: str) -> dict:
    m = _norm(mensaje)
    j = any(_norm(p) in m for p in _JURIDICA)
    p = any(_norm(x) in m for x in _PSICO)
    inm = any(_norm(x) in m for x in _INMEDIATA)
    tipo = "ambas" if j and p else "juridica" if j else "psicologica" if p else "ninguna"
    if inm and tipo == "ninguna":
        tipo = "ambas"
    urgencia = "inmediata" if inm else ("pronta" if tipo != "ninguna" else "ninguna")
    return {"tipo": tipo, "urgencia": urgencia}


_ORDEN_URG = ["ninguna", "informativa", "pronta", "inmediata"]


def combinar(a: dict | None, b: dict) -> dict:
    """Une la clasificación de Claude (a) con la de palabras clave (b): gana la más protectora."""
    if not a:
        return b
    tipos = {a.get("tipo", "ninguna"), b["tipo"]} - {"ninguna"}
    tipo = "ninguna" if not tipos else "ambas" if "ambas" in tipos or len(tipos) > 1 else tipos.pop()
    urg = max(a.get("urgencia", "ninguna"), b["urgencia"], key=lambda u: _ORDEN_URG.index(u) if u in _ORDEN_URG else 0)
    if tipo != "ninguna" and urg == "ninguna":
        urg = "informativa"
    return {"tipo": tipo, "urgencia": urg}
