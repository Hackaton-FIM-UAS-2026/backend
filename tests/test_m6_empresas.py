"""M6 · empresas: revisión humana, perfil laboral limitado y señales de alerta."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.empresas.reglas import alerta, perfil_laboral, publicable, senales_heuristicas  # noqa: E402

V_EDECAN = {"titulo": "Edecán para eventos", "sueldo": "$25,000 a la semana", "ubicacion": "Guadalajara, Jal. (viaje pagado)",
            "descripcion": "Buscamos señoritas. Enviar fotos de cuerpo completo. Viaje pagado y hospedaje incluido."}
V_NORMAL = {"titulo": "Cajera", "sueldo": "$7,800 al mes", "ubicacion": "Los Mochis", "descripcion": "Cobro en caja."}
PERFIL = {"nombre": "María López", "telefono": "668 555 0101", "curp": "X", "colonia": "Y", "correo": "m@x"}
CAMPOS = {"escolaridad": "Secundaria", "habilidades": ["Cocina", "Ventas"], "tiene_experiencia": "Sí", "cuidados": ["Niñas o niños"]}


class TestEmpresas(unittest.TestCase):
    def test_vacante_pendiente_no_publicada(self):
        self.assertFalse(publicable({"estado_revision": "pendiente"}, {"estado": "aprobada"}))
        self.assertFalse(publicable({"estado_revision": "aprobada"}, {"estado": "pendiente"}))
        self.assertFalse(publicable({"estado_revision": "aprobada"}, {"estado": "rechazada"}))
        self.assertTrue(publicable({"estado_revision": "aprobada"}, {"estado": "aprobada"}))

    def test_perfil_laboral_limitado(self):
        p = perfil_laboral(PERFIL, CAMPOS)
        self.assertEqual(set(p), {"nombre", "escolaridad", "habilidades", "experiencia", "telefono"})
        self.assertEqual(p["habilidades"], "Cocina, Ventas")
        self.assertNotIn("Niñas", str(p))

    def test_senales_edecan(self):
        s = senales_heuristicas(V_EDECAN)
        self.assertTrue(any("fotos" in x for x in s))
        self.assertTrue(any("Sinaloa" in x for x in s))
        self.assertTrue(any("sueldo" in x.lower() for x in s))

    def test_vacante_normal_sin_senales(self):
        self.assertEqual(senales_heuristicas(V_NORMAL), [])

    def test_alerta_sin_llm_usa_heuristicas(self):
        self.assertIsNotNone(alerta(V_EDECAN, llm=lambda *a: None))
        self.assertIsNone(alerta(V_NORMAL, llm=lambda *a: None))


if __name__ == "__main__":
    unittest.main()
