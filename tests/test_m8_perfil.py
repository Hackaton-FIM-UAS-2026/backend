"""Perfil de la usuaria: datos de identidad y entrevista dinámica."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.perfil.reglas import candidatas, curp_valida, rfc_valido, siguiente_pregunta  # noqa: E402

BASE = {"edad": "25 a 34", "municipio": "Ahome", "escolaridad": "Secundaria", "situacion": "Sin ingreso", "meta": "Un empleo",
        "horas_semana": "30 o más", "horario": ["Mañana"], "cuidados": ["Ninguna"], "dispositivo": "Celular con wifi",
        "habilidades": ["Cocina"], "negocio": "No", "documentos": ["CURP"]}


class TestDatos(unittest.TestCase):
    def test_curp(self):
        self.assertTrue(curp_valida("KEMU900114MSLBCR00"))
        self.assertTrue(curp_valida("kemu900114mslbcr00"))
        self.assertFalse(curp_valida("KEMU900114ZSLBCR00"))   # sexo inválido (H, M o X)
        self.assertFalse(curp_valida("ABC123"))

    def test_rfc(self):
        self.assertTrue(rfc_valido("ECB200101AB1"))
        self.assertTrue(rfc_valido("LORM920314AB3"))
        self.assertFalse(rfc_valido("12345"))


class TestEntrevista(unittest.TestCase):
    def test_no_pregunta_lo_que_ya_sabe(self):
        self.assertNotIn("edad", [c["campo"] for c in candidatas(BASE)])

    def test_omite_apoyo_cuidados_si_no_cuida_a_nadie(self):
        self.assertNotIn("apoyo_cuidados", [c["campo"] for c in candidatas(BASE)])
        self.assertIn("apoyo_cuidados", [c["campo"] for c in candidatas({**BASE, "cuidados": ["Niñas o niños"]})])

    def test_no_pregunta_rfc_si_ya_lo_marco(self):
        self.assertNotIn("tiene_rfc", [c["campo"] for c in candidatas({**BASE, "documentos": ["CURP", "RFC"]})])

    def test_la_ia_elige_y_reformula(self):
        q = siguiente_pregunta(BASE, llm=lambda *a: {"campo": "transporte", "pregunta": "Para trabajar fuera, ¿cómo te mueves?", "porque": "Así vemos qué tan lejos te queda."})
        self.assertEqual((q["campo"], q["pregunta"]), ("transporte", "Para trabajar fuera, ¿cómo te mueves?"))
        self.assertEqual(q["opciones"][0], "Camino o uso camión")   # las opciones siempre salen del diccionario

    def test_campo_inventado_por_la_ia_se_ignora(self):
        q = siguiente_pregunta(BASE, llm=lambda *a: {"campo": "salario_deseado", "pregunta": "x"})
        self.assertIn(q["campo"], [c["campo"] for c in candidatas(BASE)])

    def test_sin_ia_sigue_un_orden_fijo(self):
        q = siguiente_pregunta(BASE, llm=lambda *a: None)
        self.assertEqual(q["campo"], candidatas(BASE)[0]["campo"])

    def test_termina_cuando_no_falta_nada(self):
        todo = dict(BASE)
        for c in candidatas(BASE):
            todo[c["campo"]] = c["opciones"][0] if c["tipo"] == "unica" else [c["opciones"][0]]
        self.assertIsNone(siguiente_pregunta(todo, llm=lambda *a: None))


if __name__ == "__main__":
    unittest.main()
