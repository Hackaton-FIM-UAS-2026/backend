"""M5 · recepción: visitas previstas sin exponer el motivo."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.recepcion.vista import fila_visita, ordenar  # noqa: E402

VISITA = {"id": 1, "fecha": "2026-11-27", "franja": "mañana", "modulo": "trabajo_social", "estado": "por_llegar"}


class TestRecepcion(unittest.TestCase):
    def test_fila_no_expone_motivo(self):
        f = fila_visita({**VISITA, "motivo": "x", "usuaria_id": "u1", "origen": "asistente"}, "María L.")
        self.assertEqual(set(f), {"id", "fecha", "franja", "nombre", "modulo", "estado"})

    def test_modulo_legible(self):
        self.assertEqual(fila_visita(VISITA, "María")["modulo"], "Trabajo Social")
        self.assertEqual(fila_visita({**VISITA, "modulo": "economico"}, "M")["modulo"], "Empoderamiento económico")

    def test_orden_fecha_y_mañana_primero(self):
        v = [{**VISITA, "id": 1, "franja": "tarde"}, {**VISITA, "id": 2, "franja": "mañana"},
             {**VISITA, "id": 3, "fecha": "2026-11-26", "franja": "tarde"}]
        self.assertEqual([x["id"] for x in ordenar(v)], [3, 2, 1])


if __name__ == "__main__":
    unittest.main()
