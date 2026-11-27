"""Perfil de la usuaria: «Mis datos» (nombre, teléfono, CURP, RFC, dirección) y entrevista dinámica."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import servicios as sv
from app.auth import Sesion, usuaria
from app.db import servicio
from app.ia import claude

from .reglas import curp_valida, rfc_valido, siguiente_pregunta

router = APIRouter(prefix="/me", tags=["perfil"])
CAMPOS = ("nombre", "telefono", "curp", "rfc", "direccion")


def _perfil(uid: str) -> dict:
    f = servicio().table("perfiles").select("nombre,telefono,curp,rfc,direccion,correo").eq("usuaria_id", uid).limit(1).execute().data
    return f[0] if f else {}


@router.get("/datos")
def datos(s: Sesion = Depends(usuaria)):
    p = _perfil(s.user_id)
    return {k: p.get(k) for k in CAMPOS + ("correo",)}


class DatosIn(BaseModel):
    nombre: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=20)
    curp: str | None = Field(default=None, max_length=18)
    rfc: str | None = Field(default=None, max_length=13)
    direccion: str | None = Field(default=None, max_length=200)


@router.patch("/datos")
def editar(body: DatosIn, s: Sesion = Depends(usuaria)):
    actual = _perfil(s.user_id)
    cambios = {}
    if body.nombre is not None:
        if len(body.nombre.split()) < 2:
            raise HTTPException(422, "Escribe tu nombre completo (nombre y apellidos).")
        cambios["nombre"] = " ".join(body.nombre.split())
    if body.telefono is not None:
        tel = "".join(ch for ch in body.telefono if ch.isdigit())
        if len(tel) != 10:
            raise HTTPException(422, "El teléfono debe tener 10 dígitos.")
        cambios["telefono"] = f"{tel[:3]} {tel[3:6]} {tel[6:]}"
    if body.curp:
        curp = body.curp.strip().upper()
        if not curp_valida(curp):
            raise HTTPException(422, "Revisa tu CURP: son 18 letras y números.")
        if actual.get("curp") and actual["curp"] != curp:
            raise HTTPException(409, "Tu CURP ya está guardada. Si hay un error, acude a SEMujeres para corregirla.")
        otra = servicio().table("perfiles").select("usuaria_id").eq("curp", curp).neq("usuaria_id", s.user_id).limit(1).execute().data
        if otra:
            raise HTTPException(409, "Esa CURP ya tiene un expediente en SEMujeres. Llama al 668 102 5080 para unir tus datos.")
        cambios["curp"] = curp
    if body.rfc:
        rfc = body.rfc.strip().upper()
        if not rfc_valido(rfc):
            raise HTTPException(422, "Revisa tu RFC: son 12 o 13 letras y números.")
        cambios["rfc"] = rfc
    if body.direccion is not None and body.direccion.strip():
        cambios["direccion"] = " ".join(body.direccion.split())
    if cambios:
        servicio().table("perfiles").update(cambios).eq("usuaria_id", s.user_id).execute()
        if "rfc" in cambios:   # si escribió su RFC, ya no hay que preguntarle si lo tiene
            sv.aplicar_campos(s.token, s.user_id, {"tiene_rfc": "Sí"}, "usuaria_edito")
    return datos(s)


def _llm(system, mensaje, schema):
    return claude.usar_herramienta(system, mensaje, "siguiente_pregunta", "La siguiente pregunta de la entrevista.", schema,
                                   max_tokens=300)


@router.post("/entrevista/siguiente")
def entrevista(s: Sesion = Depends(usuaria)):
    """La siguiente pregunta de «Completar mi perfil». La IA elige y reformula; el campo y las opciones son fijos."""
    vals = sv.valores_de(sv.leer_expediente(s.token, s.user_id))
    q = siguiente_pregunta(vals, _llm)
    return q or {"terminado": True}
