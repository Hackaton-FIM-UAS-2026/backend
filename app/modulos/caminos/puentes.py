"""M3 · Caminos: metas que le convienen + los cursos que la acercan (puentes).

Los puentes salen de etiquetas revisables (`etiquetas.da` / `etiquetas.temas`),
no de lo que la IA diga en el momento.
"""
from app.dominio.requisitos import evaluar_recurso


def _resumen(r: dict, *campos: str) -> dict:
    return {k: r.get(k) for k in ("id", "titulo", "tipo", "proveedor", *campos)}


def armar_caminos(valores: dict, recursos: list[dict], limite: int = 3) -> list[dict]:
    """`recursos` llega ordenado por conveniencia (matching). Los cursos sirven de puente."""
    cursos = []
    for r in recursos:
        if r.get("tipo") == "curso" and r["id"] not in {c["id"] for c in cursos}:
            cursos.append(r)

    candidatas = []
    for orden, r in enumerate(recursos):
        if r.get("tipo") == "curso":
            continue
        ev = evaluar_recurso(r.get("requisitos") or [], valores)
        if ev["excluido"]:
            continue
        candidatas.append((r, ev))   # se respeta el orden de conveniencia del matching

    caminos, vistas = [], set()
    for r, ev in candidatas:
        if r["id"] in vistas:
            continue
        vistas.add(r["id"])
        faltan = [{"campo": q["campo"], "label": q["label"]} for q in ev["requisitos"] if q["ok"] is not True]
        puentes, usados = [], {r["id"]}
        for f in faltan:
            for c in cursos:
                if c["id"] not in usados and f["campo"] in (c.get("etiquetas") or {}).get("da", []):
                    usados.add(c["id"])
                    puentes.append({"recurso": _resumen(c, "modalidad", "costo"), "motivo": "te_falta", "para": f["label"]})
        temas = set((r.get("etiquetas") or {}).get("temas", []))
        for c in cursos:
            if c["id"] not in usados and temas & set((c.get("etiquetas") or {}).get("temas", [])):
                usados.add(c["id"])
                puentes.append({"recurso": _resumen(c, "modalidad", "costo"), "motivo": "tema", "para": None})
                break
        caminos.append({
            "meta": {**_resumen(r, "horario", "ubicacion", "sueldo"), "cumplidos": ev["cumplidos"], "total": ev["total"]},
            "faltan": faltan,
            "puentes": puentes,
        })
    elegidos = caminos[:limite]
    # Si ninguno de los primeros trae un curso que la acerque, se cambia el último por el
    # siguiente camino que sí lo traiga: así se ve qué le falta y cómo lograrlo.
    if elegidos and not any(c["puentes"] for c in elegidos):
        con_puente = next((c for c in caminos[limite:] if any(p["motivo"] == "te_falta" for p in c["puentes"])), None)
        if con_puente:
            elegidos[-1] = con_puente
    return elegidos
