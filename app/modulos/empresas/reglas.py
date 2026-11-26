"""M6 · Reglas de empresas: nada se publica sin una persona; la empresa ve solo datos de trabajo."""
import re
import unicodedata

# Ciudades y estados de la zona (lo demás se marca para revisar)
LOCALES = ("sinaloa", "los mochis", "ahome", "guasave", "el fuerte", "topolobampo", "higuera de zaragoza",
           "san blas", "culiacan", "en linea", "remoto", "a domicilio")
PALABRAS = {"fotos": "Piden fotos", "cuerpo completo": "Piden fotos de cuerpo completo", "viaje pagado": "Ofrecen viaje pagado",
            "hospedaje": "Ofrecen hospedaje", "modelo": "Mencionan «modelo»", "señoritas": "Buscan «señoritas» (posible sesgo)",
            "sin experiencia gana": "Promesa de ganancia fácil", "deposito": "Piden un depósito"}
SEMANAL_MAX, MENSUAL_MAX = 10_000, 40_000


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"[̀-ͯ]", "", t)


def publicable(vacante: dict, empresa: dict) -> bool:
    return empresa.get("estado") == "aprobada" and vacante.get("estado_revision") == "aprobada"


def perfil_laboral(perfil: dict, campos: dict) -> dict:
    """Lo único que ve la empresa: nunca CURP, colonia, cuidados ni nada de SEMujeres."""
    hab = campos.get("habilidades") or []
    exp = campos.get("tiene_experiencia")
    return {
        "nombre": perfil.get("nombre") or "Sin nombre",
        "escolaridad": campos.get("escolaridad") or "Sin dato",
        "habilidades": ", ".join(hab) if isinstance(hab, list) else str(hab),
        "experiencia": "Sí" if exp == "Sí" else ("No" if exp == "No" else "Sin dato"),
        "telefono": perfil.get("telefono") or "Sin dato",
    }


def senales_heuristicas(v: dict) -> list[str]:
    s = []
    texto = _norm(f"{v.get('titulo', '')} {v.get('descripcion', '')}")
    sueldo = _norm(v.get("sueldo") or "")
    montos = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{2,}", sueldo)]
    if montos:
        tope = SEMANAL_MAX if "semana" in sueldo else MENSUAL_MAX
        if max(montos) > tope:
            s.append(f"Sueldo muy por arriba de lo normal ({v.get('sueldo')})")
    ubic = _norm(v.get("ubicacion") or "")
    if ubic and not any(l in ubic for l in LOCALES):
        s.append(f"Trabajo fuera de Sinaloa ({v.get('ubicacion')})")
    for palabra, motivo in PALABRAS.items():
        if _norm(palabra) in texto and motivo not in s:
            s.append(motivo)
    if any("cuerpo completo" in x for x in s):
        s = [x for x in s if x != "Piden fotos"]
        s.append("Piden fotos")
    return s


SYSTEM_ALERTA = """Revisas vacantes que se publicarán para mujeres en situación vulnerable de Ahome, Sinaloa.
Escribe UNA frase corta (máx. 25 palabras) con señales de posible fraude, explotación o trata si las hay
(sueldo irreal, piden fotos, viaje fuera de la ciudad, piden dinero, datos personales de más). Si no hay, deja `nota` vacía.
Tú no decides: una persona revisará."""
SCHEMA_ALERTA = {"type": "object", "properties": {"nota": {"type": "string"}}, "required": ["nota"]}


def alerta(v: dict, llm) -> str | None:
    """Une las señales por reglas con la nota de la IA. None si no hay nada que revisar con cuidado."""
    partes = senales_heuristicas(v)
    out = llm(SYSTEM_ALERTA, f"Título: {v.get('titulo')}\nSueldo: {v.get('sueldo')}\nLugar: {v.get('ubicacion')}\n"
                             f"Descripción: {v.get('descripcion')}", SCHEMA_ALERTA) or {}
    nota = (out.get("nota") or "").strip()
    if nota:
        partes.append(nota)
    return "; ".join(partes) if partes else None
