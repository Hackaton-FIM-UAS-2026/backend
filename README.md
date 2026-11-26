# Backend · Agente de canalización económica para mujeres

FastAPI + Supabase (Auth, Postgres, JSONB, pgvector, RLS) + Claude, con embeddings de Gemini.
Las respuestas tienen la misma forma que los mocks del front (`frontend/src/services` y `src/data`).

```
app/
  dominio/        ← lógica pura y probada: diccionario, motor de ruta, requisitos, fusión, matching
    pesos_ruta.json   ← pesos del motor (se ajustan sin tocar código)
  ia/             ← Claude (tool use + JSON Schema), Gemini embeddings, plantillas del flujo sensible
  routers/        ← publico, usuaria (/me), sensible (/chat, canalización), admin (/admin)
  servicios.py    ← lee con RLS, aplica el dominio, escribe con service role
  auth.py  db.py  sensible.py (cifrado + bitácora)  config.py  main.py
supabase/migrations/0001_esquema.sql
data/catalogo.json     ← catálogo (responsable: Datos)
scripts/cargar_catalogo.py  scripts/crear_demo.py
docs/integracion-front/     ← api.js, supabase.js, useApi.js y la guía para el front
tests/test_dominio.py
```

## 1. Crear el proyecto de Supabase (10 min)

1. En [supabase.com](https://supabase.com) → **New project**. Región: la más cercana (West US u East US). Guarda la contraseña de la base de datos.
2. **SQL Editor → New query** → pega todo `supabase/migrations/0001_esquema.sql` → **Run**. Debe terminar sin errores (crea tablas, RLS, trigger de alta y funciones).
3. **Authentication → Sign In / Providers → Email**: deja Email activo y **apaga "Confirm email"** para la demo. El SMTP que trae Supabase de fábrica permite muy pocos correos por hora; si alguien se registra en vivo y depende de un correo, la demo se cae.
4. **Project Settings → API Keys**: copia la `anon` y la `service_role`. Si tu proyecto muestra las llaves nuevas (`sb_publishable_…` / `sb_secret_…`), usa la pestaña **Legacy API keys**, que son las que este backend tiene probadas con `supabase-py`.
5. La URL del proyecto está en **Project Settings → Data API** (`https://xxxx.supabase.co`).

> La `service_role` ignora RLS: va solo en el `.env` del backend y en Render. Nunca en el front, nunca en git.

## 2. Correr el backend en local

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # y llénalo
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # → SENSIBLE_KEY
uvicorn app.main:app --reload
```

La documentación viva de los endpoints queda en **http://localhost:8000/docs** (sirve como "documentación de endpoints" del entregable de Backend).

Cargar datos:

```bash
python -m scripts.cargar_catalogo        # data/catalogo.json → tabla recursos (+ embeddings si hay GEMINI_API_KEY)
python -m scripts.crear_demo             # María, Lucía, Rosa + asesora, jurídica, psicológica, coordinación
```

`ANTHROPIC_API_KEY` y `GEMINI_API_KEY` son opcionales: sin ellas todo funciona con plantillas y similitud neutra. Sirve para que Frontend trabaje desde ya.

## 3. Desplegar en Render

New → **Blueprint** → este repo (lee `render.yaml`) → llena las variables. En `CORS_ORIGINS` pon la URL del front (Vercel/Netlify ya están permitidos por patrón).
El plan gratuito se duerme: **5 minutos antes de presentar abran `/salud`** (o usen Railway).

## 4. Pruebas

```bash
python -m unittest discover -s tests -v
```

Prueban que María → Emprendimiento + puente Capacitación, Lucía → Empleabilidad y Rosa → Capacitación → Emprendimiento, además de la fusión, los requisitos, el matching y el respaldo de señales sensibles. Si alguien cambia `pesos_ruta.json` y fallan, cambió la demo.

## Endpoints

| Método | Ruta | Quién | Qué hace |
| --- | --- | --- | --- |
| GET | `/salud` | todas | despertar el servidor |
| GET | `/diccionario` | todas | test base, preguntas de entrevista, etiquetas |
| GET | `/recursos` | todas | catálogo publicado sin evaluar |
| GET | `/emergencia` | todas | 911 y contactos, sin sesión ni formularios |
| POST | `/me/registro` | usuaria | guarda consentimiento LFPDPPP |
| GET / PATCH | `/me/expediente` | usuaria | leer / fusionar campos (`fuente`: test_base, entrevista, usuaria_edito) |
| GET | `/me/ruta` | usuaria | principal, puente, factores y explicación |
| GET | `/me/recomendaciones` | usuaria | top 10 con requisitos evaluados |
| GET | `/me/recursos/{id}` | usuaria | detalle + 1 a 3 preguntas + "¡Cumples!" |
| POST | `/me/recursos/{id}/accion` | usuaria | aplicar / guardar |
| GET | `/me/seguimiento` | usuaria | versión, avance, línea de tiempo |
| POST | `/chat` | usuaria | respuesta + detección de señales (solo propone) |
| POST / GET | `/me/canalizaciones` | usuaria | crear con consentimiento / ver estado |
| DELETE | `/me/expediente-sensible` | usuaria | borrar todo lo sensible |
| GET | `/admin/yo` | personal | rol |
| GET | `/admin/usuarias`, `/admin/usuarias/{id}` | asesora | lista y ficha (queda en bitácora) |
| POST | `/admin/usuarias/{id}/situacion` | asesora | "Actualizar situación" (+ cambio de ruta con motivo) |
| POST | `/admin/usuarias/{id}/contactos` | asesora | registrar contacto |
| GET / POST | `/admin/recursos` | asesora, coordinación | catálogo completo / crear o editar |
| PATCH | `/admin/recursos/{id}/publicacion` | asesora, coordinación | publicar o pausar |
| GET | `/admin/canalizaciones`, `/{folio}` | especialistas | bandeja (por urgencia) y caso descifrado |
| PATCH | `/admin/canalizaciones/{folio}` | especialistas | estado, nota cifrada, asignarme |
| GET | `/admin/metricas` | personal | conteos (la asesora no ve los del flujo sensible) |
| GET | `/admin/bitacora` | coordinación | accesos |

## Cómo se cumple lo que promete el pitch

- **La ruta la decide el código** (`dominio/motor_ruta.py` + `pesos_ruta.json`); Claude solo la redacta y, si tarda más de 6 s, se usa una plantilla.
- **La IA no inventa recursos**: el chat solo recibe los recursos de su top 10 y los IDs que regresa se filtran contra esa lista. Las preguntas del agente solo pueden ser de campos del diccionario, con las opciones del diccionario.
- **"¿Faltan datos?" es una resta**: `dominio/requisitos.py` evalúa cada requisito como cumple / no cumple / falta el dato.
- **Expediente vivo**: una fila con `version`, cada campo con `fuente`, `confianza` y `fecha`, e historial en `expediente_eventos`. Si el personal choca con lo que dijo ella, queda en `conflictos` y no se sobrescribe.
- **Lo sensible va aparte**: `expedientes_sensibles` está cifrado con Fernet, RLS deja verlo solo a ella y a la especialista del tipo de caso, la asesora económica ni siquiera ve conteos, cada lectura queda en `bitacora_accesos` y la conversación nunca se guarda ni se escribe en logs.
- **Seguridad en la base, no en los botones**: las lecturas usan el JWT de quien pide (RLS decide); el navegador no puede escribir en ninguna tabla.

## Pendientes conocidos

- Teléfono y horario oficiales del área jurídica de la Secretaría de las Mujeres de Sinaloa → `app/ia/plantillas.py` (`CONTACTO_EMERGENCIA`). Verificar también el número de la Línea de la Vida.
- Las plantillas del flujo sensible están **a validar con CEMujeres**.
- Que la usuaria autorice que su asesora vea su caso sensible (hoy no se puede: separación total).
- Desempate de rutas con LLM (opcional según el documento); hoy en un empate gana el orden fijo.
