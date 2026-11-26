"""M3 · Etiqueta con IA los recursos publicados que aún no tienen `etiquetas.da` ni temas.

    python -m scripts.etiquetar_catalogo            # solo los que faltan
    python -m scripts.etiquetar_catalogo --todos    # vuelve a etiquetar todo
"""
import sys

from app.db import servicio
from app.ia import claude
from app.modulos.caminos.etiquetas import etiquetar


def _llm(system, mensaje, schema):
    return claude.usar_herramienta(system, mensaje, "etiquetar", "Etiquetas del recurso.", schema, max_tokens=300)


def main(todos: bool):
    sb = servicio()
    filas = sb.table("recursos").select("id,titulo,tipo,descripcion,requisitos,etiquetas").execute().data
    hechos = 0
    for r in filas:
        e = r.get("etiquetas") or {}
        if not todos and (e.get("da") or e.get("temas")):
            continue
        nuevas = etiquetar(r, _llm)
        sb.table("recursos").update({"etiquetas": nuevas}).eq("id", r["id"]).execute()
        hechos += 1
        print(f"✓ {r['id']:22} pide={nuevas['pide']} da={nuevas['da']} temas={nuevas['temas']}")
    print(f"{hechos} recursos etiquetados.")


if __name__ == "__main__":
    main("--todos" in sys.argv)
