"""M4 · permisos por área del expediente único."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.expediente.permisos import ocultar_curp, vista_expediente  # noqa: E402

EXP_JURIDICO = {
    "general": {"nombre": "María López", "edad": "25 a 34"},
    "economico": {"campos": {"escolaridad": "Secundaria"}, "recursos": []},
    "solicitudes": [{"folio": "C-014", "area_asignada": "juridica", "urgencia": "pronta",
                     "resumen": "Pensión alimenticia de 2 hijos.", "contacto": {"medio": "WhatsApp"}}],
    "eventos": [
        {"area": "general", "texto": "Hizo su test", "texto_publico": None, "fecha": "2 oct"},
        {"area": "juridico", "texto": "Asignada a Jurídico por Trabajo Social (C-014)",
         "texto_publico": "En atención jurídica desde 26 nov", "fecha": "26 nov"},
    ],
    "notas": [{"area": "juridico", "texto": "Se agenda cita el lunes.", "fecha": "26 nov"},
              {"area": "trabajo_social", "texto": "Primer contacto hecho.", "fecha": "26 nov"}],
}


class TestPermisos(unittest.TestCase):
    def test_psicologia_no_ve_juridico(self):
        v = vista_expediente("especialista_psicologica", EXP_JURIDICO)
        self.assertEqual(v["solicitudes"], [])
        self.assertEqual(v["notas"], [])
        textos = [e["texto"] for e in v["eventos"]]
        self.assertIn("En atención jurídica desde 26 nov", textos)
        self.assertNotIn("Asignada a Jurídico por Trabajo Social (C-014)", textos)
        self.assertTrue(v["bloqueos"])

    def test_juridica_ve_lo_suyo(self):
        v = vista_expediente("especialista_juridica", EXP_JURIDICO)
        self.assertEqual(v["solicitudes"][0]["folio"], "C-014")
        self.assertEqual([n["area"] for n in v["notas"]], ["juridico"])

    def test_trabajo_social_ve_resumen(self):
        v = vista_expediente("trabajo_social", EXP_JURIDICO)
        self.assertEqual(v["solicitudes"][0]["resumen"], EXP_JURIDICO["solicitudes"][0]["resumen"])
        self.assertEqual([n["area"] for n in v["notas"]], ["trabajo_social"])

    def test_asesora_ve_economico_sin_solicitudes(self):
        v = vista_expediente("asesora_economica", EXP_JURIDICO)
        self.assertIsNotNone(v["economico"])
        self.assertEqual((v["solicitudes"], v["notas"]), ([], []))

    def test_coordinacion_solo_general(self):
        v = vista_expediente("coordinacion", EXP_JURIDICO)
        self.assertIsNone(v["economico"])
        self.assertEqual(v["solicitudes"], [])

    def test_recepcion_no_entra(self):
        with self.assertRaises(PermissionError):
            vista_expediente("recepcion", EXP_JURIDICO)

    def test_curp_oculta(self):
        self.assertEqual(ocultar_curp("LORM920314MSLPMR05"), "LORM******")
        self.assertIsNone(ocultar_curp(None))


if __name__ == "__main__":
    unittest.main()


class TestPrivacidadLineaDeTiempo(unittest.TestCase):
    def test_eventos_visibles_para_ella_y_la_asesora(self):
        from app.modulos.expediente.permisos import AREAS_PUBLICAS_USUARIA
        self.assertEqual(AREAS_PUBLICAS_USUARIA, ("general", "economico"))

    def test_asignar_ambas_no_es_general(self):
        from app.modulos.expediente.router import AREA_EVENTO
        self.assertNotIn("general", AREA_EVENTO.values())
