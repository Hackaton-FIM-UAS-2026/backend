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


def cargar_empresas(sb, ruta: str = "data/empresas.json") -> dict[str, dict]:
    """Crea o actualiza las empresas (clave: RFC). Regresa {alias: {id, estado}}."""
    p = Path(ruta)
    if not p.exists():
        return {}
    out = {}
    for e in json.loads(p.read_text(encoding="utf-8"))["empresas"]:
        fila = {k: e.get(k) for k in ("nombre", "rfc", "giro", "contacto_nombre", "telefono", "estado", "logo_url")}
        hay = sb.table("empresas").select("id").eq("rfc", e["rfc"]).limit(1).execute().data
        if hay:
            sb.table("empresas").update(fila).eq("id", hay[0]["id"]).execute()
            eid = hay[0]["id"]
        else:
            eid = sb.table("empresas").insert(fila).execute().data[0]["id"]
        out[e["alias"]] = {"id": eid, "estado": e["estado"]}
        print(f"✓ empresa   {e['nombre']} ({e['estado']})")
    return out


def main(ruta: str):
    recursos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    empresas = cargar_empresas(servicio())
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
        alias = r.pop("empresa", None)
        # PostgREST rellena con null las llaves que falten en un upsert por lotes: todas iguales.
        r.setdefault("etiquetas", {"pide": [], "da": [], "temas": []})
        r.setdefault("sueldo", None)
        r.setdefault("empresa_id", None)
        r.setdefault("alerta_ia", None)
        r.setdefault("estado_revision", "aprobada")
        if alias:
            emp = empresas[alias]
            r["empresa_id"] = emp["id"]
            r["publicada"] = r["estado_revision"] == "aprobada" and emp["estado"] == "aprobada"
        else:
            r.setdefault("publicada", r["estado_revision"] == "aprobada")
    servicio().table("recursos").upsert(recursos).execute()
    print(f"✓ {len(recursos)} recursos cargados ({len(recursos) - sin_emb} con embedding).")
    if sin_emb:
        print("  Aviso: sin GEMINI_API_KEY o Gemini falló; el matching usa similitud neutra.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/catalogo.json")
