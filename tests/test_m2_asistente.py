"""M2 · equipo de agentes del asistente (sin red: la IA se inyecta)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ia.plantillas import CONTACTO_EMERGENCIA  # noqa: E402
from app.modulos.asistente.agentes import filtrar_recursos, pide_persona, responder  # noqa: E402

CATALOGO = {
    "v-barista": {"id": "v-barista", "titulo": "Barista", "tipo": "vacante", "proveedor": "Empático coffee bar", "horario": "Mañanas"},
    "c-excel": {"id": "c-excel", "titulo": "Excel básico", "tipo": "curso", "proveedor": "Ejemplo", "horario": "Flexible"},
}
CTX = {"nombre": "María", "recomendados": ["v-barista", "c-excel"], "catalogo": CATALOGO}


def falso(salida):
    return lambda *a, **k: salida


class TestAsistente(unittest.TestCase):
    def test_emergencia_sin_llm(self):
        r = responder("me va a matar, está afuera de mi casa", [], CTX, llm=lambda *a: None)
        self.assertEqual(r["agente"], "emergencia")
        self.assertEqual(r["emergencia"]["telefono"], CONTACTO_EMERGENCIA["semujeres_24h"]["telefono"])
        self.assertEqual(r["emergencia"]["respaldo"], "911")
        self.assertTrue(r["texto"])

    def test_pide_persona_siempre_canaliza(self):
        r = responder("quiero hablar con una persona", [], CTX, llm=falso({"categoria": "oportunidades"}))
        self.assertEqual(r["agente"], "canalizacion")
        self.assertEqual(r["acciones"][0]["tipo"], "confirmar_canalizacion")
        self.assertEqual(r["acciones"][0]["area"], "no_se")

    def test_fuera_de_tema_no_cita_recursos(self):
        r = responder("cuanto es 5+5", [], CTX, llm=falso({"categoria": "fuera_de_tema", "texto": "Solo puedo…"}))
        self.assertEqual((r["agente"], r["recursos"]), ("recepcion", []))
        self.assertEqual(r["texto"], "Solo puedo…")

    def test_descarta_recursos_inexistentes(self):
        self.assertEqual([x["id"] for x in filtrar_recursos(["v-barista", "inventado"], CATALOGO)], ["v-barista"])

    def test_pide_persona_variantes(self):
        for t in ["Hablar con una persona", "quiero hablar con alguien de verdad", "me pasas con una licenciada"]:
            self.assertTrue(pide_persona(t), t)
        self.assertFalse(pide_persona("busco trabajo de cajera"))

    def test_oportunidades_cita_solo_catalogo(self):
        r = responder("busco trabajo en la mañana", [], CTX,
                      llm=falso({"categoria": "oportunidades", "texto": "Mira estas:", "recurso_ids": ["v-barista", "x-falso"]}))
        self.assertEqual(r["agente"], "oportunidades")
        self.assertEqual([x["id"] for x in r["recursos"]], ["v-barista"])

    def test_oportunidades_sin_llm_usa_recomendados(self):
        r = responder("busco trabajo", [], CTX, llm=lambda *a: None)
        self.assertEqual(r["agente"], "oportunidades")
        self.assertTrue(r["texto"])
        self.assertIn("v-barista", [x["id"] for x in r["recursos"]])

    def test_senal_de_violencia_gana_a_oportunidades(self):
        r = responder("mi pareja me golpea y busco trabajo", [], CTX, llm=falso({"categoria": "oportunidades"}))
        self.assertEqual(r["agente"], "canalizacion")

    def test_amenaza_en_curso_sin_llm_es_emergencia(self):
        r = responder("ya llegó y me está amenazando", [], CTX, llm=lambda *a: None)
        self.assertEqual(r["agente"], "emergencia")
        self.assertIsNotNone(r["emergencia"])

    def test_fuera_de_tema_sin_llm_no_muestra_vacantes(self):
        r = responder("cuanto es 5+5", [], CTX, llm=lambda *a: None)
        self.assertEqual((r["agente"], r["recursos"]), ("recepcion", []))


if __name__ == "__main__":
    unittest.main()
