"""M7 · Matching: tres filtros en orden.

1. Filtro duro: ruta compatible, publicado, no vencido, municipio o en línea,
   requisitos duros que se cumplen o que todavía no se conocen.
2. Similitud semántica (pgvector) — llega ya calculada en `similitudes`.
3. Puntaje final: 0.5 × similitud + 0.3 × requisitos + 0.2 × ajuste de horario.
"""
from datetime import date

from .requisitos import evaluar_recurso

PESO_SIMILITUD, PESO_REQUISITOS, PESO_HORARIO = 0.5, 0.3, 0.2
SIMILITUD_NEUTRA = 0.5  # si no hay embeddings (sin llave de Gemini), no castiga a nadie

# Máximo de horas que cabe en cada rango del test base
HORAS_MAX = {"Menos de 10": 9, "10 a 15": 15, "16 a 29": 29, "30 o más": 60}
# Horario del recurso (plural) → horario de la usuaria (singular)
HORARIO_MAP = {"Mañanas": "Mañana", "Tardes": "Tarde", "Noches": "Noche", "Fines de semana": "Fines de semana"}


def _vigente(r: dict, hoy: date) -> bool:
    fc = r.get("fecha_cierre")
    if not fc:
        return True
    try:
        return date.fromisoformat(str(fc)[:10]) >= hoy
    except ValueError:
        return True


def _ubicacion_ok(r: dict, municipio: str | None) -> bool:
    if (r.get("modalidad") or "").lower() == "en línea":
        return True
    munis = r.get("municipios") or []
    if not munis:
        return True
    return municipio is None or municipio in munis  # si no sabemos, no excluimos


def ajuste_horario(r: dict, valores: dict) -> tuple[float, list[str]]:
    """0..1 y las razones verificables (alimentan "Por qué es para ti")."""
    razones, partes = [], []
    h_rec = r.get("horario")
    h_usr = valores.get("horario")
    if h_rec == "Flexible" or (r.get("modalidad") or "").lower() == "en línea" and h_rec in (None, "Flexible"):
        partes.append(1.0)
        razones.append("Puedes hacerlo a tu ritmo")
    elif h_rec and h_usr:
        ok = HORARIO_MAP.get(h_rec) in h_usr
        partes.append(1.0 if ok else 0.0)
        if ok:
            razones.append(f"Es por las {h_rec.lower()}, cuando tú puedes")
    else:
        partes.append(0.5)

    horas_max = HORAS_MAX.get(valores.get("horas_semana"))
    if r.get("horas_semana") and horas_max:
        ok = r["horas_semana"] <= horas_max
        partes.append(1.0 if ok else 0.0)
        if ok:
            razones.append(f"Pide {r['horas_semana']} horas a la semana y tú tienes {valores['horas_semana'].lower()} horas libres")
    else:
        partes.append(0.5)

    if (r.get("modalidad") or "").lower() == "en línea":
        razones.append("Es en línea, no tienes que trasladarte")
    return sum(partes) / len(partes), razones


def recomendar(recursos: list[dict], valores: dict, ruta: dict, similitudes: dict | None = None,
               limite: int = 10, hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    similitudes = similitudes or {}
    rutas_ok = {ruta["principal"]} | ({ruta["puente"]} if ruta.get("puente") else set())
    municipio = valores.get("municipio")

    salida = []
    for r in recursos:
        if r.get("publicada") is False or not _vigente(r, hoy):
            continue
        if not rutas_ok.intersection(r.get("rutas") or []):
            continue
        if not _ubicacion_ok(r, municipio):
            continue
        ev = evaluar_recurso(r.get("requisitos") or [], valores)
        if ev["excluido"]:
            continue

        # requisitos: cumple = 1, falta el dato = 0.5, no cumple (blando) = 0
        if ev["total"]:
            puntos = sum(1.0 if q["ok"] is True else 0.5 if q["ok"] is None else 0.0 for q in ev["requisitos"])
            frac = puntos / ev["total"]
        else:
            frac = 1.0
        horario, razones = ajuste_horario(r, valores)
        sim = similitudes.get(r["id"], SIMILITUD_NEUTRA)
        puntaje = PESO_SIMILITUD * sim + PESO_REQUISITOS * frac + PESO_HORARIO * horario
        if ruta["principal"] in (r.get("rutas") or []):
            puntaje += 0.05  # la ruta principal va primero que la puente

        salida.append({
            **{k: v for k, v in r.items() if k != "embedding"},
            "requisitos": ev["requisitos"],
            "faltantes": ev["faltantes"],
            "cumple": ev["cumple"],
            "puntaje": round(puntaje, 4),
            "porque": razones,
            "es_puente": ruta["principal"] not in (r.get("rutas") or []),
        })

    salida.sort(key=lambda x: -x["puntaje"])
    return salida[:limite]
