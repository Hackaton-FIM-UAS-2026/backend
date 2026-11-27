"""M5 · Fusión del expediente vivo.

Regla: usuaria > personal de SEMujeres > entrevista > test base > inferido por IA,
con dos matices del documento de diseño:
  * Todo lo que dice ELLA (test_base, entrevista, usuaria_edito) se actualiza con
    lo más reciente: si vuelve a contestar, su respuesta nueva gana.
  * Si el personal registra algo que choca con lo que dijo ella, NO se sobrescribe:
    se guarda como conflicto para revisarlo con ella.
  * Un dato inferido por IA con confianza < 0.7 queda `por_confirmar` y no se
    usa como requisito hasta que ella lo confirme.
"""
from datetime import datetime, timezone

from .diccionario import etiqueta, validar_valor

DE_ELLA = {"test_base", "entrevista", "usuaria_edito"}
FUENTES = DE_ELLA | {"personal_semujeres", "inferido_ia"}
UMBRAL_CONFIANZA = 0.7


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto_evento(campo, valor, fuente) -> str:
    v = ", ".join(valor) if isinstance(valor, list) else valor
    if fuente == "personal_semujeres":
        return f"Asesora registró: {etiqueta(campo).lower()} = {v}"
    if fuente == "inferido_ia":
        return f"El asistente anotó: {etiqueta(campo).lower()} = {v} (por confirmar)"
    return f"Respondió: {etiqueta(campo).lower()} = {v}"


def fusionar(expediente: dict, nuevos: dict, fuente: str, confianza: float = 1.0, autor: str | None = None) -> dict:
    """Fusiona `nuevos` (campo → valor) en una copia del expediente.

    Regresa {expediente, eventos, conflictos_nuevos, ignorados, cambio}.
    Lanza ValueError si la fuente o algún valor no son válidos.
    """
    if fuente not in FUENTES:
        raise ValueError(f"Fuente no válida: {fuente}")

    campos = {k: dict(v) for k, v in (expediente.get("campos") or {}).items()}
    conflictos = list(expediente.get("conflictos") or [])
    version = int(expediente.get("version") or 0)
    eventos, conflictos_nuevos, ignorados = [], [], []
    fecha = _ahora()

    for campo, valor in nuevos.items():
        if valor is None or valor == "":
            continue  # pregunta sin contestar: no borra lo que ya había
        valor = validar_valor(campo, valor)
        actual = campos.get(campo)

        if actual and actual.get("valor") == valor:
            # Mismo valor: si viene de ella, confirma un dato inferido.
            if fuente in DE_ELLA and actual.get("por_confirmar"):
                actual.update(fuente=fuente, confianza=1.0, por_confirmar=False, fecha=fecha)
            continue

        if actual and fuente == "personal_semujeres" and actual.get("fuente") in DE_ELLA:
            c = {"campo": campo, "valor_usuaria": actual["valor"], "valor_personal": valor,
                 "autor": autor, "fecha": fecha}
            conflictos.append(c)
            conflictos_nuevos.append(c)
            continue

        if actual and fuente == "inferido_ia" and actual.get("fuente") != "inferido_ia":
            ignorados.append(campo)
            continue

        campos[campo] = {
            "valor": valor,
            "fuente": fuente,
            "confianza": confianza,
            "fecha": fecha,
            "por_confirmar": fuente == "inferido_ia" and confianza < UMBRAL_CONFIANZA,
        }
        # Si ella responde un campo en conflicto, el conflicto se resuelve.
        if fuente in DE_ELLA:
            conflictos = [c for c in conflictos if c["campo"] != campo]
        eventos.append({
            "campo": campo,
            "valor_anterior": actual.get("valor") if actual else None,
            "valor_nuevo": valor,
            "fuente": fuente,
            "texto": _texto_evento(campo, valor, fuente),
            "autor": autor,
        })

    cambio = bool(eventos) or bool(conflictos_nuevos)
    if cambio:
        version += 1
    for e in eventos:
        e["version"] = version

    return {
        "expediente": {**expediente, "campos": campos, "conflictos": conflictos, "version": version},
        "eventos": eventos,
        "conflictos_nuevos": conflictos_nuevos,
        "ignorados": ignorados,
        "cambio": cambio,
    }


def valores(expediente: dict) -> dict:
    """campo → valor, sin los datos inferidos que falta confirmar."""
    v = {k: c["valor"] for k, c in (expediente.get("campos") or {}).items() if not c.get("por_confirmar")}
    # Quien marcó RFC en sus documentos ya tiene RFC (si contestó la pregunta suelta, gana su respuesta)
    if "tiene_rfc" not in v and "RFC" in (v.get("documentos") or []):
        v["tiene_rfc"] = "Sí"
    return v
