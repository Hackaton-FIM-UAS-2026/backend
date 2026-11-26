"""Pruebas del dominio (sin red ni dependencias): python -m unittest discover -s tests

Las tres personas de la demo son la garantía de que el motor da lo que
promete el pitch. Si alguien cambia pesos_ruta.json y estas fallan, la demo cambió.
"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.dominio.fusion import fusionar, valores  # noqa: E402
from app.dominio.matching import recomendar  # noqa: E402
from app.dominio.motor_ruta import calcular_ruta, explicacion_respaldo  # noqa: E402
from app.dominio.requisitos import evaluar_recurso  # noqa: E402

CATALOGO = json.loads((RAIZ / "data" / "catalogo.json").read_text(encoding="utf-8"))
HOY = date(2026, 11, 27)

MARIA = {"edad": "25 a 34", "municipio": "Ahome", "escolaridad": "Secundaria", "situacion": "Negocio propio",
         "meta": "Iniciar o hacer crecer un negocio", "horas_semana": "10 a 15", "horario": ["Mañana"],
         "cuidados": ["Niñas o niños"], "dispositivo": "Solo celular con datos", "habilidades": ["Cocina", "Ventas"],
         "negocio": "Ya vendo", "documentos": ["CURP", "INE"]}
LUCIA = {"edad": "18 a 24", "municipio": "Ahome", "escolaridad": "Preparatoria", "situacion": "Sin ingreso",
         "meta": "Un empleo", "horas_semana": "30 o más", "horario": ["Mañana", "Tarde"], "cuidados": ["Ninguna"],
         "dispositivo": "Computadora", "habilidades": ["Atención al cliente", "Computación"], "negocio": "No",
         "documentos": ["CURP", "INE", "RFC"]}
ROSA = {"edad": "45 a 59", "municipio": "Ahome", "escolaridad": "Primaria", "situacion": "Empleo informal",
        "meta": "Aprender algo nuevo", "horas_semana": "10 a 15", "horario": ["Tarde"], "cuidados": ["Personas mayores"],
        "dispositivo": "Solo celular con datos", "habilidades": ["Costura"], "negocio": "Tengo una idea",
        "documentos": ["CURP", "INE"]}


class TestMotorRuta(unittest.TestCase):
    def test_maria_emprendimiento_con_puente_capacitacion(self):
        r = calcular_ruta(MARIA)
        self.assertEqual((r["principal"], r["puente"]), ("emprendimiento", "capacitacion"))

    def test_lucia_empleabilidad_sin_puente(self):
        r = calcular_ruta(LUCIA)
        self.assertEqual((r["principal"], r["puente"]), ("empleabilidad", None))

    def test_rosa_capacitacion_hacia_emprendimiento(self):
        r = calcular_ruta(ROSA)
        self.assertEqual((r["principal"], r["puente"]), ("capacitacion", "emprendimiento"))

    def test_sin_datos(self):
        self.assertEqual(calcular_ruta({})["principal"], "capacitacion")

    def test_explicacion_respaldo(self):
        t = explicacion_respaldo(calcular_ruta(MARIA))
        self.assertIn("Emprendimiento", t)
        self.assertIn("Capacitación", t)


class TestRequisitos(unittest.TestCase):
    def test_faltante_y_duro(self):
        r2 = next(r for r in CATALOGO if r["id"] == "r2")
        ev = evaluar_recurso(r2["requisitos"], MARIA)
        self.assertFalse(ev["excluido"])
        self.assertEqual(ev["faltantes"], ["tiene_rfc"])
        ev = evaluar_recurso(r2["requisitos"], {**MARIA, "municipio": "Guasave"})
        self.assertTrue(ev["excluido"])

    def test_ordinal(self):
        r3 = next(r for r in CATALOGO if r["id"] == "r3")
        self.assertTrue(evaluar_recurso(r3["requisitos"], MARIA)["excluido"])  # secundaria < prepa
        ev = evaluar_recurso(r3["requisitos"], {**LUCIA, "habilidad_excel": "Intermedio"})
        self.assertTrue(ev["cumple"])

    def test_requisito_manual_no_genera_pregunta(self):
        ev = evaluar_recurso([{"campo": "req_x", "label": "Traer CV impreso", "duro": False}], MARIA)
        self.assertEqual(ev["faltantes"], [])
        self.assertIsNone(ev["requisitos"][0]["ok"])


class TestFusion(unittest.TestCase):
    def test_version_y_eventos(self):
        f = fusionar({"campos": {}, "version": 0}, MARIA, "test_base")
        self.assertEqual(f["expediente"]["version"], 1)
        self.assertEqual(len(f["eventos"]), len(MARIA))
        f2 = fusionar(f["expediente"], {"meta": MARIA["meta"]}, "test_base")
        self.assertFalse(f2["cambio"])

    def test_personal_no_sobrescribe_a_ella(self):
        e = fusionar({"campos": {}, "version": 0}, {"tiene_rfc": "No"}, "entrevista")["expediente"]
        f = fusionar(e, {"tiene_rfc": "Sí"}, "personal_cemujeres", autor="asesora-1")
        self.assertEqual(f["expediente"]["campos"]["tiene_rfc"]["valor"], "No")
        self.assertEqual(len(f["expediente"]["conflictos"]), 1)
        # Cuando ella responde, el conflicto se resuelve
        g = fusionar(f["expediente"], {"tiene_rfc": "Sí"}, "usuaria_edito")
        self.assertEqual(g["expediente"]["conflictos"], [])

    def test_inferido_baja_confianza_no_cuenta(self):
        e = fusionar({"campos": {}, "version": 0}, {"tiene_rfc": "Sí"}, "inferido_ia", confianza=0.5)["expediente"]
        self.assertNotIn("tiene_rfc", valores(e))
        e = fusionar(e, {"tiene_rfc": "Sí"}, "entrevista")["expediente"]
        self.assertEqual(valores(e)["tiene_rfc"], "Sí")

    def test_ia_no_pisa_dato_de_ella(self):
        e = fusionar({"campos": {}, "version": 0}, {"tiene_rfc": "No"}, "entrevista")["expediente"]
        f = fusionar(e, {"tiene_rfc": "Sí"}, "inferido_ia", confianza=0.9)
        self.assertEqual(f["ignorados"], ["tiene_rfc"])

    def test_valor_invalido(self):
        with self.assertRaises(ValueError):
            fusionar({"campos": {}}, {"meta": "Ser astronauta"}, "test_base")
        with self.assertRaises(ValueError):
            fusionar({"campos": {}}, {"campo_inventado": "x"}, "test_base")


class TestMatching(unittest.TestCase):
    def test_maria(self):
        recs = recomendar(CATALOGO, MARIA, calcular_ruta(MARIA), hoy=HOY)
        ids = [r["id"] for r in recs]
        self.assertNotIn("r3", ids)  # vacante: no es su ruta
        self.assertIn("r2", ids)
        self.assertFalse(recs[0]["es_puente"])  # lo de su ruta principal va primero

    def test_vencidos_fuera(self):
        recs = recomendar(CATALOGO, LUCIA, calcular_ruta(LUCIA), hoy=date(2026, 12, 11))
        self.assertNotIn("r3", [r["id"] for r in recs])

    def test_lucia_vacante(self):
        recs = recomendar(CATALOGO, LUCIA, calcular_ruta(LUCIA), hoy=HOY)
        self.assertEqual(recs[0]["id"], "r3")
        self.assertEqual(recs[0]["faltantes"], ["habilidad_excel"])


if __name__ == "__main__":
    unittest.main()


class TestSenales(unittest.TestCase):
    """Respaldo por palabras clave del flujo sensible (sin red)."""

    def setUp(self):
        from app.ia.plantillas import combinar, senal_por_palabras
        self.p, self.c = senal_por_palabras, combinar

    def test_juridica(self):
        self.assertEqual(self.p("Mi pareja no me deja trabajar")["tipo"], "juridica")

    def test_psicologica_sin_acentos(self):
        self.assertEqual(self.p("ya no puedo mas")["tipo"], "psicologica")

    def test_inmediata(self):
        self.assertEqual(self.p("Estoy en peligro, me va a matar")["urgencia"], "inmediata")

    def test_neutro(self):
        self.assertEqual(self.p("¿Hay cursos de costura?"), {"tipo": "ninguna", "urgencia": "ninguna"})

    def test_combinar_gana_lo_protector(self):
        r = self.c({"tipo": "ninguna", "urgencia": "ninguna"}, {"tipo": "juridica", "urgencia": "pronta"})
        self.assertEqual(r, {"tipo": "juridica", "urgencia": "pronta"})
        r = self.c({"tipo": "psicologica", "urgencia": "inmediata"}, {"tipo": "juridica", "urgencia": "pronta"})
        self.assertEqual(r, {"tipo": "ambas", "urgencia": "inmediata"})
        self.assertEqual(self.c(None, {"tipo": "ninguna", "urgencia": "ninguna"})["tipo"], "ninguna")
