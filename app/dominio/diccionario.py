"""Diccionario de campos: la pieza que conecta test base, requisitos y entrevista.

Es la copia "oficial" de frontend/src/data/campos.js. El front puede pedirlo
en GET /diccionario para no duplicarlo. Si un recurso pide un campo que no
está aquí, se agrega aquí primero.

tipo:
  unica    → un valor de `opciones`
  multiple → lista de valores de `opciones`
  texto    → texto libre (lo usa el personal)
`ordinal: True` → el orden de `opciones` sirve para comparar con >= / <=.
"""

TEST_BASE = [
    {"campo": "edad", "etiqueta": "Edad", "pregunta": "¿Cuántos años tienes?", "tipo": "unica", "ordinal": True,
     "opciones": ["18 a 24", "25 a 34", "35 a 44", "45 a 59", "60 o más"]},
    {"campo": "municipio", "etiqueta": "Municipio", "pregunta": "¿En qué municipio vives?", "tipo": "unica",
     "opciones": ["Ahome", "Guasave", "El Fuerte", "Otro"]},
    {"campo": "escolaridad", "etiqueta": "Escolaridad", "pregunta": "¿Hasta qué grado estudiaste?", "tipo": "unica", "ordinal": True,
     "opciones": ["Primaria", "Secundaria", "Preparatoria", "Universidad"]},
    {"campo": "situacion", "etiqueta": "Situación", "pregunta": "¿Cuál es tu situación hoy?", "tipo": "unica",
     "opciones": ["Sin ingreso", "Empleo informal", "Empleo formal", "Negocio propio"]},
    {"campo": "meta", "etiqueta": "Meta", "pregunta": "¿Qué te gustaría lograr?", "tipo": "unica",
     "opciones": ["Un empleo", "Iniciar o hacer crecer un negocio", "Aprender algo nuevo", "No sé todavía"]},
    {"campo": "horas_semana", "etiqueta": "Horas a la semana", "pregunta": "¿Cuántas horas a la semana tienes libres?", "tipo": "unica", "ordinal": True,
     "opciones": ["Menos de 10", "10 a 15", "16 a 29", "30 o más"]},
    {"campo": "horario", "etiqueta": "Horario", "pregunta": "¿En qué horario puedes?", "tipo": "multiple",
     "opciones": ["Mañana", "Tarde", "Noche", "Fines de semana"]},
    {"campo": "cuidados", "etiqueta": "Cuidados", "pregunta": "¿Tienes personas a tu cargo?", "tipo": "multiple",
     "opciones": ["Niñas o niños", "Personas mayores", "Ninguna"]},
    {"campo": "dispositivo", "etiqueta": "Dispositivo", "pregunta": "¿Con qué te conectas?", "tipo": "unica",
     "opciones": ["Solo celular con datos", "Celular con wifi", "Computadora"]},
    {"campo": "habilidades", "etiqueta": "Habilidades", "pregunta": "¿Qué sabes hacer?", "tipo": "multiple",
     "opciones": ["Cocina", "Costura", "Ventas", "Cuidado de personas", "Limpieza", "Computación", "Atención al cliente", "Otra"]},
    {"campo": "negocio", "etiqueta": "Negocio", "pregunta": "¿Tienes un negocio o una idea?", "tipo": "unica",
     "opciones": ["No", "Tengo una idea", "Ya vendo"]},
    {"campo": "documentos", "etiqueta": "Documentos", "pregunta": "¿Con qué documentos cuentas?", "tipo": "multiple",
     "opciones": ["CURP", "INE", "RFC", "Cuenta bancaria"]},
]

# Campos que NO están en el test base: se preguntan solo cuando un recurso los pide.
ENTREVISTA = [
    {"campo": "tiene_rfc", "etiqueta": "Tiene RFC", "pregunta": "¿Tienes RFC?", "tipo": "unica",
     "opciones": ["Sí", "No"]},
    {"campo": "habilidad_excel", "etiqueta": "Excel", "pregunta": "¿Qué tanto sabes usar Excel?", "tipo": "unica", "ordinal": True,
     "opciones": ["Nada", "Básico", "Intermedio"]},
    {"campo": "tiene_experiencia", "etiqueta": "Experiencia laboral", "pregunta": "¿Has trabajado antes con un patrón o en una empresa?", "tipo": "unica",
     "opciones": ["Sí", "No"]},
    {"campo": "tiene_cuenta_bancaria", "etiqueta": "Cuenta bancaria", "pregunta": "¿Tienes cuenta en un banco?", "tipo": "unica",
     "opciones": ["Sí", "No"]},
]

# Campos que solo registra el personal (fuente personal_semujeres).
PERSONAL = [
    {"campo": "estado_programa", "etiqueta": "Situación en el programa", "tipo": "texto"},
]

CAMPOS: dict[str, dict] = {c["campo"]: c for c in TEST_BASE + ENTREVISTA + PERSONAL}

# Total que se muestra en "Mi avance" (n de TOTAL datos guardados)
TOTAL_PERFIL = len(TEST_BASE) + len(ENTREVISTA)


def etiqueta(campo: str) -> str:
    return CAMPOS.get(campo, {}).get("etiqueta", campo)


def validar_valor(campo: str, valor):
    """Valida un valor contra el diccionario. Regresa el valor normalizado o lanza ValueError."""
    d = CAMPOS.get(campo)
    if d is None:
        raise ValueError(f"El campo «{campo}» no está en el diccionario")
    tipo = d["tipo"]
    if tipo == "texto":
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"«{campo}» debe ser texto")
        return valor.strip()[:500]
    opciones = d["opciones"]
    if tipo == "unica":
        if valor not in opciones:
            raise ValueError(f"«{valor}» no es una opción válida para «{campo}»")
        return valor
    if tipo == "multiple":
        if isinstance(valor, str):
            valor = [valor]
        if not isinstance(valor, list) or any(v not in opciones for v in valor):
            raise ValueError(f"Opciones no válidas para «{campo}»")
        # Sin duplicados, en el orden del diccionario
        return [o for o in opciones if o in valor]
    raise ValueError(f"Tipo desconocido para «{campo}»")


def publico() -> dict:
    """Lo que GET /diccionario le entrega al front."""
    return {
        "test_base": TEST_BASE,
        "preguntas": {c["campo"]: {"pregunta": c["pregunta"], "opciones": c["opciones"]} for c in ENTREVISTA},
        "etiquetas": {k: v["etiqueta"] for k, v in CAMPOS.items()},
        "total_perfil": TOTAL_PERFIL,
    }
