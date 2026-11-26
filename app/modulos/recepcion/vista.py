"""M5 · Lo que ve Recepción de cada visita: nunca el motivo."""
MODULO = {"trabajo_social": "Trabajo Social", "juridico": "Jurídico", "psicologia": "Psicología",
          "economico": "Empoderamiento económico"}
_FRANJA = {"mañana": 0, "tarde": 1}


def fila_visita(v: dict, nombre: str) -> dict:
    return {"id": v["id"], "fecha": v["fecha"], "franja": v["franja"], "nombre": nombre,
            "modulo": MODULO.get(v["modulo"], v["modulo"]), "estado": v["estado"]}


def ordenar(visitas: list[dict]) -> list[dict]:
    return sorted(visitas, key=lambda v: (v["fecha"], _FRANJA.get(v["franja"], 9), v["id"]))
