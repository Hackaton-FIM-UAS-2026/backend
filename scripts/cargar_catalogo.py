"""Carga (o actualiza) el catálogo desde data/catalogo.json y genera embeddings.

    python -m scripts.cargar_catalogo                 # usa data/catalogo.json
    python -m scripts.cargar_catalogo otro.json

Responsable: Datos y matching. Reglas: solo recursos reales y verificados,
`verificado_el` con mes y año, requisitos con campos del diccionario.
"""
import json
import sys
from pathlib import Path

from app.db import servicio
from app.dominio.diccionario import CAMPOS
from app.dominio.requisitos import OPS
from app.ia import embeddings


def validar(r: dict) -> list[str]:
    errores = []
    for k in ("id", "titulo", "proveedor", "tipo", "rutas"):
        if not r.get(k):
            errores.append(f"falta {k}")
    for q in r.get("requisitos", []):
        if q.get("op") and q.get("op") not in OPS:
            errores.append(f"op desconocido {q['op']}")
        if q.get("op") and q.get("campo") not in CAMPOS:
            errores.append(f"campo «{q.get('campo')}» no está en el diccionario: agrégalo en app/dominio/diccionario.py")
    return errores


def main(ruta: str):
    recursos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    malos = {r.get("id", "?"): e for r in recursos if (e := validar(r))}
    if malos:
        for k, e in malos.items():
            print(f"✗ {k}: {'; '.join(e)}")
        sys.exit(1)
    sin_emb = 0
    for r in recursos:
        v = embeddings.embed(embeddings.texto_recurso(r))
        if v:
            r["embedding"] = embeddings.como_texto(v)
        else:
            sin_emb += 1
        r.setdefault("publicada", True)
    servicio().table("recursos").upsert(recursos).execute()
    print(f"✓ {len(recursos)} recursos cargados ({len(recursos) - sin_emb} con embedding).")
    if sin_emb:
        print("  Aviso: sin GEMINI_API_KEY o Gemini falló; el matching usa similitud neutra.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/catalogo.json")
