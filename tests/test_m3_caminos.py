"""M3 · caminos con puentes (lógica pura)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.caminos.etiquetas import etiquetar  # noqa: E402
from app.modulos.caminos.puentes import armar_caminos  # noqa: E402

V_AUX_CONTABLE = {"id": "v-aux-contable", "titulo": "Auxiliar contable", "tipo": "vacante", "proveedor": "Despacho Ruiz",
                  "horario": "Mañanas", "ubicacion": "Los Mochis", "sueldo": "$8,500 al mes",
                  "requisitos": [{"campo": "escolaridad", "op": ">=", "valor": "Secundaria", "duro": True, "label": "Secundaria terminada"},
                                 {"campo": "habilidad_excel", "op": ">=", "valor": "Básico", "duro": False, "label": "Saber Excel básico"},
                                 {"campo": "tiene_rfc", "op": "==", "valor": "Sí", "duro": False, "label": "Tener RFC"}],
                  "etiquetas": {"pide": ["escolaridad", "habilidad_excel", "tiene_rfc"], "da": [], "temas": ["contabilidad", "oficina"]}}
C_EXCEL = {"id": "c-excel", "titulo": "Excel básico", "tipo": "curso", "proveedor": "Ejemplo", "modalidad": "En línea", "costo": "Gratis",
           "requisitos": [], "etiquetas": {"pide": [], "da": ["habilidad_excel"], "temas": ["oficina", "computación"]}}
C_SAT = {"id": "c-sat", "titulo": "Tu RFC y facturas", "tipo": "curso", "proveedor": "Ejemplo SAT", "modalidad": "Presencial", "costo": "Gratis",
         "requisitos": [], "etiquetas": {"pide": [], "da": ["tiene_rfc"], "temas": ["contabilidad"]}}
C_REPO = {"id": "c-repo", "titulo": "Repostería", "tipo": "curso", "proveedor": "Ejemplo", "requisitos": [],
          "etiquetas": {"pide": [], "da": [], "temas": ["alimentos"]}}

MARIA = {"escolaridad": "Secundaria", "habilidad_excel": "Nada", "documentos": ["CURP", "INE"]}
LUCIA_CON_EXCEL = {"escolaridad": "Media superior", "habilidad_excel": "Básico", "tiene_rfc": "Sí"}


class TestCaminos(unittest.TestCase):
    def test_vacante_con_puente_de_excel(self):
        c = armar_caminos(MARIA, [V_AUX_CONTABLE, C_EXCEL, C_SAT])[0]
        self.assertEqual(c["meta"]["id"], "v-aux-contable")
        pares = [(p["recurso"]["id"], p["motivo"]) for p in c["puentes"]]
        self.assertIn(("c-excel", "te_falta"), pares)
        self.assertIn(("c-sat", "te_falta"), pares)
        self.assertEqual((c["meta"]["cumplidos"], c["meta"]["total"]), (1, 3))

    def test_puente_por_tema(self):
        c = armar_caminos(LUCIA_CON_EXCEL, [V_AUX_CONTABLE, C_SAT, C_REPO])[0]
        self.assertEqual([(p["recurso"]["id"], p["motivo"]) for p in c["puentes"]], [("c-sat", "tema")])

    def test_sin_test_no_falla(self):
        caminos = armar_caminos({}, [V_AUX_CONTABLE, C_EXCEL])
        self.assertIsInstance(caminos, list)
        self.assertTrue(all("meta" in c and "puentes" in c for c in caminos))

    def test_curso_no_es_meta_ni_se_repite(self):
        caminos = armar_caminos(MARIA, [V_AUX_CONTABLE, C_EXCEL, C_EXCEL])
        self.assertTrue(all(c["meta"]["tipo"] != "curso" for c in caminos))
        ids = [p["recurso"]["id"] for p in caminos[0]["puentes"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_excluida_por_requisito_duro_no_es_meta(self):
        self.assertEqual(armar_caminos({"escolaridad": "Primaria"}, [V_AUX_CONTABLE, C_EXCEL]), [])

    def test_incluye_un_camino_con_puente_si_existe(self):
        llenas = [{"id": f"a{i}", "titulo": f"A{i}", "tipo": "apoyo", "requisitos": [], "etiquetas": {}} for i in range(4)]
        caminos = armar_caminos(MARIA, llenas + [V_AUX_CONTABLE, C_EXCEL])
        self.assertEqual(len(caminos), 3)
        self.assertIn("v-aux-contable", [c["meta"]["id"] for c in caminos])
        self.assertEqual([c["meta"]["id"] for c in caminos][:2], ["a0", "a1"])

    def test_etiquetar_descarta_campos_inventados(self):
        e = etiquetar(C_EXCEL, llm=lambda *a: {"pide": [], "da": ["habilidad_excel", "campo_falso"], "temas": ["Ofimática"]})
        self.assertEqual((e["da"], e["temas"]), (["habilidad_excel"], ["ofimática"]))

    def test_etiquetar_sin_llm_usa_requisitos(self):
        e = etiquetar(V_AUX_CONTABLE, llm=lambda *a: None)
        self.assertEqual(e["pide"], ["escolaridad", "habilidad_excel", "tiene_rfc"])
        self.assertEqual(e["da"], [])


if __name__ == "__main__":
    unittest.main()
