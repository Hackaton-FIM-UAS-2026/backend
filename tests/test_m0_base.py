"""M0 · registro automático de módulos."""
import os
import shutil
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ["EMPODERATE_TEST"] = "1"

from fastapi import FastAPI  # noqa: E402

from app.modulos import registrar  # noqa: E402

MODS = RAIZ / "app" / "modulos"


class TestRegistro(unittest.TestCase):
    def setUp(self):
        (MODS / "_prueba").mkdir(exist_ok=True)
        (MODS / "_prueba" / "__init__.py").write_text("")
        (MODS / "_prueba" / "router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
            "@router.get('/_prueba')\ndef p():\n    return {}\n")
        (MODS / "_sinrouter").mkdir(exist_ok=True)
        (MODS / "_sinrouter" / "__init__.py").write_text("")

    def tearDown(self):
        shutil.rmtree(MODS / "_prueba", ignore_errors=True)
        shutil.rmtree(MODS / "_sinrouter", ignore_errors=True)

    def test_registra_modulo_con_router(self):
        app = FastAPI()
        nombres = registrar(app)
        self.assertIn("_prueba", nombres)
        from fastapi.testclient import TestClient
        self.assertEqual(TestClient(app).get("/_prueba").status_code, 200)

    def test_ignora_carpeta_sin_router(self):
        self.assertNotIn("_sinrouter", registrar(FastAPI()))


if __name__ == "__main__":
    unittest.main()
