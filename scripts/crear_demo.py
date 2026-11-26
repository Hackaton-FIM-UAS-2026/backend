"""Crea las cuentas de la demo a partir de data/demo.json (datos 100 % FICTICIOS).

    python -m scripts.crear_demo                 # usa data/demo.json
    python -m scripts.crear_demo otro.json

Todo lo ficticio vive en data/demo.json (usuarias, personal y casos) y en
data/catalogo.json (recursos con proveedor «Ejemplo — …»). Para pasar a datos
reales se reemplazan esos archivos; este script no cambia.

Correos: <alias>@demo.example · Contraseña de todas: DEMO_PASSWORD (por defecto Demo2026!)
Se puede correr varias veces: actualiza en lugar de duplicar.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import servicio
from app.dominio.fusion import fusionar, valores
from app.dominio.motor_ruta import calcular_ruta
from app.sensible import cifrar

PASSWORD = os.getenv("DEMO_PASSWORD", "Demo2026!")


def usuario(sb, correo: str, meta: dict, existentes: dict) -> str:
    if correo in existentes:
        return existentes[correo]
    r = sb.auth.admin.create_user({"email": correo, "password": PASSWORD, "email_confirm": True, "user_metadata": meta})
    existentes[correo] = r.user.id
    return r.user.id


def main(ruta: str):
    demo = json.loads(Path(ruta).read_text(encoding="utf-8"))
    sb = servicio()
    ahora = datetime.now(timezone.utc)
    existentes = {u.email: u.id for u in sb.auth.admin.list_users(per_page=1000)}

    for alias, (nombre, rol) in demo["personal"].items():
        uid = usuario(sb, f"{alias}@demo.example", {"es_personal": True, "nombre": nombre}, existentes)
        sb.table("personal").upsert({"user_id": uid, "nombre": nombre, "rol": rol}).execute()
        print(f"✓ personal  {alias}@demo.example  ({rol})")
    asesora = existentes.get("asesora@demo.example")

    ids = {}
    for x in demo["usuarias"]:
        correo = f"{x['alias']}@demo.example"
        uid = ids[x["alias"]] = usuario(sb, correo, {"nombre": x["nombre"]}, existentes)
        alta = ahora - timedelta(days=x.get("dias_desde_registro", 0))
        sb.table("perfiles").upsert({
            "usuaria_id": uid, "nombre": x["nombre"], "correo": correo, "telefono": x["telefono"],
            "municipio": x["municipio"], "medio_contacto": x["medio_contacto"], "horario_contacto": x["horario_contacto"],
            "estado_seguimiento": x.get("estado_seguimiento", "Nueva"),
            "curp": x.get("curp"), "colonia": x.get("colonia"),
            "acepto_privacidad_at": alta.isoformat(), "created_at": alta.isoformat()}).execute()

        exp = fusionar({"campos": {}, "version": 0, "conflictos": []}, x["respuestas"], "test_base")["expediente"]
        ruta_u = {**calcular_ruta(valores(exp)), "version": exp["version"]}
        sb.table("expedientes").upsert({"usuaria_id": uid, "campos": exp["campos"], "conflictos": [],
                                        "version": exp["version"], "ruta": ruta_u}).execute()

        sb.table("expediente_eventos").delete().eq("usuaria_id", uid).execute()
        eventos = [{"usuaria_id": uid, "version": 1, "fuente": "test_base", "texto": "Test base completado",
                    "created_at": alta.isoformat()}]
        n = len(x.get("eventos", []))
        for i, texto in enumerate(x.get("eventos", []), start=1):
            de_personal = texto.startswith("Asesora")
            cuando = alta + (ahora - alta) * i / (n + 1)
            eventos.append({"usuaria_id": uid, "version": 1, "texto": texto, "created_at": cuando.isoformat(),
                            "fuente": "personal_semujeres" if de_personal else "usuaria",
                            "autor": asesora if de_personal else None})
        sb.table("expediente_eventos").insert(eventos).execute()

        sb.table("recursos_usuaria").delete().eq("usuaria_id", uid).execute()
        if x.get("acciones"):
            sb.table("recursos_usuaria").insert([{"usuaria_id": uid, "recurso_id": rid, "estado": est}
                                                 for rid, est in x["acciones"].items()]).execute()
        print(f"✓ usuaria   {correo:28} → {ruta_u['principal']} / puente {ruta_u['puente']}")

    # Casos ficticios en la bandeja de especialistas (uno por usuaria)
    for c in demo.get("casos", []):
        uid = ids[c["usuaria"]]
        area = c.get("area_asignada")
        estado = c.get("estado", "nueva")
        if area and estado == "nueva":
            estado = "asignada"
        if sb.table("canalizaciones").select("id").eq("usuaria_id", uid).execute().data:
            sb.table("canalizaciones").update({"area_asignada": area, "estado": estado}).eq("usuaria_id", uid).execute()
            continue
        cuando = (ahora - timedelta(days=c.get("dias", 0))).isoformat()
        sb.table("expedientes_sensibles").upsert({
            "usuaria_id": uid, "consentimiento_at": cuando,
            "datos_cifrados": cifrar({"tipo": c["tipo"], "resumen": "CASO FICTICIO de demostración.",
                                      "contacto": c["contacto"]})}).execute()
        sb.table("canalizaciones").insert({"usuaria_id": uid, "tipo": c["tipo"], "urgencia": c["urgencia"],
                                           "estado": estado, "area_asignada": area, "origen": "asistente",
                                           "created_at": cuando}).execute()
        print(f"✓ caso ficticio ({c['tipo']}, {c['urgencia']}) de {c['usuaria']}")
    # Visitas previstas (recepción)
    hoy = ahora.date()
    for v in demo.get("visitas", []):
        uid = ids[v["usuaria"]]
        sb.table("visitas").delete().eq("usuaria_id", uid).execute()
        sb.table("visitas").insert({"usuaria_id": uid, "fecha": (hoy + timedelta(days=v.get("dias", 0))).isoformat(),
                                    "franja": v["franja"], "modulo": v["modulo"],
                                    "estado": v.get("estado", "por_llegar"), "origen": "asistente"}).execute()
        print(f"✓ visita    {v['usuaria']} → {v['modulo']} ({v['franja']})")

    # Cuentas de empresa (la fila de la empresa la crea scripts.cargar_catalogo)
    ruta_emp = Path("data/empresas.json")
    if ruta_emp.exists():
        for e in json.loads(ruta_emp.read_text(encoding="utf-8"))["empresas"]:
            uid = usuario(sb, f"{e['alias']}@demo.example", {"es_empresa": True, "nombre": e["nombre"]}, existentes)
            sb.table("perfiles").delete().eq("usuaria_id", uid).execute()  # por si el trigger viejo la creó
            sb.table("empresas").update({"user_id": uid, "correo": f"{e['alias']}@demo.example"}).eq("rfc", e["rfc"]).execute()
            print(f"✓ empresa   {e['alias']}@demo.example ({e['estado']})")
    print(f"\nContraseña de todas las cuentas: {PASSWORD}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/demo.json")
