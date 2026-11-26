# Datos de la demo (ficticios) → datos reales

| Archivo | Qué tiene hoy | Cómo cambiarlo a real |
| --- | --- | --- |
| `catalogo.json` | 24 recursos **ficticios** (proveedor «Ejemplo — …», `url_accion: "#"`) | Reemplaza el archivo con recursos verificados (mismo formato, `verificado_el` real) y corre `python -m scripts.cargar_catalogo`. Para quitar los de ejemplo: `delete from recursos where proveedor like 'Ejemplo —%';` |
| `demo.json` | 15 usuarias, 4 cuentas de personal y 4 casos **ficticios** (`@demo.example`, teléfonos 555) | Solo para la demo. Para producción no lo cargues y borra las cuentas `@demo.example` en Supabase → Authentication. |

- Las pruebas usan `tests/catalogo_prueba.json`, así que cambiar `catalogo.json` no las rompe.
- Los requisitos solo pueden usar campos de `app/dominio/diccionario.py`; `cargar_catalogo` lo valida antes de subir.
- Contactos de emergencia: `app/ia/plantillas.py` → `CONTACTO_EMERGENCIA`. **No se inventaron**: el teléfono oficial de la Secretaría de las Mujeres sigue pendiente de confirmar.
