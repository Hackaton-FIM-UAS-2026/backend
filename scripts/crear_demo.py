"""Crea las cuentas de la demo con datos 100 % FICTICIOS.

    python -m scripts.crear_demo

Usuarias: maria / lucia / rosa @demo.example  (María se usa en vivo; puedes borrarla
           y registrarla otra vez desde el celular).
Personal: asesora / juridica / psicologica / coordinacion @demo.example
Contraseña de todas: la de DEMO_PASSWORD (por defecto Demo2026!)
"""
import os
from datetime import datetime, timezone

from app.db import servicio
from app.dominio.fusion import fusionar, valores
from app.dominio.motor_ruta import calcular_ruta
from app.sensible import cifrar

PASSWORD = os.getenv("DEMO_PASSWORD", "Demo2026!")

USUARIAS = {
    "maria": ("María Hernández", "668 555 0101", {
        "edad": "25 a 34", "municipio": "Ahome", "escolaridad": "Secundaria", "situacion": "Negocio propio",
        "meta": "Iniciar o hacer crecer un negocio", "horas_semana": "10 a 15", "horario": ["Mañana"],
        "cuidados": ["Niñas o niños"], "dispositivo": "Solo celular con datos", "habilidades": ["Cocina", "Ventas"],
        "negocio": "Ya vendo", "documentos": ["CURP", "INE"]}),
    "lucia": ("Lucía Valenzuela", "668 555 0102", {
        "edad": "18 a 24", "municipio": "Ahome", "escolaridad": "Preparatoria", "situacion": "Sin ingreso",
        "meta": "Un empleo", "horas_semana": "30 o más", "horario": ["Mañana", "Tarde"], "cuidados": ["Ninguna"],
        "dispositivo": "Computadora", "habilidades": ["Atención al cliente", "Computación"], "negocio": "No",
        "documentos": ["CURP", "INE", "RFC"]}),
    "rosa": ("Rosa Beltrán", "668 555 0103", {
        "edad": "45 a 59", "municipio": "Ahome", "escolaridad": "Primaria", "situacion": "Empleo informal",
        "meta": "Aprender algo nuevo", "horas_semana": "10 a 15", "horario": ["Tarde"], "cuidados": ["Personas mayores"],
        "dispositivo": "Solo celular con datos", "habilidades": ["Costura"], "negocio": "Tengo una idea",
        "documentos": ["CURP", "INE"]}),
}
PERSONAL = {
    "asesora": ("Ana Torres", "asesora_economica"),
    "juridica": ("Lic. Carmen Soto", "especialista_juridica"),
    "psicologica": ("Psic. Laura Mendoza", "especialista_psicologica"),
    "coordinacion": ("Coordinación CEMujeres", "coordinacion"),
}


def usuario(sb, correo: str, meta: dict) -> str:
    try:
        r = sb.auth.admin.create_user({"email": correo, "password": PASSWORD, "email_confirm": True, "user_metadata": meta})
        return r.user.id
    except Exception:
        for u in sb.auth.admin.list_users():
            if u.email == correo:
                return u.id
        raise


def main():
    sb = servicio()
    ahora = datetime.now(timezone.utc).isoformat()
    for alias, (nombre, rol) in PERSONAL.items():
        uid = usuario(sb, f"{alias}@demo.example", {"es_personal": True, "nombre": nombre})
        sb.table("personal").upsert({"user_id": uid, "nombre": nombre, "rol": rol}).execute()
        print(f"✓ personal  {alias}@demo.example  ({rol})")

    for alias, (nombre, tel, respuestas) in USUARIAS.items():
        uid = usuario(sb, f"{alias}@demo.example", {"nombre": nombre})
        sb.table("perfiles").upsert({"usuaria_id": uid, "nombre": nombre, "correo": f"{alias}@demo.example",
                                     "telefono": tel, "municipio": "Ahome", "medio_contacto": "WhatsApp",
                                     "horario_contacto": "Mañanas", "acepto_privacidad_at": ahora}).execute()
        res = fusionar({"campos": {}, "version": 0, "conflictos": []}, respuestas, "test_base")
        exp = res["expediente"]
        ruta = {**calcular_ruta(valores(exp)), "version": exp["version"]}
        sb.table("expedientes").upsert({"usuaria_id": uid, "campos": exp["campos"], "conflictos": [],
                                        "version": exp["version"], "ruta": ruta}).execute()
        sb.table("expediente_eventos").delete().eq("usuaria_id", uid).execute()
        sb.table("expediente_eventos").insert({"usuaria_id": uid, "version": 1, "fuente": "test_base",
                                               "texto": "Test base completado"}).execute()
        print(f"✓ usuaria   {alias}@demo.example  → {ruta['principal']} / puente {ruta['puente']}")

    # Un caso ficticio en la bandeja (de Rosa), para mostrar el panel de especialistas
    rosa = next(u.id for u in sb.auth.admin.list_users() if u.email == "rosa@demo.example")
    if not sb.table("canalizaciones").select("id").eq("usuaria_id", rosa).execute().data:
        sb.table("expedientes_sensibles").upsert({
            "usuaria_id": rosa, "consentimiento_at": ahora,
            "datos_cifrados": cifrar({"tipo": "juridica", "resumen": "CASO FICTICIO de demostración.",
                                      "contacto": {"medio": "Llamada", "horario": "Tardes", "mensaje": ""}})}).execute()
        sb.table("canalizaciones").insert({"usuaria_id": rosa, "tipo": "juridica", "urgencia": "pronta"}).execute()
        print("✓ caso ficticio en la bandeja jurídica")
    print(f"\nContraseña de todas las cuentas: {PASSWORD}")


if __name__ == "__main__":
    main()
