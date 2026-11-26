"""Autenticación: el front inicia sesión con supabase-js y manda
`Authorization: Bearer <access_token>`. Aquí se valida con Supabase Auth
(funciona igual con llaves JWT simétricas o asimétricas del proyecto).
"""
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .db import servicio

_CACHE: dict[str, tuple[float, "Sesion"]] = {}
_TTL = 60  # s: evita una llamada a Auth por cada petición


@dataclass
class Sesion:
    user_id: str
    token: str
    correo: str | None
    rol: str | None          # None = usuaria; si no, rol del personal
    nombre_personal: str | None = None


def _validar(token: str) -> Sesion:
    ahora = time.time()
    if (hit := _CACHE.get(token)) and hit[0] > ahora:
        return hit[1]
    try:
        r = servicio().auth.get_user(token)
        user = r.user if r else None
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "Sesión no válida o expirada")
    fila = (servicio().table("personal").select("rol,nombre,activo")
            .eq("user_id", user.id).limit(1).execute().data)
    rol = fila[0]["rol"] if fila and fila[0]["activo"] else None
    s = Sesion(user_id=user.id, token=token, correo=user.email, rol=rol,
               nombre_personal=fila[0]["nombre"] if fila else None)
    if len(_CACHE) > 5000:
        _CACHE.clear()
    _CACHE[token] = (ahora + _TTL, s)
    return s


def sesion(authorization: str | None = Header(default=None)) -> Sesion:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Falta el token (Authorization: Bearer …)")
    return _validar(authorization.split(" ", 1)[1].strip())


def usuaria(s: Sesion = Depends(sesion)) -> Sesion:
    if s.rol:
        raise HTTPException(403, "Esta ruta es para usuarias")
    return s


def con_rol(*roles: str):
    def dep(s: Sesion = Depends(sesion)) -> Sesion:
        if s.rol not in roles:
            raise HTTPException(403, "Tu rol no tiene acceso a esto")
        return s
    return dep


PERSONAL = ("asesora_economica", "especialista_juridica", "especialista_psicologica", "coordinacion")
ESPECIALISTAS = ("especialista_juridica", "especialista_psicologica")
