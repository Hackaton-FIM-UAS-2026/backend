"""Embeddings con la API de Gemini (Claude no genera embeddings).

Modelo: gemini-embedding-001, recortado a EMBEDDING_DIM (768) y normalizado.
Si cambias la dimensión, cambia también vector(768) en la migración y
vuelve a correr scripts/cargar_catalogo.py.
"""
import logging
import math

import httpx

from ..config import settings

log = logging.getLogger("ia")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:embedContent"


def embed(texto: str, tarea: str = "RETRIEVAL_DOCUMENT") -> list[float] | None:
    s = settings()
    if not s.gemini_api_key or not texto.strip():
        return None
    try:
        r = httpx.post(
            URL.format(modelo=s.embedding_model),
            headers={"x-goog-api-key": s.gemini_api_key},
            json={
                "model": f"models/{s.embedding_model}",
                "content": {"parts": [{"text": texto[:8000]}]},
                "taskType": tarea,
                "outputDimensionality": s.embedding_dim,
            },
            timeout=8,
        )
        r.raise_for_status()
        v = r.json()["embedding"]["values"]
    except Exception as e:
        log.warning("Gemini embeddings falló: %s", type(e).__name__)
        return None
    n = math.sqrt(sum(x * x for x in v)) or 1.0  # al recortar la dimensión hay que normalizar
    return [x / n for x in v]


def texto_recurso(r: dict) -> str:
    return " · ".join(str(x) for x in [r.get("titulo"), r.get("tipo"), " ".join(r.get("rutas") or []),
                                         r.get("modalidad"), r.get("horario"), r.get("descripcion")] if x)


def texto_expediente(valores: dict, ruta: dict) -> str:
    partes = [f"Ruta: {ruta.get('principal')}" + (f", puente {ruta['puente']}" if ruta.get("puente") else "")]
    for k in ("meta", "situacion", "habilidades", "negocio", "escolaridad", "horario", "horas_semana", "dispositivo"):
        if k in valores:
            v = valores[k]
            partes.append(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
    return ". ".join(partes)


def como_texto(v: list[float]) -> str:
    """pgvector vía PostgREST recibe el vector como texto '[0.1,0.2,…]'."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"
