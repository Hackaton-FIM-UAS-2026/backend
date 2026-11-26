"""M4 · Qué ve cada área del expediente único (lógica pura, sin base de datos).

Regla: cada especialista ve solo lo que necesita. Lo confidencial de otra área
se muestra como su `texto_publico` («En atención jurídica desde 26 nov») o como
candado, nunca su contenido.
"""

# Áreas de la línea de tiempo / notas que cada rol puede leer completas
AREAS_ROL = {
    "trabajo_social": {"general", "economico", "trabajo_social"},
    "especialista_juridica": {"general", "juridico"},
    "especialista_psicologica": {"general", "psicologia"},
    "asesora_economica": {"general", "economico"},
    "coordinacion": {"general"},
}
# Solicitudes (resumen + contacto seguro) por rol
SOLICITUDES_ROL = {
    "trabajo_social": None,  # todas
    "especialista_juridica": {"juridica", "ambas"},
    "especialista_psicologica": {"psicologica", "ambas"},
}
NOTAS_ROL = {"trabajo_social": "trabajo_social", "especialista_juridica": "juridico", "especialista_psicologica": "psicologia"}
NOMBRE_AREA = {"juridico": "Jurídico", "psicologia": "Psicología", "trabajo_social": "Trabajo Social"}
CONFIDENCIALES = {"juridico", "psicologia", "trabajo_social"}
# Lo único de la línea de tiempo que ven la usuaria («Mi avance») y la asesora económica
AREAS_PUBLICAS_USUARIA = ("general", "economico")


def ocultar_curp(curp: str | None) -> str | None:
    return f"{curp[:4]}******" if curp else None


def area_de_rol(rol: str) -> str | None:
    """Área con la que se guardan las notas y eventos de ese rol."""
    return NOTAS_ROL.get(rol) or ("economico" if rol == "asesora_economica" else None)


def vista_expediente(rol: str, exp: dict) -> dict:
    if rol not in AREAS_ROL:
        raise PermissionError("Este rol no puede ver expedientes")
    visibles = AREAS_ROL[rol]

    filtro = SOLICITUDES_ROL.get(rol, set())
    solicitudes = [s for s in exp.get("solicitudes", [])
                   if filtro is None or (s.get("area_asignada") in filtro)] if rol in SOLICITUDES_ROL else []

    eventos, bloqueos = [], []
    for e in exp.get("eventos", []):
        area = e.get("area") or "general"
        if area in visibles:
            eventos.append(e)
        elif e.get("texto_publico"):
            eventos.append({**e, "texto": e["texto_publico"]})
            if area in CONFIDENCIALES and e["texto_publico"] not in bloqueos:
                bloqueos.append(e["texto_publico"])

    propia = NOTAS_ROL.get(rol)
    notas = [n for n in exp.get("notas", []) if propia and n.get("area") == propia]
    for area in sorted({n.get("area") for n in exp.get("notas", [])} - {propia}):
        if area in NOMBRE_AREA:
            bloqueos.append(f"Las notas de {NOMBRE_AREA[area]} solo las ve esa área.")

    return {
        "general": exp.get("general", {}),
        "economico": exp.get("economico") if "economico" in visibles else None,
        "solicitudes": solicitudes,
        "eventos": eventos,
        "notas": notas,
        "bloqueos": bloqueos,
    }
