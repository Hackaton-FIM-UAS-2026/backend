"""Dos formas de hablar con Supabase.

* `servicio()`  → service role. Ignora RLS. Solo para ESCRIBIR después de que
  el backend ya comprobó el permiso, y para tareas del sistema.
* `como(token)` → PostgREST con el JWT de quien pide. RLS decide qué ve.
  Toda LECTURA de datos de personas pasa por aquí.
"""
from contextlib import contextmanager
from functools import lru_cache

from postgrest import SyncPostgrestClient
from supabase import Client, create_client

from .config import settings


@lru_cache
def servicio() -> Client:
    s = settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


@contextmanager
def como(token: str | None):
    s = settings()
    headers = {"apikey": s.supabase_anon_key, "Authorization": f"Bearer {token or s.supabase_anon_key}"}
    cliente = SyncPostgrestClient(f"{s.supabase_url}/rest/v1", headers=headers, timeout=10)
    try:
        yield cliente
    finally:
        # postgrest-py síncrono expone aclose(); por si cambia de nombre, cerramos la sesión httpx.
        cerrar = getattr(cliente, "aclose", None) or getattr(cliente.session, "close", None)
        if cerrar:
            cerrar()
