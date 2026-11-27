"""M4 · Métricas de cada área (lo que le toca a cada especialista, nada más)."""
from datetime import date, timedelta

AREAS = {"especialista_juridica": {"juridica", "ambas"}, "especialista_psicologica": {"psicologica", "ambas"}}
MODULO = {"especialista_juridica": "juridico", "especialista_psicologica": "psicologia", "trabajo_social": "trabajo_social"}
ABIERTOS = {"nueva", "asignada", "contactada", "en atención"}


def _del_rol(rol: str, c: dict) -> bool:
    return c.get("area_asignada") in AREAS[rol] if rol in AREAS else True


def resumen_area(rol: str, casos: list[dict], visitas: list[dict], hoy: date) -> dict:
    mios = [c for c in casos if _del_rol(rol, c)]
    fecha = lambda c: date.fromisoformat(str(c["created_at"])[:10])
    abiertos = [c for c in mios if c["estado"] in ABIERTOS]
    return {
        "abiertos": len(abiertos),
        "urgentes": sum(1 for c in abiertos if c["urgencia"] == "inmediata"),
        "nuevos_semana": sum(1 for c in mios if fecha(c) >= hoy - timedelta(days=7)),
        "cerrados_mes": sum(1 for c in mios if c["estado"] == "cerrada" and fecha(c) >= hoy - timedelta(days=30)),
        "por_estado": {e: sum(1 for c in mios if c["estado"] == e) for e in ("nueva", "asignada", "contactada", "en atención", "cerrada")},
        "visitas_hoy": sum(1 for v in visitas if v["modulo"] == MODULO.get(rol) and str(v["fecha"]) == hoy.isoformat()),
    }
