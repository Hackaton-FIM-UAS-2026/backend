"""M6 · Motor de ruta. Lo decide el CÓDIGO, no la IA: reproducible y auditable.

La IA solo redacta los `factores` que regresa esta función.
"""
import json
from pathlib import Path

from .requisitos import evaluar_condicion

RUTAS = ("empleabilidad", "emprendimiento", "capacitacion")
NOMBRE_RUTA = {"empleabilidad": "Empleabilidad", "emprendimiento": "Emprendimiento", "capacitacion": "Capacitación"}

_CONFIG = json.loads((Path(__file__).with_name("pesos_ruta.json")).read_text(encoding="utf-8"))


def calcular_ruta(valores: dict, config: dict | None = None) -> dict:
    cfg = config or _CONFIG
    puntajes = {r: 0 for r in RUTAS}
    factores = []
    for s in cfg["senales"]:
        if evaluar_condicion(s["si"], valores) is True:
            for ruta, pts in s["suma"].items():
                puntajes[ruta] += pts
            factores.append({"id": s["id"], "texto": s["texto"], "suma": s["suma"]})

    # sorted es estable: en empate gana el orden de RUTAS (igual que el front)
    orden = sorted(RUTAS, key=lambda r: -puntajes[r])
    principal, segunda = orden[0], orden[1]
    puente = None
    if puntajes[segunda] > 0 and puntajes[principal] - puntajes[segunda] <= cfg.get("margen_puente", 2):
        puente = segunda
    elif principal != "capacitacion" and "puente_capacitacion" in cfg:
        pc = cfg["puente_capacitacion"]
        if evaluar_condicion(pc["si"], valores) is True:
            puente = "capacitacion"
            factores.append({"id": "puente_capacitacion", "texto": pc["texto"], "suma": {}})

    if puntajes[principal] == 0:
        principal, puente = "capacitacion", None  # sin datos: empezar por aprender

    # Los factores que más suman primero (alimentan la explicación)
    factores.sort(key=lambda f: -sum(f["suma"].values()))
    return {"principal": principal, "puente": puente, "puntajes": puntajes, "factores": factores}


def explicacion_respaldo(ruta: dict) -> str:
    """Plantilla si el LLM falla o tarda más del límite."""
    textos = [f["texto"].lower() for f in ruta["factores"][:3]]
    base = f"Te sugerimos {NOMBRE_RUTA[ruta['principal']]}"
    if textos:
        base += " porque " + (", ".join(textos[:-1]) + " y " + textos[-1] if len(textos) > 1 else textos[0])
    base += "."
    if ruta.get("puente"):
        base += f" Como paso intermedio, te sugerimos {NOMBRE_RUTA[ruta['puente']]}."
    return base
