"""Aplicar / Guardar: idempotentes y sin bajar de estado."""
import sys
import os
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("EMPODERATE_TEST", "1")

from app.dominio.acciones import decidir_accion, es_evento_de_accion  # noqa: E402


class TestAcciones(unittest.TestCase):
    def test_accion_idempotente(self):
        self.assertEqual(decidir_accion(None, "aplicar"), ("aplicado", True))
        self.assertEqual(decidir_accion("aplicado", "aplicar"), ("aplicado", False))
        self.assertEqual(decidir_accion("guardado", "guardar"), ("guardado", False))

    def test_guardar_luego_aplicar_sube(self):
        self.assertEqual(decidir_accion("guardado", "aplicar"), ("aplicado", True))

    def test_guardar_no_baja_aplicado(self):
        self.assertEqual(decidir_accion("aplicado", "guardar"), ("aplicado", False))
        self.assertEqual(decidir_accion("contratada", "aplicar"), ("contratada", False))

    def test_seguimiento_sin_eventos_de_accion(self):
        self.assertTrue(es_evento_de_accion("Aplicó a «Auxiliar contable»"))
        self.assertTrue(es_evento_de_accion("Guardó «Excel básico»"))
        self.assertFalse(es_evento_de_accion("Test base completado"))


class _Consulta:
    """Imitación mínima del query builder de supabase-py para recursos_usuaria."""
    def __init__(self, bd, leido):
        self.bd, self.leido, self.op = bd, leido, None

    def select(self, *_):
        self.op = "select"
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def upsert(self, fila, ignore_duplicates=False):
        self.op, self.fila, self.ignorar = "upsert", fila, ignore_duplicates
        return self

    def execute(self):
        if self.op == "select":           # lectura (posiblemente atrasada)
            return SimpleNamespace(data=[{"estado": self.leido}] if self.leido else [])
        if self.ignorar and self.bd.get("estado"):
            return SimpleNamespace(data=[])  # ya existía: no se toca
        self.bd["estado"] = self.fila["estado"]
        return SimpleNamespace(data=[self.fila])


class TestRutaAccion(unittest.TestCase):
    """Dos peticiones casi simultáneas: la segunda leyó antes de que la primera escribiera."""

    def correr(self, bd, leido, accion):
        from app.routers import usuaria as u
        fila = SimpleNamespace(data=[{"id": "r", "titulo": "Cajera", "url_accion": "#"}])
        consulta = SimpleNamespace(execute=lambda: fila)
        consulta.select = consulta.eq = consulta.limit = lambda *_: consulta
        recurso = SimpleNamespace(from_=lambda *_: consulta)
        eventos = []
        with patch.object(u, "como", lambda _t: nullcontext(recurso)), \
                patch.object(u, "servicio", lambda: SimpleNamespace(table=lambda _n: _Consulta(bd, leido))), \
                patch.object(u.sv, "evento", lambda *a, **k: eventos.append(a[1])), \
                patch.object(u.sv, "ahora_iso", lambda: "2026-11-26"):
            out = u.accion("r", u.Accion(accion=accion), SimpleNamespace(user_id="x", token="t"))
        return out, eventos

    def test_guardar_atrasado_no_baja_aplicado(self):
        bd = {"estado": "aplicado"}            # la de «Aplicar» ya escribió
        out, eventos = self.correr(bd, None, "guardar")   # pero «Guardar» leyó antes
        self.assertEqual(bd["estado"], "aplicado")
        self.assertEqual(eventos, [])
        self.assertFalse(out["nuevo"])

    def test_aplicar_registra_un_evento(self):
        bd = {}
        out, eventos = self.correr(bd, None, "aplicar")
        self.assertEqual((bd["estado"], eventos, out["nuevo"]), ("aplicado", ["Aplicó a «Cajera»"], True))


class _Perfiles:
    def __init__(self, bd):
        self.bd, self.op = bd, None

    def upsert(self, fila, **_):
        self.op, self.fila = "upsert", fila
        return self

    def select(self, *_):
        self.op = "select"
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.op == "upsert":
            self.bd.update({k: v for k, v in self.fila.items() if k in ("nombre", "telefono")})
            return SimpleNamespace(data=[self.fila])
        return SimpleNamespace(data=[{"nombre": self.bd.get("nombre")}])


class TestRegistro(unittest.TestCase):
    """El front necesita saber si ya tiene nombre (cuentas de Google llegan sin él)."""

    def registrar(self, bd, **body):
        from app.routers import usuaria as u
        nada = SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))
        tablas = {"perfiles": _Perfiles(bd), "expedientes": SimpleNamespace(upsert=lambda *a, **k: nada)}
        with patch.object(u, "servicio", lambda: SimpleNamespace(table=lambda n: tablas[n])), \
                patch.object(u.sv, "ahora_iso", lambda: "2026-11-26"):
            return u.registro(u.Registro(acepto_privacidad=True, **body), SimpleNamespace(user_id="x", correo="a@b.c"))

    def test_sin_nombre(self):
        self.assertIsNone(self.registrar({})["nombre"])

    def test_conserva_nombre_guardado(self):
        self.assertEqual(self.registrar({"nombre": "Lucía"})["nombre"], "Lucía")

    def test_guarda_nombre_nuevo(self):
        self.assertEqual(self.registrar({}, nombre=" Rosa ")["nombre"], "Rosa")


if __name__ == "__main__":
    unittest.main()
