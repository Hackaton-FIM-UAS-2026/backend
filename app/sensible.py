"""Cifrado del expediente sensible y bitácora de accesos."""
import json
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .db import servicio


@lru_cache
def _f() -> Fernet:
    return Fernet(settings().sensible_key.encode())


def cifrar(datos: dict | str) -> str:
    texto = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)
    return _f().encrypt(texto.encode()).decode()


def descifrar(token: str, como_json: bool = True):
    try:
        t = _f().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
    return json.loads(t) if como_json else t


def bitacora(actor: str | None, rol: str | None, accion: str, tabla: str,
             registro: str | None = None, usuaria_id: str | None = None) -> None:
    """Nunca guarda contenido: solo quién, qué, cuándo. No debe tumbar la petición."""
    try:
        servicio().table("bitacora_accesos").insert({
            "actor": actor, "rol": rol, "accion": accion, "tabla": tabla,
            "registro": registro, "usuaria_id": usuaria_id,
        }).execute()
    except Exception as e:  # que falle la bitácora no debe tumbar la atención, pero sí se avisa
        logging.getLogger("bitacora").error("No se pudo registrar acceso %s/%s: %s", accion, tabla, e)
