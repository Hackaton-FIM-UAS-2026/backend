"""M3 · Inicio por caminos y catálogo para explorar."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app import servicios as sv
from app.auth import Sesion, usuaria
from app.dominio.matching import recomendar

from .puentes import armar_caminos

router = APIRouter(tags=["caminos (M3)"])

CAMPOS_TARJETA = ("id", "titulo", "tipo", "proveedor", "horario", "modalidad", "ubicacion", "costo", "sueldo", "fecha_cierre")
TIPOS = {"vacante": {"vacante"}, "curso": {"curso"}, "beca_apoyo": {"beca", "apoyo", "financiamiento"}}


def tarjeta(r: dict) -> dict:
    return {k: r.get(k) for k in CAMPOS_TARJETA}


def filtrar(catalogo: list[dict], tipo=None, gratis=False, en_linea=False, horario=None, q=None) -> list[dict]:
    out = []
    for r in catalogo:
        if tipo and r.get("tipo") not in TIPOS[tipo]:
            continue
        if gratis and (r.get("costo") or "").lower() != "gratis":
            continue
        if en_linea and (r.get("modalidad") or "").lower() != "en línea":
            continue
        if horario and r.get("horario") not in (horario, "Flexible"):
            continue
        if q:
            texto = f"{r.get('titulo', '')} {r.get('proveedor', '')} {r.get('descripcion', '')}".lower()
            if not all(p in texto for p in q.lower().split()):
                continue
        out.append(r)
    return out


@router.get("/me/caminos")
def caminos(s: Sesion = Depends(usuaria)):
    exp = sv.leer_expediente(s.token, s.user_id)
    vals = sv.valores_de(exp)
    perfil = sv.servicio().table("perfiles").select("nombre").eq("usuaria_id", s.user_id).limit(1).execute().data
    nombre = (perfil[0]["nombre"] or "").split(" ")[0] if perfil and perfil[0].get("nombre") else None
    if not vals:
        return {"nombre": nombre, "falta_test": True, "caminos": [], "tambien": []}
    catalogo = sv.leer_catalogo(s.token)
    ruta = sv.ruta_efectiva(exp)
    orden = [r["id"] for r in recomendar(catalogo, vals, ruta, limite=20, hoy=date.today())]
    por_id = {r["id"]: r for r in catalogo}
    ordenados = [por_id[i] for i in orden if i in por_id] + [r for r in catalogo if r["id"] not in orden]
    cms = armar_caminos(vals, ordenados)
    usados = {c["meta"]["id"] for c in cms} | {p["recurso"]["id"] for c in cms for p in c["puentes"]}
    tambien = [tarjeta(por_id[i]) for i in orden if i in por_id and i not in usados][:4]
    return {"nombre": nombre, "falta_test": False, "caminos": cms, "tambien": tambien}


@router.get("/catalogo")
def catalogo(tipo: Literal["vacante", "curso", "beca_apoyo"] | None = None, gratis: bool = False,
             en_linea: bool = False, horario: Literal["Mañanas", "Tardes", "Noches", "Fines de semana"] | None = None,
             q: str | None = Query(default=None, max_length=80)):
    """Todo lo publicado y aprobado (público). Filtros simples para «Explorar»."""
    return [tarjeta(r) for r in filtrar(sv.leer_catalogo(None), tipo, gratis, en_linea, horario, q)]
