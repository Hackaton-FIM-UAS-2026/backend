"""Evaluación de requisitos estructurados contra el expediente.

Un requisito: {campo, op, valor, duro, label}
Resultado por requisito: ok = True (cumple), False (no cumple), None (falta el dato).

"¿Faltan datos?" es una resta entre conjuntos, no una adivinanza del modelo.
"""
from .diccionario import CAMPOS

OPS = {"==", "!=", "in", "not_in", ">=", "<=", "contains", "contains_any", "not_contains", "any_not_in"}


def _indice(campo: str, v):
    opciones = CAMPOS.get(campo, {}).get("opciones", [])
    return opciones.index(v) if v in opciones else None


def evaluar_condicion(cond: dict, valores: dict) -> bool | None:
    """Evalúa {campo, op, valor} (o {all: [...]}/{any: [...]}) contra un dict campo→valor."""
    if "all" in cond:
        rs = [evaluar_condicion(c, valores) for c in cond["all"]]
        if any(r is False for r in rs):
            return False
        return None if any(r is None for r in rs) else True
    if "any" in cond:
        rs = [evaluar_condicion(c, valores) for c in cond["any"]]
        if any(r is True for r in rs):
            return True
        return None if any(r is None for r in rs) else False

    campo, op, esperado = cond.get("campo"), cond.get("op"), cond.get("valor")
    if op not in OPS:
        return None  # requisito manual (solo texto): lo revisa una persona
    if campo not in valores or valores[campo] in (None, "", []):
        return None
    actual = valores[campo]
    lista = actual if isinstance(actual, list) else [actual]
    esperados = esperado if isinstance(esperado, list) else [esperado]

    if op == "==":
        return actual == esperado
    if op == "!=":
        return actual != esperado
    if op == "in":
        return actual in esperados
    if op == "not_in":
        return actual not in esperados
    if op in (">=", "<="):
        a, e = _indice(campo, actual), _indice(campo, esperado)
        if a is None or e is None:
            try:
                a, e = float(actual), float(esperado)
            except (TypeError, ValueError):
                return None
        return a >= e if op == ">=" else a <= e
    if op == "contains":          # tiene TODOS
        return all(x in lista for x in esperados)
    if op == "contains_any":      # tiene ALGUNO
        return any(x in lista for x in esperados)
    if op == "not_contains":      # no tiene NINGUNO
        return not any(x in lista for x in esperados)
    if op == "any_not_in":        # tiene algo fuera de la lista (p. ej. cuidados ≠ "Ninguna")
        return any(x not in esperados for x in lista)
    return None


def evaluar_recurso(requisitos: list[dict], valores: dict) -> dict:
    """Regresa los requisitos con `ok`, los faltantes y si se excluye por un requisito duro."""
    evaluados, faltantes = [], []
    excluido = False
    for r in requisitos or []:
        ok = evaluar_condicion(r, valores)
        evaluados.append({
            "campo": r.get("campo"),
            "label": r.get("label") or r.get("campo"),
            "duro": bool(r.get("duro")),
            "op": r.get("op"),
            "valor": r.get("valor"),
            "ok": ok,
        })
        if ok is None and r.get("campo") in CAMPOS and r.get("op") in OPS:
            faltantes.append(r["campo"])
        if ok is False and r.get("duro"):
            excluido = True
    total = len(evaluados)
    cumplidos = sum(1 for r in evaluados if r["ok"] is True)
    return {
        "requisitos": evaluados,
        "faltantes": list(dict.fromkeys(faltantes)),
        "excluido": excluido,
        "cumple": cumplidos == total,
        "cumplidos": cumplidos,
        "total": total,
    }
