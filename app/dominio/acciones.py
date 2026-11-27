"""Aplicar / Guardar un recurso: qué estado queda y si hay que registrar un evento.

Picar dos veces no debe duplicar nada, y "Guardar" nunca baja a quien ya aplicó
(ni a quien el personal ya marcó como inscrita, contratada, etc.).
"""

ORDEN = {"guardado": 1, "aplicado": 2, "inscrita": 3, "terminado": 4, "contratada": 5}
ESTADO_DE = {"aplicar": "aplicado", "guardar": "guardado"}
PREFIJOS = ("Aplicó a «", "Guardó «")


def decidir_accion(actual: str | None, accion: str) -> tuple[str, bool]:
    """Regresa (estado que queda, si cambió)."""
    pedido = ESTADO_DE[accion]
    if actual and ORDEN.get(actual, 0) >= ORDEN[pedido]:
        return actual, False
    return pedido, True


def es_evento_de_accion(texto: str) -> bool:
    """Eventos que ya se muestran en la lista de recursos de "Mi avance"."""
    return texto.startswith(PREFIJOS)
