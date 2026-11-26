"""M7 · empresas aliadas en la landing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modulos.portada.router import aliadas  # noqa: E402


class TestPortada(unittest.TestCase):
    def test_solo_aprobadas_con_logo(self):
        filas = [{"nombre": "Medusa", "estado": "aprobada", "logo_url": "/m.png"},
                 {"nombre": "Del Valle", "estado": "pendiente", "logo_url": "/d.png"},
                 {"nombre": "Ruiz", "estado": "aprobada", "logo_url": None},
                 {"nombre": "Empático", "estado": "aprobada", "logo_url": "/e.png"}]
        self.assertEqual(aliadas(filas), [{"nombre": "Empático", "logo_url": "/e.png"}, {"nombre": "Medusa", "logo_url": "/m.png"}])


if __name__ == "__main__":
    unittest.main()
